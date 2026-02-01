"""
SQL ↔ form.io 轉換核心
將 PostgreSQL 資料表結構轉為 form.io schema，並處理 layout 合併
"""

import re
from datetime import date, datetime

# PostgreSQL 型別 → form.io 元件型別對應
TYPE_MAP = {
    'character varying': 'textfield',
    'varchar': 'textfield',
    'text': 'textarea',
    'integer': 'number',
    'bigint': 'number',
    'smallint': 'number',
    'numeric': 'number',
    'real': 'number',
    'double precision': 'number',
    'boolean': 'checkbox',
    'date': 'day',
    'timestamp without time zone': 'datetime',
    'timestamp with time zone': 'datetime',
    'jsonb': 'textarea',
    'json': 'textarea',
}

# 不進入 form 的欄位
AUTO_SKIP_COLUMNS = {'id'}

# form 中設為 disabled 的欄位
AUTO_READONLY_COLUMNS = {'created_at', 'updated_at'}

# form.io builder 中非資料欄位的元件類型
NON_DATA_COMPONENTS = {
    'panel', 'columns', 'fieldset', 'tabs', 'table',
    'well', 'htmlelement', 'content', 'button',
}


def get_table_columns(cursor, table_name):
    """查詢資料表欄位結構"""
    cursor.execute("""
        SELECT column_name, data_type, is_nullable,
               character_maximum_length, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
    """, (table_name,))
    return cursor.fetchall()


def column_to_component(col):
    """單欄位 → form.io component"""
    col_name, data_type, is_nullable, max_length, col_default = col

    if col_name in AUTO_SKIP_COLUMNS:
        return None

    formio_type = TYPE_MAP.get(data_type, 'textfield')

    component = {
        'type': formio_type,
        'key': col_name,
        'label': col_name,
        'input': True,
        'tableView': True,
    }

    # required
    if is_nullable == 'NO' and col_default is None:
        component['validate'] = {'required': True}

    # maxLength
    if max_length and formio_type in ('textfield', 'textarea'):
        component.setdefault('validate', {})['maxLength'] = max_length

    # disabled (唯讀欄位)
    if col_name in AUTO_READONLY_COLUMNS:
        component['disabled'] = True

    # day 元件特殊設定
    if formio_type == 'day':
        component['dayFirst'] = False

    return component


def columns_to_formio(columns):
    """整組欄位 → form.io schema"""
    components = []
    for col in columns:
        comp = column_to_component(col)
        if comp:
            components.append(comp)
    return {'components': components}


def _get_all_keys(components):
    """遞迴取得所有 component 的 key"""
    keys = set()
    for comp in components:
        if comp.get('key') and comp.get('type') not in NON_DATA_COMPONENTS:
            keys.add(comp['key'])
        # 遞迴子元件
        for child_list_key in ('components', 'columns'):
            children = comp.get(child_list_key, [])
            if isinstance(children, list):
                for child in children:
                    if isinstance(child, dict):
                        if 'components' in child:
                            keys |= _get_all_keys(child['components'])
                        elif child.get('key'):
                            keys.add(child['key'])
    return keys


def _find_component_by_key(components, key):
    """在 component 樹中找指定 key"""
    for comp in components:
        if comp.get('key') == key:
            return comp
        for child_list_key in ('components', 'columns'):
            children = comp.get(child_list_key, [])
            if isinstance(children, list):
                for child in children:
                    if isinstance(child, dict):
                        if 'components' in child:
                            found = _find_component_by_key(child['components'], key)
                            if found:
                                return found
                        elif child.get('key') == key:
                            return child
    return None


def merge_layout(saved_layout, auto_schema, sql_column_keys):
    """
    合併 saved layout + auto schema
    - 保留 saved layout 的排版/順序
    - 偵測 SQL 新增欄位 → 附加到末尾
    - 偵測使用者新增的非 SQL 欄位 → 警告
    """
    warnings = []

    if not saved_layout or not saved_layout.get('components'):
        return auto_schema, warnings

    saved_components = saved_layout['components']
    saved_keys = _get_all_keys(saved_components)

    auto_components = auto_schema['components']
    auto_keys = {c['key'] for c in auto_components}

    # 偵測 SQL 新增欄位 (auto 有但 saved 沒有)
    new_keys = auto_keys - saved_keys
    appended = []
    for comp in auto_components:
        if comp['key'] in new_keys:
            appended.append(comp)
            warnings.append(f"新增 SQL 欄位已自動附加: {comp['key']}")

    # 偵測使用者自行新增的非 SQL input 欄位
    for key in saved_keys:
        if key not in sql_column_keys and key != 'submit':
            comp = _find_component_by_key(saved_components, key)
            if comp and comp.get('type') not in NON_DATA_COMPONENTS:
                warnings.append(f"欄位 '{key}' 不存在於 SQL 資料表，資料不會寫入資料庫")

    result_components = list(saved_components)
    if appended:
        result_components.extend(appended)

    return {'components': result_components}, warnings


def extract_data_from_submission(submission, sql_column_keys):
    """從 form.io submission 過濾出 SQL 欄位值"""
    data = {}
    for key, value in submission.items():
        if key in sql_column_keys and key not in AUTO_SKIP_COLUMNS and key not in AUTO_READONLY_COLUMNS:
            data[key] = value
    return data


def normalize_date_value(value):
    """
    form.io day 元件格式轉換
    支援: MM/DD/YYYY, {month,day,year} dict, YYYY-MM-DD (直接回傳)
    """
    if not value:
        return None

    # 已是 YYYY-MM-DD
    if isinstance(value, str) and re.match(r'^\d{4}-\d{2}-\d{2}$', value):
        return value

    # MM/DD/YYYY 格式
    if isinstance(value, str) and re.match(r'^\d{2}/\d{2}/\d{4}$', value):
        parts = value.split('/')
        return f"{parts[2]}-{parts[0]}-{parts[1]}"

    # dict: {month: '03', day: '15', year: '2024'}
    if isinstance(value, dict):
        y = value.get('year', '')
        m = value.get('month', '')
        d = value.get('day', '')
        if y and m and d:
            return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        return None

    # 嘗試其他字串格式
    if isinstance(value, str):
        value = value.strip()
        if not value or value == '00/00/0000':
            return None
        # 嘗試解析
        for fmt in ('%Y-%m-%dT%H:%M:%S', '%m/%d/%Y', '%d/%m/%Y'):
            try:
                dt = datetime.strptime(value, fmt)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                continue

    return None
