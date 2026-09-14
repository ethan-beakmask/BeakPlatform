"""
Spec Formulate Module - Schema Specs API
多面向規格 CRUD API

URL prefix: /api/spec-formulate/schema

子模組:
  _mf_helpers.py     - 共用輔助函式與 FormIO 轉換
  _mf_specs_crud.py  - 翻譯、Data Class、規格 CRUD、版本歷史、Facet 填充
  _mf_export.py      - DOCX / PDF 匯出
  _mf_form_link.py   - 版本清單、表單關聯/解連/同步/建立
  _mf_pg.py          - 企業專屬 DB 資料表操作
"""
from flask import Blueprint

schema_bp = Blueprint(
    'spec_formulate_schema',
    __name__,
    url_prefix='/api/spec-formulate/schema'
)

# 掛載子模組路由
from . import _mf_specs_crud
from . import _mf_export
from . import _mf_form_link
from . import _mf_pg

_mf_specs_crud.register(schema_bp)
_mf_export.register(schema_bp)
_mf_form_link.register(schema_bp)
_mf_pg.register(schema_bp)
