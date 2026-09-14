"""Page IR v3 P3 測試。"""
from __future__ import annotations

import os

import pytest
from flask import Flask
from flask_login import LoginManager

from app.api.pageir_meta import pageir_meta_bp
from app.pageir import PageIrRenderError, render_page_ir_full
from app.pageir.registry import list_actions, list_resources, register_action, register_resource

os.environ.setdefault("SYSTEM_ORG_CODE", "system.local")


@pytest.fixture
def pir_app():
    app = Flask(__name__, template_folder="../app/templates")
    app.secret_key = "test-secret"
    app.jinja_env.globals["_"] = lambda text, **kwargs: text % kwargs if kwargs else text
    app.jinja_env.globals["egress_visibility"] = lambda resource, context, field: "clear"
    app.jinja_env.globals["egress_value"] = lambda resource, context, record_sc, field, value: value
    app.jinja_env.filters["tz_format"] = lambda value, fmt="%Y-%m-%d %H:%M": "DATE"
    return app


def _doc(widgets):
    return {
        "ir_version": 3,
        "page": {
            "id": "p3-page",
            "title_i18n": {"zh-TW": "P3"},
            "widgets": widgets,
        },
    }


def _form_widget(**overrides):
    widget = {
        "id": "frm",
        "type": "form",
        "formio_schema": {"display": "form", "components": [{"key": "name", "label": "Name"}]},
    }
    widget.update(overrides)
    return widget


def test_render_page_ir_full_reports_form_and_schema_script(pir_app):
    with pir_app.test_request_context("/"):
        rendered = render_page_ir_full(_doc([_form_widget()]))

    assert rendered["has_form"] is True
    assert 'data-pir-form-id="frm"' in rendered["html"]
    assert 'data-pir-form-schema="frm"' in rendered["html"]
    assert "formio_schema" not in rendered["html"]
    assert "表單元件將於後續版本啟用" not in rendered["html"]

    with pir_app.test_request_context("/"):
        no_form = render_page_ir_full(_doc([
            {"id": "txt", "type": "text", "level": "p", "content_i18n": {"zh-TW": "文字"}}
        ]))
    assert no_form["has_form"] is False


def test_form_submit_action_fail_closed_and_url_rendered(pir_app):
    actions_stub = {
        "id": "submit-action",
        "type": "actions",
        "buttons": [
            {
                "id": "btn-submit",
                "label_i18n": {"zh-TW": "送出"},
                "permission": "renderer.submit",
                "action_ref": "submit-action",
            }
        ],
    }
    with pir_app.test_request_context("/"):
        with pytest.raises(PageIrRenderError):
            render_page_ir_full(_doc([_form_widget(submit_action_ref="submit-action"), actions_stub]))

    register_action("submit-action", {"url": "/api/submit", "method": "POST"})
    from app.services import capability_service

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(capability_service, "user_can", lambda permission: False)
    with pir_app.test_request_context("/"):
        rendered = render_page_ir_full(_doc([_form_widget(submit_action_ref="submit-action"), actions_stub]))
    monkeypatch.undo()

    assert 'data-pir-submit-url="/api/submit"' in rendered["html"]


def test_registry_lists_shallow_non_callable_descriptions():
    register_resource(
        "p3-resource",
        {
            "views": ["list"],
            "fields": ["name"],
            "egress_resource": "user",
            "fetch_list": lambda *args: ([], 0),
        },
    )
    register_action("p3-action", {"url": "/api/action", "handler": lambda: None})

    resources = list_resources()
    actions = list_actions()

    resource = next(item for item in resources if item["code"] == "p3-resource")
    assert resource == {
        "code": "p3-resource",
        "views": ["list"],
        "fields": ["name"],
        "egress_resource": "user",
    }
    assert "p3-action" in actions
    assert all(not callable(value) for item in resources for value in item.values())


def test_meta_api_requires_login_or_redirect():
    app = Flask(__name__)
    app.secret_key = "test-secret"
    login_manager = LoginManager(app)

    @login_manager.user_loader
    def load_user(user_id):
        return None

    app.register_blueprint(pageir_meta_bp)

    res = app.test_client().get("/api/pageir/meta")

    assert res.status_code in {401, 302}
