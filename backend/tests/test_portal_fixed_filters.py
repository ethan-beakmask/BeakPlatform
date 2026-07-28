"""Portal fixed_filters variable isolation tests."""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask

os.environ.setdefault("SYSTEM_ORG_CODE", "system.local")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.pageir.context import clear_render_context, set_render_context
from modules.nocode_builder.services.sqlite_crud_service import (
    PortalFilterNotSupported,
    resolve_filter_variables,
)


@pytest.fixture
def flask_app():
    app = Flask(__name__)
    app.secret_key = "test-secret"
    return app


@pytest.mark.parametrize(
    ("variable", "expected"),
    [
        ("$CURRENT_USER", "platform_user_sc"),
        ("$CURRENT_USER_NAME", "platform_user"),
        ("$CURRENT_ORG", "platform_org_sc"),
    ],
)
def test_platform_context_current_user_variables_keep_existing_behavior(variable, expected):
    user = SimpleNamespace(
        secure_code="platform_user_sc",
        username="platform_user",
        org_secure_code="platform_org_sc",
    )

    assert resolve_filter_variables({"owner": variable}, user=user) == {"owner": expected}


@pytest.mark.parametrize("variable", ["$CURRENT_USER", "$CURRENT_USER_NAME", "$CURRENT_ORG", "$FOO"])
def test_portal_context_rejects_identity_and_unknown_variables(flask_app, variable):
    with flask_app.test_request_context("/"):
        set_render_context(
            "portal",
            sub_system_sc="ss_123",
            portal_user={"user_id": 1, "username": "portal_user"},
        )
        try:
            with pytest.raises(PortalFilterNotSupported):
                resolve_filter_variables({"owner": variable})
        finally:
            clear_render_context()


def test_portal_context_allows_today_variable(flask_app):
    with flask_app.test_request_context("/"):
        set_render_context("portal", sub_system_sc="ss_123", portal_user={"user_id": 1})
        try:
            assert resolve_filter_variables({"created_on": "$TODAY"}) == {
                "created_on": date.today().isoformat()
            }
        finally:
            clear_render_context()


def test_portal_context_allows_literal_fixed_values(flask_app):
    with flask_app.test_request_context("/"):
        set_render_context("portal", sub_system_sc="ss_123", portal_user={"user_id": 1})
        try:
            assert resolve_filter_variables({"status": "ACTIVE"}) == {"status": "ACTIVE"}
        finally:
            clear_render_context()


def test_portal_context_does_not_resolve_platform_current_user(flask_app):
    platform_user = SimpleNamespace(
        secure_code="test_admin_0000000001",
        username="testadmin",
        org_secure_code="test_org_00000000001",
    )
    with flask_app.test_request_context("/"):
        set_render_context(
            "portal",
            sub_system_sc="ss_123",
            portal_user={"user_id": 1, "username": "portal_user"},
        )
        try:
            with pytest.raises(PortalFilterNotSupported):
                resolve_filter_variables({"owner": "$CURRENT_USER"}, user=platform_user)
        finally:
            clear_render_context()
