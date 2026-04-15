# -*- coding: utf-8 -*-
"""
vulnmgmt DB 連線服務

負責連線外部 vulnmgmt PostgreSQL 資料庫。
BeakPlatform 的 vuln_lifecycle 模組透過此服務讀取弱點資料。
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import current_app
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


def query(sql, params=None, fetchone=False):
    """執行 SQL 查詢"""
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            if fetchone:
                row = cur.fetchone()
                return dict(row) if row else None
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def execute(sql, params=None):
    """執行 SQL 寫入"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
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
