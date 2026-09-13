"""
Data CRUD Module - DB Connector
根據視圖的 data_source 路由到正確的資料庫連線

路由策略:
  data_source='org'           → 企業專屬資料庫 (org_{org_id}) [psycopg2]
  data_source='portal'        → 子系統帳號角色 SQLite [SQLAlchemy session]
  data_source='portal_data'   → 子系統公開資料 SQLite [SQLAlchemy session]
"""
from contextlib import contextmanager

from flask_babel import gettext as _
from flask_login import current_user

class OrgDatabaseNotFound(Exception):
    """企業尚未建立專屬資料庫"""
    pass


class PortalDatabaseNotFound(Exception):
    """子系統尚未初始化 SQLite"""
    pass


def is_sqlite_source(data_source: str) -> bool:
    """判斷 data_source 是否為 SQLite 類型"""
    from .data_source_manager import SQLITE_SOURCES
    return data_source in SQLITE_SOURCES


@contextmanager
def get_data_conn(org_secure_code=None):
    """
    取得目標資料庫連線（context manager）-- 僅用於 PostgreSQL 來源

    Args:
        org_secure_code: 視圖綁定的企業代碼。
            若未指定，使用當前用戶的 org_secure_code。

    Usage:
        with get_data_conn(view.org_secure_code) as conn:
            with conn.cursor() as cur:
                cur.execute(...)

    注意: portal / portal_data 類型請用 get_sqlite_session()
    """
    org_sc = org_secure_code or current_user.org_secure_code
    yield from _get_org_data_conn(org_sc)


@contextmanager
def get_sqlite_session(sub_system_sc: str, data_source: str):
    """
    取得 SQLite 資料庫 Session (context manager)

    Args:
        sub_system_sc: 子系統 secure_code
        data_source: 'portal' 或 'portal_data'

    Usage:
        with get_sqlite_session(ss_sc, 'portal_data') as session:
            result = session.execute(text('SELECT ...'))

    Raises:
        PortalDatabaseNotFound: SQLite 檔案不存在
    """
    from .data_source_manager import DataSourceManager, SQLITE_SOURCES

    if data_source not in SQLITE_SOURCES:
        raise ValueError(f'Not a SQLite source: {data_source}')

    mgr = DataSourceManager()
    try:
        with mgr.get_session(sub_system_sc, data_source) as session:
            yield session
    except FileNotFoundError as e:
        raise PortalDatabaseNotFound(str(e)) from e


def _get_org_data_conn(org_sc):
    """企業 DB 連線"""
    try:
        from modules.form_workflow.services.sql_sync.pool import get_org_conn
        with get_org_conn(org_sc, role='sync') as conn:
            yield conn
    except RuntimeError as e:
        if '找不到企業' in str(e):
            raise OrgDatabaseNotFound(
                _('企業 %(org_sc)s 尚未建立專屬資料庫，請聯繫系統管理員', org_sc=org_sc)
            )
        raise


def get_db_display_name(org_secure_code=None):
    """取得目前連線的資料庫顯示名稱（供 UI 顯示）"""
    org_sc = org_secure_code or current_user.org_secure_code
    return _get_org_db_display_name(org_sc)


def _get_org_db_display_name(org_sc):
    """企業 DB 顯示名稱"""
    try:
        from modules.form_workflow.models.org_database import FwOrgDatabase
        org_db = FwOrgDatabase.query.filter_by(
            org_secure_code=org_sc,
            is_ready=True,
            is_deleted=False,
        ).first()
        if org_db:
            return _('%(db_name)s (企業資料庫)', db_name=org_db.db_name)
        return _('(尚未建立企業資料庫)')
    except Exception:
        return _('(無法取得資料庫資訊)')
