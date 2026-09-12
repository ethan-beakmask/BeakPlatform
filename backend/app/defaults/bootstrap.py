"""安裝與升級共用的唯一 DB bootstrap 實作。

Shell 端只負責需要 PostgreSQL superuser 的物件：DB/user、pgcrypto extension、
以及 scripts/sql/fw_sp_setup.sql。create_all、seed、選單、權限、模組同步等
應用帳號能完成的步驟一律集中在本模組；新增 seed 或 DB 物件時請加在這裡，
不要再往 shell 腳本追加流程。
"""
import logging
import os
import shutil
import subprocess
from pathlib import Path

from flask import current_app
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app import db
logger = logging.getLogger(__name__)


class BootstrapError(RuntimeError):
    """任一步失敗即拋出，CLI 以非零退出。"""


SQL_EXTRAS = (
    ('seed_workflow_node_definitions.sql', True, True),
    ('seed_node_org_grants.sql', True, False),
    ('seed_menu_defaults.sql', False, False),
    ('seed_rbac_defaults.sql', False, False),
)
# fw_sp_setup.sql 刻意不在此表：需要 superuser，由 shell 以 postgres 執行，
# bootstrap 只驗證它已完成（verify_superuser_objects）。


def default_sql_dir() -> Path:
    # current_app.root_path = <repo>/backend/app
    return Path(current_app.root_path).parent.parent / 'scripts' / 'sql'


def create_tables() -> int:
    """db.create_all()，回傳 metadata 內表數（模組 models 已由 create_app 載入）。"""
    db.create_all()
    return len(db.metadata.tables)


def _database_url():
    return make_url(current_app.config['SQLALCHEMY_DATABASE_URI'])


def _system_org_code():
    from app.constants import SYSTEM_ORG_CODE
    return SYSTEM_ORG_CODE


def verify_superuser_objects() -> None:
    """確認 fw_sp schema 與 owner 已由 postgres superuser 建好。"""
    row = db.session.execute(text("""
        SELECT n.nspname, r.rolname AS owner
        FROM pg_namespace n
        JOIN pg_roles r ON r.oid = n.nspowner
        WHERE n.nspname = 'fw_sp'
    """)).mappings().first()

    if row and row['owner'] == 'fw_sp_owner':
        return

    url = _database_url()
    db_name = url.database or '<database>'
    app_user = url.username or '<app_user>'
    detail = (
        "superuser DB 物件尚未就緒：schema fw_sp 必須存在且 owner 必須是 "
        "fw_sp_owner。請先以 postgres 執行："
        f"sudo -u postgres psql -d {db_name} -v app_user={app_user} "
        "-f scripts/sql/fw_sp_setup.sql"
    )
    raise BootstrapError(detail)


def ensure_system_org(admin_password=None) -> dict:
    """冪等建立系統企業、出廠角色與 SYSTEM_ADMIN 管理員。"""
    from app.models import Organization, Role, User
    from app.models.user import UserType
    from app.services.organization_service import OrganizationService

    system_org_code = _system_org_code()
    summary = {
        'org_created': False,
        'roles_created': False,
        'admin_created': False,
    }

    org = Organization.query.filter_by(code='SYSTEM', is_deleted=False).first()
    if org and org.secure_code != system_org_code:
        logger.warning(
            "系統企業 secure_code=%s 與目前 SYSTEM_ORG_CODE=%s 不一致",
            org.secure_code, system_org_code,
        )

    if not org:
        org = Organization(
            secure_code=system_org_code,
            code='SYSTEM',
            name=system_org_code,
            domain_name=system_org_code,
            is_active=True,
            is_system_org=True
        )
        db.session.add(org)
        db.session.flush()
        summary['org_created'] = True

    role_count = Role.query.filter_by(
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).count()
    if role_count == 0:
        OrganizationService._create_default_roles(org)
        db.session.flush()
        summary['roles_created'] = True

    admin = User.query.filter_by(
        org_secure_code=org.secure_code,
        username='admin',
        is_deleted=False,
    ).first()
    if not admin:
        if not admin_password or len(admin_password) < 8:
            raise BootstrapError('管理員密碼無效，請設定 ADMIN_INITIAL_PASSWORD 至少 8 字元')
        admin = User(
            org_secure_code=org.secure_code,
            username='admin',
            email=f'admin@{org.secure_code}',
            display_name='系統管理員',
            user_type=UserType.SYSTEM_ADMIN,
            is_active=True,
            must_change_password=True,
        )
        admin.set_password(admin_password)
        db.session.add(admin)
        summary['admin_created'] = True

    db.session.commit()
    return summary


def apply_sql_extras(sql_dir=None) -> dict:
    """用 psql 逐支執行應用帳號可完成的 SQL extras。"""
    psql = shutil.which('psql')
    if not psql:
        raise BootstrapError('找不到 psql，無法執行 SQL extras')

    url = _database_url()
    sql_path = Path(sql_dir) if sql_dir else default_sql_dir()
    env = os.environ.copy()
    if url.password:
        env['PGPASSWORD'] = url.password

    base_cmd = [psql, '-X', '-q', '-v', 'ON_ERROR_STOP=1']
    if url.host:
        base_cmd.extend(['-h', url.host])
    if url.port:
        base_cmd.extend(['-p', str(url.port)])
    if url.username:
        base_cmd.extend(['-U', url.username])
    if url.database:
        base_cmd.extend(['-d', url.database])

    result = {'applied': [], 'skipped': []}
    for filename, required, with_system_org in SQL_EXTRAS:
        file_path = sql_path / filename
        if not file_path.exists():
            if required:
                raise BootstrapError(f'必要 SQL 檔不存在: {file_path}')
            logger.info("選配 SQL 檔不存在，略過: %s", file_path)
            result['skipped'].append(filename)
            continue

        cmd = list(base_cmd)
        if with_system_org:
            cmd.extend(['-v', f'system_org={_system_org_code()}'])
        cmd.extend(['-f', str(file_path)])
        completed = subprocess.run(
            cmd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0:
            stderr_tail = '\n'.join(completed.stderr.splitlines()[-20:])
            raise BootstrapError(f'{filename} 執行失敗:\n{stderr_tail}')
        result['applied'].append(filename)
        logger.info("已執行 SQL extra: %s", filename)

    return result


def sync_modules(force=False) -> dict:
    """同步模組權限、選單、lookup 與預設角色。"""
    from app.module_loader import module_loader
    from app.services.module_sync_service import ModuleSyncService

    result = ModuleSyncService.sync_all(module_loader, force=force)
    db.session.commit()
    return result


def ensure_org_databases() -> dict:
    if not os.environ.get('SYNC_PG_ADMIN_URL'):
        logger.warning(
            '企業專屬資料庫佈建已跳過：SYNC_PG_ADMIN_URL 未設定，'
            '企業級對照表與簽核片語等功能將無法使用'
        )
        return {
            'checked': 0,
            'ok': 0,
            'failed': 0,
            'skipped': True,
            'reason': 'SYNC_PG_ADMIN_URL 未設定',
        }

    from app.models import Organization
    from app.services.org_database_service import ensure_org_database

    summary = {
        'checked': 0,
        'ok': 0,
        'failed': 0,
        'skipped': False,
        'reason': None,
    }
    orgs = Organization.query.filter_by(is_deleted=False).order_by(Organization.id).all()
    for org in orgs:
        summary['checked'] += 1
        try:
            result = ensure_org_database(org)
            if result['status'] == 'ok':
                summary['ok'] += 1
            else:
                summary['failed'] += 1
                logger.warning(
                    '企業專屬資料庫佈建失敗 code=%s org_code=%s reason=%s',
                    org.code,
                    org.secure_code,
                    result.get('message'),
                )
        except Exception as exc:
            db.session.rollback()
            summary['failed'] += 1
            logger.warning(
                '企業專屬資料庫佈建發生例外 code=%s org_code=%s reason=%s',
                org.code,
                org.secure_code,
                exc,
            )
    return summary


def _run_step(summary, step_name, func):
    logger.info(step_name)
    try:
        summary[step_name] = func()
    except Exception as exc:
        db.session.rollback()
        raise BootstrapError(f'{step_name} 失敗: {exc}') from exc


def run_bootstrap(mode, admin_password=None, sql_dir=None) -> dict:
    """執行 fresh 或 update bootstrap。

    順序有依賴，不可調換：SQL extras 的受限節點授權需要 is_system_org 的企業；
    平台選單必須在模組同步之前（模組選單先佔位會讓平台選單被誤判已存在）；
    系統企業出廠資料的 Key2 需要模組選單已存在。
    update 模式刻意不建系統企業、不種出廠資料（不回填既有環境）。
    """
    if mode not in {'fresh', 'update'}:
        raise ValueError("mode 必須是 'fresh' 或 'update'")

    from app.defaults.permission_defaults import seed_system_permissions
    from app.defaults.platform_menu_defaults import seed_platform_menus

    fresh = mode == 'fresh'
    summary = {}
    _run_step(summary, 'create_tables', create_tables)
    _run_step(summary, 'verify_superuser_objects', verify_superuser_objects)
    if fresh:
        _run_step(summary, 'ensure_system_org',
                  lambda: ensure_system_org(admin_password))
    else:
        _run_step(summary, 'check_system_org', _ensure_update_system_org_exists)
    _run_step(summary, 'apply_sql_extras', lambda: apply_sql_extras(sql_dir))
    _run_step(summary, 'seed_platform_menus',
              lambda: seed_platform_menus(force=fresh))
    _run_step(summary, 'seed_system_permissions',
              lambda: seed_system_permissions(force=False))
    _run_step(summary, 'sync_modules', lambda: sync_modules(force=fresh))
    _run_step(summary, 'ensure_org_databases', ensure_org_databases)
    if fresh:
        _run_step(summary, 'seed_system_org_defaults',
                  lambda: _seed_system_org_defaults(admin_password))

    return summary


def _ensure_update_system_org_exists() -> dict:
    from app.models import Organization

    org = Organization.query.filter_by(
        code='SYSTEM',
        is_deleted=False,
    ).first()
    if not org:
        raise BootstrapError('系統企業不存在，請走全新安裝')
    return {'system_org': org.secure_code}


def _seed_system_org_defaults(admin_password=None) -> dict:
    from app.defaults.system_org_defaults import seed_system_org_defaults

    result = seed_system_org_defaults(admin_password=admin_password)
    db.session.commit()
    return result
