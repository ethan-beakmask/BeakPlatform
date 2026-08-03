"""NoCode portal N4b write API helper tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from flask import Flask
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from modules.nocode_builder.services import data_source_manager as dsm
from modules.nocode_builder.services import portal_access_service as access
from modules.nocode_builder.web.portal_public import (
    _valid_portal_row_id,
    _writable_payload,
)


@pytest.fixture
def portal_base(tmp_path, monkeypatch):
    base = tmp_path / "nocode_portals"
    monkeypatch.setattr(dsm, "_BASE_DIR", base)
    mgr = dsm.DataSourceManager()
    for engine in list(mgr._engines.values()):
        engine.dispose()
    mgr._engines.clear()
    mgr._session_factories.clear()
    yield base
    for engine in list(mgr._engines.values()):
        engine.dispose()
    mgr._engines.clear()
    mgr._session_factories.clear()


@pytest.fixture
def portal_app():
    app = Flask(__name__)
    app.secret_key = "test-secret"
    return app


def _user(group_code=None, level_rank=0):
    return {
        "user_id": None,
        "group_code": group_code,
        "level_code": "GUEST",
        "level_rank": level_rank,
        "roles": ["PUBLIC_USER"],
    }


def _grant_level_permission(sub_sc, level_code, code):
    resource, action = code.split(".", 1)
    with dsm.DataSourceManager().get_session(sub_sc, "portal") as sess:
        sess.execute(
            text(
                "INSERT INTO portal_permissions (code, resource, action) "
                "VALUES (:code, :resource, :action)"
            ),
            {"code": code, "resource": resource, "action": action},
        )
        permission_id = sess.execute(
            text("SELECT id FROM portal_permissions WHERE code = :code"),
            {"code": code},
        ).scalar()
        level_id = sess.execute(
            text("SELECT id FROM portal_levels WHERE code = :code"),
            {"code": level_code},
        ).scalar()
        sess.execute(
            text(
                "INSERT INTO portal_level_permissions (level_id, permission_id) "
                "VALUES (:level_id, :permission_id)"
            ),
            {"level_id": level_id, "permission_id": permission_id},
        )


@pytest.mark.parametrize("matrix", [None, {}, {"read": {"required_permissions": ["bulletin.read"]}}])
@pytest.mark.parametrize("action", ["create", "update", "delete"])
def test_widget_write_access_requires_explicit_action(portal_base, portal_app, matrix, action):
    dsm.init_portal_sqlite("ss_write_explicit")
    ctx = {"sub_system_sc": "ss_write_explicit", "portal_user": _user(group_code="GENERAL")}

    with portal_app.test_request_context("/"):
        assert access.check_widget_write_access(matrix, action, ctx) is False


@pytest.mark.parametrize(
    ("required_permission", "level_rank", "expected"),
    [
        ("bulletin.create", 50, True),
        ("bulletin.update", 50, False),
        ("bulletin.create", 10, False),
    ],
)
def test_widget_write_access_uses_permission_rule(
    portal_base,
    portal_app,
    required_permission,
    level_rank,
    expected,
):
    dsm.init_portal_sqlite("ss_write_rule")
    _grant_level_permission("ss_write_rule", "STAFF", "bulletin.create")
    ctx = {
        "sub_system_sc": "ss_write_rule",
        "portal_user": _user(level_rank=level_rank),
    }
    matrix = {"create": {"required_permissions": [required_permission]}}

    with portal_app.test_request_context("/"):
        assert access.check_widget_write_access(matrix, "create", ctx) is expected


def test_widget_write_access_missing_required_permissions_fails_closed(portal_base, portal_app):
    dsm.init_portal_sqlite("ss_write_missing_level")
    ctx = {
        "sub_system_sc": "ss_write_missing_level",
        "portal_user": _user(group_code="GENERAL", level_rank=90),
    }
    matrix = {"create": {"match_mode": "any"}}

    with portal_app.test_request_context("/"):
        assert access.check_widget_write_access(matrix, "create", ctx) is False


@pytest.mark.parametrize("action", ["read", "export", "", None])
def test_widget_write_access_rejects_unknown_action(portal_base, portal_app, action):
    dsm.init_portal_sqlite("ss_write_unknown_action")
    ctx = {
        "sub_system_sc": "ss_write_unknown_action",
        "portal_user": _user(group_code="GENERAL", level_rank=50),
    }
    matrix = {
        "create": {"required_permissions": ["bulletin.create"]},
        "update": {"required_permissions": ["bulletin.update"]},
        "delete": {"required_permissions": ["bulletin.delete"]},
    }

    with portal_app.test_request_context("/"):
        assert access.check_widget_write_access(matrix, action, ctx) is False


def test_writable_payload_keeps_only_three_way_intersection():
    payload = {
        "name": "Alice",
        "email": "alice@example.test",
        "role": "admin",
        "password_hash": "hash",
        "unknown": "drop",
    }

    assert _writable_payload(
        payload,
        binding_fields=["name", "email", "password_hash"],
        resource_fields=["name", "email", "role"],
        writable_fields=["name", "role"],
    ) == {"name": "Alice"}


def test_writable_payload_excludes_sensitive_field_when_resolver_filters_it():
    payload = {"name": "Alice", "password_hash": "hash"}

    assert _writable_payload(
        payload,
        binding_fields=["name", "password_hash"],
        resource_fields=["name"],
        writable_fields=["name"],
    ) == {"name": "Alice"}


def test_writable_payload_empty_intersection_returns_empty_dict():
    assert _writable_payload(
        {"name": "Alice"},
        binding_fields=["name"],
        resource_fields=["email"],
        writable_fields=["role"],
    ) == {}


@pytest.mark.parametrize("row_id", ["abc", "ABC_123", "row-123", "1" * 128])
def test_portal_row_id_accepts_safe_values(row_id):
    assert _valid_portal_row_id(row_id) is True


@pytest.mark.parametrize("row_id", ["abc/def", "", "1" * 129, "../x"])
def test_portal_row_id_rejects_unsafe_values(row_id):
    assert _valid_portal_row_id(row_id) is False
