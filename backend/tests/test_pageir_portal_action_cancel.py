"""Page IR portal cancel action tests."""
from __future__ import annotations

import os

import pytest
from flask import Blueprint, Flask

os.environ.setdefault("SYSTEM_ORG_CODE", "system.local")

from app.pageir import validate_page_ir
from app.pageir.context import clear_render_context, set_render_context
from app.pageir.registry import (
    _ACTIONS,
    _ACCESS_EVALUATORS,
    _PORTAL_ACTIONS,
    register_access_evaluator,
    register_portal_action,
)
from app.pageir.renderer import (
    PORTAL_RECORD_PLACEHOLDER,
    _action_url,
    _prepare_action_buttons,
)


@pytest.fixture
def pir_app():
    app = Flask(__name__, template_folder="../app/templates")
    app.secret_key = "test-secret"

    bp = Blueprint("nocode_public_portal", __name__)

    @bp.route(
        "/<path_id>/api/pages/<page_sc>/widgets/<widget_id>/submissions/<record_sc>/cancel",
        methods=["POST"],
        endpoint="portal_widget_cancel_submission",
    )
    def portal_widget_cancel_submission(path_id, page_sc, widget_id, record_sc):
        return ""

    app.register_blueprint(bp)
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


def _update_matrix():
    return {"update": {"required_permissions": ["bulletin.update"]}}


def _actions_widget(**overrides):
    widget = {
        "id": "acts",
        "type": "actions",
        "access_matrix": _update_matrix(),
        "buttons": [
            {
                "id": "cancel",
                "label_i18n": {"zh-TW": "撤單"},
                "style": "danger",
                "action_ref": "portal.form.cancel",
            }
        ],
    }
    widget.update(overrides)
    return widget


def _doc(widget):
    return {
        "ir_version": 3,
        "page": {
            "id": "portal-actions-page",
            "title_i18n": {"zh-TW": "Portal Actions"},
            "widgets": [widget],
        },
    }


def _set_portal_context():
    set_render_context(
        "portal",
        sub_system_sc="ss_123",
        portal_user={"user_id": 1},
        path_id="pub12345",
        page_sc="page123456",
    )


def test_prepare_portal_cancel_row_action_renders_button(pir_app):
    register_portal_action("portal.form.cancel", {
        "endpoint": "nocode_public_portal.portal_widget_cancel_submission",
        "method": "POST",
        "requires_record": True,
        "row_flag": "_can_cancel",
        "confirm": True,
    })
    register_access_evaluator("portal", lambda matrix, action, ctx: action in matrix)

    with pir_app.test_request_context("/"):
        _set_portal_context()
        try:
            buttons = _prepare_action_buttons(_actions_widget(), row_context=True)
        finally:
            clear_render_context()

    assert buttons == [{
        "id": "cancel",
        "label": "撤單",
        "style": "danger",
        "url": "/pub12345/api/pages/page123456/widgets/acts/submissions/__PIR_RECORD_SC__/cancel",
        "method": "POST",
        "confirm": True,
        "requires_record": True,
        "row_flag": "_can_cancel",
    }]
    assert PORTAL_RECORD_PLACEHOLDER in buttons[0]["url"]


def test_prepare_portal_cancel_without_update_access_returns_empty(pir_app):
    register_portal_action("portal.form.cancel", {
        "endpoint": "nocode_public_portal.portal_widget_cancel_submission",
        "method": "POST",
        "requires_record": True,
    })
    register_access_evaluator("portal", lambda matrix, action, ctx: False)

    with pir_app.test_request_context("/"):
        _set_portal_context()
        try:
            buttons = _prepare_action_buttons(_actions_widget(), row_context=True)
        finally:
            clear_render_context()

    assert buttons == []


def test_prepare_portal_unregistered_action_returns_empty_without_raise(pir_app):
    register_access_evaluator("portal", lambda matrix, action, ctx: action in matrix)

    with pir_app.test_request_context("/"):
        _set_portal_context()
        try:
            buttons = _prepare_action_buttons(_actions_widget(), row_context=True)
        finally:
            clear_render_context()

    assert buttons == []


def test_prepare_portal_record_action_outside_row_context_returns_empty(pir_app):
    register_portal_action("portal.form.cancel", {
        "endpoint": "nocode_public_portal.portal_widget_cancel_submission",
        "method": "POST",
        "requires_record": True,
    })
    register_access_evaluator("portal", lambda matrix, action, ctx: action in matrix)

    with pir_app.test_request_context("/"):
        _set_portal_context()
        try:
            buttons = _prepare_action_buttons(_actions_widget(), row_context=False)
        finally:
            clear_render_context()

    assert buttons == []


def test_prepare_platform_action_without_permission_returns_empty(pir_app):
    with pir_app.test_request_context("/"):
        buttons = _prepare_action_buttons(_actions_widget(access_matrix=None), row_context=True)

    assert buttons == []


def test_action_url_replaces_portal_placeholder_or_appends_query():
    assert _action_url(f"/cancel/{PORTAL_RECORD_PLACEHOLDER}", "rec 1/2") == "/cancel/rec%201%2F2"
    assert _action_url("/platform/action", "rec123") == "/platform/action?sc=rec123"
    assert _action_url("/platform/action?x=1", "rec123") == "/platform/action?x=1&sc=rec123"


def test_schema_allows_action_without_permission_and_actions_access_matrix():
    ok, errors = validate_page_ir(_doc(_actions_widget()))

    assert ok is True
    assert errors == []
