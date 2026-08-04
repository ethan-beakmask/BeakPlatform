"""PF-28 system page template seed data tests."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from app.pageir import validate_page_ir


ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT_DIR / "scripts" / "seed_system_page_templates.py"
SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,63}$")
FORBIDDEN_WIDGET_TYPES = {"table", "detail", "master_detail", "form"}


def _load_seed_module():
    spec = importlib.util.spec_from_file_location(
        "seed_system_page_templates",
        SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


seed_module = _load_seed_module()
SYSTEM_TEMPLATES = seed_module.SYSTEM_TEMPLATES


def _iter_widgets(widgets):
    for widget in widgets:
        yield widget
        if widget.get("type") == "layout":
            yield from _iter_widgets(widget.get("children", []))


def _canvas_items(page):
    canvas = page.get("canvas") or {}
    if page.get("engine") == "grid":
        return canvas.get("zones", [])
    if page.get("engine") == "free":
        return canvas.get("frames", [])
    return []


def test_system_template_irs_validate():
    for template in SYSTEM_TEMPLATES:
        ok, errors = validate_page_ir(template["layout_json"])
        assert ok, (template["secure_code"], errors)


def test_system_template_irs_do_not_include_bound_widget_types():
    for template in SYSTEM_TEMPLATES:
        widgets = template["layout_json"]["page"]["widgets"]
        widget_types = {widget.get("type") for widget in _iter_widgets(widgets)}
        assert not (widget_types & FORBIDDEN_WIDGET_TYPES), template["secure_code"]


def test_system_template_menus_have_empty_items():
    for template in SYSTEM_TEMPLATES:
        widgets = template["layout_json"]["page"]["widgets"]
        for widget in _iter_widgets(widgets):
            if widget.get("type") == "menu":
                assert widget.get("items") == [], (
                    template["secure_code"],
                    widget.get("id"),
                )


def test_system_template_secure_codes_are_unique_and_short():
    secure_codes = [template["secure_code"] for template in SYSTEM_TEMPLATES]
    assert len(secure_codes) == 6
    assert len(secure_codes) == len(set(secure_codes))
    assert all(len(code) <= 32 for code in secure_codes)


def test_system_template_ids_are_slugs_and_unique_per_ir():
    for template in SYSTEM_TEMPLATES:
        doc = template["layout_json"]
        page = doc["page"]
        ids = [page["id"]]

        for widget in _iter_widgets(page["widgets"]):
            ids.append(widget["id"])

        for item in _canvas_items(page):
            ids.append(item["id"])

        assert all(SLUG_RE.match(item_id) for item_id in ids), (
            template["secure_code"],
            ids,
        )
        assert len(ids) == len(set(ids)), (template["secure_code"], ids)
