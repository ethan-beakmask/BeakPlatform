"""
SQL Sync — 企業專屬資料庫管理器

負責：
1. 為企業建立獨立的 PostgreSQL 資料庫 (org_{id})
2. 建立高低權限帳號 (bfadmin_{id} / bfsync_{id})
3. 設定正確的 GRANT 權限
4. 儲存加密憑證到 FwOrgDatabase
"""
import os
import re
import secrets
import string
import logging
from urllib.parse import urlsplit, urlunsplit

import psycopg2
from cryptography.fernet import Fernet
from psycopg2 import sql as psql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

logger = logging.getLogger(__name__)

ORG_DB_RE = re.compile(r'^org_[0-9]+$')
ADMIN_ROLE_RE = re.compile(r'^bfadmin_[0-9]+$')
SYNC_ROLE_RE = re.compile(r'^bfsync_[0-9]+$')


def _generate_password(length=24):
    """產生安全密碼（英數，無特殊字元避免 shell 問題）"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def _get_admin_conn():
    """取得 PostgreSQL 管理員連線（需有 CREATEDB + CREATEROLE 權限）"""
    url = os.environ.get('SYNC_PG_ADMIN_URL')
    if not url:
        raise RuntimeError('SYNC_PG_ADMIN_URL 環境變數未設定')
    conn = psycopg2.connect(url)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    return conn


def _dsn_for_database(dsn, db_name):
    """替換 DSN 路徑上的資料庫名稱。"""
    parts = urlsplit(dsn)
    return urlunsplit((parts.scheme, parts.netloc, f'/{db_name}', parts.query, ''))


def _dsn_password(dsn):
    try:
        return urlsplit(dsn).password
    except Exception:
        return None


def _safe_error(exc, *secret_values):
    """回傳不含 DSN / 密碼的錯誤訊息。"""
    msg = str(exc)
    secrets_to_check = [s for s in secret_values if s]
    if any(secret in msg for secret in secrets_to_check):
        return '連線失敗'
    if 'postgresql://' in msg or 'postgres://' in msg:
        return '連線失敗'
    if '[SQL:' in msg:
        msg = msg.split('[SQL:', 1)[0].strip()
    return msg or exc.__class__.__name__


def _role_exists(cur, role_name):
    """檢查 PostgreSQL 角色是否存在"""
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role_name,))
    return cur.fetchone() is not None


def _db_exists(cur, db_name):
    """檢查資料庫是否存在"""
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
    return cur.fetchone() is not None


def _ensure_can_set_role(cur, role_name):
    """確保目前連線能 SET ROLE 到 role_name。

    CREATE DATABASE ... OWNER x 要求建立者能 SET ROLE 到 x。PG16 起
    createrole_self_grant 預設為空字串，CREATEROLE 建立角色時只拿到 ADMIN OPTION、
    不含 SET，未處理會得到 `must be able to SET ROLE "..."`，而該訊息不指向根因。
    superuser 本來就通過檢查，這裡是 no-op。
    """
    try:
        cur.execute("SELECT pg_has_role(current_user, %s, 'SET')", (role_name,))
        if cur.fetchone()[0]:
            return
    except Exception:
        try:
            cur.execute("SELECT pg_has_role(current_user, %s, 'MEMBER')", (role_name,))
            if cur.fetchone()[0]:
                return
        except Exception as exc:
            logger.debug(
                'OrgDB: 檢查 SET ROLE 權限失敗：%s',
                _safe_error(exc),
            )

    try:
        cur.execute(
            psql.SQL("GRANT {} TO CURRENT_USER WITH SET TRUE").format(
                psql.Identifier(role_name)
            )
        )
        return
    except Exception as exc:
        logger.debug(
            'OrgDB: GRANT SET ROLE 權限失敗，改用舊語法：%s',
            _safe_error(exc),
        )

    try:
        cur.execute(
            psql.SQL("GRANT {} TO CURRENT_USER").format(
                psql.Identifier(role_name)
            )
        )
    except Exception as exc:
        logger.warning(
            'OrgDB: 無法授予目前連線 SET ROLE 到 %s，CREATE DATABASE 可能失敗：%s',
            role_name,
            _safe_error(exc),
        )


def provision_org_database(org_id, org_secure_code, db_host='localhost', db_port=5432):
    """
    為企業建立專屬資料庫與帳號

    流程:
    1. 產生密碼
    2. 建立角色 bfadmin_{id} (DDL 權限) + bfsync_{id} (DML 權限)
    3. 建立資料庫 org_{id}，owner 為 bfadmin_{id}
    4. 在 org DB 中設定 bfsync 的 DML 權限
    5. 儲存加密憑證到 FwOrgDatabase

    Args:
        org_id: Organization.id
        org_secure_code: Organization.secure_code
        db_host: DB host
        db_port: DB port

    Returns:
        FwOrgDatabase instance
    """
    from ...models.org_database import FwOrgDatabase
    from app import db

    db_name = f'org_{org_id}'
    admin_user = f'bfadmin_{org_id}'
    sync_user = f'bfsync_{org_id}'
    admin_pwd = _generate_password()
    sync_pwd = _generate_password()

    existing = FwOrgDatabase.query.filter_by(org_id=org_id, is_deleted=False).first()

    conn = _get_admin_conn()
    try:
        with conn.cursor() as cur:
            if existing and existing.is_ready:
                if _db_exists(cur, db_name):
                    logger.info(f'OrgDB: org_{org_id} 已存在且就緒，跳過')
                    return existing
                logger.warning(
                    'OrgDB: %s 登記 is_ready=true 但實體資料庫不存在，重新佈建',
                    db_name,
                )

            # PG16+ 讓 CREATEROLE 建立的角色自動帶 SET；PG15 以下無此參數，忽略。
            try:
                cur.execute("SET createrole_self_grant = 'set, inherit'")
            except Exception as exc:
                logger.debug(
                    'OrgDB: 無法設定 createrole_self_grant，略過：%s',
                    _safe_error(exc),
                )

            # 1. 建立角色（如不存在）
            if not _role_exists(cur, admin_user):
                cur.execute(
                    psql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD %s").format(
                        psql.Identifier(admin_user)
                    ),
                    (admin_pwd,)
                )
                logger.info(f'OrgDB: 建立角色 {admin_user}')
            else:
                # 角色已存在，更新密碼
                cur.execute(
                    psql.SQL("ALTER ROLE {} WITH PASSWORD %s").format(
                        psql.Identifier(admin_user)
                    ),
                    (admin_pwd,)
                )

            if not _role_exists(cur, sync_user):
                cur.execute(
                    psql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD %s").format(
                        psql.Identifier(sync_user)
                    ),
                    (sync_pwd,)
                )
                logger.info(f'OrgDB: 建立角色 {sync_user}')
            else:
                cur.execute(
                    psql.SQL("ALTER ROLE {} WITH PASSWORD %s").format(
                        psql.Identifier(sync_user)
                    ),
                    (sync_pwd,)
                )

            # 2. 建立資料庫（如不存在）
            if not _db_exists(cur, db_name):
                _ensure_can_set_role(cur, admin_user)
                cur.execute(
                    psql.SQL("CREATE DATABASE {} OWNER {}").format(
                        psql.Identifier(db_name),
                        psql.Identifier(admin_user),
                    )
                )
                # 移除 PUBLIC 的 CONNECT 權限，防止其他企業帳號連入
                cur.execute(
                    psql.SQL("REVOKE CONNECT ON DATABASE {} FROM PUBLIC").format(
                        psql.Identifier(db_name),
                    )
                )
                logger.info(f'OrgDB: 建立資料庫 {db_name}（已 REVOKE PUBLIC CONNECT）')
            else:
                # 既有資料庫也確保 PUBLIC CONNECT 已移除
                cur.execute(
                    psql.SQL("REVOKE CONNECT ON DATABASE {} FROM PUBLIC").format(
                        psql.Identifier(db_name),
                    )
                )
                logger.info(f'OrgDB: 資料庫 {db_name} 已存在（已確認 REVOKE PUBLIC CONNECT）')

    finally:
        conn.close()

    # 3. 連入 org DB 設定 sync 權限
    admin_dsn = f'postgresql://{admin_user}:{admin_pwd}@{db_host}:{db_port}/{db_name}'
    org_conn = psycopg2.connect(admin_dsn)
    org_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with org_conn.cursor() as cur:
            # pgcrypto 是 trusted extension，資料庫 owner 即可安裝，不需要 superuser。
            cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
            logger.info(f'OrgDB: 已在 {db_name} 安裝 pgcrypto')
            # 允許 sync_user 連入
            cur.execute(
                psql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    psql.Identifier(db_name),
                    psql.Identifier(sync_user),
                )
            )
            # 允許使用 public schema
            cur.execute(
                psql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(
                    psql.Identifier(sync_user),
                )
            )
            # 預設：sync_user 對未來建立的表有 DML 權限（含 DELETE，子表同步需要）
            cur.execute(
                psql.SQL(
                    "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
                ).format(
                    psql.Identifier(admin_user),
                    psql.Identifier(sync_user),
                )
            )
            # 預設：sync_user 對序列也有使用權限
            cur.execute(
                psql.SQL(
                    "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
                    "GRANT USAGE, SELECT ON SEQUENCES TO {}"
                ).format(
                    psql.Identifier(admin_user),
                    psql.Identifier(sync_user),
                )
            )
            logger.info(f'OrgDB: 已設定 {sync_user} 的 DML 權限')
    finally:
        org_conn.close()

    # 5. 儲存到 FwOrgDatabase
    if existing:
        org_db = existing
    else:
        org_db = FwOrgDatabase(
            org_secure_code=org_secure_code,
            org_id=org_id,
            db_name=db_name,
            db_host=db_host,
            db_port=db_port,
            admin_user=admin_user,
            sync_user=sync_user,
        )
        db.session.add(org_db)

    org_db.admin_password = admin_pwd
    org_db.sync_password = sync_pwd
    org_db.is_ready = True
    db.session.flush()

    logger.info(f'OrgDB: 企業 {org_id} 專屬資料庫 {db_name} 建立完成')
    return org_db


def ensure_pgcrypto(org_secure_code):
    """
    確保企業 DB 已安裝 pgcrypto extension

    用於升級已存在的 org DB（provision 時未安裝的情況）。

    Args:
        org_secure_code: Organization.secure_code
    """
    from ...models.org_database import FwOrgDatabase
    org_db = FwOrgDatabase.query.filter_by(
        org_secure_code=org_secure_code,
        is_ready=True,
        is_deleted=False,
    ).first()
    if not org_db:
        raise RuntimeError(f'找不到企業 {org_secure_code} 的 DB 記錄')

    conn = psycopg2.connect(org_db.get_admin_dsn())
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with conn.cursor() as cur:
            # pgcrypto 是 trusted extension，資料庫 owner 即可安裝，不需要 superuser。
            cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        logger.info(f'OrgDB: 已在 {org_db.db_name} 確認/安裝 pgcrypto')
    finally:
        conn.close()


def _drop_database_with_dsn(dsn, db_name):
    password = _dsn_password(dsn)
    conn = None
    try:
        conn = psycopg2.connect(_dsn_for_database(dsn, 'postgres'))
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        with conn.cursor() as cur:
            existed = _db_exists(cur, db_name)
            if not existed:
                return True, existed, None
            try:
                cur.execute(
                    psql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                        psql.Identifier(db_name)
                    )
                )
            except Exception as force_exc:
                logger.debug(
                    'OrgDB: DROP DATABASE WITH FORCE 失敗，改用無 FORCE：%s',
                    _safe_error(force_exc, password),
                )
                cur.execute(
                    psql.SQL("DROP DATABASE IF EXISTS {}").format(
                        psql.Identifier(db_name)
                    )
                )
            return True, existed, None
    except Exception as exc:
        return False, False, _safe_error(exc, password)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def drop_org_database(db_name, admin_dsn=None, drop_roles=True, org_id=None):
    """刪除企業專屬 PostgreSQL 資料庫與選擇性刪除角色。

    呼叫端在刪庫前必須先呼叫
    modules.form_workflow.services.sql_sync.pool.invalidate_conn(org_secure_code)
    關掉快取中的連線。連線池以 org_secure_code 為 key，本函式只拿得到 db_name，
    自行比對可能誤關其他企業連線。
    """
    result = {
        'db_name': db_name,
        'db_dropped': False,
        'db_existed': False,
        'roles_dropped': [],
        'errors': [],
        'manual_command': None,
    }

    if not ORG_DB_RE.match(db_name or ''):
        result['errors'].append({'resource': db_name or '', 'error': '不合法的資料庫名稱'})
        return result

    inferred_org_id = org_id if org_id is not None else int(db_name.split('_', 1)[1])
    admin_role = f'bfadmin_{inferred_org_id}'
    sync_role = f'bfsync_{inferred_org_id}'
    if not ADMIN_ROLE_RE.match(admin_role) or not SYNC_ROLE_RE.match(sync_role):
        result['errors'].append({'resource': db_name, 'error': '不合法的角色名稱'})
        return result

    drop_errors = []
    if admin_dsn:
        db_dropped, db_existed, error = _drop_database_with_dsn(admin_dsn, db_name)
        result['db_existed'] = result['db_existed'] or db_existed
        if db_dropped:
            result['db_dropped'] = True
        elif error:
            drop_errors.append({'resource': db_name, 'error': error})

    if not result['db_dropped']:
        try:
            conn = _get_admin_conn()
            try:
                with conn.cursor() as cur:
                    result['db_existed'] = result['db_existed'] or _db_exists(cur, db_name)
                    try:
                        cur.execute(
                            psql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                                psql.Identifier(db_name)
                            )
                        )
                    except Exception as force_exc:
                        logger.debug(
                            'OrgDB: provisioner DROP DATABASE WITH FORCE 失敗，改用無 FORCE：%s',
                            _safe_error(force_exc),
                        )
                        cur.execute(
                            psql.SQL("DROP DATABASE IF EXISTS {}").format(
                                psql.Identifier(db_name)
                            )
                        )
                    result['db_dropped'] = True
            finally:
                conn.close()
        except Exception as exc:
            drop_errors.append({'resource': db_name, 'error': _safe_error(exc)})

    if not result['db_dropped']:
        result['errors'].extend(drop_errors)
        result['manual_command'] = f'sudo -u postgres dropdb {db_name}'
        return result

    if drop_roles:
        try:
            conn = _get_admin_conn()
            try:
                with conn.cursor() as cur:
                    for role_name in (admin_role, sync_role):
                        try:
                            existed = _role_exists(cur, role_name)
                            cur.execute(
                                psql.SQL("DROP ROLE IF EXISTS {}").format(
                                    psql.Identifier(role_name)
                                )
                            )
                            if existed:
                                result['roles_dropped'].append(role_name)
                        except Exception as exc:
                            err = _safe_error(exc)
                            logger.warning('OrgDB: 刪除角色 %s 失敗：%s', role_name, err)
                            result['errors'].append({'resource': role_name, 'error': err})
            finally:
                conn.close()
        except Exception as exc:
            err = _safe_error(exc)
            logger.warning('OrgDB: 刪除角色連線失敗：%s', err)
            result['errors'].append({'resource': 'roles', 'error': err})

    return result


def provisioning_health():
    """回傳 provisioning 能力自檢結果。"""
    result = {
        'configured': bool(os.environ.get('SYNC_PG_ADMIN_URL')),
        'credential_key': False,
        'reachable': False,
        'role': None,
        'is_superuser': False,
        'can_create_db': False,
        'can_create_role': False,
        'ok': False,
        'error': None,
    }

    key = os.environ.get('SYNC_CREDENTIAL_KEY')
    if key:
        try:
            Fernet(key.encode() if isinstance(key, str) else key)
            result['credential_key'] = True
        except Exception as exc:
            result['error'] = _safe_error(exc)

    if not result['configured']:
        result['error'] = result['error'] or 'SYNC_PG_ADMIN_URL 環境變數未設定'
        return result

    url = os.environ.get('SYNC_PG_ADMIN_URL')
    conn = None
    try:
        conn = psycopg2.connect(url, connect_timeout=5)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        result['reachable'] = True
        with conn.cursor() as cur:
            cur.execute("SELECT current_user")
            result['role'] = cur.fetchone()[0]
            cur.execute(
                "SELECT rolsuper, rolcreatedb, rolcreaterole "
                "FROM pg_roles WHERE rolname = current_user"
            )
            row = cur.fetchone()
            if row:
                result['is_superuser'] = bool(row[0])
                result['can_create_db'] = bool(row[1])
                result['can_create_role'] = bool(row[2])
    except Exception as exc:
        result['error'] = _safe_error(exc, _dsn_password(url))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    result['ok'] = (
        result['configured']
        and result['credential_key']
        and result['reachable']
        and result['can_create_db']
        and result['can_create_role']
    )
    return result


def rotate_credentials(org_db):
    """
    輪換企業 DB 的帳號密碼

    Args:
        org_db: FwOrgDatabase instance
    """
    from datetime import datetime

    new_admin_pwd = _generate_password()
    new_sync_pwd = _generate_password()

    conn = _get_admin_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                psql.SQL("ALTER ROLE {} WITH PASSWORD %s").format(
                    psql.Identifier(org_db.admin_user)
                ),
                (new_admin_pwd,)
            )
            cur.execute(
                psql.SQL("ALTER ROLE {} WITH PASSWORD %s").format(
                    psql.Identifier(org_db.sync_user)
                ),
                (new_sync_pwd,)
            )
    finally:
        conn.close()

    org_db.admin_password = new_admin_pwd
    org_db.sync_password = new_sync_pwd
    org_db.last_credential_rotation = datetime.utcnow()

    logger.info(f'OrgDB: 已輪換 {org_db.db_name} 的帳號密碼')


def get_org_database(org_secure_code):
    """
    取得企業的 DB 記錄

    Args:
        org_secure_code: Organization.secure_code

    Returns:
        FwOrgDatabase or None
    """
    from ...models.org_database import FwOrgDatabase
    return FwOrgDatabase.query.filter_by(
        org_secure_code=org_secure_code,
        is_ready=True,
        is_deleted=False,
    ).first()
