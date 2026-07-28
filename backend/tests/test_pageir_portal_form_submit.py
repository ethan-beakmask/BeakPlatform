"""Page IR portal form submit foundation tests."""
from __future__ import annotations

import os

import pytest
from flask import Flask

os.environ.setdefault("SYSTEM_ORG_CODE", "system.local")

from app.pageir import PageIrRenderError, render_page_ir_full, validate_page_ir
from app.pageir.context import clear_render_context, set_render_context
from app.pageir.registry import (
    _ACTIONS,
    _ACCESS_EVALUATORS,
    _PORTAL_ACTIONS,
    get_action,
    get_portal_action,
    register_access_evaluator,
    register_portal_action,
)


@pytest.fixture
def pir_app():
    app = Flask(__name__, template_folder="../app/templates")
    app.secret_key = "test-secret"
    app.jinja_env.globals["_"] = lambda text, **kwargs: text % kwargs if kwargs else text
    app.jinja_env.globals["egress_visibility"] = lambda resource, context, field: "clear"
    app.jinja_env.globals["egress_value"] = lambda resource, context, record_sc, field, value: value
    app.jinja_env.filters["tz_format"] = lambda value, fmt="%Y-%m-%d %H:%M": "DATE"

    @app.route("/submit/<path_id>/<page_sc>/<widget_id>", endpoint="portal_widget_submit")
    def portal_widget_submit(path_id, page_sc, widget_id):
        return ""

    return app


@pytest.fixture(autouse=True)
def reset_registries():
    old_actions = dict(_ACTIONS)
    old_portal_actions = dict(_PORTAL_ACTIONS)
    old_evaluators = dict(_ACCESS_EVALUATORS)
    _ACTIONS.clear()
    _PORTAL_ACTIONS.clear()
    _ACCESS_EVALUATORS.clear()
    yield
    _ACTIONS.clear()
    _ACTIONS.update(old_actions)
    _PORTAL_ACTIONS.clear()
    _PORTAL_ACTIONS.update(old_portal_actions)
    _ACCESS_EVALUATORS.clear()
    _ACCESS_EVALUATORS.update(old_evaluators)


def _doc(widget):
    return {
        "ir_version": 3,
        "page": {
            "id": "portal-form-page",
            "title_i18n": {"zh-TW": "Portal Form"},
            "widgets": [widget],
        },
    }


def _form_widget(**overrides):
    widget = {
        "id": "frm",
        "type": "form",
        "formio_schema": {
            "display": "form",
            "components": [{"key": "name", "label": "Name", "input": True}],
        },
        "submit_action_ref": "portal.form.submit",
    }
    widget.update(overrides)
    return widget


def _read_only_matrix():
    return {"read": {"groups": None, "min_level": "GUEST"}}


def test_prepare_form_portal_without_declared_create_is_readonly(pir_app):
    register_portal_action("portal.form.submit", {"endpoint": "portal_widget_submit"})
    register_access_evaluator("portal", lambda matrix, action, ctx: action in matrix)

    with pir_app.test_request_context("/"):
        set_render_context(
            "portal",
            sub_system_sc="ss_123",
            portal_user={"user_id": 1},
            path_id="pub12345",
            page_sc="page123456",
        )
        rendered = render_page_ir_full(_doc(_form_widget(
            mapping_ref="map123456",
            access_matrix=_read_only_matrix(),
        )))
        clear_render_context()

    assert 'data-pir-submit-url=' not in rendered["html"]


def test_prepare_form_portal_without_mapping_ref_is_readonly(pir_app):
    register_portal_action("portal.form.submit", {"endpoint": "portal_widget_submit"})
    register_access_evaluator("portal", lambda matrix, action, ctx: True)

    with pir_app.test_request_context("/"):
        set_render_context(
            "portal",
            sub_system_sc="ss_123",
            portal_user={"user_id": 1},
            path_id="pub12345",
            page_sc="page123456",
        )
        rendered = render_page_ir_full(_doc(_form_widget(
            access_matrix={"create": {"groups": None, "min_level": "GUEST"}},
        )))
        clear_render_context()

    assert 'data-pir-submit-url=' not in rendered["html"]


def test_prepare_form_platform_unregistered_action_still_raises(pir_app):
    with pir_app.test_request_context("/"):
        with pytest.raises(PageIrRenderError):
            render_page_ir_full(_doc(_form_widget(submit_action_ref="missing.action")))


def test_portal_and_platform_action_registries_do_not_fallback(pir_app):
    register_portal_action("portal.form.submit", {"endpoint": "portal_widget_submit"})
    _ACTIONS["platform.action"] = {"url": "/platform"}

    with pir_app.test_request_context("/"):
        assert get_portal_action("portal.form.submit") is None

        set_render_context("portal", sub_system_sc="ss_123", portal_user={"user_id": 1})
        assert get_action("platform.action") is None
        clear_render_context()


def test_schema_accepts_form_mapping_ref_and_access_matrix():
    ok, errors = validate_page_ir(_doc(_form_widget(
        mapping_ref="map123456",
        access_matrix={"create": {"groups": None, "min_level": "GUEST"}},
    )))

    assert ok, errors


def test_schema_rejects_invalid_form_mapping_ref():
    ok, _errors = validate_page_ir(_doc(_form_widget(
        mapping_ref="bad",
        access_matrix={"create": {"groups": None, "min_level": "GUEST"}},
    )))

    assert not ok
