"""NoCode portal account N1 schema and session tests."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest
from flask import Flask, session
from sqlalchemy import text
from werkzeug.security import generate_password_hash

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from modules.nocode_builder.services import data_source_manager as dsm
from modules.nocode_builder.services import portal_auth_service as auth


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


def _db_path(base, sub_sc):
    return base / sub_sc / "portal.db"


def _read_scalar(db_path, sql, params=()):
    with sqlite3.connect(db_path) as conn:
        return conn.execute(sql, params).fetchone()[0]


def _insert_user(sub_sc, username, password="secret123", group_code="GENERAL", level_code="MEMBER"):
    with dsm.DataSourceManager().get_session(sub_sc, "portal") as sess:
        sess.execute(
            text(
                "INSERT INTO portal_users "
                "(secure_code, username, display_name, email, password_hash, role_code, "
                "group_code, level_code, is_active) "
                "VALUES (:sc, :username, :display_name, '', :pw, 'PUBLIC_USER', "
                ":group_code, :level_code, 1)"
            ),
            {
                "sc": f"sc_{username}",
                "username": username,
                "display_name": username.title(),
                "pw": generate_password_hash(password),
                "group_code": group_code,
                "level_code": level_code,
            },
        )
    return f"sc_{username}"


def test_init_portal_sqlite_sets_v2_defaults(portal_base):
    dsm.init_portal_sqlite("ss_init")
    db_path = _db_path(portal_base, "ss_init")

    assert _read_scalar(db_path, "PRAGMA user_version") == 2
    assert _read_scalar(db_path, "SELECT COUNT(*) FROM portal_groups WHERE code = 'GENERAL'") == 1
    assert _read_scalar(db_path, "SELECT rank FROM portal_levels WHERE code = 'ADMIN'") == 90


def test_ensure_portal_schema_upgrades_old_v1_idempotently(portal_base):
    sub_sc = "ss_old"
    portal_dir = portal_base / sub_sc
    portal_dir.mkdir(parents=True)
    db_path = portal_dir / "portal.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(dsm._PORTAL_SCHEMA)
        conn.execute("PRAGMA user_version = 1")
        conn.execute(
            "INSERT INTO portal_users "
            "(secure_code, username, display_name, password_hash, role_code) "
            "VALUES ('user_sc', 'olduser', 'Old User', 'hash', 'PUBLIC_USER')"
        )

    dsm.ensure_portal_schema(sub_sc)
    dsm.ensure_portal_schema(sub_sc)

    assert _read_scalar(db_path, "PRAGMA user_version") == 2
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT username, group_code, level_code FROM portal_users WHERE secure_code = 'user_sc'"
        ).fetchone()
    assert dict(row) == {"username": "olduser", "group_code": None, "level_code": None}


def test_register_assigns_general_member_and_session_rank_from_table(portal_base, portal_app):
    dsm.init_portal_sqlite("ss_register")
    with dsm.DataSourceManager().get_session("ss_register", "portal") as sess:
        sess.execute(text("UPDATE portal_levels SET rank = 12 WHERE code = 'MEMBER'"))

    with portal_app.test_request_context("/"):
        data, error = auth.register("ss_register", "member1", "secret123", "Member One", "")

        assert error == ""
        assert data["group_code"] == "GENERAL"
        assert data["level_code"] == "MEMBER"
        assert data["level_rank"] == 12
        assert session["portal_sessions"]["ss_register"] == data

    db_path = _db_path(portal_base, "ss_register")
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT group_code, level_code FROM portal_users WHERE username = 'member1'"
        ).fetchone()
    assert dict(row) == {"group_code": "GENERAL", "level_code": "MEMBER"}


def test_portal_sessions_coexist_and_logout_is_scoped(portal_base, portal_app):
    dsm.init_portal_sqlite("ss_guest")
    dsm.init_portal_sqlite("ss_login")
    _insert_user("ss_login", "loginuser")

    with portal_app.test_request_context("/"):
        guest = auth.create_guest_session("ss_guest")
        login_data, error = auth.login("ss_login", "loginuser", "secret123")

        assert error == ""
        assert session["portal_sessions"]["ss_guest"] == guest
        assert session["portal_sessions"]["ss_login"] == login_data
        assert auth.get_current_portal_user("ss_guest")["user_type"] == "GUEST"
        assert auth.get_current_portal_user("ss_login")["user_type"] == "PUBLIC_USER"

        auth.logout("ss_guest")

        assert "ss_guest" not in session["portal_sessions"]
        assert session["portal_sessions"]["ss_login"] == login_data


def test_login_missing_level_fails_closed_to_guest_rank(portal_base, portal_app):
    dsm.init_portal_sqlite("ss_missing_level")
    _insert_user("ss_missing_level", "badlevel", level_code="DELETED_LEVEL")

    with portal_app.test_request_context("/"):
        data, error = auth.login("ss_missing_level", "badlevel", "secret123")

    assert error == ""
    assert data["level_code"] == "GUEST"
    assert data["level_rank"] == 0
    assert data["group_code"] == "GENERAL"


def test_group_level_upsert_and_assignment_validation(portal_base):
    dsm.init_portal_sqlite("ss_org")
    user_sc = _insert_user("ss_org", "assigned")

    group, error = auth.upsert_group("ss_org", "VIP_GROUP", "VIP", 20)
    assert error == ""
    assert group["code"] == "VIP_GROUP"
    assert group["display_order"] == 20

    level, error = auth.upsert_level("ss_org", "VIP_LEVEL", "VIP Level", 70, 30)
    assert error == ""
    assert level["code"] == "VIP_LEVEL"
    assert level["rank"] == 70

    bad_group, error = auth.upsert_group("ss_org", "bad-code", "Bad")
    assert bad_group is None
    assert error == "群組代碼格式不正確"

    bad_level, error = auth.upsert_level("ss_org", "1BAD", "Bad", 1)
    assert bad_level is None
    assert error == "階級代碼格式不正確"

    assert auth.set_user_assignment("ss_org", user_sc, "VIP_GROUP", "VIP_LEVEL") is True
    assert auth.set_user_assignment("ss_org", user_sc, "bad-code", "VIP_LEVEL") is False
    assert auth.set_user_assignment("ss_org", user_sc, "VIP_GROUP", "NO_SUCH_LEVEL") is False

    with dsm.DataSourceManager().get_session("ss_org", "portal") as sess:
        row = sess.execute(
            text(
                "SELECT group_code, level_code FROM portal_users "
                "WHERE secure_code = :sc"
            ),
            {"sc": user_sc},
        ).mappings().first()
    assert dict(row) == {"group_code": "VIP_GROUP", "level_code": "VIP_LEVEL"}
