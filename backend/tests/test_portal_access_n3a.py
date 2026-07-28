"""NoCode portal N3a page access_matrix runtime tests."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask

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
        "user_id": 123,
        "group_code": group_code,
        "level_code": "GUEST",
        "level_rank": level_rank,
        "roles": ["PUBLIC_USER"],
    }


def _check(portal_app, sub_sc, page_sc, user):
    with portal_app.test_request_context("/"):
        return access.check_page_access(sub_sc, page_sc, user)


def test_no_node_allows_no_matrix(portal_base, portal_app, monkeypatch):
    dsm.init_portal_sqlite("ss_no_node")
    _patch_node(monkeypatch, None)

    assert _check(portal_app, "ss_no_node", "page_1", _user()) == (True, "no_matrix")


def test_node_without_access_matrix_allows_no_matrix(portal_base, portal_app, monkeypatch):
    dsm.init_portal_sqlite("ss_null_matrix")
    _patch_node(monkeypatch, _node(None))

    assert _check(portal_app, "ss_null_matrix", "page_1", _user()) == (True, "no_matrix")


def test_guest_passes_group_unlimited_guest_level(portal_base, portal_app, monkeypatch):
    dsm.init_portal_sqlite("ss_guest")
    _patch_node(monkeypatch, _node({"read": {"groups": None, "min_level": "GUEST"}}))

    assert _check(portal_app, "ss_guest", "page_1", _user(group_code=None, level_rank=0)) == (True, "ok")


@pytest.mark.parametrize(
    ("group_code", "expected"),
    [
        ("GENERAL", (True, "ok")),
        (None, (False, "group_denied")),
        ("VIP", (False, "group_denied")),
    ],
)
def test_group_matrix_checks_user_group(portal_base, portal_app, monkeypatch, group_code, expected):
    dsm.init_portal_sqlite("ss_group")
    _patch_node(
        monkeypatch,
        _node({"read": {"groups": ["GENERAL"], "min_level": "GUEST"}}),
    )

    assert _check(portal_app, "ss_group", "page_1", _user(group_code=group_code)) == expected


@pytest.mark.parametrize(
    ("level_rank", "expected"),
    [
        (10, (False, "level_denied")),
        (50, (True, "ok")),
        (90, (True, "ok")),
    ],
)
def test_min_level_checks_active_level_rank(portal_base, portal_app, monkeypatch, level_rank, expected):
    dsm.init_portal_sqlite("ss_level")
    _patch_node(
        monkeypatch,
        _node({"read": {"groups": None, "min_level": "STAFF"}}),
    )

    assert _check(portal_app, "ss_level", "page_1", _user(level_rank=level_rank)) == expected


def test_missing_min_level_fails_closed(portal_base, portal_app, monkeypatch):
    dsm.init_portal_sqlite("ss_missing_level")
    _patch_node(
        monkeypatch,
        _node({"read": {"groups": None, "min_level": "NO_SUCH_LEVEL"}}),
    )

    assert _check(portal_app, "ss_missing_level", "page_1", _user(level_rank=90)) == (
        False,
        "level_missing",
    )


@pytest.mark.parametrize(
    "matrix",
    [
        ["GENERAL"],
        {},
        {"read": "bad"},
        {"read": {"groups": None}},
        {"read": {"groups": None, "min_level": 123}},
    ],
)
def test_bad_access_matrix_fails_closed(portal_base, portal_app, monkeypatch, matrix):
    dsm.init_portal_sqlite("ss_bad_matrix")
    _patch_node(monkeypatch, _node(matrix))

    assert _check(portal_app, "ss_bad_matrix", "page_1", _user()) == (False, "bad_matrix")


def test_portal_user_none_denies_no_session(portal_base, portal_app, monkeypatch):
    dsm.init_portal_sqlite("ss_no_session")
    _patch_node(monkeypatch, _node({"read": {"groups": None, "min_level": "GUEST"}}))

    assert _check(portal_app, "ss_no_session", "page_1", None) == (False, "no_session")


def test_missing_portal_db_returns_error(portal_base, portal_app, monkeypatch):
    _patch_node(monkeypatch, _node({"read": {"groups": None, "min_level": "GUEST"}}))

    assert _check(portal_app, "ss_missing_db", "page_1", _user()) == (False, "error")
