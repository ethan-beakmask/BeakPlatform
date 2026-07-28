"""Page IR v3 N4b-2 table widget CRUD capability tests."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from flask import Flask
from markupsafe import escape

os.environ.setdefault("SYSTEM_ORG_CODE", "system.local")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.pageir import render_page_ir_full
from app.pageir.context import clear_render_context, set_render_context
from app.pageir.registry import (
    _ACCESS_EVALUATORS,
    _PROVIDERS,
    _RESOURCES,
    register_access_evaluator,
    register_resource,
    register_resource_provider,
)
from app.pageir.renderer import _prepare_table


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
            "id": "n4b2-page",
            "title_i18n": {"zh-TW": "N4b-2"},
            "widgets": widgets,
        },
    }


def _matrix(**overrides):
    rule = {"groups": ["VIP"], "min_level": "GUEST"}
    matrix = {
        "read": rule,
        "create": rule,
        "update": rule,
        "delete": rule,
    }
    matrix.update(overrides)
    return matrix


def _table_widget(resource="fake", **overrides):
    widget = {
        "id": "tbl",
        "type": "table",
        "binding": {"resource": resource, "view": "list", "fields": ["name", "email", "note"]},
        "columns": [
            {"field": "name", "label_i18n": {"zh-TW": "姓名"}, "sortable": True},
            {"field": "email", "label_i18n": {"zh-TW": "信箱"}},
            {"field": "note", "label_i18n": {"zh-TW": "備註"}},
        ],
        "page_size": 20,
    }
    widget.update(overrides)
    return widget


def _resource_config(**overrides):
    def fetch_list(fields, page, page_size, sort_field, sort_dir):
        return ([{"_sc": "row_1", "name": "Alice", "email": "a@example.com", "note": "Hi"}], 1)

    config = {
        "fields": ["name", "email", "note"],
        "views": ["list", "detail"],
        "egress_resource": None,
        "writable_fields": ["name", "note"],
        "crud": {"create": True, "update": True, "delete": True},
        "fetch_list": fetch_list,
        "fetch_detail": lambda record_sc, fields: {"_sc": record_sc, "name": "Alice"},
    }
    config.update(overrides)
    return config


def _register_platform_resource(**overrides):
    register_resource("fake", _resource_config(**overrides))


def _register_portal_provider(**overrides):
    register_resource_provider("portal", lambda code, ctx: _resource_config(**overrides))


def test_platform_context_forces_caps_false_and_has_no_create_button(pir_app):
    _register_platform_resource()
    register_access_evaluator("platform", lambda matrix, action, ctx: True)
    widget = _table_widget(access_matrix=_matrix())

    with pir_app.test_request_context("/"):
        prepared = _prepare_table(widget, {})
        rendered = render_page_ir_full(_doc([widget]))

    assert prepared["caps"] == {"create": False, "update": False, "delete": False}
    assert 'data-pir-create="tbl"' not in rendered["html"]
    assert "pir-table-toolbar" not in rendered["html"]
    assert ">新增<" not in rendered["html"]


def test_portal_allows_all_caps_and_outputs_crud_controls(pir_app):
    _register_portal_provider()
    register_access_evaluator("portal", lambda matrix, action, ctx: True)
    widget = _table_widget(resource="portal:View1234", access_matrix=_matrix())

    with pir_app.test_request_context("/"):
        set_render_context("portal", sub_system_sc="ss_123", portal_user={"user_id": 1})
        prepared = _prepare_table(widget, {})
        rendered = render_page_ir_full(_doc([widget]))
        clear_render_context()

    assert prepared["caps"] == {"create": True, "update": True, "delete": True}
    assert 'data-pir-create="tbl"' in rendered["html"]
    assert 'data-pir-edit="tbl"' in rendered["html"]
    assert 'data-pir-delete="tbl"' in rendered["html"]
    assert 'data-pir-form-fields="tbl"' in rendered["html"]


def test_resource_crud_false_disables_create_even_when_evaluator_allows(pir_app):
    _register_portal_provider(crud={"create": False, "update": True, "delete": True})
    register_access_evaluator("portal", lambda matrix, action, ctx: True)
    widget = _table_widget(resource="portal:View1234", access_matrix=_matrix())

    with pir_app.test_request_context("/"):
        set_render_context("portal", sub_system_sc="ss_123", portal_user={"user_id": 1})
        prepared = _prepare_table(widget, {})
        rendered = render_page_ir_full(_doc([widget]))
        clear_render_context()

    assert prepared["caps"]["create"] is False
    assert 'data-pir-create="tbl"' not in rendered["html"]


def test_create_evaluator_false_hides_create_button(pir_app):
    _register_portal_provider()
    register_access_evaluator("portal", lambda matrix, action, ctx: action in matrix)
    matrix = _matrix()
    del matrix["create"]
    widget = _table_widget(resource="portal:View1234", access_matrix=matrix)

    with pir_app.test_request_context("/"):
        set_render_context("portal", sub_system_sc="ss_123", portal_user={"user_id": 1})
        prepared = _prepare_table(widget, {})
        rendered = render_page_ir_full(_doc([widget]))
        clear_render_context()

    assert prepared["caps"]["create"] is False
    assert 'data-pir-create="tbl"' not in rendered["html"]


def test_missing_portal_evaluator_forces_caps_false(pir_app):
    _register_portal_provider()
    widget = _table_widget(resource="portal:View1234", access_matrix=_matrix())

    with pir_app.test_request_context("/"):
        set_render_context("portal", sub_system_sc="ss_123", portal_user={"user_id": 1})
        prepared = _prepare_table(widget, {})
        clear_render_context()

    assert prepared["caps"] == {"create": False, "update": False, "delete": False}


def test_form_fields_use_binding_writable_intersection_and_column_labels(pir_app):
    _register_portal_provider(writable_fields=["email", "note"])
    register_access_evaluator("portal", lambda matrix, action, ctx: action in {"read", "create"})
    widget = _table_widget(
        resource="portal:View1234",
        access_matrix=_matrix(),
        binding={"resource": "portal:View1234", "view": "list", "fields": ["name", "email", "ghost"]},
        columns=[
            {"field": "name", "label_i18n": {"zh-TW": "姓名"}},
            {"field": "email", "label_i18n": {"zh-TW": "信箱"}},
            {"field": "ghost", "label_i18n": {"zh-TW": "幽靈"}},
        ],
    )
    _PROVIDERS["portal"] = lambda code, ctx: _resource_config(
        fields=["name", "email", "ghost"],
        writable_fields=["email", "ghost"],
    )

    with pir_app.test_request_context("/"):
        set_render_context("portal", sub_system_sc="ss_123", portal_user={"user_id": 1})
        prepared = _prepare_table(widget, {})
        clear_render_context()

    assert prepared["form_fields"] == [
        {"field": "email", "label": "信箱"},
        {"field": "ghost", "label": "幽靈"},
    ]
