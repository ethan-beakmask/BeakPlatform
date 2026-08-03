"""NoCode portal N3a page access_matrix runtime tests."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from modules.nocode_builder.services import data_source_manager as dsm
from modules.nocode_builder.services import portal_access_service as access


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


class FakeQuery:
    def __init__(self, node):
        self.node = node
        self.filter_kwargs = None

    def filter_by(self, **kwargs):
        self.filter_kwargs = kwargs
        return self

    def first(self):
        return self.node


def _patch_node(monkeypatch, node):
    monkeypatch.setattr(access, "DcSiteMapNode", SimpleNamespace(query=FakeQuery(node)))


def _node(matrix):
    return SimpleNamespace(access_matrix=matrix)


def _user(group_code=None, level_rank=0):
    return {
        "user_id": None,
        "group_code": group_code,
        "level_code": "GUEST",
        "level_rank": level_rank,
        "roles": ["PUBLIC_USER"],
    }


def _check(portal_app, sub_sc, page_sc, user):
    with portal_app.test_request_context("/"):
        return access.check_page_access(sub_sc, page_sc, user)


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


def test_no_node_allows_no_matrix(portal_base, portal_app, monkeypatch):
    dsm.init_portal_sqlite("ss_no_node")
    _patch_node(monkeypatch, None)

    assert _check(portal_app, "ss_no_node", "page_1", _user()) == (True, "no_matrix")


def test_node_without_access_matrix_allows_no_matrix(portal_base, portal_app, monkeypatch):
    dsm.init_portal_sqlite("ss_null_matrix")
    _patch_node(monkeypatch, _node(None))

    assert _check(portal_app, "ss_null_matrix", "page_1", _user()) == (True, "no_matrix")


def test_guest_passes_required_permission_from_guest_level(portal_base, portal_app, monkeypatch):
    dsm.init_portal_sqlite("ss_guest")
    _grant_level_permission("ss_guest", "GUEST", "bulletin.read")
    _patch_node(monkeypatch, _node({"read": {"required_permissions": ["bulletin.read"]}}))

    assert _check(portal_app, "ss_guest", "page_1", _user(group_code=None, level_rank=0)) == (True, "ok")


@pytest.mark.parametrize(
    ("required_permission", "expected"),
    [
        ("bulletin.read", (True, "ok")),
        ("bulletin.create", (False, "permission_denied")),
        ("bulletin.update", (False, "permission_denied")),
    ],
)
def test_permission_matrix_checks_effective_permissions(
    portal_base,
    portal_app,
    monkeypatch,
    required_permission,
    expected,
):
    dsm.init_portal_sqlite("ss_group")
    _grant_level_permission("ss_group", "GUEST", "bulletin.read")
    _patch_node(
        monkeypatch,
        _node({"read": {"required_permissions": [required_permission]}}),
    )

    assert _check(portal_app, "ss_group", "page_1", _user()) == expected


@pytest.mark.parametrize(
    ("level_rank", "expected"),
    [
        (10, (False, "permission_denied")),
        (50, (True, "ok")),
        (90, (True, "ok")),
    ],
)
def test_level_permissions_follow_active_level_rank(portal_base, portal_app, monkeypatch, level_rank, expected):
    dsm.init_portal_sqlite("ss_level")
    _grant_level_permission("ss_level", "STAFF", "bulletin.read")
    _patch_node(
        monkeypatch,
        _node({"read": {"required_permissions": ["bulletin.read"]}}),
    )

    assert _check(portal_app, "ss_level", "page_1", _user(level_rank=level_rank)) == expected


def test_missing_required_permissions_fails_closed(portal_base, portal_app, monkeypatch):
    dsm.init_portal_sqlite("ss_missing_level")
    _patch_node(
        monkeypatch,
        _node({"read": {"match_mode": "any"}}),
    )

    assert _check(portal_app, "ss_missing_level", "page_1", _user(level_rank=90)) == (
        False,
        "bad_matrix",
    )


@pytest.mark.parametrize(
    "matrix",
    [
        ["GENERAL"],
        {},
        {"read": "bad"},
        {"read": {"required_permissions": []}},
        {"read": {"required_permissions": "bulletin.read"}},
        {"read": {"required_permissions": ["bulletin.read", 123]}},
        {"read": {"required_permissions": ["bulletin.read"], "match_mode": "none"}},
    ],
)
def test_bad_access_matrix_fails_closed(portal_base, portal_app, monkeypatch, matrix):
    dsm.init_portal_sqlite("ss_bad_matrix")
    _patch_node(monkeypatch, _node(matrix))

    assert _check(portal_app, "ss_bad_matrix", "page_1", _user()) == (False, "bad_matrix")


def test_portal_user_none_denies_no_session(portal_base, portal_app, monkeypatch):
    dsm.init_portal_sqlite("ss_no_session")
    _patch_node(monkeypatch, _node({"read": {"required_permissions": ["bulletin.read"]}}))

    assert _check(portal_app, "ss_no_session", "page_1", None) == (False, "no_session")


def test_missing_portal_db_returns_error(portal_base, portal_app, monkeypatch):
    _patch_node(monkeypatch, _node({"read": {"required_permissions": ["bulletin.read"]}}))

    assert _check(portal_app, "ss_missing_db", "page_1", _user()) == (False, "permission_denied")


def test_widget_access_undeclared_action_allows(portal_base, portal_app):
    dsm.init_portal_sqlite("ss_widget_action")
    ctx = {"sub_system_sc": "ss_widget_action", "portal_user": _user(group_code="GENERAL")}

    assert access.check_widget_access(
        {"read": {"required_permissions": ["bulletin.read"]}},
        "create",
        ctx,
    ) is True


@pytest.mark.parametrize(
    "matrix",
    [
        None,
        ["VIP"],
        {"read": "bad"},
        {"read": {"required_permissions": []}},
        {"read": {"required_permissions": ["bulletin.read"], "match_mode": "none"}},
    ],
)
def test_widget_access_bad_matrix_or_rule_fails_closed(portal_base, portal_app, matrix):
    dsm.init_portal_sqlite("ss_widget_bad")
    ctx = {"sub_system_sc": "ss_widget_bad", "portal_user": _user()}

    assert access.check_widget_access(matrix, "read", ctx) is False


@pytest.mark.parametrize(
    ("required_permission", "level_rank", "expected"),
    [
        ("bulletin.read", 50, True),
        ("bulletin.create", 50, False),
        ("bulletin.read", 10, False),
    ],
)
def test_widget_access_uses_same_permission_rule(
    portal_base,
    portal_app,
    required_permission,
    level_rank,
    expected,
):
    dsm.init_portal_sqlite("ss_widget_rule")
    _grant_level_permission("ss_widget_rule", "STAFF", "bulletin.read")
    ctx = {
        "sub_system_sc": "ss_widget_rule",
        "portal_user": _user(level_rank=level_rank),
    }

    assert access.check_widget_access(
        {"read": {"required_permissions": [required_permission]}},
        "read",
        ctx,
    ) is expected
