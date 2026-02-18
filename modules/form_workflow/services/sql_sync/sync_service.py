"""
SQL Sync — 佇列式同步服務

表單提交/簽核時呼叫 enqueue_sync()，寫入 fw_sync_queue。
實際 UPSERT 由背景 Worker 處理。

也提供 execute_sync() 供 Worker 呼叫。
"""
import json
import os
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
# PII 加密工具
# =============================================================================

def _get_pii_passphrase():
    """取得 PII 加密密鑰"""
    passphrase = os.environ.get('SYNC_PII_PASSPHRASE')
    if not passphrase:
        raise RuntimeError('SYNC_PII_PASSPHRASE 環境變數未設定')
    return passphrase


def _build_value_placeholder(is_pii):
    """
    回傳欄位值的 SQL placeholder

    非 PII: %s
    PII:    pgp_sym_encrypt(%s::text, %s)
    """
    if is_pii:
        return psql.SQL('pgp_sym_encrypt(%s::text, %s)')
    return psql.Placeholder()


# =============================================================================
# 實際同步（Worker 呼叫）
# =============================================================================

def execute_sync(queue_item):
    """
    執行單筆同步任務

    由 Worker 呼叫，從 queue_item 中取得資訊，
    用 sync 低權限帳號 UPSERT 到企業 DB。
    PII 欄位使用 pgcrypto 加密寫入。

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

    # 檢查是否有任何 PII 欄位（跳過 _ 前綴的保留 metadata key）
    has_pii = any(
        col_info.get('is_pii', False)
        for key, col_info in column_mapping.items()
        if not key.startswith('_') and isinstance(col_info, dict)
    )
    # 子表中也可能有 PII
    if not has_pii:
        for key, col_info in column_mapping.items():
            if key.startswith('_') or not isinstance(col_info, dict):
                continue
            sub = col_info.get('sub_table')
            if sub:
                has_pii = any(
                    sc.get('is_pii', False)
                    for sc in sub.get('columns', {}).values()
                )
                if has_pii:
                    break

    passphrase = _get_pii_passphrase() if has_pii else None

    # 主表 UPSERT
    _upsert_main_table(
        table_name, column_mapping, form_data,
        form_instance.secure_code, queue_item.org_secure_code, passphrase,
    )

    # 子表同步
    _sync_sub_tables(
        column_mapping, form_data,
        form_instance.secure_code, queue_item.org_secure_code, passphrase,
    )

    # Approval 子表同步
    approval_table = column_mapping.get('_approval_table')
    if approval_table:
        _sync_approval_records(
            approval_table,
            form_instance.secure_code,
            queue_item.org_secure_code,
        )

    # 更新 registry 統計
    registry.last_synced_at = datetime.utcnow()
    registry.row_count = (registry.row_count or 0) + 1
    db.session.commit()

    logger.info(f'SQL Sync: UPSERT → {table_name} (instance={form_instance.secure_code})')
    return True


def _upsert_main_table(table_name, column_mapping, form_data,
                        instance_sc, org_sc, passphrase):
    """
    主表 UPSERT（含 PII 加密）
    """
    # 固定欄位
    col_names = ['form_instance_secure_code']
    col_values = [instance_sc]
    pii_flags = [False]

    # 動態欄位（跳過 _ 前綴的保留 metadata key）
    for field_key, col_info in column_mapping.items():
        if field_key.startswith('_') or not isinstance(col_info, dict):
            continue
        if field_key not in form_data:
            continue
        pg_type = col_info.get('pg_type', 'TEXT')
        is_pii = col_info.get('is_pii', False)
        value = normalize_value(form_data[field_key], pg_type)

        # PII 欄位需轉為字串傳入 pgp_sym_encrypt
        if is_pii and value is not None:
            value = str(value) if not isinstance(value, str) else value

        col_names.append(field_key)
        col_values.append(value)
        pii_flags.append(is_pii)

    # 構建 INSERT 部分
    insert_cols = psql.SQL(', ').join([psql.Identifier(c) for c in col_names])

    val_placeholders = []
    actual_values = []
    for val, is_pii in zip(col_values, pii_flags):
        if is_pii and val is not None:
            val_placeholders.append(psql.SQL('pgp_sym_encrypt(%s::text, %s)'))
            actual_values.append(val)
            actual_values.append(passphrase)
        elif is_pii and val is None:
            val_placeholders.append(psql.SQL('NULL'))
        else:
            val_placeholders.append(psql.Placeholder())
            actual_values.append(val)

    insert_vals = psql.SQL(', ').join(val_placeholders)

    # 構建 UPDATE SET 部分
    update_parts = []
    for i, col_name in enumerate(col_names):
        if col_name == 'form_instance_secure_code':
            continue
        update_parts.append(
            psql.SQL('{} = EXCLUDED.{}').format(
                psql.Identifier(col_name), psql.Identifier(col_name)
            )
        )

    update_set = psql.SQL(', ').join(update_parts)

    upsert_sql = psql.SQL(
        'INSERT INTO {} ({}) VALUES ({}) '
        'ON CONFLICT (form_instance_secure_code) DO UPDATE SET {}'
    ).format(
        psql.Identifier(table_name),
        insert_cols,
        insert_vals,
        update_set,
    )

    with get_org_conn(org_sc, role='sync') as conn:
        with conn.cursor() as cur:
            cur.execute(upsert_sql, actual_values)
        conn.commit()


def _sync_sub_tables(column_mapping, form_data, instance_sc, org_sc, passphrase):
    """
    同步 datagrid/editgrid 子表

    策略: DELETE + batch INSERT（同一 transaction）
    """
    for field_key, col_info in column_mapping.items():
        if field_key.startswith('_') or not isinstance(col_info, dict):
            continue
        sub = col_info.get('sub_table')
        if not sub:
            continue

        sub_table = sub.get('table_name')
        sub_columns = sub.get('columns', {})
        if not sub_table or not sub_columns:
            continue

        # 從 form_data 取 grid 陣列
        grid_data = form_data.get(field_key)
        if not isinstance(grid_data, list):
            grid_data = []

        with get_org_conn(org_sc, role='sync') as conn:
            with conn.cursor() as cur:
                # DELETE 舊 rows
                cur.execute(
                    psql.SQL('DELETE FROM {} WHERE form_instance_secure_code = %s').format(
                        psql.Identifier(sub_table)
                    ),
                    (instance_sc,)
                )

                # INSERT 新 rows
                if grid_data:
                    _batch_insert_sub_rows(
                        cur, sub_table, sub_columns, grid_data,
                        instance_sc, passphrase,
                    )

            conn.commit()

        logger.debug(
            f'SQL Sync: 子表 {sub_table} 同步 {len(grid_data)} 筆 '
            f'(instance={instance_sc})'
        )


def _batch_insert_sub_rows(cur, sub_table, sub_columns, grid_data,
                            instance_sc, passphrase):
    """
    批次插入子表 rows
    """
    # 固定欄位: form_instance_secure_code, row_index
    col_names = ['form_instance_secure_code', 'row_index']
    dynamic_keys = list(sub_columns.keys())
    col_names.extend(dynamic_keys)

    insert_cols = psql.SQL(', ').join([psql.Identifier(c) for c in col_names])

    # 預先建立 PII flags
    pii_map = {k: v.get('is_pii', False) for k, v in sub_columns.items()}
    type_map = {k: v.get('pg_type', 'TEXT') for k, v in sub_columns.items()}

    for row_idx, row_data in enumerate(grid_data):
        if not isinstance(row_data, dict):
            continue

        val_placeholders = []
        actual_values = []

        # form_instance_secure_code
        val_placeholders.append(psql.Placeholder())
        actual_values.append(instance_sc)

        # row_index
        val_placeholders.append(psql.Placeholder())
        actual_values.append(row_idx)

        # dynamic columns
        for key in dynamic_keys:
            raw_val = row_data.get(key)
            pg_type = type_map[key]
            is_pii = pii_map[key]
            value = normalize_value(raw_val, pg_type)

            if is_pii and value is not None:
                value = str(value) if not isinstance(value, str) else value
                val_placeholders.append(psql.SQL('pgp_sym_encrypt(%s::text, %s)'))
                actual_values.append(value)
                actual_values.append(passphrase)
            elif is_pii and value is None:
                val_placeholders.append(psql.SQL('NULL'))
            else:
                val_placeholders.append(psql.Placeholder())
                actual_values.append(value)

        insert_vals = psql.SQL(', ').join(val_placeholders)

        insert_sql = psql.SQL('INSERT INTO {} ({}) VALUES ({})').format(
            psql.Identifier(sub_table),
            insert_cols,
            insert_vals,
        )
        cur.execute(insert_sql, actual_values)


# =============================================================================
# Approval 子表同步（Phase 3）
# =============================================================================

# approval 欄位名列表（與 FwApprovalRecord 屬性對應）
_APPROVAL_FIELDS = [
    'form_instance_secure_code',
    'node_id',
    'node_name',
    'approver_secure_code',
    'approver_name',
    'approver_dept',
    'delegate_from_secure_code',
    'delegate_from_name',
    'action',
    'comment',
    'assigned_at',
    'acted_at',
]


def _sync_approval_records(approval_table, instance_sc, org_sc):
    """
    同步簽核記錄到 approval 子表

    策略: DELETE + INSERT（與 datagrid 子表一致）
    簽核意見為操作記錄，非 PII，不加密。

    Args:
        approval_table: approval 子表名
        instance_sc: form_instance_secure_code
        org_sc: org_secure_code
    """
    from ...models.approval_record import FwApprovalRecord

    # 查詢該表單的所有簽核記錄
    records = FwApprovalRecord.query.filter_by(
        form_instance_secure_code=instance_sc,
        is_deleted=False,
    ).order_by(FwApprovalRecord.assigned_at.asc()).all()

    col_ids = [psql.Identifier(c) for c in _APPROVAL_FIELDS]
    insert_cols = psql.SQL(', ').join(col_ids)
    placeholders = psql.SQL(', ').join([psql.Placeholder()] * len(_APPROVAL_FIELDS))

    with get_org_conn(org_sc, role='sync') as conn:
        with conn.cursor() as cur:
            # DELETE 舊 rows
            cur.execute(
                psql.SQL(
                    'DELETE FROM {} WHERE form_instance_secure_code = %s'
                ).format(psql.Identifier(approval_table)),
                (instance_sc,)
            )

            # INSERT 新 rows
            if records:
                insert_sql = psql.SQL(
                    'INSERT INTO {} ({}) VALUES ({})'
                ).format(
                    psql.Identifier(approval_table),
                    insert_cols,
                    placeholders,
                )
                for rec in records:
                    values = [
                        rec.form_instance_secure_code,
                        rec.node_id,
                        rec.node_name,
                        rec.approver_secure_code,
                        rec.approver_name,
                        rec.approver_dept,
                        rec.delegate_from_secure_code,
                        rec.delegate_from_name,
                        rec.action,
                        rec.comment,
                        rec.assigned_at,
                        rec.acted_at,
                    ]
                    cur.execute(insert_sql, values)

        conn.commit()

    logger.debug(
        f'SQL Sync: approval 子表 {approval_table} 同步 {len(records)} 筆 '
        f'(instance={instance_sc})'
    )


# =============================================================================
# 向後相容（過渡期保留，新呼叫者應用 enqueue_sync_safe）
# =============================================================================

def sync_form_data_safe(form_instance, published_secure_code=None):
    """向後相容：改為寫入佇列"""
    return enqueue_sync_safe(form_instance, published_secure_code)
