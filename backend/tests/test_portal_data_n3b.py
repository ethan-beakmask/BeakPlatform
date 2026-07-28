"""Portal Page IR rows API pure helper tests."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SYSTEM_ORG_CODE", "system.local")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from modules.nocode_builder.web.portal_public import _find_table_widget, _resolve_sort


def _doc(widgets):
    return {
        "ir_version": 3,
        "page": {
            "id": "portal-page",
            "widgets": widgets,
        },
    }


def _table_widget(**overrides):
    widget = {
        "id": "tbl",
        "type": "table",
        "binding": {
            "resource": "portal:View1234",
            "view": "list",
            "fields": ["name", "email"],
        },
        "columns": [
            {"field": "name", "label_i18n": {"zh-TW": "姓名"}, "sortable": True},
            {"field": "email", "label_i18n": {"zh-TW": "信箱"}, "sortable": False},
        ],
        "default_sort": {"field": "name", "dir": "desc"},
    }
    widget.update(overrides)
    return widget


def test_find_table_widget_finds_nested_layout_child():
    table = _table_widget(id="nested_tbl")
    doc = _doc([
        {
            "id": "layout_1",
            "type": "layout",
            "children": [
                {
                    "id": "layout_2",
                    "type": "layout",
                    "children": [table],
                }
            ],
        }
    ])

    assert _find_table_widget(doc, "nested_tbl") is table


def test_find_table_widget_returns_none_for_matching_non_table():
    doc = _doc([
        {"id": "headline", "type": "text", "level": "h2", "content_i18n": {"zh-TW": "Hi"}}
    ])

    assert _find_table_widget(doc, "headline") is None


def test_find_table_widget_returns_none_when_missing():
    assert _find_table_widget(_doc([_table_widget()]), "missing") is None


def test_resolve_sort_falls_back_when_sort_not_in_binding_fields():
    widget = _table_widget()

    assert _resolve_sort(widget, widget["binding"], "secret", "asc") == ("name", "desc")


def test_resolve_sort_falls_back_when_column_is_not_sortable():
    widget = _table_widget()

    assert _resolve_sort(widget, widget["binding"], "email", "asc") == ("name", "desc")


def test_resolve_sort_accepts_legal_sort_and_normalizes_bad_dir():
    widget = _table_widget()

    assert _resolve_sort(widget, widget["binding"], "name", "sideways") == ("name", "asc")


def test_resolve_sort_returns_empty_safe_value_without_default_sort():
    widget = _table_widget(default_sort=None)

    assert _resolve_sort(widget, widget["binding"], "secret", "desc") == (None, None)
