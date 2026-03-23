"""
SQL Sync — 企業專屬資料庫管理器

負責：
1. 為企業建立獨立的 PostgreSQL 資料庫 (org_{id})
2. 建立高低權限帳號 (bfadmin_{id} / bfsync_{id})
3. 設定正確的 GRANT 權限
4. 儲存加密憑證到 FwOrgDatabase
"""
import os
import secrets
import string
import logging

import psycopg2
from psycopg2 import sql as psql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

logger = logging.getLogger(__name__)


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


def _role_exists(cur, role_name):
    """檢查 PostgreSQL 角色是否存在"""
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role_name,))
    return cur.fetchone() is not None


def _db_exists(cur, db_name):
    """檢查資料庫是否存在"""
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
    return cur.fetchone() is not None


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

    # 檢查是否已存在
    existing = FwOrgDatabase.query.filter_by(org_id=org_id, is_deleted=False).first()
    if existing and existing.is_ready:
        logger.info(f'OrgDB: org_{org_id} 已存在且就緒，跳過')
        return existing

    conn = _get_admin_conn()
    try:
        with conn.cursor() as cur:
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

    # 3. 用 superuser 連入 org DB 安裝 pgcrypto（需要 superuser 權限）
    su_url = os.environ.get('SYNC_PG_ADMIN_URL', '')
    # 替換連線 URL 中的資料庫名稱為 org DB
    if '/' in su_url:
        su_base = su_url.rsplit('/', 1)[0]
        su_dsn = f'{su_base}/{db_name}'
    else:
        su_dsn = f'postgresql://postgres:postgres123@{db_host}:{db_port}/{db_name}'
    su_conn = psycopg2.connect(su_dsn)
    su_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with su_conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
            logger.info(f'OrgDB: 已在 {db_name} 安裝 pgcrypto')
    finally:
        su_conn.close()

    # 4. 連入 org DB 設定 sync 權限
    admin_dsn = f'postgresql://{admin_user}:{admin_pwd}@{db_host}:{db_port}/{db_name}'
    org_conn = psycopg2.connect(admin_dsn)
    org_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with org_conn.cursor() as cur:
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

    su_url = os.environ.get('SYNC_PG_ADMIN_URL', '')
    if '/' in su_url:
        su_base = su_url.rsplit('/', 1)[0]
        su_dsn = f'{su_base}/{org_db.db_name}'
    else:
        su_dsn = f'postgresql://postgres:postgres123@{org_db.db_host}:{org_db.db_port}/{org_db.db_name}'

    conn = psycopg2.connect(su_dsn)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        logger.info(f'OrgDB: 已在 {org_db.db_name} 確認/安裝 pgcrypto')
    finally:
        conn.close()


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
