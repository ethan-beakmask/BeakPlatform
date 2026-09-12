"""Platform façade for organization database provisioning and cleanup.

翻譯函式的用法：只有「一定在 request 語境下被呼叫」的訊息才包 `_()`
（孤兒判定的拒絕理由會直接顯示在健康頁上）。`_safe_error()` 與
`drop_collected_databases()` 也會被 bootstrap／CLI 呼叫，
在那裡 flask_babel 取不到 locale，所以那幾則維持固定字串。
"""
import logging
import re

import psycopg2
from flask_babel import gettext as _
from psycopg2 import sql as psql

from app import db
from app.models.organization import Organization

logger = logging.getLogger(__name__)

ORG_DB_RE = re.compile(r'^org_[0-9]+$')
ORG_ROLE_RE = re.compile(r'^(bfadmin|bfsync)_[0-9]+$')


def _safe_error(exc):
    msg = str(exc)
    if 'postgresql://' in msg or 'postgres://' in msg:
        return '連線失敗'
    if '[SQL:' in msg:
        msg = msg.split('[SQL:', 1)[0].strip()
    return msg or exc.__class__.__name__


def _bypass_rls():
    """讓孤兒判定看得到完整的 `organizations`。

    判定的前提是「這個 org_id 在 organizations 表裡不存在」，所以只要有任何一列
    被 RLS 藏起來，使用中的企業庫就會被判成孤兒刪掉。`organizations` 現在沒有 RLS，
    這是防未來的（與 org_physical_cleanup_service 的四個端點同一個理由）。
    """
    try:
        db.session.execute(db.text("SET LOCAL app.is_system_admin = 'true'"))
    except Exception as exc:  # 無交易語境（CLI）時是 no-op，不該讓判定失敗
        logger.debug('OrgDB: 設定 app.is_system_admin 失敗：%s', _safe_error(exc))


def _blank_drop_result():
    return {
        'databases_dropped': [],
        'roles_dropped': [],
        'manual_required': [],
        'errors': [],
    }


def ensure_org_database(org) -> dict:
    """Ensure an org DB after the Organization row has already been committed.

    Contract: callers must commit the Organization before calling this function.
    On success this function commits the DB registration row. On failure it rolls
    back only the provisioning attempt so the caller can report the message.
    """
    from modules.form_workflow.services.sql_sync.org_db_manager import (
        provision_org_database,
    )

    db_name = f'org_{org.id}'
    try:
        org_db = provision_org_database(org.id, org.secure_code)
        db.session.commit()
        return {'status': 'ok', 'db_name': org_db.db_name, 'message': None}
    except Exception as exc:
        db.session.rollback()
        message = _safe_error(exc)
        logger.warning('OrgDB: 企業 %s provisioning 失敗：%s', org.id, message)
        return {'status': 'failed', 'db_name': db_name, 'message': message}


def collect_org_databases(org_codes: list[str]) -> list[dict]:
    """收集這些企業的專屬資料庫與 owner 憑證，供稍後刪除使用。

    必須在 `fw_org_databases` 資料列被刪掉「之前」呼叫——登記一旦刪掉就查不到
    該刪哪個庫、也拿不到 owner 憑證。實際的 DROP 則要等主交易 commit 之後再做
    （交易若回滾，企業還在而庫已被刪就無法復原），所以收集與刪除分成兩支。
    """
    if not org_codes:
        return []

    from modules.form_workflow.models.org_database import FwOrgDatabase

    rows = FwOrgDatabase.query.filter(
        FwOrgDatabase.org_secure_code.in_(org_codes),
        FwOrgDatabase.is_deleted.is_(False),
    ).all()

    collected = []
    for org_db in rows:
        admin_dsn = None
        try:
            admin_dsn = org_db.get_admin_dsn()
        except Exception as exc:
            logger.warning(
                'OrgDB: 取得 %s owner DSN 失敗：%s', org_db.db_name, _safe_error(exc)
            )
        collected.append({
            'db_name': org_db.db_name,
            'org_secure_code': org_db.org_secure_code,
            'org_id': org_db.org_id,
            'admin_dsn': admin_dsn,
        })
    return collected


def drop_collected_databases(items: list[dict]) -> dict:
    """刪除 `collect_org_databases()` 收集到的資料庫與角色。

    呼叫時機：主交易 commit 之後（與 encrypted_storage / EDL 目錄的刪除同一時機）。
    """
    result = _blank_drop_result()
    if not items:
        return result

    from modules.form_workflow.services.sql_sync.org_db_manager import (
        drop_org_database,
    )
    from modules.form_workflow.services.sql_sync.pool import invalidate_conn

    for item in items:
        db_name = item.get('db_name')
        try:
            invalidate_conn(item.get('org_secure_code'))
        except Exception as exc:
            err = _safe_error(exc)
            logger.warning(
                'OrgDB: 關閉企業 %s 快取連線失敗：%s', item.get('org_secure_code'), err
            )
            result['errors'].append({
                'resource': item.get('org_secure_code') or db_name,
                'error': err,
            })

        drop_result = drop_org_database(
            db_name,
            admin_dsn=item.get('admin_dsn'),
            org_id=item.get('org_id'),
            drop_roles=True,
        )
        if drop_result.get('db_dropped'):
            result['databases_dropped'].append(db_name)
        result['roles_dropped'].extend(drop_result.get('roles_dropped', []))
        result['errors'].extend(drop_result.get('errors', []))
        if drop_result.get('manual_command'):
            reason = '; '.join(
                err.get('error', '') for err in drop_result.get('errors', [])
            ) or '需要管理員手動刪除'
            result['manual_required'].append({
                'name': db_name,
                'reason': reason,
                'command': drop_result['manual_command'],
            })

    return result


def drop_databases_for_orgs(org_codes: list[str]) -> dict:
    """收集並立即刪除這些企業的專屬資料庫（收集與刪除之間沒有交易邊界時使用）。"""
    return drop_collected_databases(collect_org_databases(org_codes))


def _pg_database_exists(db_name: str) -> bool:
    row = db.session.execute(
        db.text("SELECT 1 FROM pg_database WHERE datname = :db_name"),
        {'db_name': db_name},
    ).first()
    return row is not None


def _registered_org_db_exists(db_name: str) -> bool:
    from modules.form_workflow.models.org_database import FwOrgDatabase

    return FwOrgDatabase.query.filter_by(
        db_name=db_name,
        is_deleted=False,
    ).first() is not None


def drop_orphan_database(db_name: str) -> dict:
    """Drop a physical org database only after fail-closed orphan validation."""
    _bypass_rls()
    if not ORG_DB_RE.match(db_name or ''):
        return {'ok': False, 'error': _('不合法的資料庫名稱')}

    org_id = int(db_name.split('_', 1)[1])
    try:
        if not _pg_database_exists(db_name):
            return {'ok': False, 'error': _('資料庫不存在')}
        if Organization.query.filter_by(id=org_id).first() is not None:
            return {'ok': False, 'error': _('企業仍存在，拒絕刪除')}
        if _registered_org_db_exists(db_name):
            return {'ok': False, 'error': _('企業資料庫登記仍存在，拒絕刪除')}
    except Exception as exc:
        err = _safe_error(exc)
        logger.warning('OrgDB: 判定孤兒資料庫 %s 失敗：%s', db_name, err)
        return {'ok': False, 'error': err}

    from modules.form_workflow.services.sql_sync.org_db_manager import (
        drop_org_database,
    )

    result = drop_org_database(db_name, admin_dsn=None, drop_roles=True)
    return {'ok': bool(result.get('db_dropped')), **result}


def drop_orphan_roles(role_names: list[str]) -> dict:
    """Drop orphan bfadmin/bfsync roles after fail-closed validation."""
    result = {'roles_dropped': [], 'errors': []}
    if not role_names:
        return result

    _bypass_rls()

    from modules.form_workflow.services.sql_sync.org_db_manager import _get_admin_conn

    valid_roles = []
    for role_name in role_names:
        if not ORG_ROLE_RE.match(role_name or ''):
            result['errors'].append({
                'resource': role_name or '',
                'error': _('不合法的角色名稱'),
            })
            continue
        org_id = int(role_name.rsplit('_', 1)[1])
        db_name = f'org_{org_id}'
        try:
            role_exists = db.session.execute(
                db.text("SELECT 1 FROM pg_roles WHERE rolname = :role_name"),
                {'role_name': role_name},
            ).first() is not None
            if not role_exists:
                result['errors'].append({
                    'resource': role_name,
                    'error': _('角色不存在'),
                })
                continue
            if Organization.query.filter_by(id=org_id).first() is not None:
                result['errors'].append({
                    'resource': role_name,
                    'error': _('企業仍存在，拒絕刪除'),
                })
                continue
            if _pg_database_exists(db_name):
                result['errors'].append({
                    'resource': role_name,
                    'error': _('企業資料庫仍存在，拒絕刪除角色'),
                })
                continue
            valid_roles.append(role_name)
        except Exception as exc:
            err = _safe_error(exc)
            logger.warning('OrgDB: 判定孤兒角色 %s 失敗：%s', role_name, err)
            result['errors'].append({'resource': role_name, 'error': err})

    if not valid_roles:
        return result

    try:
        conn = _get_admin_conn()
        try:
            with conn.cursor() as cur:
                for role_name in valid_roles:
                    try:
                        cur.execute(
                            psql.SQL("DROP ROLE IF EXISTS {}").format(
                                psql.Identifier(role_name)
                            )
                        )
                        result['roles_dropped'].append(role_name)
                    except Exception as exc:
                        err = _safe_error(exc)
                        logger.warning('OrgDB: 刪除孤兒角色 %s 失敗：%s', role_name, err)
                        result['errors'].append({'resource': role_name, 'error': err})
        finally:
            conn.close()
    except Exception as exc:
        err = _safe_error(exc)
        logger.warning('OrgDB: 刪除孤兒角色連線失敗：%s', err)
        result['errors'].append({'resource': 'roles', 'error': err})

    return result


def _pg_org_database_info():
    # pg_database_size() 需要該庫的 CONNECT 權限（建庫時已 REVOKE ... FROM PUBLIC），
    # 平台帳號對企業庫沒有 CONNECT，直接呼叫會整句 InsufficientPrivilege。
    # 用 has_database_privilege() 擋掉，拿不到大小就回 NULL（顯示為「—」）。
    rows = db.session.execute(db.text(
        "SELECT datname, "
        "CASE WHEN has_database_privilege(datname, 'CONNECT') "
        "     THEN pg_database_size(datname) ELSE NULL END "
        "FROM pg_database WHERE datname ~ :pattern"
    ), {'pattern': r'^org_[0-9]+$'})
    return {row[0]: row[1] for row in rows}


def _pg_org_roles():
    rows = db.session.execute(db.text(
        "SELECT rolname FROM pg_roles WHERE rolname ~ :pattern"
    ), {'pattern': r'^(bfadmin|bfsync)_[0-9]+$'})
    return [row[0] for row in rows]


def _connect_with_sync(org_db):
    try:
        conn = psycopg2.connect(org_db.get_sync_dsn(), connect_timeout=3)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            return True, None
        finally:
            conn.close()
    except Exception as exc:
        return False, _safe_error(exc)


def scan_org_database_health() -> dict:
    """Return the complete org database health snapshot."""
    from modules.form_workflow.models.org_database import FwOrgDatabase
    from modules.form_workflow.services.sql_sync.org_db_manager import (
        provisioning_health,
    )

    _bypass_rls()
    provisioning = provisioning_health()
    orgs = Organization.query.filter_by(is_deleted=False).order_by(
        Organization.id.asc()
    ).all()
    all_org_ids = {
        row[0] for row in db.session.query(Organization.id).all()
    }
    org_db_rows = FwOrgDatabase.query.filter_by(is_deleted=False).all()
    org_db_by_id = {row.org_id: row for row in org_db_rows}
    pg_dbs = _pg_org_database_info()
    pg_db_names = set(pg_dbs)

    org_results = []
    ok_count = 0
    for org in orgs:
        db_name = f'org_{org.id}'
        org_db = org_db_by_id.get(org.id)
        registered = org_db is not None
        is_ready = bool(org_db and org_db.is_ready)
        db_exists = db_name in pg_db_names
        connectable = False
        detail = None

        if not registered:
            status = 'missing_registration'
        elif not is_ready:
            status = 'not_ready'
        elif not db_exists:
            status = 'missing_database'
        else:
            connectable, detail = _connect_with_sync(org_db)
            status = 'ok' if connectable else 'unreachable'

        if status == 'ok':
            ok_count += 1

        org_results.append({
            'org_secure_code': org.secure_code,
            'org_code': org.code,
            'org_name': org.name,
            'org_id': org.id,
            'is_system_org': bool(org.is_system_org),
            'db_name': db_name,
            'registered': registered,
            'is_ready': is_ready,
            'db_exists': db_exists,
            'connectable': connectable,
            'status': status,
            'detail': detail,
        })

    orphan_databases = [
        {'db_name': name, 'size_bytes': pg_dbs.get(name)}
        for name in sorted(pg_db_names)
        if int(name.split('_', 1)[1]) not in all_org_ids
    ]

    orphan_roles = []
    for role_name in _pg_org_roles():
        org_id = int(role_name.rsplit('_', 1)[1])
        if org_id not in all_org_ids and f'org_{org_id}' not in pg_db_names:
            orphan_roles.append(role_name)
    orphan_roles.sort()

    total = len(org_results)
    return {
        'provisioning': provisioning,
        'orgs': org_results,
        'orphan_databases': orphan_databases,
        'orphan_roles': orphan_roles,
        'summary': {
            'total': total,
            'ok': ok_count,
            'abnormal': total - ok_count,
            'orphan_databases': len(orphan_databases),
            'orphan_roles': len(orphan_roles),
        },
    }
