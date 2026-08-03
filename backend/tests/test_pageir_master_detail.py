"""Page IR v3 master_detail backend tests."""
from __future__ import annotations

import os

import pytest
from flask import Flask
from markupsafe import escape

os.environ.setdefault("SYSTEM_ORG_CODE", "system.local")

from app.pageir import PageIrRenderError, validate_page_ir
from app.pageir.context import clear_render_context, set_render_context
from app.pageir.registry import (
    _ACCESS_EVALUATORS,
    _PROVIDERS,
    _RESOURCES,
    register_access_evaluator,
    register_resource,
    register_resource_provider,
)
from app.pageir.renderer import _prepare_master_detail


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
    clear_render_context()
    _RESOURCES.clear()
    _RESOURCES.update(old_resources)
    _PROVIDERS.clear()
    _PROVIDERS.update(old_providers)
    _ACCESS_EVALUATORS.clear()
    _ACCESS_EVALUATORS.update(old_evaluators)


def _matrix():
    rule = {"required_permissions": ["bulletin.read"]}
    return {"read": rule, "create": rule, "update": rule}


def _widget(**overrides):
    widget = {
        "id": "md",
        "type": "master_detail",
        "master": {
            "binding": {
                "resource": "portal:MasterView",
                "view": "detail",
                "fields": ["name", "phone"],
            },
            "fields": [
                {"field": "name", "label_i18n": {"zh-TW": "姓名"}},
                {"field": "phone", "label_i18n": {"zh-TW": "電話"}},
            ],
            "layout_columns": 2,
        },
        "detail": {
            "binding": {
                "resource": "portal:DetailView",
                "view": "list",
                "fields": ["service", "note", "customer_id"],
            },
            "foreign_key": "customer_id",
            "columns": [
                {"field": "service", "label_i18n": {"zh-TW": "服務"}},
                {"field": "note", "label_i18n": {"zh-TW": "備註"}},
            ],
            "page_size": 20,
        },
        "access_matrix": _matrix(),
    }
    widget.update(overrides)
    return widget


def _doc(widget):
    return {
        "ir_version": 3,
        "page": {
            "id": "md-page",
            "title_i18n": {"zh-TW": "主細表"},
            "widgets": [widget],
        },
    }


def _resource_config(kind, **overrides):
    if kind == "master":
        config = {
            "fields": ["name", "phone"],
            "writable_fields": ["name", "phone"],
            "views": ["detail", "list"],
            "crud": {"create": True, "update": True, "delete": False},
            "egress_resource": None,
            "fetch_detail": lambda record_sc, fields: (
                {"_sc": record_sc, "name": "Alice", "phone": "0912345678"}
                if record_sc == "customer_1"
                else None
            ),
        }
    else:
        config = {
            "fields": ["service", "note", "customer_id"],
            "writable_fields": ["service", "note", "customer_id"],
            "views": ["detail", "list"],
            "crud": {"create": True, "update": False, "delete": False},
            "egress_resource": None,
            "fetch_detail": lambda record_sc, fields: None,
            "fetch_list": lambda fields, page, page_size, sort_field, sort_dir: ([], 0),
        }
    config.update(overrides)
    return config


def _register_portal_resources(master_overrides=None, detail_overrides=None):
    master_overrides = master_overrides or {}
    detail_overrides = detail_overrides or {}

    def provider(code, ctx):
        if code == "portal:MasterView":
            return _resource_config("master", **master_overrides)
        if code == "portal:DetailView":
            return _resource_config("detail", **detail_overrides)
        return None

    register_resource_provider("portal", provider)


def _set_portal_context():
    register_access_evaluator("portal", lambda matrix, action, ctx: action in (matrix or {}))
    set_render_context(
        "portal",
        sub_system_sc="ss_123",
        portal_user={"user_id": 1},
        path_id="portal-path",
        page_sc="page_123",
    )


def test_schema_accepts_master_detail_and_requires_foreign_key():
    ok, errors = validate_page_ir(_doc(_widget()))
    assert ok is True
    assert errors == []

    invalid = _widget()
    del invalid["detail"]["foreign_key"]
    ok, errors = validate_page_ir(_doc(invalid))
    assert ok is False
    assert any(error["code"] == "oneOf" for error in errors)


def test_foreign_key_must_be_writable(pir_app):
    _register_portal_resources(detail_overrides={"writable_fields": ["service", "note"]})

    with pir_app.test_request_context("/page"):
        _set_portal_context()
        with pytest.raises(PageIrRenderError, match="foreign_key is not writable"):
            _prepare_master_detail(_widget(), {})


def test_master_fields_and_detail_columns_must_stay_in_whitelist(pir_app):
    _register_portal_resources()

    bad_master = _widget()
    bad_master["master"]["fields"].append({"field": "secret", "label_i18n": {"zh-TW": "秘密"}})
    with pir_app.test_request_context("/page"):
        _set_portal_context()
        with pytest.raises(PageIrRenderError, match="master fields exceed whitelist"):
            _prepare_master_detail(bad_master, {})

    bad_detail = _widget()
    bad_detail["detail"]["columns"].append({"field": "secret", "label_i18n": {"zh-TW": "秘密"}})
    with pir_app.test_request_context("/page"):
        _set_portal_context()
        with pytest.raises(PageIrRenderError, match="Table column exceeds whitelist"):
            _prepare_master_detail(bad_detail, {})


def test_no_sc_uses_new_mode(pir_app):
    _register_portal_resources()

    with pir_app.test_request_context("/page"):
        _set_portal_context()
        prepared = _prepare_master_detail(_widget(), {})

    assert prepared["mode"] == "new"
    assert prepared["master"]["record"] is None


def test_missing_master_record_does_not_leak_existence(pir_app):
    _register_portal_resources()

    with pir_app.test_request_context("/page?md__sc=other_customer"):
        _set_portal_context()
        prepared = _prepare_master_detail(_widget(), {})

    assert prepared["mode"] == "new"
    assert prepared["master"]["record"] is None


def test_master_editable_false_is_readonly(pir_app):
    _register_portal_resources()
    widget = _widget()
    widget["master"]["editable"] = False

    with pir_app.test_request_context("/page?md__sc=customer_1"):
        _set_portal_context()
        prepared = _prepare_master_detail(widget, {})

    assert prepared["mode"] == "readonly"
    assert prepared["master"]["record"]["name"] == "Alice"


def test_history_without_fetch_related_is_disabled(pir_app):
    _register_portal_resources()
    widget = _widget(history={"enabled": True, "page_size": 10})

    with pir_app.test_request_context("/page?md__sc=customer_1"):
        _set_portal_context()
        prepared = _prepare_master_detail(widget, {})

    assert prepared["history"]["enabled"] is False


def test_platform_world_has_no_submit_url(pir_app):
    register_resource("master", _resource_config("master"))
    register_resource("detail", _resource_config("detail"))
    widget = _widget(
        master={
            **_widget()["master"],
            "binding": {"resource": "master", "view": "detail", "fields": ["name", "phone"]},
        },
        detail={
            **_widget()["detail"],
            "binding": {"resource": "detail", "view": "list", "fields": ["service", "note", "customer_id"]},
        },
    )

    with pir_app.test_request_context("/page"):
        prepared = _prepare_master_detail(widget, {})

    assert prepared["submit_url"] is None


def test_history_fetch_related_uses_foreign_key_dynamic_filter_inputs(pir_app):
    calls = []

    def fetch_related(filter_field, filter_value, fields, page, page_size, sort_field, sort_dir):
        calls.append((filter_field, filter_value, fields, page, page_size, sort_field, sort_dir))
        return ([{"_sc": "svc_1", "service": "Call", "note": "Done"}], 1)

    _register_portal_resources(detail_overrides={"fetch_related": fetch_related})
    widget = _widget(
        history={
            "enabled": True,
            "page_size": 7,
            "default_sort": {"field": "service", "dir": "desc"},
        }
    )

    with pir_app.test_request_context("/page?md__sc=customer_1&md__hpage=2"):
        _set_portal_context()
        prepared = _prepare_master_detail(widget, {})

    assert prepared["history"]["enabled"] is True
    assert prepared["history"]["rows"] == [{"_sc": "svc_1", "service": "Call", "note": "Done"}]
    assert calls == [
        (
            "customer_id",
            "customer_1",
            ["service", "note", "customer_id"],
            2,
            7,
            "service",
            "desc",
        )
    ]
