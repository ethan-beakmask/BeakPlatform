"""
Data CRUD Module - DB Connector
根據用戶身分取得正確的資料庫連線

系統管理員 → 主資料庫 (beakplatform_dev)
企業用戶   → 企業專屬資料庫 (org_{org_id})
"""
import logging
from contextlib import contextmanager

import psycopg2
from flask import current_app
from flask_login import current_user

logger = logging.getLogger(__name__)


class OrgDatabaseNotFound(Exception):
    """企業尚未建立專屬資料庫"""
    pass


def _get_main_db_dsn() -> str:
    """從 Flask config 取得主資料庫 DSN"""
    return current_app.config['SQLALCHEMY_DATABASE_URI']


@contextmanager
def get_data_conn():
    """
    取得目標資料庫連線（context manager）

    系統管理員 → 主資料庫（psycopg2 直連）
    企業用戶   → 企業 DB（透過 form_workflow pool）

    Usage:
        with get_data_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(...)
    """
    if current_user.is_system_admin:
        # 系統管理員: 連主資料庫
        dsn = _get_main_db_dsn()
        conn = psycopg2.connect(dsn)
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        # 企業用戶: 連企業專屬 DB
        org_sc = current_user.org_secure_code
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


def get_db_display_name() -> str:
    """取得目前連線的資料庫顯示名稱（供 UI 顯示）"""
    if current_user.is_system_admin:
        return 'beakplatform_dev (系統主資料庫)'
    else:
        try:
            from modules.form_workflow.models.org_database import FwOrgDatabase
            org_db = FwOrgDatabase.query.filter_by(
                org_secure_code=current_user.org_secure_code,
                is_ready=True,
                is_deleted=False,
            ).first()
            if org_db:
                return f'{org_db.db_name} (企業資料庫)'
            return '(尚未建立企業資料庫)'
        except Exception:
            return '(無法取得資料庫資訊)'
