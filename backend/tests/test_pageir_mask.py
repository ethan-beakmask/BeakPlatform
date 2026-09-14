"""Page IR v3 field visual masking tests."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from flask import Flask
from markupsafe import escape

os.environ.setdefault("SYSTEM_ORG_CODE", "system.local")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.pageir import validate_page_ir
from app.pageir.context import clear_render_context, set_render_context
from app.pageir.masking import (
    FULL_MASK,
    apply_record_masks,
    apply_row_masks,
    mask_value,
    masked_fields,
)
from app.pageir.registry import (
    _ACCESS_EVALUATORS,
    _PROVIDERS,
    _RESOURCES,
    register_access_evaluator,
    register_resource_provider,
)
from app.pageir.renderer import _prepare_detail, _prepare_table


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


@pytest.mark.parametrize(
    ("value", "mask", "expected"),
    [
        ("abcdef", {"type": "partial", "keep_head": 1, "keep_tail": 2}, "a***ef"),
        ("abcdef", {"type": "partial"}, "**cdef"),
        ("secret-value", {"type": "full"}, FULL_MASK),
        ("alice@example.com", {"type": "email"}, "a***e@example.com"),
        ("0912345678", {"type": "phone"}, "0912***678"),
        ("0912-345-678", {"type": "phone"}, "0912-***-678"),
    ],
)
def test_mask_value_outputs_supported_types(value, mask, expected):
    assert mask_value(value, mask) == expected


def test_mask_value_handles_none_empty_and_non_strings():
    assert mask_value(None, {"type": "full"}) is None
    assert mask_value("", {"type": "full"}) == ""
    assert mask_value(123456789, {"type": "partial", "keep_head": 2, "keep_tail": 3}) == "12****789"


def test_partial_short_value_fails_closed_to_full_mask():
    assert mask_value("abc", {"type": "partial", "keep_head": 1, "keep_tail": 2}) == FULL_MASK


def test_email_edge_cases_fail_closed_or_mask_short_local_part():
    assert mask_value("not-an-email", {"type": "email"}) == FULL_MASK
    assert mask_value("ab@example.com", {"type": "email"}) == "***@example.com"


def test_phone_with_too_few_digits_fails_closed():
    assert mask_value("123-4567", {"type": "phone"}) == FULL_MASK


@pytest.mark.parametrize("mask", [{"type": "unknown"}, {}, "bad-mask"])
def test_bad_mask_config_fails_closed(mask):
    assert mask_value("secret", mask) == FULL_MASK


def test_mask_none_returns_original_value():
    assert mask_value("secret", None) == "secret"


def test_apply_row_masks_returns_new_rows_and_preserves_unlisted_keys():
    rows = [{"_sc": "row_1", "email": "alice@example.com", "name": "Alice"}]
    specs = [{"field": "email", "mask": {"type": "email"}}]

    masked = apply_row_masks(rows, specs)

    assert masked == [{"_sc": "row_1", "email": "a***e@example.com", "name": "Alice"}]
    assert rows == [{"_sc": "row_1", "email": "alice@example.com", "name": "Alice"}]
    assert masked is not rows
    assert masked[0] is not rows[0]


def test_apply_record_masks_handles_none_and_masks_copy():
    record = {"_sc": "row_1", "phone": "0912345678"}

    assert apply_record_masks(None, [{"field": "phone", "mask": {"type": "phone"}}]) is None
    assert apply_record_masks(record, [{"field": "phone", "mask": {"type": "phone"}}]) == {
        "_sc": "row_1",
        "phone": "0912***678",
    }
    assert record["phone"] == "0912345678"


def test_masked_fields_extracts_field_names_with_mask():
    specs = [
        {"field": "email", "mask": {"type": "email"}},
        {"field": "phone"},
        {"field": "token", "mask": {}},
        {"mask": {"type": "full"}},
        "bad",
    ]

    assert masked_fields(specs) == {"email", "token"}


def _doc(widgets):
    return {
        "ir_version": 3,
        "page": {
            "id": "mask-page",
            "title_i18n": {"zh-TW": "Mask"},
            "widgets": widgets,
        },
    }


def _matrix():
    rule = {"required_permissions": ["bulletin.read"]}
    return {"read": rule, "create": rule, "update": rule, "delete": rule}


def _table_widget(**overrides):
    widget = {
        "id": "tbl",
        "type": "table",
        "binding": {"resource": "portal:View1234", "view": "list", "fields": ["name", "email"]},
        "columns": [
            {"field": "name", "label_i18n": {"zh-TW": "姓名"}, "sortable": True},
            {
                "field": "email",
                "label_i18n": {"zh-TW": "信箱"},
                "sortable": True,
                "mask": {"type": "email"},
            },
        ],
        "page_size": 20,
        "default_sort": {"field": "email", "dir": "asc"},
        "access_matrix": _matrix(),
    }
    widget.update(overrides)
    return widget


def _detail_widget(**overrides):
    widget = {
        "id": "dtl",
        "type": "detail",
        "binding": {"resource": "portal:View1234", "view": "detail", "fields": ["name", "email"]},
        "fields": [
            {"field": "name", "label_i18n": {"zh-TW": "姓名"}},
            {"field": "email", "label_i18n": {"zh-TW": "信箱"}, "mask": {"type": "email"}},
        ],
    }
    widget.update(overrides)
    return widget


def _resource_config(calls=None):
    def fetch_list(fields, page, page_size, sort_field, sort_dir):
        if calls is not None:
            calls.append((fields, page, page_size, sort_field, sort_dir))
        return ([{"_sc": "row_1", "name": "Alice", "email": "alice@example.com"}], 1)

    return {
        "fields": ["name", "email"],
        "views": ["list", "detail"],
        "egress_resource": None,
        "writable_fields": ["name", "email"],
        "crud": {"create": True, "update": True, "delete": True},
        "fetch_list": fetch_list,
        "fetch_detail": lambda record_sc, fields: {
            "_sc": record_sc,
            "name": "Alice",
            "email": "alice@example.com",
        },
    }


def test_schema_accepts_table_and_detail_masks():
    ok, errors = validate_page_ir(_doc([_table_widget(), _detail_widget()]))

    assert ok, errors


def test_prepare_table_masks_rows_and_blocks_masked_sort_and_form_field(pir_app):
    calls = []
    register_resource_provider("portal", lambda code, ctx: _resource_config(calls))
    register_access_evaluator("portal", lambda matrix, action, ctx: True)

    with pir_app.test_request_context("/?tbl__sort=email&tbl__dir=desc"):
        set_render_context("portal", sub_system_sc="ss_123", portal_user={"user_id": 1})
        prepared = _prepare_table(_table_widget(), {})
        clear_render_context()

    assert prepared["rows"][0]["email"] == "a***e@example.com"
    assert prepared["columns"][1]["masked"] is True
    assert prepared["columns"][1]["sortable"] is False
    assert prepared["form_fields"] == [{"field": "name", "label": "姓名"}]
    assert calls[0][3:] == (None, None)


def test_prepare_detail_masks_record(pir_app):
    register_resource_provider("portal", lambda code, ctx: _resource_config())

    with pir_app.test_request_context("/?dtl__sc=row_1"):
        set_render_context("portal", sub_system_sc="ss_123", portal_user={"user_id": 1})
        prepared = _prepare_detail(_detail_widget(), {})
        clear_render_context()

    assert prepared["record"]["email"] == "a***e@example.com"
