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
import time
import urllib.request
import json

logger = logging.getLogger(__name__)

# BeakRisk health check 快取
_health_cache = {'result': None, 'ts': 0}
HEALTH_CACHE_TTL = 60  # 秒
BEAKRISK_HEALTH_URL = 'http://localhost:5088/health'
BEAKRISK_HEALTH_TIMEOUT = 3  # 秒


def check_beakrisk_health():
    """
    檢查 BeakRisk 服務狀態，結果快取 60 秒。

    回傳 dict:
      status: 'ok' | 'service_down' | 'not_installed' | 'db_error'
      message: 人類可讀訊息
      detail: 原始回應（status=ok 時）
    """
    now = time.time()
    if _health_cache['result'] and (now - _health_cache['ts']) < HEALTH_CACHE_TTL:
        return _health_cache['result']

    result = _do_health_check()
    _health_cache['result'] = result
    _health_cache['ts'] = now
    return result


def _do_health_check():
    """實際執行 health check"""
    try:
        req = urllib.request.Request(BEAKRISK_HEALTH_URL)
        with urllib.request.urlopen(req, timeout=BEAKRISK_HEALTH_TIMEOUT) as resp:
            data = json.loads(resp.read())
            if resp.status == 200 and data.get('status') == 'ok':
                return {
                    'status': 'ok',
                    'message': 'BeakRisk 運行中',
                    'detail': data,
                }
            # 503 from BeakRisk = DB error
            return {
                'status': 'db_error',
                'message': 'BeakRisk 資料庫暫時不可用',
                'detail': data,
            }
    except urllib.error.HTTPError as e:
        if e.code == 503:
            try:
                data = json.loads(e.read())
            except Exception:
                data = {}
            return {
                'status': 'db_error',
                'message': 'BeakRisk 資料庫暫時不可用',
                'detail': data,
            }
        return {
            'status': 'service_down',
            'message': f'BeakRisk 服務異常 (HTTP {e.code})',
            'detail': {},
        }
    except (urllib.error.URLError, ConnectionRefusedError, OSError):
        return {
            'status': 'service_down',
            'message': 'BeakRisk 服務未啟動',
            'detail': {},
        }
    except Exception as e:
        logger.warning(f"BeakRisk health check failed: {e}")
        return {
            'status': 'service_down',
            'message': 'BeakRisk 服務未啟動',
            'detail': {},
        }

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
