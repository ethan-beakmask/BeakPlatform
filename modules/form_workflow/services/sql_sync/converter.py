"""
SQL Sync — form.io → PostgreSQL 型別轉換器

方向：form.io schema → SQL CREATE TABLE DDL
（與 POC 的 converter.py 方向相反：POC 是 SQL → form.io）
"""
import re
import logging
from datetime import datetime

from psycopg2 import sql

logger = logging.getLogger(__name__)

# form.io type → PostgreSQL type
FORMIO_TO_PG = {
    'textfield': 'VARCHAR(500)',
    'textarea': 'TEXT',
    'number': 'NUMERIC',
    'checkbox': 'BOOLEAN',
    'day': 'DATE',
    'datetime': 'TIMESTAMP',
    'email': 'VARCHAR(200)',
    'phoneNumber': 'VARCHAR(50)',
    'select': 'VARCHAR(500)',
    'radio': 'VARCHAR(200)',
    'selectboxes': 'JSONB',
    'file': 'JSONB',
    'signature': 'TEXT',
    'hidden': 'TEXT',
    'currency': 'NUMERIC(15,2)',
    'url': 'VARCHAR(1000)',
    'tags': 'JSONB',
}

# 不需同步的元件類型（版面元件、按鈕等）
SKIP_TYPES = {
    'panel', 'columns', 'fieldset', 'tabs', 'table',
    'well', 'htmlelement', 'content', 'button',
}


def schema_to_columns(form_schema):
    """
    form.io schema → [(field_key, pg_type, nullable)] 列表

    遞迴處理 components（含巢狀 panel/columns/fieldset/tabs 等容器元件）。
    只抽取資料欄位，跳過版面元件。

    Args:
        form_schema: form.io schema dict，含 'components' key

    Returns:
        list of (field_key, pg_type, nullable) tuples
    """
    columns = []
    seen_keys = set()

    def _extract(components):
        for comp in (components or []):
            comp_type = comp.get('type', '')

            # 容器元件：遞迴子元件
            if comp_type in SKIP_TYPES or 'components' in comp:
                _extract(comp.get('components', []))
                # columns 元件的子欄位在 columns[].components 裡
                for col in comp.get('columns', []):
                    if isinstance(col, dict):
                        _extract(col.get('components', []))
                # tabs 的 components 可能是巢狀的
                continue

            key = comp.get('key')
            if not key or key in seen_keys:
                continue
            if comp_type in SKIP_TYPES:
                continue

            seen_keys.add(key)

            # 決定 PG 型別
            pg_type = FORMIO_TO_PG.get(comp_type, 'TEXT')

            # 是否 required
            validate = comp.get('validate', {})
            nullable = not validate.get('required', False)

            # PII 標記（Phase 2 加密用，由表單設計者在欄位屬性勾選）
            is_pii = bool(comp.get('properties', {}).get('pii', False))

            columns.append((key, pg_type, nullable, is_pii))

    _extract(form_schema.get('components', []))
    return columns


def build_column_mapping(columns):
    """
    從 columns 列表建立 column_mapping dict（存入 FwSqlFormRegistry）

    Returns:
        dict: {field_key: {'pg_type': '...', 'nullable': True/False, 'is_pii': False}}
    """
    mapping = {}
    for key, pg_type, nullable, *rest in columns:
        is_pii = rest[0] if rest else False
        mapping[key] = {
            'pg_type': pg_type,
            'nullable': nullable,
            'is_pii': is_pii,
        }
    return mapping


def build_create_table_sql(table_name, columns):
    """
    產生 CREATE TABLE DDL

    使用 psycopg2.sql 安全拼接表名和欄位名，防止 SQL injection。

    固定欄位:
    - id SERIAL PRIMARY KEY
    - form_instance_secure_code VARCHAR(32) NOT NULL UNIQUE

    動態欄位: 從 columns 參數產生

    Args:
        table_name: SQL 表名（已驗證前綴）
        columns: [(field_key, pg_type, nullable)] 列表

    Returns:
        psycopg2.sql.Composed: 可安全執行的 SQL
    """
    # 固定欄位定義
    parts = [
        sql.SQL('CREATE TABLE IF NOT EXISTS {} (').format(
            sql.Identifier(table_name)
        ),
        sql.SQL('  id SERIAL PRIMARY KEY,'),
        sql.SQL('  form_instance_secure_code VARCHAR(32) NOT NULL UNIQUE,'),
    ]

    # 動態欄位
    for i, (key, pg_type, nullable, *_rest) in enumerate(columns):
        null_str = '' if nullable else ' NOT NULL'
        # 最後一個欄位不加逗號
        is_last = (i == len(columns) - 1)
        comma = '' if is_last else ','
        parts.append(
            sql.SQL('  {} {}{}{}').format(
                sql.Identifier(key),
                sql.SQL(pg_type),
                sql.SQL(null_str),
                sql.SQL(comma),
            )
        )

    parts.append(sql.SQL(')'))

    return sql.SQL('\n').join(parts)


def build_create_table_ddl_text(table_name, columns):
    """
    產生 CREATE TABLE DDL 的純文字版本（用於存入 registry.create_ddl）

    Args:
        table_name: SQL 表名
        columns: [(field_key, pg_type, nullable)] 列表

    Returns:
        str: DDL 文字
    """
    lines = [f'CREATE TABLE IF NOT EXISTS "{table_name}" (']
    lines.append('  id SERIAL PRIMARY KEY,')
    lines.append('  form_instance_secure_code VARCHAR(32) NOT NULL UNIQUE,')

    for i, (key, pg_type, nullable, *_rest) in enumerate(columns):
        null_str = '' if nullable else ' NOT NULL'
        comma = '' if i == len(columns) - 1 else ','
        lines.append(f'  "{key}" {pg_type}{null_str}{comma}')

    lines.append(')')
    return '\n'.join(lines)


# =====================================================
# form_data 值轉換（form.io → SQL 寫入值）
# =====================================================

def normalize_date_value(value):
    """
    form.io day 元件格式轉換
    支援: MM/DD/YYYY, {month,day,year} dict, YYYY-MM-DD (直接回傳)
    """
    if not value:
        return None

    if isinstance(value, str) and re.match(r'^\d{4}-\d{2}-\d{2}$', value):
        return value

    if isinstance(value, str) and re.match(r'^\d{2}/\d{2}/\d{4}$', value):
        parts = value.split('/')
        return f"{parts[2]}-{parts[0]}-{parts[1]}"

    if isinstance(value, dict):
        y = value.get('year', '')
        m = value.get('month', '')
        d = value.get('day', '')
        if y and m and d:
            return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        return None

    if isinstance(value, str):
        value = value.strip()
        if not value or value == '00/00/0000':
            return None
        for fmt in ('%Y-%m-%dT%H:%M:%S', '%m/%d/%Y', '%d/%m/%Y'):
            try:
                dt = datetime.strptime(value, fmt)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                continue

    return None


def normalize_value(value, pg_type):
    """
    根據 PG 型別轉換 form_data 的值

    Args:
        value: form_data 中的原始值
        pg_type: PostgreSQL 型別字串

    Returns:
        轉換後的值
    """
    if value is None or value == '':
        return None

    pg_upper = pg_type.upper()

    if pg_upper == 'DATE':
        return normalize_date_value(value)

    if pg_upper == 'BOOLEAN':
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes')
        return bool(value)

    if pg_upper.startswith('NUMERIC'):
        try:
            return float(value) if value else None
        except (ValueError, TypeError):
            return None

    if pg_upper == 'JSONB':
        import json
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return value

    if pg_upper == 'TIMESTAMP':
        if isinstance(value, str):
            for fmt in ('%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S'):
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
        return value

    # VARCHAR / TEXT: 直接回傳字串
    return str(value) if value is not None else None
