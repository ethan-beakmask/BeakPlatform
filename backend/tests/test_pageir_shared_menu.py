"""Page IR shared menu reference tests."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from flask import Flask

os.environ.setdefault("SYSTEM_ORG_CODE", "system.local")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.pageir import validate_page_ir
from app.pageir.context import clear_render_context, set_render_context
from app.pageir.registry import (
    _MENU_PROVIDERS,
    _SHARED_MENU_RESOLVERS,
    register_menu_provider,
    register_shared_menu_resolver,
)
from app.pageir.renderer import _prepare_menu
from modules.nocode_builder.services.page_template_service import sanitize_template_ir


@pytest.fixture
def pir_app():
    app = Flask(__name__, template_folder="../app/templates")
    app.secret_key = "test-secret"
    return app


@pytest.fixture(autouse=True)
def reset_menu_registry():
    old_menu_providers = dict(_MENU_PROVIDERS)
    old_resolvers = dict(_SHARED_MENU_RESOLVERS)
    _MENU_PROVIDERS.clear()
    _SHARED_MENU_RESOLVERS.clear()
    yield
    _MENU_PROVIDERS.clear()
    _MENU_PROVIDERS.update(old_menu_providers)
    _SHARED_MENU_RESOLVERS.clear()
    _SHARED_MENU_RESOLVERS.update(old_resolvers)
    clear_render_context()


def _doc(widget):
    return {
        "ir_version": 3,
        "page": {
            "id": "shared-menu-page",
            "title_i18n": {"zh-TW": "Shared Menu"},
            "widgets": [widget],
        },
    }


def test_menu_schema_accepts_shared_ref_without_items():
    ok, errors = validate_page_ir(_doc({
        "id": "menu",
        "type": "menu",
        "shared_ref": "SharedMenuRef001",
        "nav_source": "parent_selection",
    }))

    assert ok, errors


def test_prepare_menu_fail_closed_when_shared_ref_unresolved(pir_app):
    calls = []
    register_menu_provider("portal", lambda items, ctx: calls.append(items) or items)

    with pir_app.test_request_context("/"):
        set_render_context("portal", sub_system_sc="ss_123")
        prepared = _prepare_menu(
            {"id": "menu", "type": "menu", "shared_ref": "MissingShared001", "items": []},
            {},
        )

    assert prepared["entries"] == []
    assert calls == [[]]


def test_prepare_menu_shared_config_page_style_overrides(pir_app):
    captured = {}

    def provider(items, ctx):
        captured["items"] = items
        captured["ctx"] = ctx
        return [{"label": item["node"], "url": "/x", "icon": None, "node": item["node"], "children": []} for item in items]

    register_menu_provider("portal", provider)
    register_shared_menu_resolver("portal", lambda ref, ctx: {
        "items": [{"kind": "node", "node": "SharedMenuNode001"}],
        "config": {
            "orientation": "horizontal",
            "item_gap": 18,
            "hover_expand": False,
            "nav_source": "self",
            "nav_key": "sharednav",
            "style": {
                "bg_color": "#111111",
                "item_text_color": "#222222",
            },
        },
    })

    with pir_app.test_request_context("/"):
        set_render_context("portal", sub_system_sc="ss_123")
        prepared = _prepare_menu(
            {
                "id": "menu",
                "type": "menu",
                "shared_ref": "SharedMenu001",
                "items": [{"kind": "node", "node": "LocalMenuNode001"}],
                "orientation": "vertical",
                "style": {"bg_color": "#ffffff"},
            },
            {"menu": {"id": "menu", "type": "menu", "nav_key": "sharednav"}},
        )

    assert captured["items"] == [{"kind": "node", "node": "SharedMenuNode001"}]
    assert prepared["orientation"] == "vertical"
    assert prepared["item_gap"] == 18
    assert prepared["hover_expand"] is False
    assert captured["ctx"]["menu_nav_key"] == "sharednav"
    assert "--pir-menu-bg:#ffffff" in prepared["style_css"]
    assert "--pir-menu-item-text:#333333" in prepared["style_css"]


def test_sanitize_template_ir_clears_shared_ref_and_adds_items():
    doc = _doc({
        "id": "menu",
        "type": "menu",
        "shared_ref": "SharedMenuRef001",
        "orientation": "horizontal",
    })

    new_ir, report = sanitize_template_ir(
        doc,
        source_sub_system_sc="source_subsystem1",
        target_sub_system_sc="target_subsystem1",
        source_org_sc="test_org_00000000001",
        target_org_sc="test_org_00000000001",
    )

    menu = new_ir["page"]["widgets"][0]
    assert "shared_ref" not in menu
    assert menu["items"] == []
    assert report["cleared"]["shared_menu_refs"] == 1
    ok, errors = validate_page_ir(new_ir)
    assert ok, errors
