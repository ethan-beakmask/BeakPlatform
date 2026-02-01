"""
SQL Sync — psycopg2 連線池管理

為 beakform_data 獨立資料庫提供連線池。
與主 DB (beakplatform_dev) 完全分離。
"""
import os
import logging
from contextlib import contextmanager

import psycopg2
from psycopg2.pool import SimpleConnectionPool

logger = logging.getLogger(__name__)

_pool = None


def init_pool(app):
    """
    初始化 beakform_data 連線池

    從 app.config 或環境變數讀取 FORMDATA_DATABASE_URL。
    若未設定則跳過（SQL sync 不啟用）。
    """
    global _pool

    url = (
        app.config.get('FORMDATA_DATABASE_URL')
        or os.environ.get('FORMDATA_DATABASE_URL')
    )
    if not url:
        logger.info('SQL Sync: FORMDATA_DATABASE_URL 未設定，SQL sync 不啟用')
        return

    try:
        _pool = SimpleConnectionPool(minconn=1, maxconn=5, dsn=url)
        logger.info('SQL Sync: 連線池已初始化 (minconn=1, maxconn=5)')
    except Exception as e:
        logger.error(f'SQL Sync: 連線池初始化失敗: {e}')
        _pool = None


def is_pool_ready():
    """檢查連線池是否已初始化"""
    return _pool is not None


@contextmanager
def get_conn():
    """
    取得 beakform_data 連線 (context manager)

    Usage:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(...)
            conn.commit()
    """
    if _pool is None:
        raise RuntimeError('SQL Sync 連線池未初始化')

    conn = _pool.getconn()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


def close_pool():
    """關閉連線池"""
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None
        logger.info('SQL Sync: 連線池已關閉')
