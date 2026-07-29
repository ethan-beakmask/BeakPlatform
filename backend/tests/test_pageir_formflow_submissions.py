"""Page IR formflow portal submissions resource tests."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask
from flask_babel import Babel

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("SYSTEM_ORG_CODE", "system.local")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db
from app.pageir import validate_page_ir
from app.pageir.context import clear_render_context, set_render_context
from app.pageir.registry import _PROVIDERS, get_resource

from modules.nocode_builder.services import pageir_formflow_resources as formflow_resources
from modules.form_workflow.models import (
    FwFormInstance,
    FwNodeExecutionQueue,
    FwWorkflowInstance,
)


@pytest.fixture(autouse=True)
def reset_formflow_provider():
    old_providers = dict(_PROVIDERS)
    _PROVIDERS.clear()
    yield
    _PROVIDERS.clear()
    _PROVIDERS.update(old_providers)


@pytest.fixture
def mini_app(tmp_path):
    app = Flask(__name__, template_folder="../app/templates")
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'formflow.db'}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={},
    )
    db.init_app(app)
    Babel(app)
    with app.app_context():
        for table in (
            FwFormInstance.__table__,
            FwWorkflowInstance.__table__,
            FwNodeExecutionQueue.__table__,
        ):
            table.create(db.engine, checkfirst=True)
        yield app
        db.session.remove()
        for table in (
            FwNodeExecutionQueue.__table__,
            FwWorkflowInstance.__table__,
            FwFormInstance.__table__,
        ):
            table.drop(db.engine, checkfirst=True)


class FakeQuery:
    def __init__(self, value):
        self.value = value

    def filter_by(self, **kwargs):
        return self

    def first(self):
        return self.value


def _doc(resource="formflow:submissions"):
    return {
        "ir_version": 3,
        "page": {
            "id": "portal-submissions",
            "title_i18n": {"zh-TW": "我送出的表單"},
            "widgets": [{
                "id": "tbl",
                "type": "table",
                "binding": {
                    "resource": resource,
                    "view": "list",
                    "fields": ["serial_number", "status_label", "submitted_at"],
                },
                "columns": [
                    {"field": "serial_number", "label_i18n": {"zh-TW": "表單編號"}},
                    {"field": "status_label", "label_i18n": {"zh-TW": "狀態"}},
                    {"field": "submitted_at", "label_i18n": {"zh-TW": "送出時間"}},
                ],
                "page_size": 20,
            }],
        },
    }


def _patch_sub_system(monkeypatch, sub_system):
    monkeypatch.setattr(
        formflow_resources,
        "DcSubSystem",
        SimpleNamespace(query=FakeQuery(sub_system)),
    )


def _seed_submissions():
    sub_system = SimpleNamespace(
        secure_code="sub_formflow_000000000001",
        org_secure_code="org_formflow_000000000001",
        code="PORTAL",
        name="Portal",
        is_active=True,
        is_deleted=False,
    )

    now = datetime(2026, 7, 29, 1, 0, 0)
    form_a = FwFormInstance(
        secure_code="fi_formflow_user_a_000001",
        org_secure_code=sub_system.org_secure_code,
        form_template_secure_code="tmpl_formflow_00000000001",
        workflow_template_secure_code="wf_tpl_formflow_00000001",
        workflow_instance_secure_code="wi_formflow_user_a_000001",
        form_data={"field": "a"},
        serial_number="FORM-A",
        subject="User A submission",
        submitted_at=now,
        is_deleted=False,
    )
    wi_a = FwWorkflowInstance(
        secure_code="wi_formflow_user_a_000001",
        org_secure_code=sub_system.org_secure_code,
        form_instance_secure_code=form_a.secure_code,
        workflow_template_secure_code="wf_tpl_formflow_00000001",
        execution_code="PROC-A",
        status="RUNNING",
        nocode_sub_system_sc=sub_system.secure_code,
        nocode_user_ref="u:1",
        is_deleted=False,
    )
    q_later = FwNodeExecutionQueue(
        secure_code="q_formflow_user_a_later01",
        org_secure_code=sub_system.org_secure_code,
        workflow_instance_secure_code=wi_a.secure_code,
        form_instance_secure_code=form_a.secure_code,
        node_id="approve-2",
        node_type="Approve",
        node_name="Second approval",
        status="WAITING",
        scheduled_at=now + timedelta(minutes=5),
        is_deleted=False,
    )
    q_first = FwNodeExecutionQueue(
        secure_code="q_formflow_user_a_first01",
        org_secure_code=sub_system.org_secure_code,
        workflow_instance_secure_code=wi_a.secure_code,
        form_instance_secure_code=form_a.secure_code,
        node_id="approve-1",
        node_type="Approve",
        node_name="First approval",
        status="WAITING",
        scheduled_at=now,
        is_deleted=False,
    )

    form_b = FwFormInstance(
        secure_code="fi_formflow_user_b_000001",
        org_secure_code=sub_system.org_secure_code,
        form_template_secure_code="tmpl_formflow_00000000001",
        workflow_template_secure_code="wf_tpl_formflow_00000001",
        workflow_instance_secure_code="wi_formflow_user_b_000001",
        form_data={"field": "b"},
        serial_number="FORM-B",
        subject="User B submission",
        submitted_at=now + timedelta(minutes=1),
        is_deleted=False,
    )
    wi_b = FwWorkflowInstance(
        secure_code="wi_formflow_user_b_000001",
        org_secure_code=sub_system.org_secure_code,
        form_instance_secure_code=form_b.secure_code,
        workflow_template_secure_code="wf_tpl_formflow_00000001",
        execution_code="PROC-B",
        status="COMPLETED",
        nocode_sub_system_sc=sub_system.secure_code,
        nocode_user_ref="u:2",
        is_deleted=False,
    )
    db.session.add_all([form_a, wi_a, q_later, q_first, form_b, wi_b])
    db.session.commit()
    return sub_system, form_a, form_b


def test_formflow_resource_is_none_in_platform_world(mini_app):
    formflow_resources.init_formflow_pageir_resources()

    with mini_app.test_request_context("/"):
        assert get_resource("formflow:submissions") is None


def test_resolver_returns_none_without_portal_user_or_sub_system():
    assert formflow_resources._resolve_formflow_resource(
        "formflow:submissions",
        {"world": "portal", "sub_system_sc": "sub_formflow_000000000001"},
    ) is None
    assert formflow_resources._resolve_formflow_resource(
        "formflow:submissions",
        {"world": "portal", "portal_user": {"user_id": 1}},
    ) is None


def test_resolver_returns_readonly_crud_callables(mini_app, monkeypatch):
    sub_system, _form_a, _form_b = _seed_submissions()
    _patch_sub_system(monkeypatch, sub_system)
    resource = formflow_resources._resolve_formflow_resource(
        "formflow:submissions",
        {"world": "portal", "sub_system_sc": sub_system.secure_code, "portal_user": {"user_id": 1}},
    )

    assert resource is not None
    assert resource["crud"] == {"create": False, "update": False, "delete": False}
    assert resource["writable_fields"] == []
    assert resource["create_row"]({}) == (False, "readonly")
    assert resource["update_row"]("anything", {}) == (False, "readonly")
    assert resource["delete_row"]("anything") == (False, "readonly")


def test_resolver_rejects_other_formflow_code():
    assert formflow_resources._resolve_formflow_resource(
        "formflow:other",
        {"world": "portal", "sub_system_sc": "sub_formflow_000000000001", "portal_user": {"user_id": 1}},
    ) is None


def test_schema_accepts_formflow_submissions_binding():
    ok, errors = validate_page_ir(_doc())
    assert ok, errors


def test_different_nocode_user_refs_cannot_read_each_other(mini_app, monkeypatch):
    sub_system, form_a, form_b = _seed_submissions()
    _patch_sub_system(monkeypatch, sub_system)
    formflow_resources.init_formflow_pageir_resources()

    with mini_app.test_request_context("/"):
        set_render_context(
            "portal",
            sub_system_sc=sub_system.secure_code,
            portal_user={"user_id": 1},
        )
        resource = get_resource("formflow:submissions")
        clear_render_context()

    assert resource is not None
    rows, total = resource["fetch_list"](
        ["serial_number", "execution_code", "status_label", "current_step", "submitted_at"],
        1,
        20,
        "submitted_at",
        "desc",
    )
    assert total == 1
    assert rows == [{
        "_sc": form_a.secure_code,
        "serial_number": "FORM-A",
        "execution_code": "PROC-A",
        "status_label": "審核中",
        "current_step": "First approval",
        "submitted_at": form_a.submitted_at,
    }]
    assert resource["fetch_detail"](form_a.secure_code, ["serial_number"]) == {
        "_sc": form_a.secure_code,
        "serial_number": "FORM-A",
    }
    assert resource["fetch_detail"](
        form_b.secure_code,
        ["serial_number", "execution_code", "status_label"],
    ) is None
