# -*- coding: utf-8 -*-
"""
vulnmgmt DB 連線服務

負責連線外部 vulnmgmt PostgreSQL 資料庫。
BeakPlatform 的 vuln_lifecycle 模組透過此服務讀取弱點資料。
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import current_app
from datetime import datetime, date
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

# 預設連線參數（可透過 Flask config 覆蓋）
DEFAULT_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'user': 'beakplatform',
    'password': 'postgres123',
    'database': 'vulnmgmt',
}


def _get_config():
    """取得 vulnmgmt DB 連線參數"""
    try:
        app_config = current_app.config
        return {
            'host': app_config.get('VULNMGMT_DB_HOST', DEFAULT_CONFIG['host']),
            'port': app_config.get('VULNMGMT_DB_PORT', DEFAULT_CONFIG['port']),
            'user': app_config.get('VULNMGMT_DB_USER', DEFAULT_CONFIG['user']),
            'password': app_config.get('VULNMGMT_DB_PASSWORD', DEFAULT_CONFIG['password']),
            'database': app_config.get('VULNMGMT_DB_NAME', DEFAULT_CONFIG['database']),
        }
    except RuntimeError:
        return DEFAULT_CONFIG


def get_conn():
    """取得 vulnmgmt DB 連線"""
    cfg = _get_config()
    return psycopg2.connect(**cfg)


def _serialize_row(row):
    """將 DB row 中的非 JSON 可序列化類型轉為字串"""
    result = {}
    for k, v in row.items():
        if isinstance(v, datetime):
            result[k] = v.isoformat()
        elif isinstance(v, date):
            result[k] = v.isoformat()
        elif isinstance(v, Decimal):
            result[k] = float(v)
        else:
            result[k] = v
    return result


class VulnDBUnavailable(Exception):
    """vulnmgmt 資料庫無法連線"""
    pass


def query(sql, params=None, fetchone=False):
    """執行 SQL 查詢"""
    try:
        conn = get_conn()
    except Exception as e:
        logger.error(f"vulnmgmt DB 連線失敗: {e}")
        raise VulnDBUnavailable(str(e))
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            if fetchone:
                row = cur.fetchone()
                return _serialize_row(dict(row)) if row else None
            return [_serialize_row(dict(r)) for r in cur.fetchall()]
    except psycopg2.Error as e:
        logger.error(f"vulnmgmt DB 查詢失敗: {e}")
        raise VulnDBUnavailable(str(e))
    finally:
        conn.close()


def execute(sql, params=None):
    """執行 SQL 寫入"""
    try:
        conn = get_conn()
    except Exception as e:
        logger.error(f"vulnmgmt DB 連線失敗: {e}")
        raise VulnDBUnavailable(str(e))
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
    except psycopg2.Error as e:
        logger.error(f"vulnmgmt DB 寫入失敗: {e}")
        raise VulnDBUnavailable(str(e))
    finally:
        conn.close()


def get_deployment_mode():
    """取得目前部署模式"""
    try:
        row = query(
            "SELECT value FROM system_config WHERE key = 'deployment_mode'",
            fetchone=True
        )
        return row['value'] if row else 'standalone'
    except Exception as e:
        logger.warning(f"Failed to read deployment_mode: {e}")
        return 'unknown'
