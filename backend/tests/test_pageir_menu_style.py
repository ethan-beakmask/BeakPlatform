"""Page IR v3 menu style and custom tree tests."""
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
from app.services import file_service
from modules.nocode_builder.services import pageir_portal_menu


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


def _node(sc, name, deleted=False, node_type="page", page_sc=None):
    return SimpleNamespace(
        secure_code=sc,
        sub_system_secure_code="ss_123",
        parent_secure_code=None,
        name=name,
        icon=None,
        node_type=node_type,
        page_layout_secure_code=page_sc,
        display_order=0,
        is_active=True,
        is_deleted=deleted,
    )


class FilteringQuery:
    def __init__(self, nodes):
        self.nodes = nodes
        self.filters = {}

    def filter_by(self, **kwargs):
        self.filters.update(kwargs)
        return self

    def all(self):
        result = self.nodes
        for key, value in self.filters.items():
            result = [node for node in result if getattr(node, key) == value]
        return result


def test_old_flat_menu_items_validate_and_render(pir_app):
    doc = _doc(_menu([{"kind": "node", "node": "OldFlatNodeCode01"}]))
    ok, errors = validate_page_ir(doc)
    assert ok, errors

    with pir_app.test_request_context("/"):
        set_render_context("platform")
        rendered = render_page_ir_full(doc)

    assert 'pir-menu--vertical' in rendered["html"]
    assert 'class="pir-menu-empty"' in rendered["html"]


def test_menu_style_color_injection_rejected_by_schema():
    for value in ["red", "var(--x)", "url(javascript:alert(1))"]:
        ok, errors = validate_page_ir(
            _doc(_menu(
                [{"kind": "node", "node": "ColorNodeSecure1"}],
                style={"bg_color": value},
            ))
        )
        assert not ok
        assert any(error["code"] == "pattern" for error in errors)


def test_menu_background_file_invalid_or_wrong_context_is_ignored(monkeypatch, pir_app):
    doc = _doc(_menu(
        [{"kind": "node", "node": "BgNodeSecureCode"}],
        style={"background_file": "MissingBackground"},
    ))
    monkeypatch.setattr(file_service, "get_file_by_sc", lambda sc: None)
    with pir_app.test_request_context("/"):
        set_render_context("platform")
        rendered = render_page_ir_full(doc)
    assert "--pir-menu-bg-image" not in rendered["html"]

    wrong_context = SimpleNamespace(is_deleted=False, context_type="org_logo")
    monkeypatch.setattr(file_service, "get_file_by_sc", lambda sc: wrong_context)
    with pir_app.test_request_context("/"):
        set_render_context("platform")
        rendered = render_page_ir_full(doc)
    assert "--pir-menu-bg-image" not in rendered["html"]


def test_menu_depth_and_duplicate_node_semantic_errors():
    deep_items = [{"kind": "node", "node": "DepthNodeCode001", "children": []}]
    current = deep_items[0]
    for index in range(2, 7):
        child = {"kind": "node", "node": f"DepthNodeCode00{index}", "children": []}
        current["children"].append(child)
        current = child

    ok, errors = validate_page_ir(_doc(_menu(deep_items)))
    assert not ok
    assert any(error["code"] == "menu_depth" for error in errors)

    duplicate = [
        {"kind": "node", "node": "DuplicateNode001"},
        {"kind": "node", "node": "DuplicateNode001"},
    ]
    ok, errors = validate_page_ir(_doc(_menu(duplicate)))
    assert not ok
    assert any(error["code"] == "menu_duplicate_node" for error in errors)


def test_parent_selection_nav_renders_only_selected_children(pir_app):
    parent_sc = "ParentSelection01"
    child_sc = "ChildSelection001"
    sibling_sc = "SiblingSelect001"

    def provider(items, ctx):
        del ctx
        return [
            {"label": item["node"], "url": f"/p/{item['node']}", "icon": None, "node": item["node"], "children": []}
            for item in items
        ]

    register_menu_provider("portal", provider)
    doc = _doc(_menu(
        [
            {"kind": "node", "node": parent_sc, "children": [{"kind": "node", "node": child_sc}]},
            {"kind": "node", "node": sibling_sc},
        ],
        nav_source="parent_selection",
    ))

    with pir_app.test_request_context(f"/?nav={parent_sc}"):
        set_render_context("portal", sub_system_sc="ss_123", portal_user={"user_id": 1}, path_id="portal1")
        rendered = render_page_ir_full(doc)

    assert child_sc in rendered["html"]
    assert parent_sc not in rendered["html"]
    assert sibling_sc not in rendered["html"]


def test_portal_provider_soft_deleted_node_and_children_disappear(monkeypatch, pir_app):
    parent = _node("DeletedParent001", "Deleted", deleted=True, node_type="folder")
    child = _node("VisibleChild0001", "Child", page_sc="PageVisible0001")
    query = FilteringQuery([parent, child])
    monkeypatch.setattr(pageir_portal_menu, "DcSiteMapNode", SimpleNamespace(query=query))
    monkeypatch.setattr(pageir_portal_menu.portal_access_service, "check_page_access", lambda *args: (True, ""))

    with pir_app.test_request_context("/"):
        entries = pageir_portal_menu._build_portal_menu(
            [{"kind": "node", "node": parent.secure_code, "children": [{"kind": "node", "node": child.secure_code}]}],
            {"sub_system_sc": "ss_123", "portal_user": {"user_id": 1}, "path_id": "portal1"},
        )

    assert entries == []
