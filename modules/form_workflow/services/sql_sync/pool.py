"""
SQL Sync — 連線管理

支援兩種資料庫連線：
1. 企業 DB (org_XX): 每企業獨立，admin/sync 雙角色
2. 集團 DB (cg_XX): 集團共享，admin/member 雙角色，member 搭配 RLS

連線按需建立、快取、自動回收。
"""
import logging
import time
from contextlib import contextmanager

import psycopg2
import psycopg2.extensions

logger = logging.getLogger(__name__)

# 企業 DB 連線快取：{org_secure_code: {'admin': conn, 'sync': conn, 'last_used': ts}}
_conn_cache = {}
# 集團 DB 連線快取：{'cg:'+cg_sc: {'admin': conn, 'member': conn, 'last_used': ts}}
_cg_conn_cache = {}
_CACHE_TTL = 300  # 5 分鐘未使用則關閉連線


def _get_org_db(org_secure_code):
    """取得企業 DB 記錄"""
    from ...models.org_database import FwOrgDatabase
    return FwOrgDatabase.query.filter_by(
        org_secure_code=org_secure_code,
        is_ready=True,
        is_deleted=False,
    ).first()


def _ensure_conn(org_secure_code, role='sync'):
    """
    確保連線可用（從快取取或新建）

    Args:
        org_secure_code: 企業 secure_code
        role: 'admin' 或 'sync'

    Returns:
        psycopg2 connection
    """
    cache_key = org_secure_code
    now = time.time()

    # 嘗試從快取取
    if cache_key in _conn_cache:
        entry = _conn_cache[cache_key]
        conn = entry.get(role)
        if conn and not conn.closed:
            try:
                # 測試連線是否還活著
                with conn.cursor() as test_cur:
                    test_cur.execute('SELECT 1')
                # 確保不在壞掉的 transaction 裡
                if conn.status == psycopg2.extensions.STATUS_BEGIN:
                    conn.rollback()
                entry['last_used'] = now
                return conn
            except Exception:
                # 連線壞了，關掉重建
                try:
                    conn.close()
                except Exception:
                    pass

    # 新建連線
    org_db = _get_org_db(org_secure_code)
    if not org_db:
        raise RuntimeError(f'找不到企業 {org_secure_code} 的 DB 記錄')

    dsn = org_db.get_admin_dsn() if role == 'admin' else org_db.get_sync_dsn()
    conn = psycopg2.connect(dsn)

    if cache_key not in _conn_cache:
        _conn_cache[cache_key] = {'last_used': now}
    _conn_cache[cache_key][role] = conn
    _conn_cache[cache_key]['last_used'] = now

    return conn


@contextmanager
def get_org_conn(org_secure_code, role='sync'):
    """
    取得企業 DB 連線 (context manager)

    Args:
        org_secure_code: 企業 secure_code
        role: 'admin'（DDL 建表）或 'sync'（DML 寫入）

    Usage:
        with get_org_conn('xxx', role='sync') as conn:
            with conn.cursor() as cur:
                cur.execute(...)
            conn.commit()
    """
    conn = _ensure_conn(org_secure_code, role)
    try:
        yield conn
    except Exception:
        if not conn.closed:
            conn.rollback()
        raise
    finally:
        # 連線將回到快取，確保不留打開的 transaction（避免鎖表）
        if conn and not conn.closed and not getattr(conn, 'autocommit', False):
            try:
                if conn.status == psycopg2.extensions.STATUS_BEGIN:
                    conn.rollback()
            except Exception:
                pass


def invalidate_conn(org_secure_code, role=None):
    """
    關閉並清除指定企業的連線快取

    Args:
        org_secure_code: 企業 secure_code
        role: 'admin'/'sync'/None(全清)
    """
    if org_secure_code not in _conn_cache:
        return

    entry = _conn_cache[org_secure_code]
    roles = [role] if role else ['admin', 'sync']
    for r in roles:
        conn = entry.pop(r, None)
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    if 'admin' not in entry and 'sync' not in entry:
        _conn_cache.pop(org_secure_code, None)


def cleanup_idle_conns():
    """清理超過 TTL 的閒置連線（由 Worker 定期呼叫，含企業+集團）"""
    now = time.time()
    expired = [
        key for key, entry in _conn_cache.items()
        if now - entry.get('last_used', 0) > _CACHE_TTL
    ]
    for key in expired:
        invalidate_conn(key)
    # 同時清理集團連線
    cg_expired = [
        key for key, entry in _cg_conn_cache.items()
        if now - entry.get('last_used', 0) > _CACHE_TTL
    ]
    for key in cg_expired:
        invalidate_cg_conn(key)
    total = len(expired) + len(cg_expired)
    if total:
        logger.debug(f'SQL Sync: 清理 {total} 個閒置連線')


def close_all():
    """關閉所有連線（企業 + 集團）"""
    for key in list(_conn_cache.keys()):
        invalidate_conn(key)
    for key in list(_cg_conn_cache.keys()):
        invalidate_cg_conn(key)
    logger.info('SQL Sync: 所有連線已關閉')


# === 集團 DB 連線管理 ===

def _get_cg_db(conglomerate_secure_code):
    """取得集團 DB 記錄"""
    from ...models.conglomerate_database import FwConglomerateDatabase
    return FwConglomerateDatabase.query.filter_by(
        conglomerate_secure_code=conglomerate_secure_code,
        is_ready=True,
        is_deleted=False,
    ).first()


def _ensure_cg_conn(conglomerate_secure_code, role='member'):
    """
    確保集團 DB 連線可用（從快取取或新建）

    Args:
        conglomerate_secure_code: 集團 secure_code
        role: 'admin' 或 'member'

    Returns:
        psycopg2 connection
    """
    cache_key = conglomerate_secure_code
    now = time.time()

    # 嘗試從快取取
    if cache_key in _cg_conn_cache:
        entry = _cg_conn_cache[cache_key]
        conn = entry.get(role)
        if conn and not conn.closed:
            try:
                with conn.cursor() as test_cur:
                    test_cur.execute('SELECT 1')
                if conn.status == psycopg2.extensions.STATUS_BEGIN:
                    conn.rollback()
                entry['last_used'] = now
                return conn
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass

    # 新建連線
    cg_db = _get_cg_db(conglomerate_secure_code)
    if not cg_db:
        raise RuntimeError(
            f'找不到集團 {conglomerate_secure_code} 的 DB 記錄'
        )

    if role == 'admin':
        dsn = cg_db.get_admin_dsn()
    else:
        dsn = cg_db.get_member_dsn()
    conn = psycopg2.connect(dsn)

    if cache_key not in _cg_conn_cache:
        _cg_conn_cache[cache_key] = {'last_used': now}
    _cg_conn_cache[cache_key][role] = conn
    _cg_conn_cache[cache_key]['last_used'] = now

    return conn


@contextmanager
def get_cg_conn(conglomerate_secure_code, role='member',
                org_secure_code=None):
    """
    取得集團 DB 連線 (context manager)

    Args:
        conglomerate_secure_code: 集團 secure_code
        role: 'admin'（DDL）或 'member'（DML，需搭配 org_secure_code）
        org_secure_code: 使用 member 角色時必須提供，用於 SET app.org_code

    Usage:
        # admin 連線（DDL 操作，不受 RLS 限制）
        with get_cg_conn('xxx', role='admin') as conn:
            ...

        # member 連線（DML 操作，RLS 自動生效）
        with get_cg_conn('xxx', role='member', org_secure_code='yyy') as conn:
            ...
    """
    if role == 'member' and not org_secure_code:
        raise ValueError(
            '集團 DB member 連線必須提供 org_secure_code '
            '（用於 RLS 身份識別）'
        )

    conn = _ensure_cg_conn(conglomerate_secure_code, role)

    # member 連線自動設定 RLS 身份
    if role == 'member' and org_secure_code:
        with conn.cursor() as cur:
            cur.execute(
                "SET app.org_code = %s", (org_secure_code,)
            )

    try:
        yield conn
    except Exception:
        if not conn.closed:
            conn.rollback()
        raise
    finally:
        if conn and not conn.closed and not getattr(conn, 'autocommit', False):
            try:
                if conn.status == psycopg2.extensions.STATUS_BEGIN:
                    conn.rollback()
            except Exception:
                pass


def invalidate_cg_conn(conglomerate_secure_code, role=None):
    """
    關閉並清除指定集團的連線快取

    Args:
        conglomerate_secure_code: 集團 secure_code
        role: 'admin'/'member'/None(全清)
    """
    if conglomerate_secure_code not in _cg_conn_cache:
        return

    entry = _cg_conn_cache[conglomerate_secure_code]
    roles = [role] if role else ['admin', 'member']
    for r in roles:
        conn = entry.pop(r, None)
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    if 'admin' not in entry and 'member' not in entry:
        _cg_conn_cache.pop(conglomerate_secure_code, None)


def cleanup_idle_cg_conns():
    """清理超過 TTL 的閒置集團 DB 連線"""
    now = time.time()
    expired = [
        key for key, entry in _cg_conn_cache.items()
        if now - entry.get('last_used', 0) > _CACHE_TTL
    ]
    for key in expired:
        invalidate_cg_conn(key)
    if expired:
        logger.debug(f'SQL Sync: 清理 {len(expired)} 個閒置集團連線')


# === 向後相容（舊介面，供過渡期使用） ===

def is_pool_ready():
    """向後相容：永遠回傳 True（新架構不需要全域連線池）"""
    return True
