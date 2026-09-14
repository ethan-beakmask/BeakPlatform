"""
Spec PDF Writer - 規格書 PDF 產生器

將多筆規格的指定 facet 套版匯出為 .pdf 制式開發規格書。
樣式常數對齊 docx_writer.py，確保 DOCX 與 PDF 輸出一致。
"""

import os
from weasyprint import HTML

# ============================================================
# 樣式常數（對齊 docx_writer.py）
# ============================================================

_FONT_FAMILY = "'Noto Sans CJK TC', 'Calibri', sans-serif"

_COLOR_HEADER_BG = '#D6E4F0'
_COLOR_PII_ROW_BG = '#FCE4EC'
_COLOR_BORDER = '#8EAADB'
_COLOR_TEXT = '#333333'
_COLOR_HEADING = '#1F3864'

_FACET_COLORS = {
    'postgresql': '#DBEAFE',
    'formio': '#FEF3C7',
    'excel': '#D1FAE5',
    'csv': '#E5E7EB',
}

FACET_LABELS = {
    'postgresql': 'PostgreSQL',
    'formio': 'FormIO',
    'excel': 'Excel',
    'csv': 'CSV',
}


# ============================================================
# 固定模板文字（對齊 docx_writer.py）
# ============================================================

PREAMBLE = (
    '本章節定義系統所使用之資料結構規格。'
    '各資料表之欄位名稱、資料類別、格式映射、約束條件及欄位用途說明如下。'
    '<br><br>'
    '欄位命名採用小寫底線命名法 (snake_case)，以確保跨平台相容性。'
    '各格式映射依據規格系統 (Spec Schema) 的定義自動產生。'
)

POSTSCRIPT = (
    '上述資料結構設計依循正規化原則，避免資料冗餘與更新異常。'
    '<br><br>'
    '如需異動資料結構，應先更新規格定義，經審核確認後再進行實際變更。'
)


# ============================================================
# 各 facet 表格欄位定義
# ============================================================

# (header_text, width_percent, alignment, value_fn)
# value_fn(field, facet_data) -> str

def _pg_type(f, fd):
    return _esc(fd.get('pg_type', '-'))

def _pg_pk(f, fd):
    return 'V' if fd.get('primary_key') else ''

def _pg_nullable(f, fd):
    return 'V' if fd.get('nullable') else ''

def _pg_default(f, fd):
    v = fd.get('default')
    return _esc(str(v)) if v is not None else ''

def _formio_component(f, fd):
    return _esc(fd.get('component_type', '-'))

def _formio_validate(f, fd):
    v = fd.get('validate', {})
    if not v:
        return ''
    parts = []
    if v.get('required'):
        parts.append('required')
    if v.get('maxLength'):
        parts.append(f"maxLen={v['maxLength']}")
    if v.get('min') is not None:
        parts.append(f"min={v['min']}")
    if v.get('max') is not None:
        parts.append(f"max={v['max']}")
    if v.get('pattern'):
        parts.append(f"pattern={v['pattern']}")
    return _esc(', '.join(parts)) if parts else ''

def _excel_format(f, fd):
    return _esc(fd.get('format', '-'))

def _excel_width(f, fd):
    w = fd.get('column_width')
    return str(w) if w else ''

def _csv_quote(f, fd):
    return _esc(fd.get('quote_mode', '-'))

def _core_required(f, fd):
    core = f.get('core', {})
    return 'V' if core.get('required') else ''

def _core_pii(f, fd):
    core = f.get('core', {})
    return 'V' if core.get('is_pii') else ''

def _field_desc(f, fd):
    return _esc(f.get('description', '') or '')


# 共用前置欄
_COMMON_PREFIX = [
    ('#', 4, 'center', None),
    ('Field Key', 16, 'left', None),
    ('Label', 12, 'left', None),
    ('Data Class', 10, 'left', None),
]

FACET_TABLE_COLUMNS = {
    'postgresql': [
        ('PG Type', 12, 'left', _pg_type),
        ('PK', 4, 'center', _pg_pk),
        ('Null', 4, 'center', _pg_nullable),
        ('Default', 10, 'left', _pg_default),
        ('PII', 4, 'center', _core_pii),
        ('Required', 5, 'center', _core_required),
        ('Description', 19, 'left', _field_desc),
    ],
    'formio': [
        ('Component', 12, 'left', _formio_component),
        ('Validation', 18, 'left', _formio_validate),
        ('PII', 5, 'center', _core_pii),
        ('Required', 5, 'center', _core_required),
        ('Description', 22, 'left', _field_desc),
    ],
    'excel': [
        ('Format', 12, 'left', _excel_format),
        ('Width', 6, 'center', _excel_width),
        ('PII', 5, 'center', _core_pii),
        ('Required', 5, 'center', _core_required),
        ('Description', 24, 'left', _field_desc),
    ],
    'csv': [
        ('Quote Mode', 12, 'left', _csv_quote),
        ('PII', 5, 'center', _core_pii),
        ('Required', 5, 'center', _core_required),
        ('Description', 32, 'left', _field_desc),
    ],
}


# ============================================================
# HTML escape
# ============================================================

def _esc(text):
    """HTML escape"""
    if not text:
        return ''
    return (
        str(text)
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
    )


# ============================================================
# 主函式
# ============================================================

def generate_spec_pdf(entries, output_path, doc_title='資料結構規格書'):
    """
    產生多面向規格書 PDF 文件。

    Args:
        entries: 規格項目列表，每項為 dict（格式同 docx_writer）:
            {
                'name': str,
                'description': str,
                'version': int,
                'fields': list,
                'active_facets': list,
                'facets': list,
            }
        output_path: 輸出檔案路徑
        doc_title: 文件標題

    Returns:
        輸出檔案的絕對路徑
    """
    output_path = os.path.abspath(output_path)
    html_content = _build_html(entries, doc_title)
    HTML(string=html_content).write_pdf(output_path)
    return output_path


# ============================================================
# HTML 組裝
# ============================================================

def _build_html(entries, doc_title):
    """組裝完整 HTML 文件"""
    parts = []
    parts.append(_html_head(doc_title))
    parts.append('<body>')

    # 標題
    parts.append(f'<h1>{_esc(doc_title)}</h1>')

    # 前文
    parts.append(f'<p class="preamble">{PREAMBLE}</p>')

    # 規格目錄摘要
    if len(entries) > 1:
        parts.append('<h2>規格目錄</h2>')
        parts.append('<ol class="toc">')
        for entry in entries:
            facet_str = ', '.join(
                FACET_LABELS.get(f, f) for f in entry['facets']
            )
            parts.append(
                f'<li>{_esc(entry["name"])} '
                f'(v{entry["version"]}) -- {_esc(facet_str)}</li>'
            )
        parts.append('</ol>')

    # 各規格
    for seq, entry in enumerate(entries, start=1):
        parts.append(_build_spec_section(seq, entry))

    # 後文
    parts.append(f'<p class="postscript">{POSTSCRIPT}</p>')

    parts.append('</body></html>')
    return '\n'.join(parts)


def _html_head(doc_title):
    """HTML head + CSS"""
    return f'''<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<title>{_esc(doc_title)}</title>
<style>
@page {{
    size: A4 landscape;
    margin: 2cm 2cm 1.8cm 2cm;
}}
body {{
    font-family: {_FONT_FAMILY};
    font-size: 10pt;
    color: {_COLOR_TEXT};
    line-height: 1.5;
}}
h1 {{
    color: {_COLOR_HEADING};
    font-size: 18pt;
    border-bottom: 2px solid {_COLOR_HEADING};
    padding-bottom: 4pt;
    margin-bottom: 8pt;
}}
h2 {{
    color: {_COLOR_HEADING};
    font-size: 14pt;
    margin-top: 16pt;
    margin-bottom: 6pt;
}}
h3 {{
    color: {_COLOR_HEADING};
    font-size: 12pt;
    margin-top: 12pt;
    margin-bottom: 4pt;
}}
.preamble, .postscript {{
    font-size: 10pt;
    margin-bottom: 8pt;
}}
.toc {{
    font-size: 9.5pt;
    margin-bottom: 12pt;
}}
.toc li {{
    margin-bottom: 2pt;
}}
.spec-summary {{
    font-size: 9.5pt;
    color: #555;
    margin-bottom: 6pt;
}}
.spec-desc {{
    font-size: 9.5pt;
    font-style: italic;
    margin-bottom: 4pt;
}}
table {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 12pt;
    font-size: 8.5pt;
}}
th, td {{
    border: 1px solid {_COLOR_BORDER};
    padding: 3pt 5pt;
    word-wrap: break-word;
}}
th {{
    color: {_COLOR_HEADING};
    font-weight: bold;
    font-size: 8.5pt;
    text-align: center;
}}
.pii-row {{
    background-color: {_COLOR_PII_ROW_BG};
}}
.text-center {{
    text-align: center;
}}
.text-left {{
    text-align: left;
}}
</style>
</head>'''


def _build_spec_section(seq, entry):
    """組裝單一規格的 HTML 區塊"""
    parts = []
    name = _esc(entry['name'])
    parts.append(f'<h2>{seq}. {name} (v{entry["version"]})</h2>')

    if entry.get('description'):
        parts.append(
            f'<p class="spec-desc">{_esc(entry["description"])}</p>'
        )

    fields = entry.get('fields') or []
    valid_fields = [f for f in fields if f.get('field_key')]
    pii_count = sum(
        1 for f in valid_fields if f.get('core', {}).get('is_pii')
    )
    summary = f"共 {len(valid_fields)} 個欄位"
    if pii_count > 0:
        summary += f" (PII: {pii_count})"
    parts.append(f'<p class="spec-summary">{summary}</p>')

    for facet_idx, facet_name in enumerate(entry['facets']):
        facet_label = FACET_LABELS.get(facet_name, facet_name)
        parts.append(
            f'<h3>{seq}.{facet_idx + 1} {facet_label} 格式</h3>'
        )
        parts.append(_build_facet_table(valid_fields, facet_name))

    return '\n'.join(parts)


def _build_facet_table(fields, facet_name):
    """組裝單一 facet 的 HTML 表格"""
    facet_cols = FACET_TABLE_COLUMNS.get(facet_name, [])
    all_cols = list(_COMMON_PREFIX) + facet_cols
    header_bg = _FACET_COLORS.get(facet_name, _COLOR_HEADER_BG)

    parts = []
    parts.append('<table>')

    # colgroup
    parts.append('<colgroup>')
    for _, width_pct, _, _ in all_cols:
        parts.append(f'<col style="width: {width_pct}%">')
    parts.append('</colgroup>')

    # 表頭
    parts.append('<thead><tr>')
    for header_text, _, _, _ in all_cols:
        parts.append(
            f'<th style="background-color: {header_bg}">'
            f'{_esc(header_text)}</th>'
        )
    parts.append('</tr></thead>')

    # 資料列
    parts.append('<tbody>')
    for row_idx, field in enumerate(fields):
        facet_data = field.get('facets', {}).get(facet_name, {})
        core = field.get('core', {})
        is_pii = core.get('is_pii', False)
        row_class = ' class="pii-row"' if is_pii else ''

        parts.append(f'<tr{row_class}>')

        # 共用前置欄值
        prefix_values = [
            str(row_idx + 1),
            _esc(field.get('field_key', '')),
            _esc(field.get('label', '')),
            _esc(core.get('data_class', '-')),
        ]

        # facet 專屬欄值
        facet_values = [
            fn(field, facet_data) if fn else ''
            for (_, _, _, fn) in facet_cols
        ]

        all_values = prefix_values + facet_values

        for col_idx, val in enumerate(all_values):
            align = all_cols[col_idx][2]
            td_class = f' class="text-{align}"'
            parts.append(f'<td{td_class}>{val}</td>')

        parts.append('</tr>')

    parts.append('</tbody></table>')
    return '\n'.join(parts)
