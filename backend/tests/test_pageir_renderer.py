"""Page IR v3 渲染器單元測試。"""
from __future__ import annotations

import os

import pytest
from flask import Flask
from markupsafe import escape

from app.pageir import PageIrRenderError, render_page_ir
from app.pageir.registry import register_resource

os.environ.setdefault("SYSTEM_ORG_CODE", "system.local")


@pytest.fixture
def pir_app():
    app = Flask(__name__, template_folder="../app/templates")
    app.secret_key = "test-secret"
    app.jinja_env.globals["_"] = lambda text, **kwargs: text % kwargs if kwargs else text
    app.jinja_env.globals["egress_visibility"] = lambda resource, context, field: "clear"
    app.jinja_env.globals["egress_value"] = (
        lambda resource, context, record_sc, field, value: escape(value)
    )
    app.jinja_env.filters["tz_format"] = lambda value, fmt="%Y-%m-%d %H:%M": "DATE"
    return app


def _doc(widgets):
    return {
        "ir_version": 3,
        "page": {
            "id": "renderer-page",
            "title_i18n": {"zh-TW": "渲染測試"},
            "widgets": widgets,
        },
    }


def _table_widget(**overrides):
    widget = {
        "id": "tbl",
        "type": "table",
        "binding": {"resource": "fake", "view": "list", "fields": ["name", "email"]},
        "columns": [
            {"field": "name", "label_i18n": {"zh-TW": "姓名"}, "sortable": True},
            {"field": "email", "label_i18n": {"zh-TW": "信箱"}},
        ],
        "page_size": 2,
        "default_sort": {"field": "name", "dir": "asc"},
    }
    widget.update(overrides)
    return widget


def _register_fake_resource(calls=None):
    rows = [
        {"_sc": "row_sc_0001", "name": "Alice", "email": "a@example.com"},
        {"_sc": "row_sc_0002", "name": "Bob", "email": "b@example.com"},
    ]

    def fetch_list(fields, page, page_size, sort_field, sort_dir):
        if calls is not None:
            calls.append((fields, page, page_size, sort_field, sort_dir))
        return [{field: row[field] for field in fields} | {"_sc": row["_sc"]} for row in rows], 2

    def fetch_detail(record_sc, fields):
        for row in rows:
            if row["_sc"] == record_sc:
                return {field: row[field] for field in fields} | {"_sc": row["_sc"]}
        return None

    register_resource(
        "fake",
        {
            "fields": ["name", "email"],
            "egress_resource": None,
            "views": ["list", "detail"],
            "fetch_list": fetch_list,
            "fetch_detail": fetch_detail,
        },
    )


def test_text_layout_render_tags_and_grid(pir_app):
    doc = _doc([
        {
            "id": "main-grid",
            "type": "layout",
            "columns": 2,
            "gap": 16,
            "children": [
                {
                    "id": "intro",
                    "type": "text",
                    "level": "h2",
                    "content_i18n": {"zh-TW": "<安全標題>"},
                }
            ],
        }
    ])

    with pir_app.test_request_context("/"):
        html = render_page_ir(doc)

    assert 'class="pir-layout"' in html
    assert "grid-template-columns: repeat(2, 1fr); gap: 16px" in html
    assert '<h2 id="intro"' in html
    assert "&lt;安全標題&gt;" in html


def test_unknown_table_resource_fails_closed(pir_app):
    doc = _doc([_table_widget(binding={"resource": "missing", "view": "list", "fields": ["name"]})])

    with pir_app.test_request_context("/"):
        with pytest.raises(PageIrRenderError):
            render_page_ir(doc)


def test_binding_fields_outside_whitelist_fails_closed(pir_app):
    _register_fake_resource()
    doc = _doc([
        _table_widget(
            binding={"resource": "fake", "view": "list", "fields": ["name", "secret"]},
            columns=[{"field": "name", "label_i18n": {"zh-TW": "姓名"}}],
        )
    ])

    with pir_app.test_request_context("/"):
        with pytest.raises(PageIrRenderError):
            render_page_ir(doc)


def test_table_renders_rows_and_pagination(pir_app):
    _register_fake_resource()
    doc = _doc([_table_widget()])

    with pir_app.test_request_context("/?tbl__page=1"):
        html = render_page_ir(doc)

    assert "Alice" in html
    assert "Bob" in html
    assert "總數" in html
    assert "2" in html


def test_non_sortable_query_uses_default_sort(pir_app):
    calls = []
    _register_fake_resource(calls)
    doc = _doc([_table_widget()])

    with pir_app.test_request_context("/?tbl__sort=email&tbl__dir=desc"):
        render_page_ir(doc)

    assert calls[-1] == (["name", "email"], 1, 2, "name", "asc")


def test_actions_permission_and_unregistered_action(pir_app, monkeypatch):
    from app.services import capability_service

    action_doc = _doc([
        {
            "id": "act",
            "type": "actions",
            "buttons": [
                {
                    "id": "btn-run",
                    "label_i18n": {"zh-TW": "執行"},
                    "permission": "renderer.run",
                    "action_ref": "renderer.missing",
                }
            ],
        }
    ])

    monkeypatch.setattr(capability_service, "user_can", lambda permission: False)
    with pir_app.test_request_context("/"):
        html = render_page_ir(action_doc)
    assert "btn-run" not in html

    monkeypatch.setattr(capability_service, "user_can", lambda permission: True)
    with pir_app.test_request_context("/"):
        with pytest.raises(PageIrRenderError):
            render_page_ir(action_doc)


def test_form_placeholder_does_not_render_schema(pir_app):
    doc = _doc([
        {
            "id": "frm",
            "type": "form",
            "formio_schema": {"components": [{"label": "Secret Schema Text"}]},
        }
    ])

    with pir_app.test_request_context("/"):
        html = render_page_ir(doc)

    assert "表單元件將於後續版本啟用" in html
    assert "Secret Schema Text" not in html


def test_invalid_ir_fails_closed(pir_app):
    with pir_app.test_request_context("/"):
        with pytest.raises(PageIrRenderError):
            render_page_ir({"version": 2, "widgets": []})
