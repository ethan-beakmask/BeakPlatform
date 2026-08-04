"""Page template instantiation helpers."""
from __future__ import annotations

import copy
from typing import Any


def sanitize_template_ir(
    layout_json,
    *,
    source_sub_system_sc,
    target_sub_system_sc,
    source_org_sc,
    target_org_sc,
):
    """回傳 (new_layout_json, report)。不修改傳入的 dict（深拷貝後處理）。"""
    new_ir = copy.deepcopy(layout_json)
    sanitized = (not source_sub_system_sc) or (source_sub_system_sc != target_sub_system_sc)
    cross_org = (not source_org_sc) or (source_org_sc != target_org_sc)
    report = {
        "sanitized": bool(sanitized),
        "cross_org": bool(cross_org),
        "removed_widgets": [],
        "cleared": {
            "menu_nodes": 0,
            "background_files": 0,
            "mapping_refs": 0,
            "row_link_refs": 0,
            "row_actions_refs": 0,
            "menu_nav_sources": 0,
            "shared_menu_refs": 0,
        },
        "warnings": [],
    }

    if not sanitized:
        return new_ir, report

    page = new_ir.get("page") or {}
    widgets = page.get("widgets") or []
    _sanitize_widgets(widgets, report, cross_org)
    existing_ids = {widget.get("id") for widget in _iter_widgets(widgets) if widget.get("id")}

    for widget in _iter_widgets(widgets):
        row_link_ref = widget.get("row_link_ref")
        if row_link_ref and row_link_ref not in existing_ids:
            widget.pop("row_link_ref", None)
            report["cleared"]["row_link_refs"] += 1

        row_actions_ref = widget.get("row_actions_ref")
        if row_actions_ref and row_actions_ref not in existing_ids:
            widget.pop("row_actions_ref", None)
            report["cleared"]["row_actions_refs"] += 1

    _filter_canvas_widget_ids(page, existing_ids)
    return new_ir, report


def _sanitize_widgets(widgets: list[dict[str, Any]], report: dict, cross_org: bool) -> None:
    kept = []
    for widget in widgets:
        widget_type = widget.get("type")
        widget_id = widget.get("id")

        if widget_type in {"table", "detail", "master_detail"}:
            report["removed_widgets"].append({
                "id": widget_id,
                "type": widget_type,
                "reason": "binding_unavailable",
            })
            continue

        if widget_type == "layout":
            _sanitize_widgets(widget.get("children") or [], report, cross_org)
        elif widget_type == "menu":
            if widget.get("shared_ref"):
                widget.pop("shared_ref", None)
                report["cleared"]["shared_menu_refs"] += 1
                if "items" not in widget:
                    widget["items"] = []
            widget["items"] = _sanitize_menu_items(widget.get("items") or [], report)
            if cross_org:
                _clear_menu_background(widget, report)
            # nav_source=parent_selection 必須至少有一個帶 children 的 node
            # （validator 的 menu_nav_no_children 規則）。節點被清空後這個前提不成立，
            # 不拿掉的話淨化產物過不了 validate_page_ir。拿掉會記進 report，不靜默。
            if widget.get("nav_source") == "parent_selection" and not _menu_has_node_with_children(widget.get("items") or []):
                widget.pop("nav_source", None)
                widget.pop("nav_key", None)
                report["cleared"]["menu_nav_sources"] += 1
        elif widget_type == "form":
            if "mapping_ref" in widget:
                widget.pop("mapping_ref", None)
                report["cleared"]["mapping_refs"] += 1

        _collect_warnings(widget, report)
        kept.append(widget)

    widgets[:] = kept


def _sanitize_menu_items(items: list[dict[str, Any]], report: dict) -> list[dict[str, Any]]:
    kept = []
    for item in items:
        if item.get("kind") == "node":
            report["cleared"]["menu_nodes"] += _count_node_items([item])
            continue
        kept.append(item)
    return kept


def _count_node_items(items: list[dict[str, Any]]) -> int:
    count = 0
    for item in items or []:
        if item.get("kind") == "node":
            count += 1
        count += _count_node_items(item.get("children") or [])
    return count


def _clear_menu_background(widget: dict[str, Any], report: dict) -> None:
    style = widget.get("style")
    if not isinstance(style, dict) or "background_file" not in style:
        return
    style.pop("background_file", None)
    style.pop("background_size", None)
    style.pop("background_repeat", None)
    style.pop("background_position", None)
    report["cleared"]["background_files"] += 1


def _menu_has_node_with_children(items: list[dict[str, Any]]) -> bool:
    for item in items or []:
        children = item.get("children") or []
        if item.get("kind") == "node" and children:
            return True
        if _menu_has_node_with_children(children):
            return True
    return False


def _collect_warnings(widget: dict[str, Any], report: dict) -> None:
    widget_id = widget.get("id")
    if widget.get("submit_action_ref"):
        report["warnings"].append({
            "widget_id": widget_id,
            "kind": "submit_action_ref",
            "value": widget["submit_action_ref"],
        })

    if widget.get("type") == "actions":
        for button in widget.get("buttons") or []:
            if button.get("action_ref"):
                report["warnings"].append({
                    "widget_id": widget_id,
                    "kind": "action_ref",
                    "value": button["action_ref"],
                })
            if button.get("permission"):
                report["warnings"].append({
                    "widget_id": widget_id,
                    "kind": "permission",
                    "value": button["permission"],
                })

    for permission in _access_matrix_permissions(widget.get("access_matrix")):
        report["warnings"].append({
            "widget_id": widget_id,
            "kind": "access_matrix",
            "value": permission,
        })


def _access_matrix_permissions(access_matrix) -> list[str]:
    permissions = []
    if not isinstance(access_matrix, dict):
        return permissions
    for rule in access_matrix.values():
        if not isinstance(rule, dict):
            continue
        for permission in rule.get("required_permissions") or []:
            permissions.append(permission)
    return permissions


def _filter_canvas_widget_ids(page: dict[str, Any], existing_ids: set[str]) -> None:
    canvas = page.get("canvas")
    if not isinstance(canvas, dict):
        return
    for area in canvas.get("zones") or []:
        area["widget_ids"] = [widget_id for widget_id in area.get("widget_ids", []) if widget_id in existing_ids]
    for area in canvas.get("frames") or []:
        area["widget_ids"] = [widget_id for widget_id in area.get("widget_ids", []) if widget_id in existing_ids]


def _iter_widgets(widgets: list[dict[str, Any]]):
    for widget in widgets or []:
        yield widget
        if widget.get("type") == "layout":
            yield from _iter_widgets(widget.get("children") or [])
