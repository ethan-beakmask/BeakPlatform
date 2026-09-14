"""
Schema Reader -- 讀取企業 DB 實際表結構

從 information_schema.columns 讀取欄位定義，
並提供 PG column -> spec field 反向轉換。
"""
import logging

from .pool import get_org_conn

logger = logging.getLogger(__name__)

# 系統固定欄位，不納入 spec
_SYSTEM_COLUMNS = {
    'id', 'form_instance_secure_code', 'row_index',
}

# PostgreSQL data_type -> FormIO type 反向映射
PG_TO_FORMIO = {
    'character varying': 'textfield',
    'text': 'textarea',
    'numeric': 'number',
    'integer': 'number',
    'bigint': 'number',
    'smallint': 'number',
    'boolean': 'checkbox',
    'date': 'day',
    'timestamp without time zone': 'datetime',
    'timestamp with time zone': 'datetime',
    'jsonb': 'textarea',  # 預設，datagrid 需檢查 column_mapping
    'json': 'textarea',
    'bytea': 'textfield',  # PII，需從 column_mapping 還原
    'double precision': 'number',
    'real': 'number',
}


def list_tables(org_sc):
    """
    列出企業 DB 中 public schema 所有使用者表

    Args:
        org_sc: 企業 secure_code

    Returns:
        list of dict: [{'table_name', 'row_estimate'}]
    """
    with get_org_conn(org_sc, role='sync') as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT c.relname AS table_name,
                       c.reltuples::bigint AS row_estimate
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relkind = 'r'
                ORDER BY c.relname
            """)
            rows = cur.fetchall()

    return [{'table_name': r[0], 'row_estimate': max(r[1], 0)} for r in rows]


def read_table_columns(org_sc, table_name):
    """
    從 information_schema.columns 讀取實際表結構

    Args:
        org_sc: 企業 secure_code
        table_name: SQL 表名

    Returns:
        list of dict: [{'column_name', 'data_type', 'character_maximum_length',
                        'is_nullable', 'column_default', 'ordinal_position'}]
    """
    with get_org_conn(org_sc, role='sync') as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT column_name, data_type, character_maximum_length,
                       is_nullable, column_default, ordinal_position,
                       udt_name
                FROM information_schema.columns
                WHERE table_name = %s
                  AND table_schema = 'public'
                ORDER BY ordinal_position
            """, (table_name,))
            rows = cur.fetchall()

    columns = []
    for row in rows:
        col_name = row[0]
        if col_name in _SYSTEM_COLUMNS:
            continue
        columns.append({
            'column_name': col_name,
            'data_type': row[1],
            'character_maximum_length': row[2],
            'is_nullable': row[3],
            'column_default': row[4],
            'ordinal_position': row[5],
            'udt_name': row[6],
        })

    return columns


def pg_columns_to_spec_fields(columns, column_mapping=None):
    """
    PG column info -> spec fields list

    Args:
        columns: read_table_columns() 的回傳值
        column_mapping: FwSqlFormRegistry.column_mapping (用於還原 is_pii 和 formio_type)

    Returns:
        list of spec field dicts
    """
    column_mapping = column_mapping or {}
    fields = []

    for i, col in enumerate(columns):
        col_name = col['column_name']
        data_type = col['data_type']
        max_len = col['character_maximum_length']

        # 從 column_mapping 還原 metadata
        cm = column_mapping.get(col_name, {})
        if not isinstance(cm, dict):
            cm = {}

        is_pii = cm.get('is_pii', False)
        orig_pg_type = cm.get('pg_type', '')
        formio_type_hint = cm.get('formio_type', '')

        # 推導 pg_type
        if is_pii and data_type == 'bytea':
            # PII 欄位：還原原始 pg_type
            pg_type = orig_pg_type or 'VARCHAR(500)'
        elif data_type == 'character varying' and max_len:
            pg_type = f'VARCHAR({max_len})'
        elif data_type == 'numeric':
            pg_type = orig_pg_type or 'NUMERIC'
        else:
            pg_type = orig_pg_type or data_type.upper()

        # 推導 formio_type
        if formio_type_hint:
            formio_type = formio_type_hint
        elif is_pii:
            formio_type = PG_TO_FORMIO.get(orig_pg_type.lower().split('(')[0] if orig_pg_type else '', 'textfield')
        else:
            formio_type = PG_TO_FORMIO.get(data_type, 'textfield')

        # 特殊處理 JSONB: 檢查 column_mapping 判斷是否是 datagrid
        if data_type == 'jsonb' and not formio_type_hint:
            if cm.get('is_grid', False) or orig_pg_type == 'JSONB':
                formio_type = 'textarea'  # 預設為 textarea，除非有明確標記

        constraints = {
            'required': False,
            'maxLength': max_len if data_type == 'character varying' else None,
            'minLength': None,
            'min': None,
            'max': None,
            'pattern': None,
            'customValidation': None,
        }

        fields.append({
            'field_key': col_name,
            'label': cm.get('label', col_name),
            'formio_type': formio_type,
            'pg_type': pg_type,
            'constraints': constraints,
            'is_pii': is_pii,
            'description': '',
            'default_value': None,
            'options': None,
            'grid_children': None,
            'sort_order': i,
        })

    return fields
