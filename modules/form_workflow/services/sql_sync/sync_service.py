"""
SQL Sync — UPSERT 同步服務

將 form_instance.form_data (JSONB) UPSERT 到對應的 SQL 表。
sync 失敗不影響主流程（JSONB 是 primary，SQL 只是副本）。
"""
import logging
from datetime import datetime

from psycopg2 import sql as psql

from .pool import get_conn, is_pool_ready
from .converter import normalize_value

logger = logging.getLogger(__name__)


def _find_registry(form_instance, published_secure_code=None):
    """
    找到 form_instance 對應的 FwSqlFormRegistry

    查找順序:
    1. published_secure_code 直接查
    2. form_instance.published_secure_code 查

    Returns:
        FwSqlFormRegistry or None
    """
    from ...models.sql_form_registry import FwSqlFormRegistry

    psc = published_secure_code or getattr(form_instance, 'published_secure_code', None)
    if not psc:
        return None

    return FwSqlFormRegistry.query.filter_by(
        published_secure_code=psc,
        status='active',
    ).first()


def sync_form_data(form_instance, published_secure_code=None):
    """
    將 form_instance.form_data UPSERT 到對應的 SQL 表

    流程:
    1. 查 FwSqlFormRegistry 找到對應的 table_name
    2. 從 column_mapping 取得欄位對應
    3. 從 form_data 抽取 SQL 欄位值（型別轉換）
    4. INSERT ... ON CONFLICT (form_instance_secure_code) DO UPDATE

    Args:
        form_instance: FwFormInstance 實例
        published_secure_code: 發行版本 secure_code（可選，優先於 form_instance.published_secure_code）

    Returns:
        bool: 是否成功
    """
    if not is_pool_ready():
        logger.debug('SQL Sync: 連線池未初始化，跳過 sync')
        return False

    registry = _find_registry(form_instance, published_secure_code)
    if not registry:
        logger.debug(f'SQL Sync: 找不到 registry (published_sc={published_secure_code})')
        return False

    table_name = registry.table_name
    column_mapping = registry.column_mapping or {}
    form_data = form_instance.form_data or {}

    # 準備固定欄位
    fixed_data = {
        'form_instance_secure_code': form_instance.secure_code,
        'org_secure_code': form_instance.org_secure_code,
        'applicant_secure_code': getattr(form_instance, 'applicant_secure_code', None),
        'applicant_name': getattr(form_instance, 'applicant_name', None),
        'status': getattr(form_instance, 'status', None),
        'serial_number': getattr(form_instance, 'serial_number', None),
        'submitted_at': getattr(form_instance, 'submitted_at', None),
        'synced_at': datetime.utcnow(),
    }

    # 準備動態欄位（從 form_data 抽取，根據 column_mapping 轉換）
    dynamic_data = {}
    for field_key, col_info in column_mapping.items():
        if field_key in form_data:
            pg_type = col_info.get('pg_type', 'TEXT')
            dynamic_data[field_key] = normalize_value(form_data[field_key], pg_type)

    # 合併所有欄位
    all_data = {**fixed_data, **dynamic_data}

    # 建立 UPSERT SQL
    col_names = list(all_data.keys())
    col_values = [all_data[k] for k in col_names]

    insert_cols = psql.SQL(', ').join([psql.Identifier(c) for c in col_names])
    insert_vals = psql.SQL(', ').join([psql.Placeholder()] * len(col_names))

    # ON CONFLICT 更新除了 form_instance_secure_code 以外的所有欄位
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

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(upsert_sql, col_values)
        conn.commit()

    # 更新 registry 的 row_count 和 last_synced_at
    from app import db
    registry.last_synced_at = datetime.utcnow()
    registry.row_count = (registry.row_count or 0) + 1  # 簡單累加，不完全精確
    db.session.commit()

    logger.info(
        f'SQL Sync: UPSERT 成功 → {table_name} '
        f'(instance={form_instance.secure_code})'
    )
    return True


def sync_form_data_safe(form_instance, published_secure_code=None):
    """
    安全版本 — try/except 包裝，SQL sync 失敗不影響主流程。
    失敗時 log warning，不拋例外。

    Args:
        form_instance: FwFormInstance 實例
        published_secure_code: 發行版本 secure_code

    Returns:
        bool: 是否成功
    """
    try:
        return sync_form_data(form_instance, published_secure_code)
    except Exception as e:
        logger.warning(
            f'SQL Sync: 同步失敗 (instance={form_instance.secure_code}): {e}',
            exc_info=True,
        )
        return False
