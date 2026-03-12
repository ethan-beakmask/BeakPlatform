"""
Data CRUD Module - DB Connector
根據視圖的 org_secure_code 取得企業專屬資料庫連線

路由策略:
  視圖綁定的 org_secure_code → 企業專屬資料庫 (org_{org_id})
  無論當前用戶是系統管理員或企業用戶，SQL Sync 表都在企業 DB。
"""
import logging
from contextlib import contextmanager

from flask_login import current_user

logger = logging.getLogger(__name__)


class OrgDatabaseNotFound(Exception):
    """企業尚未建立專屬資料庫"""
    pass


@contextmanager
def get_data_conn(org_secure_code=None):
    """
    取得目標資料庫連線（context manager）

    統一透過 form_workflow pool 連企業 DB，與 SQL Sync 使用相同路徑。

    Args:
        org_secure_code: 視圖綁定的企業代碼。
            若未指定，使用當前用戶的 org_secure_code。

    Usage:
        with get_data_conn(view.org_secure_code) as conn:
            with conn.cursor() as cur:
                cur.execute(...)
    """
    org_sc = org_secure_code or current_user.org_secure_code
    try:
        from modules.form_workflow.services.sql_sync.pool import get_org_conn
        with get_org_conn(org_sc, role='sync') as conn:
            yield conn
    except RuntimeError as e:
        if '找不到企業' in str(e):
            raise OrgDatabaseNotFound(
                f'企業 {org_sc} 尚未建立專屬資料庫，請聯繫系統管理員'
            )
        raise


def get_db_display_name(org_secure_code=None):
    """取得目前連線的資料庫顯示名稱（供 UI 顯示）"""
    org_sc = org_secure_code or current_user.org_secure_code
    try:
        from modules.form_workflow.models.org_database import FwOrgDatabase
        org_db = FwOrgDatabase.query.filter_by(
            org_secure_code=org_sc,
            is_ready=True,
            is_deleted=False,
        ).first()
        if org_db:
            return f'{org_db.db_name} (企業資料庫)'
        return '(尚未建立企業資料庫)'
    except Exception:
        return '(無法取得資料庫資訊)'
