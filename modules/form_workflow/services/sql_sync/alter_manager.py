"""
Alter Manager -- Spec->SQL ALTER TABLE 管理

比對現有 column_mapping vs 新 spec fields，
產生 ALTER 計劃並執行。支援 ADD/ALTER TYPE/DROP COLUMN。
"""
import logging
import secrets
import re

from psycopg2 import sql as psql

from .pool import get_org_conn

logger = logging.getLogger(__name__)

# 用於儲存 token -> plan 的暫存（簡易方式）
_plan_tokens = {}


def _derive_pg_type(spec_field):
    """從 spec field 推導 pg_type"""
    pg = spec_field.get('pg_type')
    if pg:
        return pg
    from .converter import FORMIO_TO_PG
    return FORMIO_TO_PG.get(spec_field.get('formio_type', 'textfield'), 'TEXT')


def _resolve_actual_type(pg_type, is_pii):
    """PII -> BYTEA"""
    return 'BYTEA' if is_pii else pg_type


def _normalize_pg_type(pg_type):
    """正規化 pg_type 用於比對"""
    if not pg_type:
        return ''
    t = pg_type.upper().strip()
    # TIMESTAMP WITH TIME ZONE -> TIMESTAMP
    t = t.replace('WITHOUT TIME ZONE', '').replace('WITH TIME ZONE', '').strip()
    return t


def _is_safe_type_change(old_type, new_type):
    """判斷型別變更是否安全"""
    old = _normalize_pg_type(old_type)
    new = _normalize_pg_type(new_type)

    if old == new:
        return True

    # VARCHAR(n) -> VARCHAR(m) 且 m > n
    old_m = re.match(r'VARCHAR\((\d+)\)', old)
    new_m = re.match(r'VARCHAR\((\d+)\)', new)
    if old_m and new_m:
        return int(new_m.group(1)) >= int(old_m.group(1))

    # VARCHAR -> TEXT
    if old.startswith('VARCHAR') and new == 'TEXT':
        return True

    # NUMERIC -> NUMERIC(p,s) 或 NUMERIC(p,s) -> NUMERIC（精度增加）
    if old.startswith('NUMERIC') and new.startswith('NUMERIC'):
        # 簡化處理：同為 NUMERIC 家族視為安全
        return True

    return False


def _check_column_has_data(org_sc, table_name, column_name):
    """檢查欄位是否有非 NULL 資料"""
    with get_org_conn(org_sc, role='sync') as conn:
        with conn.cursor() as cur:
            cur.execute(
                psql.SQL("SELECT COUNT(*) FROM {} WHERE {} IS NOT NULL").format(
                    psql.Identifier(table_name),
                    psql.Identifier(column_name),
                ),
            )
            count = cur.fetchone()[0]
    return count


def compute_alter_plan(current_mapping, new_spec_fields, org_sc, table_name):
    """
    比對現有 column_mapping vs 新 spec fields，產生 ALTER 計劃

    Args:
        current_mapping: FwSqlFormRegistry.column_mapping dict
        new_spec_fields: spec fields list
        org_sc: 企業 secure_code
        table_name: SQL 表名

    Returns:
        dict: {add_columns, alter_types, drop_columns, warnings, risk_level, confirmation_token}
    """
    current_mapping = current_mapping or {}
    # 過濾 metadata key（_ 開頭）
    current_keys = {k for k in current_mapping if not k.startswith('_')}
    new_map = {f['field_key']: f for f in (new_spec_fields or []) if f.get('field_key')}
    new_keys = set(new_map.keys())

    add_columns = []
    alter_types = []
    drop_columns = []
    warnings = []

    # 新增欄位
    for key in (new_keys - current_keys):
        sf = new_map[key]
        pg_type = _derive_pg_type(sf)
        is_pii = sf.get('is_pii', False)
        add_columns.append({
            'key': key,
            'pg_type': _resolve_actual_type(pg_type, is_pii),
            'original_pg_type': pg_type,
            'is_pii': is_pii,
        })

    # 型別變更
    for key in (current_keys & new_keys):
        cm = current_mapping[key]
        if not isinstance(cm, dict):
            continue
        sf = new_map[key]

        old_pg = cm.get('pg_type', '')
        old_pii = cm.get('is_pii', False)
        new_pg = _derive_pg_type(sf)
        new_pii = sf.get('is_pii', False)

        old_actual = _resolve_actual_type(old_pg, old_pii)
        new_actual = _resolve_actual_type(new_pg, new_pii)

        if _normalize_pg_type(old_actual) != _normalize_pg_type(new_actual):
            safe = _is_safe_type_change(old_actual, new_actual)
            alter_types.append({
                'key': key,
                'old_type': old_actual,
                'new_type': new_actual,
                'safe': safe,
            })
            if not safe:
                warnings.append(f'欄位 "{key}" 型別變更 {old_actual} -> {new_actual} 可能導致資料遺失')

    # 刪除欄位
    for key in (current_keys - new_keys):
        row_count = 0
        try:
            row_count = _check_column_has_data(org_sc, table_name, key)
        except Exception as e:
            warnings.append(f'無法檢查欄位 "{key}" 資料量: {e}')

        drop_columns.append({
            'key': key,
            'current_type': current_mapping[key].get('pg_type', '') if isinstance(current_mapping[key], dict) else '',
            'row_count_with_data': row_count,
        })
        if row_count > 0:
            warnings.append(f'欄位 "{key}" 有 {row_count} 筆非 NULL 資料，DROP 將永久刪除')

    # 風險等級
    risk_level = 'low'
    if alter_types:
        has_unsafe = any(not a['safe'] for a in alter_types)
        risk_level = 'high' if has_unsafe else 'medium'
    if drop_columns:
        has_data = any(d['row_count_with_data'] > 0 for d in drop_columns)
        risk_level = 'critical' if has_data else max(risk_level, 'high', key=lambda x: ['low', 'medium', 'high', 'critical'].index(x))

    token = secrets.token_urlsafe(32)
    plan = {
        'add_columns': add_columns,
        'alter_types': alter_types,
        'drop_columns': drop_columns,
        'warnings': warnings,
        'risk_level': risk_level,
        'confirmation_token': token,
    }

    _plan_tokens[token] = {
        'plan': plan,
        'table_name': table_name,
        'org_sc': org_sc,
    }

    return plan


def execute_alter_plan(org_sc, table_name, plan, confirm_token, confirm_table_name=None):
    """
    執行 ALTER TABLE

    Args:
        org_sc: 企業 secure_code
        table_name: SQL 表名
        plan: compute_alter_plan() 回傳的計劃
        confirm_token: 確認 token
        confirm_table_name: critical 風險需輸入表名確認

    Returns:
        dict: {success, executed_statements, new_column_mapping}

    Raises:
        ValueError: token 不合法或確認失敗
    """
    # 驗證 token
    stored = _plan_tokens.pop(confirm_token, None)
    if not stored:
        raise ValueError('confirm_token 無效或已過期')

    if stored['table_name'] != table_name or stored['org_sc'] != org_sc:
        raise ValueError('confirm_token 與目標表不匹配')

    # critical 風險需要輸入表名確認
    if plan.get('risk_level') == 'critical':
        if not confirm_table_name or confirm_table_name != table_name:
            raise ValueError(f'高風險操作需輸入表名「{table_name}」確認')

    executed = []

    with get_org_conn(org_sc, role='admin') as conn:
        with conn.cursor() as cur:
            # SAVEPOINT
            cur.execute("SAVEPOINT alter_plan")

            try:
                # ADD COLUMN
                for col in plan.get('add_columns', []):
                    stmt = psql.SQL("ALTER TABLE {} ADD COLUMN {} {}").format(
                        psql.Identifier(table_name),
                        psql.Identifier(col['key']),
                        psql.SQL(col['pg_type']),
                    )
                    cur.execute(stmt)
                    executed.append(f"ADD COLUMN {col['key']} {col['pg_type']}")

                # ALTER TYPE
                for alt in plan.get('alter_types', []):
                    stmt = psql.SQL(
                        "ALTER TABLE {} ALTER COLUMN {} TYPE {} USING {}::{}"
                    ).format(
                        psql.Identifier(table_name),
                        psql.Identifier(alt['key']),
                        psql.SQL(alt['new_type']),
                        psql.Identifier(alt['key']),
                        psql.SQL(alt['new_type']),
                    )
                    cur.execute(stmt)
                    executed.append(f"ALTER COLUMN {alt['key']} TYPE {alt['new_type']}")

                # DROP COLUMN
                for drop in plan.get('drop_columns', []):
                    stmt = psql.SQL("ALTER TABLE {} DROP COLUMN {}").format(
                        psql.Identifier(table_name),
                        psql.Identifier(drop['key']),
                    )
                    cur.execute(stmt)
                    executed.append(f"DROP COLUMN {drop['key']}")

                cur.execute("RELEASE SAVEPOINT alter_plan")
                conn.commit()

            except Exception as e:
                cur.execute("ROLLBACK TO SAVEPOINT alter_plan")
                conn.commit()
                logger.error(f'ALTER TABLE 失敗，已回滾: {e}')
                raise

    # 計算新的 column_mapping
    # 讀取 plan 中的 spec fields 資訊重建 mapping 不太直接
    # 改為從 schema_reader 讀取實際表結構
    try:
        from .schema_reader import read_table_columns
        new_columns = read_table_columns(org_sc, table_name)
        new_mapping = {}
        for col in new_columns:
            col_name = col['column_name']
            data_type = col['data_type']
            max_len = col['character_maximum_length']

            if data_type == 'character varying' and max_len:
                pg_type = f'VARCHAR({max_len})'
            else:
                pg_type = data_type.upper()

            # 從 add_columns 中取得 is_pii 資訊
            is_pii = False
            for add in plan.get('add_columns', []):
                if add['key'] == col_name:
                    is_pii = add.get('is_pii', False)
                    pg_type = add.get('original_pg_type', pg_type)
                    break

            new_mapping[col_name] = {
                'pg_type': pg_type,
                'nullable': col['is_nullable'] == 'YES',
                'is_pii': is_pii,
            }
    except Exception as e:
        logger.warning(f'讀取新表結構失敗（ALTER 已執行）: {e}')
        new_mapping = None

    return {
        'success': True,
        'executed_statements': executed,
        'new_column_mapping': new_mapping,
    }
