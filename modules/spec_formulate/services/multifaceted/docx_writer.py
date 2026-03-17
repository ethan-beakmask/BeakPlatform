"""
Multifaceted DOCX Writer - 多面向規格書文件產生器

將多筆規格的指定 facet 套版匯出為 .docx 制式開發規格書。
"""

import os
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn


# ============================================================
# 固定模板文字
# ============================================================

PREAMBLE = (
    '本章節定義系統所使用之資料結構規格。'
    '各資料表之欄位名稱、資料類別、格式映射、約束條件及欄位用途說明如下。\n\n'
    '欄位命名採用小寫底線命名法 (snake_case)，以確保跨平台相容性。'
    '各格式映射依據多面向規格系統 (Multifaceted Spec) 的定義自動產生。'
)

POSTSCRIPT = (
    '上述資料結構設計依循正規化原則，避免資料冗餘與更新異常。\n\n'
    '如需異動資料結構，應先更新多面向規格定義，經審核確認後再進行實際變更。'
)


# ============================================================
# 樣式常數
# ============================================================

_FONT_EN = 'Calibri'
_FONT_ZH = 'Noto Sans CJK TC'

_COLOR_HEADER_BG = 'D6E4F0'
_COLOR_PII_ROW_BG = 'FCE4EC'
_COLOR_BORDER = '8EAADB'
_COLOR_TEXT = '333333'
_COLOR_HEADING = '1F3864'

# 各 facet 的表頭色
_FACET_COLORS = {
    'postgresql': 'DBEAFE',
    'formio': 'FEF3C7',
    'excel': 'D1FAE5',
    'csv': 'E5E7EB',
}

# 各 facet 的中文名
FACET_LABELS = {
    'postgresql': 'PostgreSQL',
    'formio': 'FormIO',
    'excel': 'Excel',
    'csv': 'CSV',
}


# ============================================================
# 各 facet 表格欄位定義
# ============================================================

# 每個 facet 的表頭和取值函式
# (header_text, width_cm, alignment, value_fn)
# value_fn(field, facet_data) -> str

def _pg_type(f, fd):
    return fd.get('pg_type', '-')

def _pg_pk(f, fd):
    return 'V' if fd.get('primary_key') else ''

def _pg_nullable(f, fd):
    return 'V' if fd.get('nullable') else ''

def _pg_default(f, fd):
    v = fd.get('default')
    return str(v) if v is not None else ''

def _formio_component(f, fd):
    return fd.get('component_type', '-')

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
    return ', '.join(parts) if parts else ''

def _excel_format(f, fd):
    return fd.get('format', '-')

def _excel_width(f, fd):
    w = fd.get('column_width')
    return str(w) if w else ''

def _csv_quote(f, fd):
    return fd.get('quote_mode', '-')


def _core_required(f, fd):
    core = f.get('core', {})
    return 'V' if core.get('required') else ''

def _core_pii(f, fd):
    core = f.get('core', {})
    return 'V' if core.get('is_pii') else ''

def _field_desc(f, fd):
    return f.get('description', '') or ''


# 共用前置欄: #, Field Key, Label, Data Class
_COMMON_PREFIX = [
    ('#', 0.7, WD_ALIGN_PARAGRAPH.CENTER, None),
    ('Field Key', 2.8, WD_ALIGN_PARAGRAPH.LEFT, None),
    ('Label', 2.2, WD_ALIGN_PARAGRAPH.LEFT, None),
    ('Data Class', 1.8, WD_ALIGN_PARAGRAPH.LEFT, None),
]

FACET_TABLE_COLUMNS = {
    'postgresql': [
        ('PG Type', 2.2, WD_ALIGN_PARAGRAPH.LEFT, _pg_type),
        ('PK', 0.7, WD_ALIGN_PARAGRAPH.CENTER, _pg_pk),
        ('Null', 0.7, WD_ALIGN_PARAGRAPH.CENTER, _pg_nullable),
        ('Default', 1.8, WD_ALIGN_PARAGRAPH.LEFT, _pg_default),
        ('PII', 0.7, WD_ALIGN_PARAGRAPH.CENTER, _core_pii),
        ('Required', 0.8, WD_ALIGN_PARAGRAPH.CENTER, _core_required),
        ('Description', 3.0, WD_ALIGN_PARAGRAPH.LEFT, _field_desc),
    ],
    'formio': [
        ('Component', 2.0, WD_ALIGN_PARAGRAPH.LEFT, _formio_component),
        ('Validation', 3.0, WD_ALIGN_PARAGRAPH.LEFT, _formio_validate),
        ('PII', 0.7, WD_ALIGN_PARAGRAPH.CENTER, _core_pii),
        ('Required', 0.8, WD_ALIGN_PARAGRAPH.CENTER, _core_required),
        ('Description', 3.5, WD_ALIGN_PARAGRAPH.LEFT, _field_desc),
    ],
    'excel': [
        ('Format', 2.0, WD_ALIGN_PARAGRAPH.LEFT, _excel_format),
        ('Width', 1.0, WD_ALIGN_PARAGRAPH.CENTER, _excel_width),
        ('PII', 0.7, WD_ALIGN_PARAGRAPH.CENTER, _core_pii),
        ('Required', 0.8, WD_ALIGN_PARAGRAPH.CENTER, _core_required),
        ('Description', 3.5, WD_ALIGN_PARAGRAPH.LEFT, _field_desc),
    ],
    'csv': [
        ('Quote Mode', 2.0, WD_ALIGN_PARAGRAPH.LEFT, _csv_quote),
        ('PII', 0.7, WD_ALIGN_PARAGRAPH.CENTER, _core_pii),
        ('Required', 0.8, WD_ALIGN_PARAGRAPH.CENTER, _core_required),
        ('Description', 4.5, WD_ALIGN_PARAGRAPH.LEFT, _field_desc),
    ],
}


# ============================================================
# 主函式
# ============================================================

def generate_spec_docx(entries, output_path, doc_title='資料結構規格書'):
    """
    產生多面向規格書 Word 文件。

    Args:
        entries: 規格項目列表，每項為 dict:
            {
                'name': str,           # 規格名稱
                'description': str,    # 描述
                'version': int,        # 版本
                'fields': list,        # 欄位 JSONB 陣列
                'active_facets': list, # 已啟用格式
                'facets': list,        # 本次要匯出的格式
            }
        output_path: 輸出檔案路徑
        doc_title: 文件標題

    Returns:
        輸出檔案的絕對路徑
    """
    output_path = os.path.abspath(output_path)

    doc = Document()

    # 預設字型
    style = doc.styles['Normal']
    font = style.font
    font.name = _FONT_EN
    font.size = Pt(11)
    font.color.rgb = RGBColor.from_string(_COLOR_TEXT)
    style.element.rPr.rFonts.set(qn('w:eastAsia'), _FONT_ZH)

    # 頁面邊距
    for section in doc.sections:
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.0)

    # 章節標題
    _add_heading(doc, doc_title, level=1)

    # 前文
    for para_text in PREAMBLE.strip().split('\n\n'):
        p = doc.add_paragraph(para_text.strip())
        _set_paragraph_font(p)
        p.paragraph_format.space_after = Pt(6)

    # 規格目錄摘要
    if len(entries) > 1:
        _add_heading(doc, '規格目錄', level=2)
        for idx, entry in enumerate(entries, start=1):
            facet_str = ', '.join(
                FACET_LABELS.get(f, f) for f in entry['facets']
            )
            line = f"{idx}. {entry['name']} (v{entry['version']}) -- {facet_str}"
            p = doc.add_paragraph(line)
            _set_paragraph_font(p, size=Pt(10))
            p.paragraph_format.space_after = Pt(2)

    # 各規格
    spec_seq = 0
    for entry in entries:
        spec_seq += 1
        doc.add_paragraph()  # 空行

        # 規格標題
        title = f"{spec_seq}. {entry['name']} (v{entry['version']})"
        _add_heading(doc, title, level=2)

        # 描述
        if entry.get('description'):
            p = doc.add_paragraph(entry['description'])
            _set_paragraph_font(p, italic=True, size=Pt(10))
            p.paragraph_format.space_after = Pt(4)

        # 欄位摘要
        fields = entry.get('fields') or []
        valid_fields = [f for f in fields if f.get('field_key')]
        pii_count = sum(
            1 for f in valid_fields
            if f.get('core', {}).get('is_pii')
        )
        summary = f"共 {len(valid_fields)} 個欄位"
        if pii_count > 0:
            summary += f" (PII: {pii_count})"
        p = doc.add_paragraph(summary)
        _set_paragraph_font(p, size=Pt(10))
        p.paragraph_format.space_after = Pt(6)

        # 每個選取的 facet 各一張表
        for facet_name in entry['facets']:
            facet_label = FACET_LABELS.get(facet_name, facet_name)
            _add_heading(doc, f"{spec_seq}.{entry['facets'].index(facet_name)+1} {facet_label} 格式", level=3)

            _add_facet_table(doc, valid_fields, facet_name)

    # 後文
    doc.add_paragraph()
    for para_text in POSTSCRIPT.strip().split('\n\n'):
        p = doc.add_paragraph(para_text.strip())
        _set_paragraph_font(p)
        p.paragraph_format.space_after = Pt(6)

    doc.save(output_path)
    return output_path


# ============================================================
# 內部函式
# ============================================================

def _add_heading(doc, text, level=1):
    """新增標題"""
    h = doc.add_heading(level=level)
    run = h.add_run(text)
    run.font.name = _FONT_EN
    run.font.color.rgb = RGBColor.from_string(_COLOR_HEADING)
    run.element.rPr.rFonts.set(qn('w:eastAsia'), _FONT_ZH)


def _set_paragraph_font(paragraph, bold=False, italic=False, size=None):
    """設定段落字型"""
    for run in paragraph.runs:
        run.font.name = _FONT_EN
        run.element.rPr.rFonts.set(qn('w:eastAsia'), _FONT_ZH)
        if bold:
            run.font.bold = True
        if italic:
            run.font.italic = True
        if size:
            run.font.size = size


def _add_facet_table(doc, fields, facet_name):
    """新增指定 facet 的欄位表格"""
    facet_cols = FACET_TABLE_COLUMNS.get(facet_name, [])
    all_cols = list(_COMMON_PREFIX) + facet_cols
    col_count = len(all_cols)
    row_count = len(fields) + 1  # +1 表頭

    table = doc.add_table(rows=row_count, cols=col_count)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = 'Table Grid'

    # 表頭
    header_bg = _FACET_COLORS.get(facet_name, _COLOR_HEADER_BG)
    header_row = table.rows[0]
    for i, (header_text, width, align, _) in enumerate(all_cols):
        cell = header_row.cells[i]
        cell.text = ''
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(header_text)
        run.bold = True
        run.font.size = Pt(9)
        run.font.name = _FONT_EN
        run.font.color.rgb = RGBColor.from_string(_COLOR_HEADING)
        run.element.rPr.rFonts.set(qn('w:eastAsia'), _FONT_ZH)
        _set_cell_bg(cell, header_bg)
        cell.width = Cm(width)

    # 資料列
    for row_idx, field in enumerate(fields):
        row = table.rows[row_idx + 1]
        facet_data = field.get('facets', {}).get(facet_name, {})
        core = field.get('core', {})
        dc = core.get('data_class', '-')

        # 共用前置欄值
        prefix_values = [
            str(row_idx + 1),
            field.get('field_key', ''),
            field.get('label', ''),
            dc,
        ]

        # facet 專屬欄值
        facet_values = [
            fn(field, facet_data) if fn else ''
            for (_, _, _, fn) in facet_cols
        ]

        all_values = prefix_values + facet_values

        for col_idx, val in enumerate(all_values):
            cell = row.cells[col_idx]
            cell.text = ''
            p = cell.paragraphs[0]
            p.alignment = all_cols[col_idx][2]
            run = p.add_run(str(val))
            run.font.size = Pt(9)
            run.font.name = _FONT_EN
            run.element.rPr.rFonts.set(qn('w:eastAsia'), _FONT_ZH)
            cell.width = Cm(all_cols[col_idx][1])

        # PII 列淺紅底
        if core.get('is_pii'):
            for cell in row.cells:
                _set_cell_bg(cell, _COLOR_PII_ROW_BG)

    _set_table_borders(table)


def _set_cell_bg(cell, color_hex):
    """設定儲存格背景色"""
    tc_pr = cell._element.get_or_add_tcPr()
    shading_elem = tc_pr.makeelement(qn('w:shd'), {
        qn('w:val'): 'clear',
        qn('w:color'): 'auto',
        qn('w:fill'): color_hex,
    })
    tc_pr.append(shading_elem)


def _set_table_borders(table):
    """設定表格框線"""
    tbl = table._tbl
    tbl_pr = tbl.tblPr if tbl.tblPr is not None else tbl.makeelement(
        qn('w:tblPr'), {}
    )

    borders = tbl_pr.makeelement(qn('w:tblBorders'), {})
    for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        element = borders.makeelement(qn(f'w:{edge}'), {
            qn('w:val'): 'single',
            qn('w:sz'): '4',
            qn('w:space'): '0',
            qn('w:color'): _COLOR_BORDER,
        })
        borders.append(element)

    # 移除既有的 tblBorders
    for existing in tbl_pr.findall(qn('w:tblBorders')):
        tbl_pr.remove(existing)

    tbl_pr.append(borders)
