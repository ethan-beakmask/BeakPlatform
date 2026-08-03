"""PF-7 portal permission-code model tests."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from modules.nocode_builder.services import data_source_manager as dsm
from modules.nocode_builder.services import portal_access_service as access
from modules.nocode_builder.services import portal_permission_service as perms


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


def _db_path(base, sub_sc):
    return base / sub_sc / "portal.db"


def _user(user_id=1, group_code="GENERAL", level_rank=10):
    return {
        "sub_system_sc": "ss",
        "user_id": user_id,
        "user_type": "PUBLIC_USER" if user_id is not None else "GUEST",
        "group_code": group_code,
        "level_code": "MEMBER",
        "level_rank": level_rank,
        "roles": [],
        "display_name": "Test User",
    }


def _insert_user(sub_sc, *, is_active=1):
    with dsm.DataSourceManager().get_session(sub_sc, "portal") as sess:
        sess.execute(
            text(
                "INSERT INTO portal_users "
                "(secure_code, username, display_name, password_hash, role_code, "
                "group_code, level_code, is_active) "
                "VALUES (:sc, :username, :name, 'hash', 'PUBLIC_USER', "
                "'GENERAL', 'MEMBER', :is_active)"
            ),
            {
                "sc": f"user_{sub_sc}_{is_active}",
                "username": f"user_{sub_sc}_{is_active}",
                "name": "Test User",
                "is_active": is_active,
            },
        )
        return sess.execute(text("SELECT last_insert_rowid()")).scalar()


def _permission(sess, code):
    resource, action = code.split(".", 1)
    sess.execute(
        text(
            "INSERT INTO portal_permissions (code, resource, action) "
            "VALUES (:code, :resource, :action)"
        ),
        {"code": code, "resource": resource, "action": action},
    )
    return sess.execute(text("SELECT id FROM portal_permissions WHERE code = :code"), {"code": code}).scalar()


def _level_id(sess, code):
    return sess.execute(
        text("SELECT id FROM portal_levels WHERE code = :code"),
        {"code": code},
    ).scalar()


def _grant_level(sess, level_code, permission_id):
    sess.execute(
        text(
            "INSERT INTO portal_level_permissions (level_id, permission_id) "
            "VALUES (:level_id, :permission_id)"
        ),
        {"level_id": _level_id(sess, level_code), "permission_id": permission_id},
    )


def _role(sess, code):
    sess.execute(
        text("INSERT INTO portal_admin_roles (code, name) VALUES (:code, :name)"),
        {"code": code, "name": code},
    )
    return sess.execute(text("SELECT id FROM portal_admin_roles WHERE code = :code"), {"code": code}).scalar()


def _grant_role(sess, role_id, permission_id):
    sess.execute(
        text(
            "INSERT INTO portal_role_permissions (role_id, permission_id) "
            "VALUES (:role_id, :permission_id)"
        ),
        {"role_id": role_id, "permission_id": permission_id},
    )


def _assign_role(sess, user_id, role_id, valid_until=None):
    sess.execute(
        text(
            "INSERT INTO portal_user_roles (user_id, role_id, valid_until) "
            "VALUES (:user_id, :role_id, :valid_until)"
        ),
        {"user_id": user_id, "role_id": role_id, "valid_until": valid_until},
    )


def _grant_user(sess, user_id, permission_id, effect):
    sess.execute(
        text(
            "INSERT INTO portal_user_permissions (user_id, permission_id, effect) "
            "VALUES (:user_id, :permission_id, :effect)"
        ),
        {"user_id": user_id, "permission_id": permission_id, "effect": effect},
    )


def test_schema_v3_upgrade_is_idempotent_from_v2_and_preserves_users(portal_base):
    sub_sc = "ss_v2_upgrade"
    portal_dir = portal_base / sub_sc
    portal_dir.mkdir(parents=True)
    db_path = portal_dir / "portal.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(dsm._PORTAL_SCHEMA)
        conn.executescript(dsm._PORTAL_SCHEMA_V2)
        conn.execute("ALTER TABLE portal_users ADD COLUMN group_code TEXT DEFAULT NULL")
        conn.execute("ALTER TABLE portal_users ADD COLUMN level_code TEXT DEFAULT NULL")
        conn.execute("PRAGMA user_version = 2")
        conn.execute(
            "INSERT INTO portal_users "
            "(secure_code, username, display_name, password_hash, role_code, group_code, level_code) "
            "VALUES ('user_sc', 'olduser', 'Old User', 'hash', 'PUBLIC_USER', 'GENERAL', 'MEMBER')"
        )

    dsm.ensure_portal_schema(sub_sc)
    dsm.ensure_portal_schema(sub_sc)

    expected_tables = {
        "portal_permissions",
        "portal_admin_roles",
        "portal_role_permissions",
        "portal_user_roles",
        "portal_user_permissions",
        "portal_level_permissions",
    }
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert expected_tables.issubset(tables)
        row = conn.execute(
            "SELECT username, group_code, level_code FROM portal_users WHERE secure_code = 'user_sc'"
        ).fetchone()
    assert row == ("olduser", "GENERAL", "MEMBER")


def test_level_permissions_inherit_downward_by_rank(portal_base):
    sub_sc = "ss_level_inherit"
    dsm.init_portal_sqlite(sub_sc)
    with dsm.DataSourceManager().get_session(sub_sc, "portal") as sess:
        low = _permission(sess, "bulletin.read")
        _grant_level(sess, "MEMBER", low)

    effective = perms.resolve_effective_permissions(sub_sc, _user(user_id=None, level_rank=90))

    assert effective == frozenset({"bulletin.read"})


def test_admin_roles_union_without_inheritance(portal_base):
    sub_sc = "ss_role_union"
    dsm.init_portal_sqlite(sub_sc)
    user_id = _insert_user(sub_sc)
    with dsm.DataSourceManager().get_session(sub_sc, "portal") as sess:
        read = _permission(sess, "bulletin.read")
        create = _permission(sess, "bulletin.create")
        role_a = _role(sess, "EDITOR")
        role_b = _role(sess, "PUBLISHER")
        _grant_role(sess, role_a, read)
        _grant_role(sess, role_b, create)
        _assign_role(sess, user_id, role_a)
        _assign_role(sess, user_id, role_b)

    effective = perms.resolve_effective_permissions(sub_sc, _user(user_id=user_id, level_rank=0))

    assert effective == frozenset({"bulletin.read", "bulletin.create"})


def test_user_deny_overrides_level_and_role_permissions(portal_base):
    sub_sc = "ss_deny"
    dsm.init_portal_sqlite(sub_sc)
    user_id = _insert_user(sub_sc)
    with dsm.DataSourceManager().get_session(sub_sc, "portal") as sess:
        permission_id = _permission(sess, "bulletin.delete")
        _grant_level(sess, "MEMBER", permission_id)
        role_id = _role(sess, "ADMINISH")
        _grant_role(sess, role_id, permission_id)
        _assign_role(sess, user_id, role_id)
        _grant_user(sess, user_id, permission_id, "deny")

    effective = perms.resolve_effective_permissions(sub_sc, _user(user_id=user_id, level_rank=10))

    assert "bulletin.delete" not in effective


def test_expired_role_assignment_does_not_grant_permissions(portal_base):
    sub_sc = "ss_expired_role"
    dsm.init_portal_sqlite(sub_sc)
    user_id = _insert_user(sub_sc)
    with dsm.DataSourceManager().get_session(sub_sc, "portal") as sess:
        permission_id = _permission(sess, "bulletin.archive")
        role_id = _role(sess, "ARCHIVER")
        _grant_role(sess, role_id, permission_id)
        _assign_role(sess, user_id, role_id, "2000-01-01 00:00:00")

    effective = perms.resolve_effective_permissions(sub_sc, _user(user_id=user_id, level_rank=0))

    assert effective == frozenset()


def test_inactive_portal_user_has_no_permissions(portal_base):
    sub_sc = "ss_inactive_user"
    dsm.init_portal_sqlite(sub_sc)
    user_id = _insert_user(sub_sc, is_active=0)
    with dsm.DataSourceManager().get_session(sub_sc, "portal") as sess:
        permission_id = _permission(sess, "bulletin.read")
        _grant_level(sess, "MEMBER", permission_id)

    effective = perms.resolve_effective_permissions(sub_sc, _user(user_id=user_id, level_rank=10))

    assert effective == frozenset()


def test_anonymous_user_only_receives_level_permissions(portal_base):
    sub_sc = "ss_guest_only_level"
    dsm.init_portal_sqlite(sub_sc)
    persisted_user_id = _insert_user(sub_sc)
    with dsm.DataSourceManager().get_session(sub_sc, "portal") as sess:
        level_permission = _permission(sess, "bulletin.read")
        role_permission = _permission(sess, "bulletin.create")
        user_permission = _permission(sess, "bulletin.update")
        _grant_level(sess, "GUEST", level_permission)
        role_id = _role(sess, "EDITOR")
        _grant_role(sess, role_id, role_permission)
        _assign_role(sess, persisted_user_id, role_id)
        _grant_user(sess, persisted_user_id, user_permission, "allow")

    effective = perms.resolve_effective_permissions(sub_sc, _user(user_id=None, level_rank=0))

    assert effective == frozenset({"bulletin.read"})


def test_evaluate_rule_permission_form_any_and_all_allow_and_deny(portal_base):
    sub_sc = "ss_rule_perms"
    dsm.init_portal_sqlite(sub_sc)
    user_id = _insert_user(sub_sc)
    with dsm.DataSourceManager().get_session(sub_sc, "portal") as sess:
        read = _permission(sess, "bulletin.read")
        create = _permission(sess, "bulletin.create")
        _grant_user(sess, user_id, read, "allow")
        _grant_user(sess, user_id, create, "allow")

    user = _user(user_id=user_id, level_rank=0)

    assert access._evaluate_rule(
        sub_sc,
        {"required_permissions": ["bulletin.read", "bulletin.missing"], "match_mode": "any"},
        user,
    ) == (True, "ok")
    assert access._evaluate_rule(
        sub_sc,
        {"required_permissions": ["bulletin.read", "bulletin.create"], "match_mode": "all"},
        user,
    ) == (True, "ok")
    assert access._evaluate_rule(
        sub_sc,
        {"required_permissions": ["bulletin.read", "bulletin.missing"], "match_mode": "all"},
        user,
    ) == (False, "permission_denied")


def test_evaluate_rule_permission_denies_when_code_not_effective(portal_base):
    sub_sc = "ss_rule_denied"
    dsm.init_portal_sqlite(sub_sc)
    user_id = _insert_user(sub_sc)
    with dsm.DataSourceManager().get_session(sub_sc, "portal") as sess:
        read = _permission(sess, "bulletin.read")
        _grant_user(sess, user_id, read, "allow")

    user = _user(user_id=user_id, group_code="GENERAL", level_rank=10)

    assert access._evaluate_rule(
        sub_sc,
        {"required_permissions": ["bulletin.read"]},
        user,
    ) == (True, "ok")
    assert access._evaluate_rule(
        sub_sc,
        {"required_permissions": ["bulletin.missing"]},
        user,
    ) == (False, "permission_denied")
    assert access._evaluate_rule(
        sub_sc,
        {"required_permissions": ["bulletin.missing"], "match_mode": "all"},
        user,
    ) == (False, "permission_denied")


@pytest.mark.parametrize(
    "rule",
    [
        {"required_permissions": []},
        {"required_permissions": "bulletin.read"},
        {"required_permissions": ["bulletin.read", 123]},
        {"required_permissions": ["bulletin.read"], "match_mode": "none"},
        {"required_permissions": ["bulletin.read"], "unknown": True},
    ],
)
def test_evaluate_rule_permission_bad_matrix_forms(portal_base, rule):
    sub_sc = "ss_bad_perm_matrix"
    dsm.init_portal_sqlite(sub_sc)

    assert access._evaluate_rule(sub_sc, rule, _user(user_id=None)) == (False, "bad_matrix")


def test_validate_access_matrix_accepts_permission_forms(monkeypatch):
    monkeypatch.setenv("SYSTEM_ORG_CODE", "system.local")
    from modules.nocode_builder.api.site_map_api import _validate_access_matrix

    valid_inputs = [
        {"read": {"required_permissions": ["bulletin.read"]}},
        {"read": {"required_permissions": ["bulletin.read"], "match_mode": "all"}},
    ]

    for value in valid_inputs:
        ok, err = _validate_access_matrix(value)
        assert ok is True
        assert err == ""


@pytest.mark.parametrize(
    "value",
    [
        {"read": {"required_permissions": ["bulletin.read"], "unknown": True}},
        {"read": {"required_permissions": []}},
        {"read": {"required_permissions": ["Bulletin.Read"]}},
        {"read": {"required_permissions": ["bulletinread"]}},
        {"read": {"match_mode": "all"}},
        {"read": {"required_permissions": ["bulletin.read"], "unknown": True}},
    ],
)
def test_validate_access_matrix_rejects_bad_permission_forms(monkeypatch, value):
    monkeypatch.setenv("SYSTEM_ORG_CODE", "system.local")
    from modules.nocode_builder.api.site_map_api import _validate_access_matrix

    ok, err = _validate_access_matrix(value)

    assert ok is False
    assert err


def test_pageir_schema_v3_portal_access_rule_accepts_permission_forms_only():
    import json

    from jsonschema import Draft202012Validator

    schema_path = Path(__file__).resolve().parents[1] / "app" / "pageir" / "schema_v3.json"
    with schema_path.open(encoding="utf-8") as fh:
        schema = json.load(fh)
    validator = Draft202012Validator(
        {
            "$ref": "#/$defs/portal_access_rule",
            "$defs": schema["$defs"],
        }
    )

    valid_rules = [
        {"required_permissions": ["bulletin.read"]},
        {"required_permissions": ["bulletin.read"], "match_mode": "all"},
    ]
    invalid_rules = [
        {"unknown": True},
        {"required_permissions": ["bulletin.read"], "unknown": True},
        {"required_permissions": []},
        {"required_permissions": ["Bulletin.Read"]},
        {"required_permissions": ["bulletinread"]},
        {"required_permissions": ["bulletin.read"], "match_mode": "none"},
        {"required_permissions": ["bulletin.read"], "unknown": True},
    ]

    for rule in valid_rules:
        assert list(validator.iter_errors(rule)) == []
    for rule in invalid_rules:
        assert list(validator.iter_errors(rule))
