"""
Data CRUD Module - DB Connector
根據視圖的 data_source 路由到正確的資料庫連線

路由策略:
  data_source='org'           → 企業專屬資料庫 (org_{org_id}) [psycopg2]
  data_source='conglomerate'  → 集團共享資料庫 (cg_{cg_id}) [psycopg2]
  data_source='portal'        → 子系統帳號角色 SQLite [SQLAlchemy session]
  data_source='portal_data'   → 子系統公開資料 SQLite [SQLAlchemy session]
"""
import logging
from contextlib import contextmanager

from flask_babel import gettext as _
from flask_login import current_user

logger = logging.getLogger(__name__)


class OrgDatabaseNotFound(Exception):
    """企業尚未建立專屬資料庫"""
    pass


class CgDatabaseNotFound(Exception):
    """集團尚未建立共享資料庫，或企業不屬於任何集團"""
    pass


class PortalDatabaseNotFound(Exception):
    """子系統尚未初始化 SQLite"""
    pass


def is_sqlite_source(data_source: str) -> bool:
    """判斷 data_source 是否為 SQLite 類型"""
    from .data_source_manager import SQLITE_SOURCES
    return data_source in SQLITE_SOURCES


@contextmanager
def get_data_conn(org_secure_code=None, data_source='org'):
    """
    取得目標資料庫連線（context manager）-- 僅用於 PostgreSQL 來源

    Args:
        org_secure_code: 視圖綁定的企業代碼。
            若未指定，使用當前用戶的 org_secure_code。
        data_source: 'org' = 企業 DB, 'conglomerate' = 集團共享 DB

    Usage:
        with get_data_conn(view.org_secure_code, view.data_source) as conn:
            with conn.cursor() as cur:
                cur.execute(...)

    注意: portal / portal_data 類型請用 get_sqlite_session()
    """
    org_sc = org_secure_code or current_user.org_secure_code

    if data_source == 'conglomerate':
        yield from _get_cg_data_conn(org_sc)
    else:
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


def _get_cg_data_conn(org_sc):
    """集團共享 DB 連線（member 角色，RLS 自動生效）"""
    from app.models.organization import Organization
    try:
        org = Organization.query.filter_by(
            secure_code=org_sc,
            is_deleted=False,
        ).first()
    except Exception:
        org = None

    if not org:
        raise CgDatabaseNotFound(_('找不到企業 %(org_sc)s', org_sc=org_sc))

    cg_sc = getattr(org, 'conglomerate_secure_code', None)
    if not cg_sc:
        raise CgDatabaseNotFound(
            _('企業 %(org_sc)s 不屬於任何集團，無法存取集團共享資料庫', org_sc=org_sc)
        )

    try:
        from modules.form_workflow.services.sql_sync.pool import get_cg_conn
        with get_cg_conn(cg_sc, role='member', org_secure_code=org_sc) as conn:
            yield conn
    except RuntimeError as e:
        if '找不到集團' in str(e):
            raise CgDatabaseNotFound(
                _('集團 %(cg_sc)s 尚未建立共享資料庫，請聯繫系統管理員', cg_sc=cg_sc)
            )
        raise


def get_db_display_name(org_secure_code=None, data_source='org'):
    """取得目前連線的資料庫顯示名稱（供 UI 顯示）"""
    org_sc = org_secure_code or current_user.org_secure_code

    if data_source == 'conglomerate':
        return _get_cg_db_display_name(org_sc)
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


def _get_cg_db_display_name(org_sc):
    """集團 DB 顯示名稱"""
    try:
        from app.models.organization import Organization
        org = Organization.query.filter_by(
            secure_code=org_sc,
            is_deleted=False,
        ).first()
        if not org or not org.conglomerate_secure_code:
            return _('(不屬於任何集團)')

        from modules.form_workflow.models.conglomerate_database import (
            FwConglomerateDatabase,
        )
        cg_db = FwConglomerateDatabase.query.filter_by(
            conglomerate_secure_code=org.conglomerate_secure_code,
            is_ready=True,
            is_deleted=False,
        ).first()
        if cg_db:
            return _('%(db_name)s (集團共享資料庫)', db_name=cg_db.db_name)
        return _('(集團尚未建立共享資料庫)')
    except Exception:
        return _('(無法取得集團資料庫資訊)')


def check_cg_available(org_secure_code=None):
    """
    檢查企業是否可使用集團共享 DB

    Returns:
        dict: {available: bool, conglomerate_name: str|None, db_name: str|None}
    """
    org_sc = org_secure_code or current_user.org_secure_code
    try:
        from app.models.organization import Organization
        org = Organization.query.filter_by(
            secure_code=org_sc,
            is_deleted=False,
        ).first()
        if not org or not org.conglomerate_secure_code:
            return {'available': False, 'conglomerate_name': None, 'db_name': None}

        from app.models.conglomerate import Conglomerate
        cg = Conglomerate.query.filter_by(
            secure_code=org.conglomerate_secure_code,
            is_deleted=False,
        ).first()
        if not cg or not cg.has_shared_db:
            return {
                'available': False,
                'conglomerate_name': cg.name if cg else None,
                'db_name': None,
            }

        from modules.form_workflow.models.conglomerate_database import (
            FwConglomerateDatabase,
        )
        cg_db = FwConglomerateDatabase.query.filter_by(
            conglomerate_secure_code=org.conglomerate_secure_code,
            is_ready=True,
            is_deleted=False,
        ).first()
        return {
            'available': bool(cg_db),
            'conglomerate_name': cg.name,
            'db_name': cg_db.db_name if cg_db else None,
        }
    except Exception as e:
        logger.warning('check_cg_available error: %s', e)
        return {'available': False, 'conglomerate_name': None, 'db_name': None}
