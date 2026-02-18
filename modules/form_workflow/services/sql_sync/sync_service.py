"""
SQL Sync — 佇列式同步服務

表單提交/簽核時呼叫 enqueue_sync()，寫入 fw_sync_queue。
實際 UPSERT 由背景 Worker 處理。

也提供 execute_sync() 供 Worker 呼叫。
"""
import logging
from datetime import datetime

from psycopg2 import sql as psql

from .pool import get_org_conn
from .converter import normalize_value

logger = logging.getLogger(__name__)


# =============================================================================
# 佇列寫入（Flask app 呼叫）
# =============================================================================

def enqueue_sync(form_instance, published_secure_code=None):
    """
    將同步任務寫入佇列

    取代舊版的 sync_form_data_safe()，改為非同步佇列模式。

    Args:
        form_instance: FwFormInstance 實例
        published_secure_code: 發行版本 secure_code

    Returns:
        bool: 是否成功入列
    """
    from app import db
    from ...models.sync_queue import FwSyncQueue
    from ...models.sql_form_registry import FwSqlFormRegistry

    psc = published_secure_code or getattr(form_instance, 'published_secure_code', None)
    if not psc:
        return False

    # 查 registry 確認有 SQL sync
    registry = FwSqlFormRegistry.query.filter_by(
        published_secure_code=psc,
        status='active',
    ).first()
    if not registry:
        return False

    try:
        item = FwSyncQueue(
            org_secure_code=form_instance.org_secure_code,
            form_instance_secure_code=form_instance.secure_code,
            published_secure_code=psc,
            registry_id=registry.id,
            action='upsert',
        )
        db.session.add(item)
        # 不單獨 commit，讓呼叫者的 transaction 一起提交
        db.session.flush()
        return True
    except Exception as e:
        logger.warning(f'SQL Sync: 入列失敗 (instance={form_instance.secure_code}): {e}')
        return False


def enqueue_sync_safe(form_instance, published_secure_code=None):
    """安全版本 — 失敗不拋異常"""
    try:
        return enqueue_sync(form_instance, published_secure_code)
    except Exception as e:
        logger.warning(
            f'SQL Sync: 入列失敗 (instance={form_instance.secure_code}): {e}',
            exc_info=True,
        )
        return False


# =============================================================================
# 實際同步（Worker 呼叫）
# =============================================================================

def execute_sync(queue_item):
    """
    執行單筆同步任務

    由 Worker 呼叫，從 queue_item 中取得資訊，
    用 sync 低權限帳號 UPSERT 到企業 DB。

    Args:
        queue_item: FwSyncQueue 實例

    Returns:
        bool: 是否成功
    """
    from ...models.sql_form_registry import FwSqlFormRegistry
    from ...models.form_instance import FwFormInstance
    from app import db

    # 查 registry
    registry = FwSqlFormRegistry.query.get(queue_item.registry_id)
    if not registry:
        registry = FwSqlFormRegistry.query.filter_by(
            published_secure_code=queue_item.published_secure_code,
            status='active',
        ).first()
    if not registry:
        raise ValueError(f'找不到 registry (published_sc={queue_item.published_secure_code})')

    # 查 form_instance
    form_instance = FwFormInstance.query.filter_by(
        secure_code=queue_item.form_instance_secure_code,
        is_deleted=False,
    ).first()
    if not form_instance:
        raise ValueError(f'找不到 form_instance (sc={queue_item.form_instance_secure_code})')

    table_name = registry.table_name
    column_mapping = registry.column_mapping or {}
    form_data = form_instance.form_data or {}

    # 固定欄位：只保留關聯鍵，系統欄位由主庫 fw_form_instances 提供
    fixed_data = {
        'form_instance_secure_code': form_instance.secure_code,
    }

    # 準備動態欄位
    dynamic_data = {}
    for field_key, col_info in column_mapping.items():
        if field_key in form_data:
            pg_type = col_info.get('pg_type', 'TEXT')
            # Phase 2: 此處可依 col_info.get('is_pii') 做加密
            dynamic_data[field_key] = normalize_value(form_data[field_key], pg_type)

    all_data = {**fixed_data, **dynamic_data}

    # UPSERT
    col_names = list(all_data.keys())
    col_values = [all_data[k] for k in col_names]

    insert_cols = psql.SQL(', ').join([psql.Identifier(c) for c in col_names])
    insert_vals = psql.SQL(', ').join([psql.Placeholder()] * len(col_names))

    update_cols = [c for c in col_names if c != 'form_instance_secure_code']
    update_set = psql.SQL(', ').join([
        psql.SQL('{} = EXCLUDED.{}').format(
            psql.Identifier(c), psql.Identifier(c)
        )
        for c in update_cols
    ])

    upsert_sql = psql.SQL(
        'INSERT INTO {} ({}) VALUES ({}) '
        'ON CONFLICT (form_instance_secure_code) DO UPDATE SET {}'
    ).format(
        psql.Identifier(table_name),
        insert_cols,
        insert_vals,
        update_set,
    )

    # 用 sync（低權限）帳號連線到企業 DB
    with get_org_conn(queue_item.org_secure_code, role='sync') as conn:
        with conn.cursor() as cur:
            cur.execute(upsert_sql, col_values)
        conn.commit()

    # 更新 registry 統計
    registry.last_synced_at = datetime.utcnow()
    registry.row_count = (registry.row_count or 0) + 1
    db.session.commit()

    logger.info(f'SQL Sync: UPSERT → {table_name} (instance={form_instance.secure_code})')
    return True


# =============================================================================
# 向後相容（過渡期保留，新呼叫者應用 enqueue_sync_safe）
# =============================================================================

def sync_form_data_safe(form_instance, published_secure_code=None):
    """向後相容：改為寫入佇列"""
    return enqueue_sync_safe(form_instance, published_secure_code)
