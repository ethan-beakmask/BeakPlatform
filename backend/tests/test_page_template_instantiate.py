"""PF-26 page template instantiation sanitization tests."""
from __future__ import annotations

import copy
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.ext.compiler import compiles

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("SYSTEM_ORG_CODE", "system.local")
os.environ.setdefault("SKIP_MODULE_SYNC", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import create_app, db
from app.models import Organization, User
from app.models.user import UserType
from app.pageir import validate_page_ir
from modules.nocode_builder.models import DcPageLayout, DcPageTemplate, DcSubSystem
from modules.nocode_builder.services.page_template_service import sanitize_template_ir


API_PREFIX = "/beakplatform/api/nocode-builder"


@pytest.fixture(scope="function")
def app():
    from app.module_loader import module_loader

    module_loader._loaded = False
    module_loader.modules.clear()
    for name in list(sys.modules):
        if name == "modules.nocode_builder.api" or name.startswith("modules.nocode_builder.api."):
            del sys.modules[name]
    flask_app = create_app("testing")

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@compiles(JSONB, "sqlite")
def _compile_jsonb_on_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(INET, "sqlite")
def _compile_inet_on_sqlite(type_, compiler, **kw):
    return "TEXT"


@pytest.fixture
def second_org_admin(app, db_session):
    org = Organization(
        secure_code="test_org_00000000002",
        code="TEST_ORG_2",
        name="Second Organization",
        domain_name="test2.local",
        is_active=True,
        is_deleted=False,
    )
    admin = User(
        secure_code="test_admin_0000000002",
        org_secure_code=org.secure_code,
        username="testadmin2",
        email="admin2@example.com",
        display_name="Second Admin",
        user_type=UserType.ORG_ADMIN,
        is_active=True,
        is_deleted=False,
    )
    admin.set_password("password123")
    db_session.add_all([org, admin])
    db_session.commit()
    return org, admin


def _login(client, user, org):
    with client.session_transaction() as sess:
        sess["_user_id"] = user.get_id()
        sess["_fresh"] = True
        sess["org_secure_code"] = org.secure_code
        sess["org_domain"] = org.domain_name


def _text(widget_id="intro-text"):
    return {
        "id": widget_id,
        "type": "text",
        "level": "h2",
        "content_i18n": {"zh-TW": widget_id},
    }


def _binding():
    return {"resource": "portal:resource01", "view": "list", "fields": ["name"]}


def _table(widget_id="table-one", **extra):
    widget = {
        "id": widget_id,
        "type": "table",
        "binding": _binding(),
        "columns": [{"field": "name", "label_i18n": {"zh-TW": "名稱"}}],
    }
    widget.update(extra)
    return widget


def _detail(widget_id="detail-one"):
    return {
        "id": widget_id,
        "type": "detail",
        "binding": _binding(),
        "fields": [{"field": "name", "label_i18n": {"zh-TW": "名稱"}}],
    }


def _form(widget_id="form-one", **extra):
    widget = {
        "id": widget_id,
        "type": "form",
        "formio_schema": {"components": []},
    }
    widget.update(extra)
    return widget


def _menu(widget_id="menu-one", **extra):
    widget = {
        "id": widget_id,
        "type": "menu",
        "items": [
            {
                "kind": "node",
                "node": "node_secure_000001",
                "children": [{"kind": "node", "node": "node_secure_000002"}],
            },
            {"kind": "system", "link": "login"},
        ],
    }
    widget.update(extra)
    return widget


def _doc(widgets, **page_extra):
    page = {
        "id": "template-page",
        "title_i18n": {"zh-TW": "樣板頁"},
        "widgets": widgets,
    }
    page.update(page_extra)
    return {"ir_version": 3, "page": page}


def _grid_canvas(*widget_ids):
    return {
        "min_width": 1280,
        "col_widths": [1],
        "row_heights": [120],
        "zones": [{
            "id": "zone-one",
            "row": 1,
            "col": 1,
            "row_span": 1,
            "col_span": 1,
            "widget_ids": list(widget_ids),
        }],
    }


def _free_canvas(*widget_ids):
    return {
        "min_width": 1280,
        "row_unit": 60,
        "columns": 12,
        "frames": [{
            "id": "frame-one",
            "x": 0,
            "y": 0,
            "w": 6,
            "h": 4,
            "widget_ids": list(widget_ids),
        }],
    }


def _sub_system(db_session, org_sc, secure_code):
    sub = DcSubSystem(
        secure_code=secure_code,
        org_secure_code=org_sc,
        code=secure_code[-8:],
        name=secure_code,
        is_active=True,
        is_deleted=False,
    )
    db_session.add(sub)
    db_session.commit()
    return sub


def _template(db_session, *, secure_code, org_secure_code, layout_json, **extra):
    tpl = DcPageTemplate(
        secure_code=secure_code,
        org_secure_code=org_secure_code,
        name=extra.pop("name", "樣板"),
        category="常用",
        layout_json=layout_json,
        style_config={},
        is_active=True,
        is_deleted=False,
        **extra,
    )
    db_session.add(tpl)
    db_session.commit()
    return tpl


def test_same_sub_system_instantiate_preserves_layout_exactly(admin_client, db_session, test_org):
    sub = _sub_system(db_session, test_org.secure_code, "subsystem_00000001")
    layout = _doc([
        _menu(),
        _table("table-one", row_link_ref="detail-one"),
        _detail(),
    ])
    tpl = _template(
        db_session,
        secure_code="template_000000001",
        org_secure_code=test_org.secure_code,
        scope="sub_system",
        sub_system_secure_code=sub.secure_code,
        source_sub_system_sc=sub.secure_code,
        layout_json=layout,
    )

    resp = admin_client.post(
        f"{API_PREFIX}/templates/{tpl.secure_code}/instantiate",
        json={"name": "新頁面", "sub_system_secure_code": sub.secure_code},
    )

    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["report"]["sanitized"] is False
    page = db_session.query(DcPageLayout).filter_by(secure_code=data["page"]["secure_code"]).one()
    # 除了頁面標題換成新頁名稱之外，同子系統套用不動任何引用
    assert page.layout_json["page"]["title_i18n"] == {"zh-TW": "新頁面"}
    expected = copy.deepcopy(layout)
    expected["page"]["title_i18n"] = {"zh-TW": "新頁面"}
    assert page.layout_json == expected


def test_create_sub_system_template_defaults_source_sub_system(admin_client, db_session, test_org):
    sub = _sub_system(db_session, test_org.secure_code, "subsystem_00000004")

    resp = admin_client.post(
        f"{API_PREFIX}/templates",
        json={
            "name": "子系統樣板",
            "scope": "sub_system",
            "sub_system_secure_code": sub.secure_code,
            "layout_json": _doc([_text()]),
        },
    )

    assert resp.status_code == 200
    secure_code = resp.get_json()["data"]["secure_code"]
    tpl = db_session.query(DcPageTemplate).filter_by(secure_code=secure_code).one()
    assert tpl.source_sub_system_sc == sub.secure_code
    assert resp.get_json()["data"]["source_sub_system_sc"] == sub.secure_code


def test_cross_sub_system_sanitizes_external_references():
    layout = _doc([
        _menu(),
        _table("table-one", row_link_ref="detail-one"),
        _detail(),
        _form(mapping_ref="mapping001"),
    ])

    new_ir, report = sanitize_template_ir(
        layout,
        source_sub_system_sc="source_subsystem1",
        target_sub_system_sc="target_subsystem1",
        source_org_sc="test_org_00000000001",
        target_org_sc="test_org_00000000001",
    )

    widgets = new_ir["page"]["widgets"]
    assert report["sanitized"] is True
    assert {item["id"] for item in report["removed_widgets"]} == {"table-one", "detail-one"}
    assert [item["kind"] for item in widgets[0]["items"]] == ["system"]
    assert widgets[1]["type"] == "form"
    assert "mapping_ref" not in widgets[1]
    assert all("row_link_ref" not in widget for widget in widgets)


def test_grid_canvas_filters_removed_widget_ids():
    layout = _doc(
        [_text(), _table("table-one")],
        engine="grid",
        canvas=_grid_canvas("intro-text", "table-one", "missing-widget"),
    )

    new_ir, _report = sanitize_template_ir(
        layout,
        source_sub_system_sc="source_subsystem1",
        target_sub_system_sc="target_subsystem1",
        source_org_sc="test_org_00000000001",
        target_org_sc="test_org_00000000001",
    )

    assert new_ir["page"]["canvas"]["zones"][0]["widget_ids"] == ["intro-text"]


def test_free_canvas_filters_removed_widget_ids():
    layout = _doc(
        [_text(), _detail("detail-one")],
        engine="free",
        canvas=_free_canvas("intro-text", "detail-one", "missing-widget"),
    )

    new_ir, _report = sanitize_template_ir(
        layout,
        source_sub_system_sc="source_subsystem1",
        target_sub_system_sc="target_subsystem1",
        source_org_sc="test_org_00000000001",
        target_org_sc="test_org_00000000001",
    )

    assert new_ir["page"]["canvas"]["frames"][0]["widget_ids"] == ["intro-text"]


def test_nested_layout_child_table_is_removed():
    layout = _doc([{
        "id": "layout-one",
        "type": "layout",
        "columns": 2,
        "children": [_text("child-text"), _table("child-table")],
    }])

    new_ir, report = sanitize_template_ir(
        layout,
        source_sub_system_sc="source_subsystem1",
        target_sub_system_sc="target_subsystem1",
        source_org_sc="test_org_00000000001",
        target_org_sc="test_org_00000000001",
    )

    assert report["removed_widgets"][0]["id"] == "child-table"
    assert [w["id"] for w in new_ir["page"]["widgets"][0]["children"]] == ["child-text"]


def test_background_file_is_cleared_only_cross_org():
    layout = _doc([_menu(style={
        "background_file": "file_secure_001",
        "background_size": "cover",
        "background_repeat": "no-repeat",
        "background_position": "center",
    })])

    same_org_ir, same_org_report = sanitize_template_ir(
        layout,
        source_sub_system_sc="source_subsystem1",
        target_sub_system_sc="target_subsystem1",
        source_org_sc="test_org_00000000001",
        target_org_sc="test_org_00000000001",
    )
    cross_org_ir, cross_org_report = sanitize_template_ir(
        layout,
        source_sub_system_sc="source_subsystem1",
        target_sub_system_sc="target_subsystem1",
        source_org_sc="test_org_00000000001",
        target_org_sc="test_org_00000000002",
    )

    assert same_org_report["cross_org"] is False
    assert same_org_ir["page"]["widgets"][0]["style"]["background_file"] == "file_secure_001"
    assert cross_org_report["cross_org"] is True
    assert cross_org_report["cleared"]["background_files"] == 1
    assert "background_file" not in cross_org_ir["page"]["widgets"][0]["style"]
    assert "background_size" not in cross_org_ir["page"]["widgets"][0]["style"]


def test_sanitized_ir_validates_and_warnings_preserve_permission_refs():
    layout = _doc([
        _form(submit_action_ref="donation.create", access_matrix={
            "create": {"required_permissions": ["bulletin.read"]}
        }),
        {
            "id": "actions-one",
            "type": "actions",
            "buttons": [{
                "id": "create-button",
                "label_i18n": {"zh-TW": "建立"},
                "action_ref": "donation.create",
                "permission": "donation.create",
            }],
        },
    ])

    new_ir, report = sanitize_template_ir(
        layout,
        source_sub_system_sc="source_subsystem1",
        target_sub_system_sc="target_subsystem1",
        source_org_sc="test_org_00000000001",
        target_org_sc="test_org_00000000001",
    )
    ok, errors = validate_page_ir(new_ir)

    assert ok, errors
    assert {"widget_id": "actions-one", "kind": "action_ref", "value": "donation.create"} in report["warnings"]
    assert {"widget_id": "actions-one", "kind": "permission", "value": "donation.create"} in report["warnings"]
    assert {"widget_id": "form-one", "kind": "access_matrix", "value": "bulletin.read"} in report["warnings"]


def test_system_template_can_be_instantiated_by_another_org(client, db_session, test_org, second_org_admin):
    second_org, second_admin = second_org_admin
    target = _sub_system(db_session, second_org.secure_code, "subsystem_00000002")
    tpl = _template(
        db_session,
        secure_code="system_tpl_000001",
        org_secure_code=None,
        scope="system",
        layout_json=_doc([_text()]),
    )
    _login(client, second_admin, second_org)

    resp = client.post(
        f"{API_PREFIX}/templates/{tpl.secure_code}/instantiate",
        json={"name": "第二企業頁面", "sub_system_secure_code": target.secure_code},
    )

    assert resp.status_code == 201
    report = resp.get_json()["data"]["report"]
    assert report["sanitized"] is True
    assert report["cross_org"] is True


def test_instantiate_missing_target_sub_system_returns_404(admin_client, db_session, test_org):
    tpl = _template(
        db_session,
        secure_code="template_000000002",
        org_secure_code=test_org.secure_code,
        scope="org",
        source_sub_system_sc="subsystem_00000001",
        layout_json=_doc([_text()]),
    )

    resp = admin_client.post(
        f"{API_PREFIX}/templates/{tpl.secure_code}/instantiate",
        json={"name": "新頁面", "sub_system_secure_code": "missing_subsystem1"},
    )

    assert resp.status_code == 404


def test_instantiate_empty_name_returns_400(admin_client, db_session, test_org):
    sub = _sub_system(db_session, test_org.secure_code, "subsystem_00000003")
    tpl = _template(
        db_session,
        secure_code="template_000000003",
        org_secure_code=test_org.secure_code,
        scope="org",
        source_sub_system_sc=sub.secure_code,
        layout_json=_doc([_text()]),
    )

    resp = admin_client.post(
        f"{API_PREFIX}/templates/{tpl.secure_code}/instantiate",
        json={"name": "   ", "sub_system_secure_code": sub.secure_code},
    )

    assert resp.status_code == 400


def test_empty_menu_items_validate_after_schema_change():
    layout = _doc([_menu(items=[{"kind": "node", "node": "node_secure_000001"}])])

    new_ir, report = sanitize_template_ir(
        layout,
        source_sub_system_sc="source_subsystem1",
        target_sub_system_sc="target_subsystem1",
        source_org_sc="test_org_00000000001",
        target_org_sc="test_org_00000000001",
    )
    ok, errors = validate_page_ir(new_ir)

    assert report["cleared"]["menu_nodes"] == 1
    assert new_ir["page"]["widgets"][0]["items"] == []
    assert ok, errors


def test_sanitize_drops_parent_selection_nav_and_stays_valid():
    """menu 節點被清空後，parent_selection 的前提消失，nav_source 必須一併拿掉。

    validator 的 menu_nav_no_children 規則要求 parent_selection 至少有一個
    帶 children 的 node；不拿掉的話淨化產物過不了 validate_page_ir，
    instantiate 會回 500。拿掉這件事要記進 report，不可靜默。
    """
    doc = _doc([_menu(nav_source="parent_selection", nav_key="nav")])
    ok, errors = validate_page_ir(doc)
    assert ok, errors

    new_ir, report = sanitize_template_ir(
        doc,
        source_sub_system_sc="sub_system_00000001",
        target_sub_system_sc="sub_system_00000002",
        source_org_sc="test_org_00000000001",
        target_org_sc="test_org_00000000001",
    )

    menu = new_ir["page"]["widgets"][0]
    assert menu["items"] == [{"kind": "system", "link": "login"}]
    assert "nav_source" not in menu
    assert "nav_key" not in menu
    assert report["cleared"]["menu_nav_sources"] == 1

    ok, errors = validate_page_ir(new_ir)
    assert ok, errors


def test_instantiate_overwrites_page_title_with_new_name(admin_client, db_session, test_org):
    """樣板的 title_i18n 是樣板自己的標題，套用後必須換成新頁名稱。

    不換的話 portal 上渲染出來的頁面標題會是樣板名，
    設計器的標題欄也會顯示錯的（使用者以為自己建錯了）。
    """
    sub = _sub_system(db_session, test_org.secure_code, "subsystem_00000091")
    tpl = _template(
        db_session,
        secure_code="template_000000091",
        org_secure_code=test_org.secure_code,
        scope="org",
        source_sub_system_sc=sub.secure_code,
        layout_json=_doc([_text()]),
    )

    resp = admin_client.post(
        f"{API_PREFIX}/templates/{tpl.secure_code}/instantiate",
        json={"name": "我的新頁", "sub_system_secure_code": sub.secure_code},
    )
    assert resp.status_code == 201, resp.get_json()

    page_sc = resp.get_json()["data"]["page"]["secure_code"]
    page = db_session.query(DcPageLayout).filter_by(secure_code=page_sc).one()
    assert page.name == "我的新頁"
    assert page.layout_json["page"]["title_i18n"] == {"zh-TW": "我的新頁"}

    ok, errors = validate_page_ir(page.layout_json)
    assert ok, errors
