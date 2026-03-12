"""
Spec SQL Table Service

在設計階段直接操作 org DB 中的 SQL Table：
- 列出表
- 從既有表匯入欄位定義到 spec
- 將 spec 欄位定義建立/更新到 SQL Table
"""
import secrets
import logging

from psycopg2 import sql as psql

logger = logging.getLogger(__name__)


def list_org_tables(org_sc):
    """
    列出企業 DB 中所有 public 表

    Args:
        org_sc: 企業 secure_code

    Returns:
        list of dict: [{'table_name', 'row_estimate'}]

    Raises:
        ValueError: org DB 未就緒
    """
    from modules.form_workflow.services.sql_sync.schema_reader import list_tables
    return list_tables(org_sc)


def compute_spec_table_name(spec, form_template=None):
    """
    計算 spec 對應的 SQL 表名

    命名規則:
    - 有表單綁定: {form_template.code.lower()}_v{spec.version}
    - 獨立規格: {spec.sql_table_code.lower()}_v{spec.version}

    Args:
        spec: FwFormFieldSpec instance
        form_template: FwFormTemplate instance (optional)

    Returns:
        str: 表名
    """
    if form_template and form_template.code:
        base_code = form_template.code.lower()
    elif spec.sql_table_code:
        base_code = spec.sql_table_code.lower()
    else:
        # 自動產生並儲存
        code = f'FT{secrets.token_hex(4).upper()}'
        spec.sql_table_code = code
        base_code = code.lower()

    return f'{base_code}_v{spec.version}'


def ensure_org_db(org_sc, org_id):
    """
    確認 org DB 已就緒，否則 provision

    Args:
        org_sc: 企業 secure_code
        org_id: 企業 id

    Returns:
        FwOrgDatabase instance

    Raises:
        RuntimeError: provision 失敗
    """
    from modules.form_workflow.services.sql_sync.org_db_manager import get_org_database, provision_org_database

    org_db = get_org_database(org_sc)
    if org_db:
        return org_db

    org_db = provision_org_database(org_id=org_id, org_secure_code=org_sc)
    if not org_db or not org_db.is_ready:
        raise RuntimeError(f'無法建立企業資料庫: org_sc={org_sc}')
    return org_db


def spec_fields_to_columns(spec_fields):
    """
    將 spec fields 轉為 converter 相容的 column tuples

    Args:
        spec_fields: list of spec field dicts

    Returns:
        list of (field_key, pg_type, nullable, is_pii) tuples
    """
    from modules.form_workflow.services.sql_sync.converter import FORMIO_TO_PG

    columns = []
    for sf in (spec_fields or []):
        key = sf.get('field_key')
        if not key:
            continue
        pg_type = sf.get('pg_type') or FORMIO_TO_PG.get(sf.get('formio_type', ''), 'TEXT')
        is_pii = bool(sf.get('is_pii', False))
        columns.append((key, pg_type, True, is_pii))
    return columns


def _read_existing_columns(org_sc, table_name):
    """
    讀取現有表的欄位結構（轉為比對用 dict）

    Returns:
        dict: {column_name: {'pg_type': ..., 'is_nullable': ...}}
    """
    from modules.form_workflow.services.sql_sync.schema_reader import read_table_columns

    raw_cols = read_table_columns(org_sc, table_name)
    result = {}
    for col in raw_cols:
        name = col['column_name']
        dt = col['data_type']
        max_len = col['character_maximum_length']
        if dt == 'character varying' and max_len:
            pg_type = f'VARCHAR({max_len})'
        elif dt == 'numeric':
            pg_type = 'NUMERIC'
        elif dt == 'timestamp without time zone':
            pg_type = 'TIMESTAMP'
        elif dt == 'timestamp with time zone':
            pg_type = 'TIMESTAMP WITH TIME ZONE'
        else:
            pg_type = dt.upper()
        result[name] = {
            'pg_type': pg_type,
            'is_nullable': col['is_nullable'] == 'YES',
        }
    return result


def _compute_alter_plan(existing_cols, spec_columns):
    """
    比較現有表與 spec 欄位，產生 ALTER 計劃

    Args:
        existing_cols: _read_existing_columns() 的回傳
        spec_columns: spec_fields_to_columns() 的回傳

    Returns:
        dict: {
            'add': [(key, pg_type, nullable, is_pii)],
            'modify': [(key, old_type, new_type)],
            'drop_candidates': [key],  # 只提示，不自動刪除
        }
    """
    from modules.form_workflow.services.sql_sync.converter import FORMIO_TO_PG

    plan = {'add': [], 'modify': [], 'drop_candidates': []}
    spec_keys = set()

    for (key, pg_type, nullable, is_pii) in spec_columns:
        spec_keys.add(key)
        # PII 欄位在 DB 中是 BYTEA
        actual_pg = 'BYTEA' if is_pii else pg_type

        if key not in existing_cols:
            plan['add'].append((key, pg_type, nullable, is_pii))
        else:
            old_type = existing_cols[key]['pg_type']
            if old_type.upper() != actual_pg.upper():
                plan['modify'].append((key, old_type, actual_pg))

    # 找出 spec 沒有但 DB 有的欄位（不含系統欄位）
    system_cols = {'id', 'form_instance_secure_code', 'row_index'}
    for col_name in existing_cols:
        if col_name not in spec_keys and col_name not in system_cols:
            plan['drop_candidates'].append(col_name)

    return plan


def _build_alter_sql(table_name, plan):
    """
    根據 alter plan 產生 ALTER TABLE SQL statements

    Returns:
        list of psycopg2.sql.Composed
    """
    stmts = []

    for (key, pg_type, nullable, is_pii) in plan['add']:
        actual_type = 'BYTEA' if is_pii else pg_type
        stmts.append(
            psql.SQL('ALTER TABLE {} ADD COLUMN {} {}').format(
                psql.Identifier(table_name),
                psql.Identifier(key),
                psql.SQL(actual_type),
            )
        )

    for (key, old_type, new_type) in plan['modify']:
        stmts.append(
            psql.SQL('ALTER TABLE {} ALTER COLUMN {} TYPE {} USING {}::{}').format(
                psql.Identifier(table_name),
                psql.Identifier(key),
                psql.SQL(new_type),
                psql.Identifier(key),
                psql.SQL(new_type),
            )
        )

    return stmts


def _build_alter_ddl_text(table_name, plan):
    """
    根據 alter plan 產生可讀的 DDL 文字

    Returns:
        str
    """
    lines = []
    for (key, pg_type, nullable, is_pii) in plan['add']:
        actual_type = 'BYTEA' if is_pii else pg_type
        lines.append(f'ALTER TABLE "{table_name}" ADD COLUMN "{key}" {actual_type};')

    for (key, old_type, new_type) in plan['modify']:
        lines.append(
            f'ALTER TABLE "{table_name}" ALTER COLUMN "{key}" '
            f'TYPE {new_type} USING "{key}"::{new_type};'
            f'  -- was: {old_type}'
        )

    if plan.get('drop_candidates'):
        lines.append('')
        lines.append('-- 以下欄位存在於 DB 但不在 spec 中（不會自動刪除）:')
        for col in plan['drop_candidates']:
            lines.append(f'-- DROP COLUMN "{col}"')

    return '\n'.join(lines)


def apply_spec_to_sql(org_sc, table_name, spec_fields, confirm=False):
    """
    將 spec 欄位定義建立或更新到 SQL Table

    Args:
        org_sc: 企業 secure_code
        table_name: 目標表名
        spec_fields: spec.fields list
        confirm: True=執行, False=僅預覽

    Returns:
        dict: {
            'action': 'create' | 'alter' | 'no_change',
            'table_name': str,
            'ddl': str (preview DDL text),
            'plan': dict (for alter),
            'executed': bool,
        }
    """
    from modules.form_workflow.services.sql_sync.table_manager import table_exists, validate_design_table_name
    from modules.form_workflow.services.sql_sync.converter import build_create_table_sql, build_create_table_ddl_text
    from modules.form_workflow.services.sql_sync.pool import get_org_conn

    validate_design_table_name(table_name)
    columns = spec_fields_to_columns(spec_fields)

    if not columns:
        raise ValueError('spec 沒有任何欄位')

    # 檢查表是否存在
    with get_org_conn(org_sc, role='admin') as conn:
        exists = table_exists(table_name, conn)

    if not exists:
        # CREATE TABLE
        ddl_text = build_create_table_ddl_text(table_name, columns)

        if confirm:
            with get_org_conn(org_sc, role='admin') as conn:
                create_sql = build_create_table_sql(table_name, columns)
                with conn.cursor() as cur:
                    cur.execute(create_sql)
                conn.commit()
            logger.info(f'SpecSQL: 建立表 {table_name} (org={org_sc})')

        return {
            'action': 'create',
            'table_name': table_name,
            'ddl': ddl_text,
            'plan': None,
            'executed': confirm,
        }
    else:
        # ALTER TABLE
        existing_cols = _read_existing_columns(org_sc, table_name)
        plan = _compute_alter_plan(existing_cols, columns)

        if not plan['add'] and not plan['modify']:
            return {
                'action': 'no_change',
                'table_name': table_name,
                'ddl': '-- 表結構與 spec 一致，無需變更',
                'plan': plan,
                'executed': False,
            }

        ddl_text = _build_alter_ddl_text(table_name, plan)

        if confirm:
            alter_stmts = _build_alter_sql(table_name, plan)
            with get_org_conn(org_sc, role='admin') as conn:
                with conn.cursor() as cur:
                    for stmt in alter_stmts:
                        cur.execute(stmt)
                conn.commit()
            logger.info(
                f'SpecSQL: ALTER 表 {table_name} '
                f'(add={len(plan["add"])}, modify={len(plan["modify"])})'
            )

        return {
            'action': 'alter',
            'table_name': table_name,
            'ddl': ddl_text,
            'plan': {
                'add': [{'key': k, 'pg_type': ('BYTEA' if p else t)}
                        for k, t, _, p in plan['add']],
                'modify': [{'key': k, 'old_type': o, 'new_type': n}
                           for k, o, n in plan['modify']],
                'drop_candidates': plan['drop_candidates'],
            },
            'executed': confirm,
        }
