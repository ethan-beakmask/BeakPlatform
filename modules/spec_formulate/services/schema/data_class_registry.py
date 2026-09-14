"""
Data Class Registry - 抽象資料類別與格式映射

data_class 是格式無關的抽象層，每個 data_class 定義了：
- 該類別在各格式下的預設型別/元件/格式
- 各格式是否支援該類別
- 格式專屬 facet 的預設值模板

使用方式：
    from .data_class_registry import DATA_CLASS_REGISTRY, get_facet_defaults

    reg = DATA_CLASS_REGISTRY['integer']
    pg_default = reg['facets']['postgresql']       # {'pg_type': 'INTEGER', ...}
    supported = reg['facets']['excel']['supported'] # True
"""


# 支援的格式名稱常數
FACET_POSTGRESQL = 'postgresql'
FACET_FORMIO = 'formio'
FACET_EXCEL = 'excel'
FACET_CSV = 'csv'

ALL_FACETS = [FACET_POSTGRESQL, FACET_FORMIO, FACET_EXCEL, FACET_CSV]


DATA_CLASS_REGISTRY = {
    # ── 文字類 ──
    'text': {
        'label': '文字',
        'description': '單行文字',
        'facets': {
            'postgresql': {
                'supported': True,
                'pg_type': 'VARCHAR(500)',
                'nullable': True,
            },
            'formio': {
                'supported': True,
                'component_type': 'textfield',
                'validate': {'maxLength': 500},
            },
            'excel': {
                'supported': True,
                'format': '@',
                'column_width': 20,
            },
            'csv': {
                'supported': True,
                'quote_mode': 'auto',
            },
        },
    },
    'text_long': {
        'label': '長文字',
        'description': '多行文字、備註',
        'facets': {
            'postgresql': {
                'supported': True,
                'pg_type': 'TEXT',
                'nullable': True,
            },
            'formio': {
                'supported': True,
                'component_type': 'textarea',
                'validate': {},
            },
            'excel': {
                'supported': True,
                'format': '@',
                'column_width': 30,
            },
            'csv': {
                'supported': True,
                'quote_mode': 'always',
            },
        },
    },

    # ── 數值類 ──
    'integer': {
        'label': '整數',
        'description': '整數值',
        'facets': {
            'postgresql': {
                'supported': True,
                'pg_type': 'INTEGER',
                'nullable': True,
            },
            'formio': {
                'supported': True,
                'component_type': 'number',
                'validate': {},
            },
            'excel': {
                'supported': True,
                'format': '#,##0',
                'column_width': 12,
            },
            'csv': {
                'supported': True,
                'quote_mode': 'never',
            },
        },
    },
    'decimal': {
        'label': '小數',
        'description': '帶小數點的數值',
        'facets': {
            'postgresql': {
                'supported': True,
                'pg_type': 'NUMERIC',
                'nullable': True,
            },
            'formio': {
                'supported': True,
                'component_type': 'number',
                'validate': {},
            },
            'excel': {
                'supported': True,
                'format': '#,##0.00',
                'column_width': 14,
            },
            'csv': {
                'supported': True,
                'quote_mode': 'never',
            },
        },
    },
    'currency': {
        'label': '貨幣',
        'description': '貨幣金額',
        'facets': {
            'postgresql': {
                'supported': True,
                'pg_type': 'NUMERIC(15,2)',
                'nullable': True,
            },
            'formio': {
                'supported': True,
                'component_type': 'currency',
                'validate': {},
            },
            'excel': {
                'supported': True,
                'format': '$#,##0.00',
                'column_width': 14,
            },
            'csv': {
                'supported': True,
                'quote_mode': 'never',
            },
        },
    },
    'serial': {
        'label': '自動遞增',
        'description': 'PostgreSQL 自動遞增序號，其他格式不支援',
        'facets': {
            'postgresql': {
                'supported': True,
                'pg_type': 'SERIAL',
                'nullable': False,
                'primary_key': True,
            },
            'formio': {
                'supported': False,
                'reason': 'FormIO 無自動遞增概念，建議設為 hidden number',
            },
            'excel': {
                'supported': False,
                'reason': 'Excel 無自動遞增，匯出時顯示為整數值',
            },
            'csv': {
                'supported': False,
                'reason': 'CSV 無自動遞增，匯出時顯示為整數值',
            },
        },
    },

    # ── 布林類 ──
    'boolean': {
        'label': '布林',
        'description': '是/否',
        'facets': {
            'postgresql': {
                'supported': True,
                'pg_type': 'BOOLEAN',
                'nullable': True,
            },
            'formio': {
                'supported': True,
                'component_type': 'checkbox',
                'validate': {},
            },
            'excel': {
                'supported': True,
                'format': 'General',
                'column_width': 8,
            },
            'csv': {
                'supported': True,
                'quote_mode': 'never',
            },
        },
    },

    # ── 日期時間類 ──
    'date': {
        'label': '日期',
        'description': '年月日',
        'facets': {
            'postgresql': {
                'supported': True,
                'pg_type': 'DATE',
                'nullable': True,
            },
            'formio': {
                'supported': True,
                'component_type': 'day',
                'validate': {},
            },
            'excel': {
                'supported': True,
                'format': 'yyyy-mm-dd',
                'column_width': 12,
            },
            'csv': {
                'supported': True,
                'quote_mode': 'auto',
            },
        },
    },
    'datetime': {
        'label': '日期時間',
        'description': '年月日時分秒',
        'facets': {
            'postgresql': {
                'supported': True,
                'pg_type': 'TIMESTAMP',
                'nullable': True,
            },
            'formio': {
                'supported': True,
                'component_type': 'datetime',
                'validate': {},
            },
            'excel': {
                'supported': True,
                'format': 'yyyy-mm-dd hh:mm',
                'column_width': 18,
            },
            'csv': {
                'supported': True,
                'quote_mode': 'auto',
            },
        },
    },

    # ── 聯絡資訊類 ──
    'email': {
        'label': '電子郵件',
        'description': 'Email 地址',
        'facets': {
            'postgresql': {
                'supported': True,
                'pg_type': 'VARCHAR(200)',
                'nullable': True,
            },
            'formio': {
                'supported': True,
                'component_type': 'email',
                'validate': {},
            },
            'excel': {
                'supported': True,
                'format': '@',
                'column_width': 24,
            },
            'csv': {
                'supported': True,
                'quote_mode': 'auto',
            },
        },
    },
    'phone': {
        'label': '電話',
        'description': '電話號碼',
        'facets': {
            'postgresql': {
                'supported': True,
                'pg_type': 'VARCHAR(50)',
                'nullable': True,
            },
            'formio': {
                'supported': True,
                'component_type': 'phoneNumber',
                'validate': {},
            },
            'excel': {
                'supported': True,
                'format': '@',
                'column_width': 16,
            },
            'csv': {
                'supported': True,
                'quote_mode': 'always',
            },
        },
    },
    'url': {
        'label': 'URL',
        'description': '網址連結',
        'facets': {
            'postgresql': {
                'supported': True,
                'pg_type': 'VARCHAR(1000)',
                'nullable': True,
            },
            'formio': {
                'supported': True,
                'component_type': 'url',
                'validate': {},
            },
            'excel': {
                'supported': True,
                'format': '@',
                'column_width': 30,
            },
            'csv': {
                'supported': True,
                'quote_mode': 'always',
            },
        },
    },

    # ── 選擇類 ──
    'enum_single': {
        'label': '單選',
        'description': '從選項中選擇一個值',
        'facets': {
            'postgresql': {
                'supported': True,
                'pg_type': 'VARCHAR(500)',
                'nullable': True,
            },
            'formio': {
                'supported': True,
                'component_type': 'select',
                'validate': {},
            },
            'excel': {
                'supported': True,
                'format': 'General',
                'column_width': 16,
            },
            'csv': {
                'supported': True,
                'quote_mode': 'auto',
            },
        },
    },
    'enum_multi': {
        'label': '複選',
        'description': '從選項中選擇多個值',
        'facets': {
            'postgresql': {
                'supported': True,
                'pg_type': 'JSONB',
                'nullable': True,
            },
            'formio': {
                'supported': True,
                'component_type': 'selectboxes',
                'validate': {},
            },
            'excel': {
                'supported': True,
                'format': 'General',
                'column_width': 20,
                'note': '匯出為逗號分隔文字',
            },
            'csv': {
                'supported': True,
                'quote_mode': 'always',
                'note': '匯出為 JSON 陣列字串',
            },
        },
    },

    # ── 結構類 ──
    'json': {
        'label': 'JSON',
        'description': 'JSON 結構化資料',
        'facets': {
            'postgresql': {
                'supported': True,
                'pg_type': 'JSONB',
                'nullable': True,
            },
            'formio': {
                'supported': True,
                'component_type': 'hidden',
                'validate': {},
                'note': 'FormIO 以 hidden 欄位儲存 JSON 字串',
            },
            'excel': {
                'supported': False,
                'reason': 'Excel 無法原生表達 JSON 結構',
            },
            'csv': {
                'supported': True,
                'quote_mode': 'always',
                'note': '匯出為 JSON 字串',
            },
        },
    },
    'tags': {
        'label': '標籤',
        'description': '標籤陣列',
        'facets': {
            'postgresql': {
                'supported': True,
                'pg_type': 'JSONB',
                'nullable': True,
            },
            'formio': {
                'supported': True,
                'component_type': 'tags',
                'validate': {},
            },
            'excel': {
                'supported': True,
                'format': 'General',
                'column_width': 20,
                'note': '匯出為逗號分隔文字',
            },
            'csv': {
                'supported': True,
                'quote_mode': 'always',
                'note': '匯出為 JSON 陣列字串',
            },
        },
    },

    # ── 二進位/檔案類 ──
    'binary': {
        'label': '二進位',
        'description': '二進位資料（檔案、圖片等）',
        'facets': {
            'postgresql': {
                'supported': True,
                'pg_type': 'BYTEA',
                'nullable': True,
            },
            'formio': {
                'supported': True,
                'component_type': 'file',
                'validate': {},
                'note': 'FormIO file 元件處理上傳，儲存為參考路徑或 base64',
            },
            'excel': {
                'supported': False,
                'reason': 'Excel 無法儲存任意二進位資料',
            },
            'csv': {
                'supported': False,
                'reason': 'CSV 無法儲存二進位資料',
            },
        },
    },
    'signature': {
        'label': '簽名',
        'description': '手寫簽名（base64 圖片）',
        'facets': {
            'postgresql': {
                'supported': True,
                'pg_type': 'TEXT',
                'nullable': True,
            },
            'formio': {
                'supported': True,
                'component_type': 'signature',
                'validate': {},
            },
            'excel': {
                'supported': False,
                'reason': 'Excel 無法原生嵌入簽名圖片',
            },
            'csv': {
                'supported': False,
                'reason': 'CSV 無法儲存簽名圖片',
            },
        },
    },
}


def get_data_class_list():
    """取得所有 data_class 清單（供前端下拉選單用）"""
    result = []
    for key, reg in DATA_CLASS_REGISTRY.items():
        supported_facets = [
            f for f in ALL_FACETS
            if reg['facets'].get(f, {}).get('supported', False)
        ]
        unsupported_facets = [
            f for f in ALL_FACETS
            if not reg['facets'].get(f, {}).get('supported', True)
        ]
        result.append({
            'value': key,
            'label': reg['label'],
            'description': reg['description'],
            'supported_facets': supported_facets,
            'unsupported_facets': unsupported_facets,
        })
    return result


def get_facet_defaults(data_class, facet_name):
    """
    取得指定 data_class 在特定格式下的預設 facet 值

    Returns:
        dict: facet 預設值（含 supported 旗標）
        None: data_class 或 facet 不存在
    """
    reg = DATA_CLASS_REGISTRY.get(data_class)
    if not reg:
        return None
    return reg['facets'].get(facet_name)


def is_facet_supported(data_class, facet_name):
    """檢查指定 data_class 是否支援該格式"""
    defaults = get_facet_defaults(data_class, facet_name)
    if defaults is None:
        return False
    return defaults.get('supported', False)


def get_unsupported_reason(data_class, facet_name):
    """取得不支援的原因說明"""
    defaults = get_facet_defaults(data_class, facet_name)
    if defaults is None:
        return f'未知的 data_class: {data_class}'
    if defaults.get('supported', False):
        return None
    return defaults.get('reason', '不支援')


def build_field_template(field_key, label, data_class, description=''):
    """
    建立新欄位模板（僅含 core，無 facets）

    用於新建欄位時產生初始結構，facets 由後續操作按需填入。
    """
    if data_class not in DATA_CLASS_REGISTRY:
        raise ValueError(f'未知的 data_class: {data_class}')

    return {
        'field_key': field_key,
        'label': label,
        'sort_order': 0,
        'description': description,
        'core': {
            'data_class': data_class,
            'required': False,
            'is_pii': False,
            'default_value': None,
        },
        'facets': {},
    }


def populate_facet_defaults(field, facet_name):
    """
    為欄位填入指定格式的預設 facet 值

    根據 field['core']['data_class'] 查表，
    將預設值寫入 field['facets'][facet_name]。
    已存在的值不覆蓋。

    Returns:
        dict: 更新後的 field
        None: data_class 不支援該格式
    """
    data_class = field.get('core', {}).get('data_class')
    defaults = get_facet_defaults(data_class, facet_name)
    if defaults is None or not defaults.get('supported', False):
        return None

    facets = field.get('facets', {})
    existing = facets.get(facet_name, {})

    # 合併：已有值優先，缺值用預設補
    merged = {}
    for k, v in defaults.items():
        if k in ('supported', 'reason', 'note'):
            continue
        merged[k] = existing.get(k, v)

    # PostgreSQL: 補上通用結構屬性預設值
    if facet_name == 'postgresql':
        pg_extras = {
            'primary_key': False,
            'index': False,
            'unique': False,
            'foreign_key': None,
        }
        for k, v in pg_extras.items():
            if k not in merged:
                merged[k] = v

    facets[facet_name] = merged
    field['facets'] = facets
    return field
