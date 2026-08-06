"""Page IR v3 PF-8c menu widget tests."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask

os.environ.setdefault("SYSTEM_ORG_CODE", "system.local")
os.environ.setdefault("SECRET_KEY", "test-secret")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.pageir import render_page_ir_full, validate_page_ir
from app.pageir.context import clear_render_context, set_render_context
from app.pageir.registry import _MENU_PROVIDERS, register_menu_provider
from modules.nocode_builder.services import pageir_portal_menu
from modules.nocode_builder.services import site_map_service
from modules.nocode_builder.services.site_map_service import SiteMapService


@pytest.fixture
def pir_app():
    app = Flask(__name__, template_folder="../app/templates")
    app.secret_key = "test-secret"
    app.jinja_env.globals["_"] = lambda text, **kwargs: text % kwargs if kwargs else text
    app.jinja_env.globals["egress_visibility"] = lambda resource, context, field: "clear"
    app.jinja_env.globals["egress_value"] = lambda resource, context, record_sc, field, value: value
    app.jinja_env.filters["tz_format"] = lambda value, fmt="%Y-%m-%d %H:%M": "DATE"
    return app


@pytest.fixture(autouse=True)
def reset_menu_providers():
    old_menu_providers = dict(_MENU_PROVIDERS)
    _MENU_PROVIDERS.clear()
    yield
    _MENU_PROVIDERS.clear()
    _MENU_PROVIDERS.update(old_menu_providers)
    clear_render_context()


def _doc(widget):
    return {
        "ir_version": 3,
        "page": {
            "id": "menu-page",
            "title_i18n": {"zh-TW": "Menu"},
            "widgets": [widget],
        },
    }


def _menu(items, **overrides):
    widget = {
        "id": "menu",
        "type": "menu",
        "title_i18n": {"zh-TW": "導覽"},
        "items": items,
    }
    widget.update(overrides)
    return widget


def _node(sc, name, order=0, parent=None, node_type="page", page_sc=None, icon=None, created_at=None):
    return SimpleNamespace(
        secure_code=sc,
        sub_system_secure_code="ss_123",
        parent_secure_code=parent,
        name=name,
        icon=icon,
        node_type=node_type,
        page_layout_secure_code=page_sc,
        display_order=order,
        created_at=created_at or "2026-01-01T00:00:00",
        is_active=True,
        is_deleted=False,
    )


class FakeQuery:
    def __init__(self, nodes):
        self.nodes = nodes
        self.calls = []

    def filter_by(self, **kwargs):
        self.calls.append(kwargs)
        return self

    def all(self):
        return self.nodes


def _patch_nodes(monkeypatch, nodes):
    query = FakeQuery(nodes)
    monkeypatch.setattr(pageir_portal_menu, "DcSiteMapNode", SimpleNamespace(query=query))
    return query


def test_schema_menu_widget_accepts_node_system_and_mixed():
    docs = [
        _doc(_menu([{"kind": "node", "node": "YWuxwE3kg-_WjDSZOpihQI"}])),
        _doc(_menu([{"kind": "system", "link": "login"}])),
        _doc(_menu([
            {"kind": "node", "node": "YWuxwE3kg-_WjDSZOpihQI"},
            {"kind": "system", "link": "logout"},
        ])),
    ]
    for doc in docs:
        ok, errors = validate_page_ir(doc)
        assert ok, errors


def test_schema_menu_widget_accepts_empty_items_and_rejects_invalid_items():
    ok, errors = validate_page_ir(_doc(_menu([])))
    assert ok, errors

    invalid_widgets = [
        _menu([{"kind": "system", "link": "profile"}]),
        _menu([{"kind": "node", "node": "bad.node.code0000"}]),
        _menu([{"kind": "node", "node": "YWuxwE3kg-_WjDSZOpihQI", "extra": True}]),
    ]
    for widget in invalid_widgets:
        ok, _errors = validate_page_ir(_doc(widget))
        assert not ok


def test_schema_menu_widget_accepts_auto_without_items_and_renderer_passes_context(pir_app):
    captured = {}

    def provider(items, ctx):
        captured["items"] = items
        captured["ctx"] = ctx
        return []

    widget = {
        "id": "menu",
        "type": "menu",
        "source_mode": "auto",
        "include_system_links": True,
    }
    ok, errors = validate_page_ir(_doc(widget))
    assert ok, errors

    register_menu_provider("portal", provider)
    with pir_app.test_request_context("/"):
        set_render_context(
            "portal",
            sub_system_sc="ss_123",
            portal_user={"user_id": None},
            path_id="pub12345",
        )
        render_page_ir_full(_doc(widget))

    assert captured["items"] == []
    assert captured["ctx"]["menu_source_mode"] == "auto"
    assert captured["ctx"]["menu_include_system_links"] is True


def test_renderer_platform_without_menu_provider_returns_empty_entries(pir_app):
    with pir_app.test_request_context("/"):
        set_render_context("platform")
        rendered = render_page_ir_full(_doc(_menu([{"kind": "system", "link": "login"}])))

    assert rendered["has_form"] is False
    assert 'class="pir-menu-empty"' in rendered["html"]
    assert "沒有可顯示的項目" in rendered["html"]


def test_renderer_menu_provider_exception_fails_closed(pir_app):
    def broken_provider(items, ctx):
        raise RuntimeError("boom")

    register_menu_provider("portal", broken_provider)
    with pir_app.test_request_context("/"):
        set_render_context(
            "portal",
            sub_system_sc="ss_123",
            portal_user={"user_id": None},
            path_id="pub12345",
        )
        rendered = render_page_ir_full(_doc(_menu([{"kind": "system", "link": "login"}])))

    assert 'class="pir-menu-empty"' in rendered["html"]


def test_portal_provider_shows_unselected_parent_for_selected_child(monkeypatch, pir_app):
    parent = _node("ParentSecureCode01", "Parent", node_type="folder")
    child = _node("ChildSecureCode001", "Child", parent=parent.secure_code, page_sc="PageSecureCode001")
    query = _patch_nodes(monkeypatch, [child, parent])
    monkeypatch.setattr(pageir_portal_menu.portal_access_service, "check_page_access", lambda *args: (True, ""))

    with pir_app.test_request_context("/", environ_overrides={"SCRIPT_NAME": "/beakplatform"}):
        entries = pageir_portal_menu._build_portal_menu(
            [{"kind": "node", "node": parent.secure_code, "children": [{"kind": "node", "node": child.secure_code}]}],
            {"sub_system_sc": "ss_123", "portal_user": {"user_id": 1}, "path_id": "portal1"},
        )

    assert len(query.calls) == 1
    assert entries[0]["label"] == "Parent"
    assert entries[0]["url"] is None
    assert entries[0]["children"][0]["label"] == "Child"
    assert entries[0]["children"][0]["url"] == "/beakplatform/public/portal/portal1/p/PageSecureCode001"


def test_portal_provider_removes_denied_leaf_and_empty_parent(monkeypatch, pir_app):
    parent = _node("ParentSecureCode01", "Parent", node_type="folder")
    child = _node("ChildSecureCode001", "Child", parent=parent.secure_code, page_sc="PageSecureCode001")
    _patch_nodes(monkeypatch, [parent, child])
    monkeypatch.setattr(pageir_portal_menu.portal_access_service, "check_page_access", lambda *args: (False, "deny"))

    with pir_app.test_request_context("/"):
        entries = pageir_portal_menu._build_portal_menu(
            [{"kind": "node", "node": parent.secure_code, "children": [{"kind": "node", "node": child.secure_code}]}],
            {"sub_system_sc": "ss_123", "portal_user": {"user_id": 1}, "path_id": "portal1"},
        )

    assert entries == []


def test_portal_provider_orders_nodes_by_items(monkeypatch, pir_app):
    first = _node("FirstSecureCode001", "First", order=1, page_sc="PageFirst001")
    second = _node("SecondSecureCode01", "Second", order=2, page_sc="PageSecond01")
    _patch_nodes(monkeypatch, [second, first])
    monkeypatch.setattr(pageir_portal_menu.portal_access_service, "check_page_access", lambda *args: (True, ""))

    with pir_app.test_request_context("/"):
        entries = pageir_portal_menu._build_portal_menu(
            [
                {"kind": "node", "node": second.secure_code},
                {"kind": "node", "node": first.secure_code},
            ],
            {"sub_system_sc": "ss_123", "portal_user": {"user_id": 1}, "path_id": "portal1"},
        )

    assert [entry["label"] for entry in entries] == ["Second", "First"]


def test_auto_items_shape_order_depth_and_system_links(monkeypatch):
    root_b = _node("RootBSecureCode01", "Root B", order=1, created_at="2026-01-02T00:00:00")
    root_a = _node("RootASecureCode01", "Root A", order=1, created_at="2026-01-01T00:00:00")
    child = _node("ChildSecureCode001", "Child", parent=root_a.secure_code, order=1)
    grandchild = _node("GrandSecureCode001", "Grand", parent=child.secure_code, order=1)
    level4 = _node("Level4SecureCode01", "Level4", parent=grandchild.secure_code, order=1)
    level5 = _node("Level5SecureCode01", "Level5", parent=level4.secure_code, order=1)
    level6 = _node("Level6SecureCode01", "Level6", parent=level5.secure_code, order=1)
    _patch_nodes(monkeypatch, [root_b, level6, level5, level4, grandchild, child, root_a])

    items = pageir_portal_menu._build_auto_items(
        "ss_123",
        {"menu_include_system_links": True},
    )

    assert items == [
        {
            "kind": "node",
            "node": root_a.secure_code,
            "children": [
                {
                    "kind": "node",
                    "node": child.secure_code,
                    "children": [
                        {
                            "kind": "node",
                            "node": grandchild.secure_code,
                            "children": [
                                {
                                    "kind": "node",
                                    "node": level4.secure_code,
                                    "children": [
                                        {
                                            "kind": "node",
                                            "node": level5.secure_code,
                                            "children": [],
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
        },
        {"kind": "node", "node": root_b.secure_code, "children": []},
        {"kind": "system", "link": "login"},
        {"kind": "system", "link": "register"},
        {"kind": "system", "link": "logout"},
    ]


def test_portal_provider_auto_ignores_manual_items_and_reuses_item_entry(monkeypatch, pir_app):
    root = _node("RootSecureCode001", "Root", page_sc="PageRoot001")
    manual = _node("ManualSecureCode01", "Manual", parent="NotRootSecureCode1", page_sc="PageManual001")
    _patch_nodes(monkeypatch, [root, manual])
    monkeypatch.setattr(pageir_portal_menu.portal_access_service, "check_page_access", lambda *args: (True, ""))

    with pir_app.test_request_context("/"):
        entries = pageir_portal_menu._build_portal_menu(
            [{"kind": "node", "node": manual.secure_code}],
            {
                "sub_system_sc": "ss_123",
                "portal_user": {"user_id": 1},
                "path_id": "portal1",
                "menu_source_mode": "auto",
                "menu_include_system_links": False,
            },
        )

    assert [entry["node"] for entry in entries] == [root.secure_code]
    assert entries[0]["url"] == "/public/portal/portal1/p/PageRoot001"


def test_portal_provider_system_links_follow_user_state(monkeypatch, pir_app):
    _patch_nodes(monkeypatch, [])
    monkeypatch.setattr(pageir_portal_menu, "_", lambda text: text)
    monkeypatch.setattr(pageir_portal_menu.portal_auth_service, "is_registration_allowed", lambda sub_sc: False)
    items = [
        {"kind": "system", "link": "login"},
        {"kind": "system", "link": "register"},
        {"kind": "system", "link": "logout"},
    ]

    with pir_app.test_request_context("/", environ_overrides={"SCRIPT_NAME": "/beakplatform"}):
        anonymous = pageir_portal_menu._build_portal_menu(
            items,
            {"sub_system_sc": "ss_123", "portal_user": {"user_id": None}, "path_id": "portal1"},
        )
        logged_in = pageir_portal_menu._build_portal_menu(
            items,
            {"sub_system_sc": "ss_123", "portal_user": {"user_id": 7}, "path_id": "portal1"},
        )

    assert [(entry["label"], entry["url"]) for entry in anonymous] == [
        ("登入", "/beakplatform/public/portal/portal1/login"),
    ]
    assert [(entry["label"], entry["url"]) for entry in logged_in] == [
        ("登出", "/beakplatform/public/portal/portal1/logout"),
    ]


def test_site_map_create_node_accepts_folder_without_page_layout(monkeypatch):
    added = []

    class FakeSession:
        def add(self, obj):
            added.append(obj)

        def flush(self):
            return None

    class FakeNode:
        query = None

        def __init__(self, **kwargs):
            self.secure_code = "FolderSecureCode01"
            for key, value in kwargs.items():
                setattr(self, key, value)

    def fail_layout(*args, **kwargs):
        raise AssertionError("folder must not create DcPageLayout")

    monkeypatch.setattr(site_map_service, "db", SimpleNamespace(session=FakeSession()))
    monkeypatch.setattr(site_map_service, "DcSiteMapNode", FakeNode)
    monkeypatch.setattr(site_map_service, "DcPageLayout", fail_layout)

    folder = SiteMapService.create_node(
        sub_system_sc="ss_123",
        org_sc="org_123",
        name="Docs",
        node_type="folder",
        parent_sc="ParentSecureCode01",
        page_layout_sc="ShouldBeIgnored001",
    )

    assert folder.node_type == "folder"
    assert folder.page_layout_secure_code is None
    assert added == [folder]


def test_site_map_create_node_rejects_folder_root(monkeypatch):
    class FakeQuery:
        def filter(self, *args):
            return self

        def first(self):
            return None

    class FakeNode:
        sub_system_secure_code = "sub_system_secure_code"
        org_secure_code = "org_secure_code"
        parent_secure_code = None
        is_deleted = False
        query = FakeQuery()

    monkeypatch.setattr(site_map_service, "DcSiteMapNode", FakeNode)

    with pytest.raises(ValueError, match="根節點只能是 page"):
        SiteMapService.create_node(
            sub_system_sc="ss_123",
            org_sc="org_123",
            name="welcome",
            node_type="folder",
        )
