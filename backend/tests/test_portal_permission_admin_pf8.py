"""PF-8 portal permission administration service tests."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from modules.nocode_builder.services import data_source_manager as dsm
from modules.nocode_builder.services import portal_permission_admin_service as admin
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


class FakeQuery:
    def __init__(self, nodes):
        self.nodes = nodes
        self.filter_kwargs = None

    def filter_by(self, **kwargs):
        self.filter_kwargs = kwargs
        return self

    def all(self):
        return self.nodes


def _patch_nodes(monkeypatch, nodes=None):
    monkeypatch.setattr(admin, "DcSiteMapNode", SimpleNamespace(query=FakeQuery(nodes or [])))


def _codes(sub_sc, sql, params=None):
    with dsm.DataSourceManager().get_session(sub_sc, "portal") as sess:
        return [row[0] for row in sess.execute(text(sql), params or {}).all()]


def _count(sub_sc, sql, params=None):
    with dsm.DataSourceManager().get_session(sub_sc, "portal") as sess:
        return sess.execute(text(sql), params or {}).scalar()


def _insert_user(sub_sc, secure_code="user_sc", level_code="MEMBER"):
    with dsm.DataSourceManager().get_session(sub_sc, "portal") as sess:
        sess.execute(
            text(
                "INSERT INTO portal_users "
                "(secure_code, username, display_name, password_hash, role_code, "
                "group_code, level_code, is_active) "
                "VALUES (:sc, :username, 'User', 'hash', 'PUBLIC_USER', "
                "'GENERAL', :level_code, 1)"
            ),
            {"sc": secure_code, "username": secure_code, "level_code": level_code},
        )
        return sess.execute(text("SELECT last_insert_rowid()")).scalar()


def _permission_codes(sub_sc):
    return _codes(sub_sc, "SELECT code FROM portal_permissions ORDER BY code")


def _role_permissions(sub_sc, role_code):
    return _codes(
        sub_sc,
        "SELECT p.code FROM portal_role_permissions rp "
        "JOIN portal_admin_roles r ON r.id = rp.role_id "
        "JOIN portal_permissions p ON p.id = rp.permission_id "
        "WHERE r.code = :code ORDER BY p.code",
        {"code": role_code},
    )


def _level_permissions(sub_sc, level_code):
    return _codes(
        sub_sc,
        "SELECT p.code FROM portal_level_permissions lp "
        "JOIN portal_levels l ON l.id = lp.level_id "
        "JOIN portal_permissions p ON p.id = lp.permission_id "
        "WHERE l.code = :code ORDER BY p.code",
        {"code": level_code},
    )


def test_init_seeds_default_system_roles_idempotently(portal_base):
    sub_sc = "ss_seed"
    dsm.init_portal_sqlite(sub_sc)
    rows = _codes(
        sub_sc,
        "SELECT code || ':' || is_system FROM portal_admin_roles ORDER BY display_order, code",
    )
    assert rows == [
        "MEMBER_MANAGER:1",
        "MATERIAL_MANAGER:1",
        "BULLETIN_MANAGER:1",
        "REPORT_MANAGER:1",
        "AUDITOR:1",
        "SYSTEM_ADMIN:1",
    ]
    admin.seed_default_admin_roles(sub_sc)
    assert _count(sub_sc, "SELECT COUNT(*) FROM portal_admin_roles") == 6


def test_upsert_permission_derives_parts_and_rejects_bad_codes(portal_base):
    sub_sc = "ss_perm"
    dsm.init_portal_sqlite(sub_sc)
    item, error = admin.upsert_permission(sub_sc, "portal_record.read_own", "讀取", "low")
    assert error == ""
    assert item["resource"] == "portal_record"
    assert item["action"] == "read_own"
    for bad_code in ["Portal.read", "portal_read", "portal.read.extra"]:
        item, error = admin.upsert_permission(sub_sc, bad_code)
        assert item is None
        assert error


def test_upsert_permission_rejects_invalid_risk_level(portal_base):
    sub_sc = "ss_risk"
    dsm.init_portal_sqlite(sub_sc)
    item, error = admin.upsert_permission(sub_sc, "portal_page.view", risk_level="danger")
    assert item is None
    assert error == "風險等級不正確"


def test_set_role_permissions_replaces_whole_set(portal_base):
    sub_sc = "ss_role_replace"
    dsm.init_portal_sqlite(sub_sc)
    admin.upsert_admin_role(sub_sc, "EDITOR", "編輯")
    for code in ["portal.a", "portal.b", "portal.c"]:
        admin.upsert_permission(sub_sc, code)
    assert admin.set_role_permissions(sub_sc, "EDITOR", ["portal.a", "portal.b", "portal.c"]) == (True, "")
    assert admin.set_role_permissions(sub_sc, "EDITOR", ["portal.b"]) == (True, "")
    assert _role_permissions(sub_sc, "EDITOR") == ["portal.b"]


def test_set_role_permissions_rejects_missing_code_without_partial_write(portal_base):
    sub_sc = "ss_role_reject"
    dsm.init_portal_sqlite(sub_sc)
    admin.upsert_admin_role(sub_sc, "EDITOR", "編輯")
    admin.upsert_permission(sub_sc, "portal.a")
    admin.upsert_permission(sub_sc, "portal.b")
    admin.set_role_permissions(sub_sc, "EDITOR", ["portal.a"])
    ok, error = admin.set_role_permissions(sub_sc, "EDITOR", ["portal.b", "portal.missing"])
    assert ok is False
    assert error
    assert _role_permissions(sub_sc, "EDITOR") == ["portal.a"]


def test_set_level_permissions_empty_list_clears(portal_base):
    sub_sc = "ss_level_clear"
    dsm.init_portal_sqlite(sub_sc)
    admin.upsert_permission(sub_sc, "portal.a")
    admin.set_level_permissions(sub_sc, "MEMBER", ["portal.a"])
    assert admin.set_level_permissions(sub_sc, "MEMBER", []) == (True, "")
    assert _level_permissions(sub_sc, "MEMBER") == []


def test_set_user_roles_replaces_and_missing_user_errors(portal_base):
    sub_sc = "ss_user_roles"
    dsm.init_portal_sqlite(sub_sc)
    _insert_user(sub_sc)
    admin.upsert_admin_role(sub_sc, "EDITOR", "編輯")
    admin.upsert_admin_role(sub_sc, "REVIEWER", "審核")
    assert admin.set_user_roles(sub_sc, "user_sc", ["EDITOR", "REVIEWER"]) == (True, "")
    assert admin.set_user_roles(sub_sc, "user_sc", ["REVIEWER"]) == (True, "")
    model = admin.get_permission_model(sub_sc)
    assert model["users"][0]["roles"] == ["REVIEWER"]
    ok, error = admin.set_user_roles(sub_sc, "missing", ["REVIEWER"])
    assert ok is False
    assert error == "帳號不存在"


def test_set_user_permission_override_upserts_and_deletes(portal_base):
    sub_sc = "ss_override"
    dsm.init_portal_sqlite(sub_sc)
    _insert_user(sub_sc)
    admin.upsert_permission(sub_sc, "portal.a")
    assert admin.set_user_permission_override(sub_sc, "user_sc", "portal.a", "allow", "one") == (True, "")
    assert admin.set_user_permission_override(sub_sc, "user_sc", "portal.a", "deny", "two") == (True, "")
    assert _codes(
        sub_sc,
        "SELECT effect || ':' || reason FROM portal_user_permissions",
    ) == ["deny:two"]
    assert admin.set_user_permission_override(sub_sc, "user_sc", "portal.a", None) == (True, "")
    assert _count(sub_sc, "SELECT COUNT(*) FROM portal_user_permissions") == 0


def test_delete_permission_refuses_portal_refs_then_deletes_after_unlinked(portal_base, monkeypatch):
    sub_sc = "ss_delete_refs"
    dsm.init_portal_sqlite(sub_sc)
    _patch_nodes(monkeypatch)
    _insert_user(sub_sc)
    admin.upsert_admin_role(sub_sc, "EDITOR", "編輯")
    admin.upsert_permission(sub_sc, "portal.a")
    admin.set_role_permissions(sub_sc, "EDITOR", ["portal.a"])
    admin.set_level_permissions(sub_sc, "MEMBER", ["portal.a"])
    admin.set_user_permission_override(sub_sc, "user_sc", "portal.a", "allow")
    ok, error = admin.delete_permission(sub_sc, "portal.a")
    assert ok is False
    assert "引用" in error
    admin.set_role_permissions(sub_sc, "EDITOR", [])
    admin.set_level_permissions(sub_sc, "MEMBER", [])
    admin.set_user_permission_override(sub_sc, "user_sc", "portal.a", None)
    assert admin.delete_permission(sub_sc, "portal.a") == (True, "")
    assert _permission_codes(sub_sc) == []


def test_delete_permission_refuses_site_map_access_matrix_refs(portal_base, monkeypatch):
    sub_sc = "ss_delete_site_map"
    dsm.init_portal_sqlite(sub_sc)
    admin.upsert_permission(sub_sc, "portal.a")
    _patch_nodes(
        monkeypatch,
        [SimpleNamespace(access_matrix={"read": {"required_permissions": ["portal.a"]}})],
    )
    ok, error = admin.delete_permission(sub_sc, "portal.a")
    assert ok is False
    assert "access_matrix" in error


def test_delete_admin_role_refuses_system_role(portal_base):
    sub_sc = "ss_delete_system"
    dsm.init_portal_sqlite(sub_sc)
    ok, error = admin.delete_admin_role(sub_sc, "SYSTEM_ADMIN")
    assert ok is False
    assert error == "系統角色不可刪除"


def test_apply_member_template_creates_permissions_and_links_idempotently(portal_base):
    sub_sc = "ss_template_member"
    dsm.init_portal_sqlite(sub_sc)
    result, error = admin.apply_permission_template(sub_sc, "MEMBER_ONLY")
    assert error == ""
    assert result["created_permissions"] == [
        "portal_page.view_member",
        "portal_record.read_own",
        "portal_record.create",
    ]
    assert result["linked_levels"] == [{
        "code": "MEMBER",
        "permissions": [
            "portal_page.view_member",
            "portal_record.read_own",
            "portal_record.create",
        ],
    }]
    result, error = admin.apply_permission_template(sub_sc, "MEMBER_ONLY")
    assert error == ""
    assert result["created_permissions"] == []
    assert sorted(_level_permissions(sub_sc, "MEMBER")) == sorted([
        "portal_page.view_member",
        "portal_record.read_own",
        "portal_record.create",
    ])


def test_apply_template_skips_missing_level(portal_base):
    sub_sc = "ss_template_skip"
    dsm.init_portal_sqlite(sub_sc)
    with dsm.DataSourceManager().get_session(sub_sc, "portal") as sess:
        sess.execute(text("DELETE FROM portal_levels WHERE code = 'MEMBER'"))
    result, error = admin.apply_permission_template(sub_sc, "MEMBER_ONLY")
    assert error == ""
    assert result["linked_levels"] == []
    assert sorted(result["created_permissions"]) == sorted([
        "portal_page.view_member",
        "portal_record.read_own",
        "portal_record.create",
    ])


def test_template_permissions_flow_into_pf7_effective_permissions(portal_base):
    sub_sc = "ss_pf7_bridge"
    dsm.init_portal_sqlite(sub_sc)
    user_id = _insert_user(sub_sc)
    admin.apply_permission_template(sub_sc, "MEMBER_ONLY")
    effective = perms.resolve_effective_permissions(
        sub_sc,
        {
            "sub_system_sc": sub_sc,
            "user_id": user_id,
            "user_type": "PUBLIC_USER",
            "group_code": "GENERAL",
            "level_code": "MEMBER",
            "level_rank": 10,
            "roles": [],
            "display_name": "User",
        },
    )
    assert {
        "portal_page.view_member",
        "portal_record.read_own",
        "portal_record.create",
    }.issubset(effective)
