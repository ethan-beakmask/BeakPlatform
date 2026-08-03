"""Page IR v3 N4a widget access_matrix tests."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from flask import Flask
from markupsafe import escape

os.environ.setdefault("SYSTEM_ORG_CODE", "system.local")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.pageir import render_page_ir_full, validate_page_ir
from app.pageir.context import clear_render_context, set_render_context
from app.pageir.registry import (
    _ACCESS_EVALUATORS,
    _PROVIDERS,
    _RESOURCES,
    register_access_evaluator,
    register_resource,
    register_resource_provider,
)


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


@pytest.fixture(autouse=True)
def reset_pageir_registry():
    old_resources = dict(_RESOURCES)
    old_providers = dict(_PROVIDERS)
    old_evaluators = dict(_ACCESS_EVALUATORS)
    _RESOURCES.clear()
    _PROVIDERS.clear()
    _ACCESS_EVALUATORS.clear()
    yield
    _RESOURCES.clear()
    _RESOURCES.update(old_resources)
    _PROVIDERS.clear()
    _PROVIDERS.update(old_providers)
    _ACCESS_EVALUATORS.clear()
    _ACCESS_EVALUATORS.update(old_evaluators)


def _doc(widgets):
    return {
        "ir_version": 3,
        "page": {
            "id": "n4a-page",
            "title_i18n": {"zh-TW": "N4a"},
            "widgets": widgets,
        },
    }


def _matrix():
    rule = {"required_permissions": ["bulletin.read"]}
    return {
        "read": rule,
        "create": {"required_permissions": ["bulletin.create"]},
        "update": rule,
        "delete": rule,
    }


def _table_widget(resource="fake", **overrides):
    widget = {
        "id": "tbl",
        "type": "table",
        "binding": {"resource": resource, "view": "list", "fields": ["name", "email"]},
        "columns": [
            {"field": "name", "label_i18n": {"zh-TW": "姓名"}, "sortable": True},
            {"field": "email", "label_i18n": {"zh-TW": "信箱"}},
        ],
        "page_size": 20,
    }
    widget.update(overrides)
    return widget


def _detail_widget(**overrides):
    widget = {
        "id": "dtl",
        "type": "detail",
        "binding": {"resource": "fake", "view": "detail", "fields": ["name", "email"]},
        "fields": [
            {"field": "name", "label_i18n": {"zh-TW": "姓名"}},
            {"field": "email", "label_i18n": {"zh-TW": "信箱"}},
        ],
    }
    widget.update(overrides)
    return widget


def _register_platform_resource(calls=None):
    register_resource("fake", _resource_config(calls))


def _register_portal_provider(calls=None):
    register_resource_provider("portal", lambda code, ctx: _resource_config(calls))


def _resource_config(calls=None):
    def fetch_list(fields, page, page_size, sort_field, sort_dir):
        if calls is not None:
            calls.append((fields, page, page_size, sort_field, sort_dir))
        return ([{"_sc": "row_1", "name": "Alice", "email": "a@example.com"}], 1)

    return {
        "fields": ["name", "email"],
        "views": ["list", "detail"],
        "egress_resource": None,
        "fetch_list": fetch_list,
        "fetch_detail": lambda record_sc, fields: {"_sc": record_sc, "name": "Alice"},
    }


def test_schema_accepts_table_access_matrix_with_four_actions():
    doc = _doc([_table_widget(access_matrix=_matrix())])

    ok, errors = validate_page_ir(doc)

    assert ok, errors


def test_schema_accepts_detail_access_matrix():
    ok, errors = validate_page_ir(_doc([_detail_widget(access_matrix={"read": _matrix()["read"]})]))

    assert ok, errors


@pytest.mark.parametrize(
    "access_matrix",
    [
        {"read": {"required_permissions": []}},
        {"read": {"required_permissions": ["Bulletin.Read"]}},
        {"read": {"required_permissions": ["bulletinread"]}},
        {"read": {"required_permissions": ["bulletin.read"]}, "export": {"required_permissions": ["bulletin.read"]}},
        {},
    ],
)
def test_schema_rejects_bad_widget_access_matrix(access_matrix):
    ok, _errors = validate_page_ir(_doc([_table_widget(access_matrix=access_matrix)]))

    assert not ok


def test_platform_context_ignores_widget_access_matrix_and_does_not_call_evaluator(pir_app):
    calls = []
    evaluator_calls = []
    _register_platform_resource(calls)
    register_access_evaluator("platform", lambda matrix, action, ctx: evaluator_calls.append(action) or False)

    with pir_app.test_request_context("/"):
        rendered = render_page_ir_full(_doc([_table_widget(access_matrix=_matrix())]))

    assert 'id="tbl"' in rendered["html"]
    assert calls
    assert evaluator_calls == []


def test_portal_evaluator_true_renders_and_fetches_rows(pir_app):
    calls = []
    _register_portal_provider(calls)
    register_access_evaluator("portal", lambda matrix, action, ctx: True)

    with pir_app.test_request_context("/"):
        set_render_context("portal", sub_system_sc="ss_123", portal_user={"user_id": 1})
        rendered = render_page_ir_full(_doc([_table_widget(resource="portal:View1234", access_matrix=_matrix())]))
        clear_render_context()

    assert 'id="tbl"' in rendered["html"]
    assert calls


def test_portal_evaluator_false_hides_widget_and_does_not_fetch_rows(pir_app):
    calls = []
    _register_portal_provider(calls)
    register_access_evaluator("portal", lambda matrix, action, ctx: False)

    with pir_app.test_request_context("/"):
        set_render_context("portal", sub_system_sc="ss_123", portal_user={"user_id": 1})
        rendered = render_page_ir_full(_doc([_table_widget(resource="portal:View1234", access_matrix=_matrix())]))
        clear_render_context()

    assert 'id="tbl"' not in rendered["html"]
    assert "Alice" not in rendered["html"]
    assert calls == []


def test_portal_missing_evaluator_with_matrix_fails_closed(pir_app):
    calls = []
    _register_portal_provider(calls)

    with pir_app.test_request_context("/"):
        set_render_context("portal", sub_system_sc="ss_123", portal_user={"user_id": 1})
        rendered = render_page_ir_full(_doc([_table_widget(resource="portal:View1234", access_matrix=_matrix())]))
        clear_render_context()

    assert 'id="tbl"' not in rendered["html"]
    assert calls == []


def test_nested_layout_survives_when_denied_child_is_filtered(pir_app):
    _register_portal_provider([])
    register_access_evaluator("portal", lambda matrix, action, ctx: False)
    doc = _doc([
        {
            "id": "main-grid",
            "type": "layout",
            "columns": 2,
            "gap": 8,
            "children": [
                _table_widget(resource="portal:View1234", access_matrix=_matrix()),
                {"id": "intro", "type": "text", "level": "p", "content_i18n": {"zh-TW": "Visible"}},
            ],
        }
    ])

    with pir_app.test_request_context("/"):
        set_render_context("portal", sub_system_sc="ss_123", portal_user={"user_id": 1})
        rendered = render_page_ir_full(doc)
        clear_render_context()

    assert 'id="main-grid"' in rendered["html"]
    assert 'id="tbl"' not in rendered["html"]
    assert 'id="intro"' in rendered["html"]


def test_only_denied_table_means_has_form_false_and_table_absent(pir_app):
    _register_portal_provider([])
    register_access_evaluator("portal", lambda matrix, action, ctx: False)

    with pir_app.test_request_context("/"):
        set_render_context("portal", sub_system_sc="ss_123", portal_user={"user_id": 1})
        rendered = render_page_ir_full(_doc([_table_widget(resource="portal:View1234", access_matrix=_matrix())]))
        clear_render_context()

    assert rendered["has_form"] is False
    assert 'id="tbl"' not in rendered["html"]


def test_evaluator_exception_fails_closed(pir_app):
    calls = []
    _register_portal_provider(calls)

    def boom(matrix, action, ctx):
        raise RuntimeError("boom")

    register_access_evaluator("portal", boom)

    with pir_app.test_request_context("/"):
        set_render_context("portal", sub_system_sc="ss_123", portal_user={"user_id": 1})
        rendered = render_page_ir_full(_doc([_table_widget(resource="portal:View1234", access_matrix=_matrix())]))
        clear_render_context()

    assert 'id="tbl"' not in rendered["html"]
    assert calls == []
