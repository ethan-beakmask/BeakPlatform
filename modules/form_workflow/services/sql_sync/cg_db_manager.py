"""
SQL Sync — 集團共享資料庫管理器

負責：
1. 為集團建立獨立的 PostgreSQL 資料庫 (cg_{id})
2. 建立高低權限帳號 (cgadmin_{id} / cgmember_{id})
3. REVOKE PUBLIC CONNECT（集團間隔離）
4. 設定 RLS 基礎設施（啟用 RLS + 提供 policy 套用函數）
5. 儲存加密憑證到 FwConglomerateDatabase

RLS 設計：
- 每張表必須有 owner_org_code VARCHAR(32) 欄位
- member 帳號連線後平台 SET app.org_code = '企業 SC'
- SELECT: 所有成員可讀（USING true）
- INSERT/UPDATE/DELETE: 只能操作 owner_org_code 符合的 row
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


def provision_conglomerate_database(
    conglomerate_id, conglomerate_secure_code,
    db_host='localhost', db_port=5432
):
    """
    為集團建立共享資料庫與帳號

    流程:
    1. 產生密碼
    2. 建立角色 cgadmin_{id} (DDL) + cgmember_{id} (DML)
    3. 建立資料庫 cg_{id}，owner 為 cgadmin_{id}
    4. REVOKE CONNECT FROM PUBLIC（集團間隔離）
    5. 安裝 pgcrypto
    6. 設定 member 的 DML 權限 + RLS 基礎設施
    7. 儲存加密憑證到 FwConglomerateDatabase

    Args:
        conglomerate_id: Conglomerate.id
        conglomerate_secure_code: Conglomerate.secure_code
        db_host: DB host
        db_port: DB port

    Returns:
        FwConglomerateDatabase instance
    """
    from ...models.conglomerate_database import FwConglomerateDatabase
    from app import db

    db_name = f'cg_{conglomerate_id}'
    admin_user = f'cgadmin_{conglomerate_id}'
    member_user = f'cgmember_{conglomerate_id}'
    admin_pwd = _generate_password()
    member_pwd = _generate_password()

    # 檢查是否已存在
    existing = FwConglomerateDatabase.query.filter_by(
        conglomerate_id=conglomerate_id, is_deleted=False
    ).first()
    if existing and existing.is_ready:
        logger.info(f'CgDB: cg_{conglomerate_id} 已存在且就緒，跳過')
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
                logger.info(f'CgDB: 建立角色 {admin_user}')
            else:
                cur.execute(
                    psql.SQL("ALTER ROLE {} WITH PASSWORD %s").format(
                        psql.Identifier(admin_user)
                    ),
                    (admin_pwd,)
                )

            if not _role_exists(cur, member_user):
                cur.execute(
                    psql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD %s").format(
                        psql.Identifier(member_user)
                    ),
                    (member_pwd,)
                )
                logger.info(f'CgDB: 建立角色 {member_user}')
            else:
                cur.execute(
                    psql.SQL("ALTER ROLE {} WITH PASSWORD %s").format(
                        psql.Identifier(member_user)
                    ),
                    (member_pwd,)
                )

            # 2. 建立資料庫（如不存在）
            if not _db_exists(cur, db_name):
                cur.execute(
                    psql.SQL("CREATE DATABASE {} OWNER {}").format(
                        psql.Identifier(db_name),
                        psql.Identifier(admin_user),
                    )
                )
                # 移除 PUBLIC 的 CONNECT 權限，防止其他集團/企業帳號連入
                cur.execute(
                    psql.SQL(
                        "REVOKE CONNECT ON DATABASE {} FROM PUBLIC"
                    ).format(psql.Identifier(db_name))
                )
                logger.info(
                    f'CgDB: 建立資料庫 {db_name}'
                    f'（已 REVOKE PUBLIC CONNECT）'
                )
            else:
                # 既有資料庫也確保 PUBLIC CONNECT 已移除
                cur.execute(
                    psql.SQL(
                        "REVOKE CONNECT ON DATABASE {} FROM PUBLIC"
                    ).format(psql.Identifier(db_name))
                )
                logger.info(
                    f'CgDB: 資料庫 {db_name} 已存在'
                    f'（已確認 REVOKE PUBLIC CONNECT）'
                )

    finally:
        conn.close()

    # 3. 用 superuser 連入集團 DB 安裝 pgcrypto
    su_url = os.environ.get('SYNC_PG_ADMIN_URL', '')
    if '/' in su_url:
        su_base = su_url.rsplit('/', 1)[0]
        su_dsn = f'{su_base}/{db_name}'
    else:
        su_dsn = (
            f'postgresql://postgres:postgres123'
            f'@{db_host}:{db_port}/{db_name}'
        )
    su_conn = psycopg2.connect(su_dsn)
    su_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with su_conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
            logger.info(f'CgDB: 已在 {db_name} 安裝 pgcrypto')
    finally:
        su_conn.close()

    # 4. 連入集團 DB 設定 member 權限 + RLS 基礎設施
    admin_dsn = (
        f'postgresql://{admin_user}:{admin_pwd}'
        f'@{db_host}:{db_port}/{db_name}'
    )
    cg_conn = psycopg2.connect(admin_dsn)
    cg_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with cg_conn.cursor() as cur:
            # 允許 member_user 連入
            cur.execute(
                psql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    psql.Identifier(db_name),
                    psql.Identifier(member_user),
                )
            )
            # 允許使用 public schema
            cur.execute(
                psql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(
                    psql.Identifier(member_user),
                )
            )
            # 預設：member_user 對未來建立的表有 DML 權限
            cur.execute(
                psql.SQL(
                    "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
                ).format(
                    psql.Identifier(admin_user),
                    psql.Identifier(member_user),
                )
            )
            # 預設：member_user 對序列也有使用權限
            cur.execute(
                psql.SQL(
                    "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
                    "GRANT USAGE, SELECT ON SEQUENCES TO {}"
                ).format(
                    psql.Identifier(admin_user),
                    psql.Identifier(member_user),
                )
            )
            logger.info(f'CgDB: 已設定 {member_user} 的 DML 權限')
    finally:
        cg_conn.close()

    # 5. 儲存到 FwConglomerateDatabase
    if existing:
        cg_db = existing
    else:
        cg_db = FwConglomerateDatabase(
            conglomerate_secure_code=conglomerate_secure_code,
            conglomerate_id=conglomerate_id,
            db_name=db_name,
            db_host=db_host,
            db_port=db_port,
            admin_user=admin_user,
            member_user=member_user,
        )
        db.session.add(cg_db)

    cg_db.admin_password = admin_pwd
    cg_db.member_password = member_pwd
    cg_db.is_ready = True
    db.session.flush()

    logger.info(
        f'CgDB: 集團 {conglomerate_id} 共享資料庫 {db_name} 建立完成'
    )
    return cg_db


def apply_rls_to_table(conglomerate_secure_code, table_name):
    """
    對集團 DB 中的表套用 RLS policy

    前置條件：表必須有 owner_org_code VARCHAR(32) 欄位

    RLS 規則：
    - SELECT: 所有成員可讀（USING true）
    - INSERT: 只能寫入 owner_org_code = current_setting('app.org_code') 的 row
    - UPDATE: 只能改 owner_org_code = current_setting('app.org_code') 的 row
    - DELETE: 只能刪 owner_org_code = current_setting('app.org_code') 的 row

    admin 帳號是 table owner，RLS 不適用（PostgreSQL 預設行為），
    所以 DDL 操作不受影響。

    Args:
        conglomerate_secure_code: 集團 secure_code
        table_name: 資料表名稱
    """
    from .pool import get_cg_conn

    with get_cg_conn(conglomerate_secure_code, role='admin') as conn:
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        with conn.cursor() as cur:
            tbl = psql.Identifier(table_name)

            # 啟用 RLS
            cur.execute(
                psql.SQL("ALTER TABLE {} ENABLE ROW LEVEL SECURITY").format(
                    tbl
                )
            )

            # 先清除舊 policy（冪等）
            for policy_name in [
                f'cg_read_{table_name}',
                f'cg_insert_{table_name}',
                f'cg_update_{table_name}',
                f'cg_delete_{table_name}',
            ]:
                cur.execute(
                    psql.SQL(
                        "DROP POLICY IF EXISTS {} ON {}"
                    ).format(
                        psql.Identifier(policy_name), tbl
                    )
                )

            # SELECT: 所有成員可讀
            cur.execute(
                psql.SQL(
                    "CREATE POLICY {} ON {} FOR SELECT USING (true)"
                ).format(
                    psql.Identifier(f'cg_read_{table_name}'), tbl
                )
            )

            # INSERT: 只能寫自己的 org_code
            cur.execute(
                psql.SQL(
                    "CREATE POLICY {} ON {} FOR INSERT "
                    "WITH CHECK ("
                    "owner_org_code = current_setting('app.org_code')"
                    ")"
                ).format(
                    psql.Identifier(f'cg_insert_{table_name}'), tbl
                )
            )

            # UPDATE: 只能改自己的 row
            cur.execute(
                psql.SQL(
                    "CREATE POLICY {} ON {} FOR UPDATE "
                    "USING ("
                    "owner_org_code = current_setting('app.org_code')"
                    ")"
                ).format(
                    psql.Identifier(f'cg_update_{table_name}'), tbl
                )
            )

            # DELETE: 只能刪自己的 row
            cur.execute(
                psql.SQL(
                    "CREATE POLICY {} ON {} FOR DELETE "
                    "USING ("
                    "owner_org_code = current_setting('app.org_code')"
                    ")"
                ).format(
                    psql.Identifier(f'cg_delete_{table_name}'), tbl
                )
            )

            logger.info(f'CgDB: 已對 {table_name} 套用 RLS policy')


def rotate_credentials(cg_db):
    """
    輪換集團 DB 的帳號密碼

    Args:
        cg_db: FwConglomerateDatabase instance
    """
    from datetime import datetime

    new_admin_pwd = _generate_password()
    new_member_pwd = _generate_password()

    conn = _get_admin_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                psql.SQL("ALTER ROLE {} WITH PASSWORD %s").format(
                    psql.Identifier(cg_db.admin_user)
                ),
                (new_admin_pwd,)
            )
            cur.execute(
                psql.SQL("ALTER ROLE {} WITH PASSWORD %s").format(
                    psql.Identifier(cg_db.member_user)
                ),
                (new_member_pwd,)
            )
    finally:
        conn.close()

    cg_db.admin_password = new_admin_pwd
    cg_db.member_password = new_member_pwd
    cg_db.last_credential_rotation = datetime.utcnow()

    logger.info(f'CgDB: 已輪換 {cg_db.db_name} 的帳號密碼')


def get_conglomerate_database(conglomerate_secure_code):
    """
    取得集團的 DB 記錄

    Args:
        conglomerate_secure_code: Conglomerate.secure_code

    Returns:
        FwConglomerateDatabase or None
    """
    from ...models.conglomerate_database import FwConglomerateDatabase
    return FwConglomerateDatabase.query.filter_by(
        conglomerate_secure_code=conglomerate_secure_code,
        is_ready=True,
        is_deleted=False,
    ).first()
