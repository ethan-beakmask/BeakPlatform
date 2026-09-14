"""PF-44 stage A portal file backend foundation tests.

API 層由主 Claude 以 curl 實測；本 pytest app 未必註冊 nocode_builder blueprint。
"""
from __future__ import annotations

import io
import sqlite3
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db
from app.models import Organization, Permission
from modules.nocode_builder.models import DcPageLayout, DcSubSystem, DcSubSystemPage
from modules.nocode_builder.services import data_source_manager as dsm
from modules.nocode_builder.services import portal_file_service as pfs
from app.services import file_service

API_PREFIX = "/beakplatform"


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


def _table_names(conn):
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }


def _index_names(conn):
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        ).fetchall()
    }


def test_schema_v4_init_and_upgrade_idempotent(portal_base):
    sub_sc = "portal_file_schema"
    dsm.init_portal_sqlite(sub_sc)
    dsm.ensure_portal_schema(sub_sc)
    dsm.ensure_portal_schema(sub_sc)

    db_path = _db_path(portal_base, sub_sc)
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
        assert {"portal_files", "portal_file_acl"}.issubset(_table_names(conn))
        assert {
            "idx_portal_files_widget",
            "idx_portal_files_uploader",
        }.issubset(_index_names(conn))

        conn.execute("DROP TABLE portal_file_acl")
        conn.execute("DROP TABLE portal_files")
        conn.execute("PRAGMA user_version = 3")

    dsm.ensure_portal_schema(sub_sc)
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
        assert {"portal_files", "portal_file_acl"}.issubset(_table_names(conn))


def test_context_type_registration():
    assert file_service.CONTEXT_STORAGE_MAP["portal_file"] == "encrypted"
    assert file_service.CONTEXT_ALLOWED_EXT["portal_file"] == {
        "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
        "odt", "ods", "csv", "txt", "rtf",
        "png", "jpg", "jpeg", "gif", "webp", "bmp",
        "zip", "7z", "rar",
    }
    assert file_service.CONTEXT_MAX_SIZE["portal_file"] == 50 * 1024 * 1024
    assert "portal_file" not in file_service.PUBLIC_CONTEXT_TYPES
    assert file_service.GENERIC_UPLOAD_CONTEXT_TYPES == {"form_attachment", "subsystem_file"}


def test_find_file_box_widget():
    layout = {
        "ir_version": 3,
        "page": {
            "widgets": [
                {"id": "top", "type": "file_box"},
                {"id": "not-file", "type": "text"},
                {
                    "id": "outer",
                    "type": "layout",
                    "children": [{"id": "nested", "type": "file_box"}],
                },
            ],
        },
    }
    assert pfs.find_file_box_widget(layout, "top")["id"] == "top"
    assert pfs.find_file_box_widget(layout, "nested")["id"] == "nested"
    assert pfs.find_file_box_widget(layout, "not-file") is None
    assert pfs.find_file_box_widget(layout, "missing") is None


def test_widget_setting_defaults_and_type_fallbacks():
    default = pfs.widget_setting({"id": "w", "type": "file_box"})
    assert default["upload_by"] == "portal_user"
    assert default["max_files"] == 20
    assert default["read_scope"] == []
    assert default["allowed_ext"] == set()

    bad = pfs.widget_setting({
        "id": "w",
        "type": "file_box",
        "max_files": "abc",
        "read_scope": "x",
    })
    assert bad["max_files"] == 20
    assert bad["read_scope"] == []

    good = pfs.widget_setting({
        "id": "w",
        "type": "file_box",
        "upload_by": "designer",
        "per_file_acl": True,
        "guest_readable": True,
        "read_scope": ["donation.manage", 1],
        "max_files": 3,
        "allowed_ext": [".PDF", "png"],
    })
    assert good["upload_by"] == "designer"
    assert good["per_file_acl"] is True
    assert good["guest_readable"] is True
    assert good["read_scope"] == ["donation.manage"]
    assert good["max_files"] == 3
    assert good["allowed_ext"] == {"pdf", "png"}


def test_service_crud_and_acl_replacement(portal_base):
    sub_sc = "portal_file_crud"
    dsm.init_portal_sqlite(sub_sc)
    with dsm.DataSourceManager().get_session(sub_sc, "portal") as sess:
        sess.execute(
            text(
                "INSERT INTO portal_users "
                "(secure_code, username, display_name, password_hash, role_code, is_active) "
                "VALUES (:sc, 'active', 'Active', 'hash', 'PUBLIC_USER', 1)"
            ),
            {"sc": "active_user_sc"},
        )
        sess.execute(
            text(
                "INSERT INTO portal_users "
                "(secure_code, username, display_name, password_hash, role_code, is_active) "
                "VALUES (:sc, 'inactive', 'Inactive', 'hash', 'PUBLIC_USER', 0)"
            ),
            {"sc": "inactive_user_sc"},
        )

    row = pfs.create_file_record(
        sub_sc,
        platform_file_sc="platform_file_sc",
        page_sc="page_sc",
        widget_id="filebox",
        uploader_ref="designer:designer_sc",
        original_name="a.pdf",
        file_size=123,
        file_ext="pdf",
    )

    assert pfs.list_widget_files(sub_sc, "page_sc", "filebox")[0]["secure_code"] == row["secure_code"]
    assert pfs.count_uploader_files(sub_sc, "page_sc", "filebox", "designer:designer_sc") == 1
    assert pfs.get_file(sub_sc, row["secure_code"])["platform_file_sc"] == "platform_file_sc"

    first_acl = pfs.set_file_acl(sub_sc, row["secure_code"], [
        {"grantee_type": "user", "grantee_code": "active_user_sc"},
        {"grantee_type": "role", "grantee_code": "PORTAL_ADMIN"},
    ])
    assert {(a["grantee_type"], a["grantee_code"]) for a in first_acl} == {
        ("user", "active_user_sc"),
        ("role", "PORTAL_ADMIN"),
    }
    second_acl = pfs.set_file_acl(sub_sc, row["secure_code"], [
        {"grantee_type": "role", "grantee_code": "PORTAL_ADMIN"},
    ])
    assert [(a["grantee_type"], a["grantee_code"]) for a in second_acl] == [
        ("role", "PORTAL_ADMIN")
    ]

    assert pfs.acl_grantees_exist(sub_sc, [{"grantee_type": "user", "grantee_code": "active_user_sc"}]) == (True, "")
    assert pfs.acl_grantees_exist(sub_sc, [{"grantee_type": "user", "grantee_code": "missing_user"}]) == (False, "missing_user")
    assert pfs.acl_grantees_exist(sub_sc, [{"grantee_type": "user", "grantee_code": "inactive_user_sc"}]) == (False, "inactive_user_sc")

    assert pfs.soft_delete_file(sub_sc, row["secure_code"]) is True
    assert pfs.list_widget_files(sub_sc, "page_sc", "filebox") == []
    assert pfs.count_uploader_files(sub_sc, "page_sc", "filebox", "designer:designer_sc") == 0
    assert pfs.get_file(sub_sc, row["secure_code"]) is None
    assert pfs.list_file_acl(sub_sc, row["secure_code"]) == []


@pytest.mark.parametrize("context_type", [
    "org_logo",
    "nc_background",
    "wf_background",
    "portal_file",
    "whatever_unknown",
])
def test_generic_upload_rejects_non_generic_context_types(auth_client, context_type):
    response = auth_client.post(
        f"{API_PREFIX}/api/files/upload",
        data={
            "context_type": context_type,
            "file": (io.BytesIO(b"x"), "x.png"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert response.get_json()["success"] is False


@pytest.fixture
def nocode_manage_permission(app):
    permission = Permission(
        secure_code="perm_nocode_manage01",
        resource_type="nocode_builder",
        action="manage",
        code="nocode_builder.manage",
        name="NoCode Manage",
        permission_level="ORG",
        is_system_permission=True,
        is_active=True,
        is_deleted=False,
    )
    db.session.add(permission)
    db.session.commit()
    return permission


def _sub_system(org_sc, secure_code):
    sub = DcSubSystem(
        secure_code=secure_code,
        org_secure_code=org_sc,
        code=secure_code[-8:],
        name=secure_code,
        is_active=True,
        is_deleted=False,
    )
    db.session.add(sub)
    db.session.commit()
    return sub


def _page(org_sc, secure_code, widget):
    page = DcPageLayout(
        secure_code=secure_code,
        org_secure_code=org_sc,
        name=secure_code,
        layout_json={
            "ir_version": 3,
            "page": {"id": secure_code, "widgets": [widget]},
        },
        style_config={},
        is_active=True,
        is_deleted=False,
    )
    db.session.add(page)
    db.session.commit()
    return page


def _mount(org_sc, sub_sc, page_sc):
    mount = DcSubSystemPage(
        secure_code=f"mnt_{sub_sc[-8:]}_{page_sc[-8:]}",
        org_secure_code=org_sc,
        sub_system_secure_code=sub_sc,
        page_layout_secure_code=page_sc,
        display_name="Page",
        is_active=True,
        is_deleted=False,
    )
    db.session.add(mount)
    db.session.commit()
    return mount


def test_portal_file_api_integrations_when_blueprint_registered(
        app, client, admin_client, test_org, nocode_manage_permission):
    info = client.get(f"{API_PREFIX}/api/nocode-builder/info")
    if info.status_code == 404:
        pytest.skip("test app 未註冊 nocode_builder blueprint；API 層由主 Claude 以 curl 實測")

    response = client.post(f"{API_PREFIX}/api/nocode-builder/sub-systems/sub_api_000000000001/portal-files")
    assert response.status_code != 200

    other = Organization(
        secure_code="other_org_0000000001",
        code="OTHER_ORG",
        name="Other Org",
        domain_name="other.local",
        is_active=True,
        is_deleted=False,
    )
    db.session.add(other)
    db.session.commit()
    _sub_system(other.secure_code, "sub_other_0000000001")
    response = admin_client.delete(
        f"{API_PREFIX}/api/nocode-builder/sub-systems/sub_other_0000000001/portal-files/file_00000000000001"
    )
    assert response.status_code == 404

    sub = _sub_system(test_org.secure_code, "sub_api_000000000001")
    text_page = _page(test_org.secure_code, "page_api_00000000001", {"id": "box1", "type": "text"})
    _mount(test_org.secure_code, sub.secure_code, text_page.secure_code)
    response = admin_client.get(
        f"{API_PREFIX}/api/nocode-builder/sub-systems/{sub.secure_code}/portal-files"
        f"?page={text_page.secure_code}&widget=box1"
    )
    assert response.status_code == 404

    portal_user_page = _page(
        test_org.secure_code,
        "page_api_00000000002",
        {"id": "box2", "type": "file_box", "upload_by": "portal_user"},
    )
    _mount(test_org.secure_code, sub.secure_code, portal_user_page.secure_code)
    response = admin_client.post(
        f"{API_PREFIX}/api/nocode-builder/sub-systems/{sub.secure_code}/portal-files",
        data={
            "page_sc": portal_user_page.secure_code,
            "widget_id": "box2",
            "file": (io.BytesIO(b"x"), "x.pdf"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert response.get_json()["success"] is False
