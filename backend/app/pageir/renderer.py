"""Page IR v3 伺服器端渲染器。"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from math import ceil
from urllib.parse import quote, urlencode

from flask import current_app, render_template, request, url_for

from app.pageir.context import get_render_context
from app.pageir.masking import apply_record_masks, apply_row_masks, masked_fields
from app.pageir.registry import (
    get_access_evaluator,
    get_action,
    get_menu_provider,
    get_portal_action,
    get_resource,
    get_shared_component_resolver,
)
from app.pageir.validator import validate_page_ir

logger = logging.getLogger(__name__)
PORTAL_RECORD_PLACEHOLDER = "__PIR_RECORD_SC__"
_MENU_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
_MENU_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_MENU_STYLE_DEFAULTS = {
    "bg_color": "#ffffff",
    "item_bg_color": "#ffffff",
    "item_text_color": "#333333",
    "item_hover_bg_color": "#e9ecef",
    "item_hover_text_color": "#333333",
    "accent_color": "#e67e22",
    "border_color": "#dddddd",
    "border_width": 1,
    "border_radius": 4,
    "background_size": "cover",
    "background_repeat": "no-repeat",
    "background_position": "center",
}


class PageIrRenderError(Exception):
    """渲染拒絕（fail-closed），message 只進 log"""


def render_page_ir(doc: dict) -> str:
    """驗證 + 渲染 Page IR v3 文件，回傳 HTML 片段。"""
    return render_page_ir_full(doc)["html"]


def render_page_ir_full(doc: dict) -> dict:
    """驗證 + 渲染 Page IR v3 文件，回傳 HTML 與 runtime meta。"""
    ok, errors = validate_page_ir(doc)
    if not ok:
        raise PageIrRenderError(f"Invalid Page IR: {errors[:5]}")

    current_app.jinja_env.tests["datetime"] = _is_datetime
    current_app.jinja_env.globals["pir_sort_url"] = _sort_url
    current_app.jinja_env.globals["pir_action_url"] = _action_url

    page = doc["page"]
    engine = page.get("engine", "flow")
    widgets = page.get("widgets", [])
    widgets_by_id = _index_widgets(widgets)
    prepared = [
        prepared_widget
        for widget in widgets
        if (prepared_widget := _prepare_widget(widget, widgets_by_id, responsive=engine == "flow")) is not None
    ]
    canvas = _prepare_canvas(page, prepared) if engine in {"grid", "free"} else None
    rendered_widgets = prepared
    if canvas is not None:
        containers = canvas["zones"] if engine == "grid" else canvas["frames"]
        rendered_widgets = [widget for container in containers for widget in container["widgets"]]
    return {
        "html": render_template("pageir/_page_ir.html", widgets=prepared, engine=engine, canvas=canvas),
        "has_form": _has_widget_type(rendered_widgets, "form"),
        "engine": engine,
    }


def _index_widgets(widgets: list[dict]) -> dict[str, dict]:
    indexed = {}
    for widget in widgets:
        indexed[widget["id"]] = widget
        if widget.get("type") == "layout":
            indexed.update(_index_widgets(widget.get("children", [])))
    return indexed


def _has_widget_type(widgets: list[dict], widget_type: str) -> bool:
    for widget in widgets:
        if widget.get("type") == widget_type:
            return True
        if widget.get("type") == "layout" and _has_widget_type(widget.get("children", []), widget_type):
            return True
    return False


def _prepare_canvas(page: dict, prepared_widgets: list[dict]) -> dict:
    engine = page.get("engine", "flow")
    canvas = page.get("canvas")
    if not isinstance(canvas, dict):
        raise PageIrRenderError("Canvas must be an object")

    prepared_by_id = {widget["id"]: widget for widget in prepared_widgets}
    top_widget_ids = {widget.get("id") for widget in page.get("widgets", [])}
    referenced: set[str] = set()
    if engine == "grid":
        prepared_canvas = _prepare_grid_canvas(canvas, prepared_by_id, top_widget_ids, referenced)
    elif engine == "free":
        prepared_canvas = _prepare_free_canvas(canvas, prepared_by_id, top_widget_ids, referenced)
    else:
        raise PageIrRenderError(f"Unsupported canvas engine: {engine}")

    for widget in prepared_widgets:
        if widget["id"] not in referenced:
            logger.info("Page IR top-level widget is not placed on canvas: widget=%s", widget["id"])
    return prepared_canvas


def _prepare_grid_canvas(
    canvas: dict,
    prepared_by_id: dict[str, dict],
    top_widget_ids: set[str],
    referenced: set[str],
) -> dict:
    col_widths = [_safe_float(value, 0.1, 20, "grid col_width") for value in canvas.get("col_widths", [])]
    row_heights = [_safe_int(value, 48, 2000, "grid row_height") for value in canvas.get("row_heights", [])]
    zones = []
    for zone in canvas.get("zones", []):
        row = _safe_int(zone.get("row"), 1, len(row_heights), "grid zone row")
        col = _safe_int(zone.get("col"), 1, len(col_widths), "grid zone col")
        row_span = _safe_int(zone.get("row_span"), 1, len(row_heights), "grid zone row_span")
        col_span = _safe_int(zone.get("col_span"), 1, len(col_widths), "grid zone col_span")
        if row + row_span - 1 > len(row_heights) or col + col_span - 1 > len(col_widths):
            raise PageIrRenderError("Grid zone out of range")
        widgets = _canvas_widgets(zone.get("widget_ids", []), prepared_by_id, top_widget_ids, referenced)
        zones.append({
            "id": zone["id"],
            "row": row,
            "col": col,
            "row_span": row_span,
            "col_span": col_span,
            "overflow": zone.get("overflow", "auto"),
            "widgets": widgets,
        })
    return {
        "min_width": _safe_int(canvas.get("min_width", 1280), 320, 4096, "grid min_width"),
        "col_template": " ".join(_format_fr(value) for value in col_widths),
        "row_template": " ".join(f"{value}px" for value in row_heights),
        "gap": _safe_int(canvas.get("gap", 8), 0, 64, "grid gap"),
        "zones": zones,
    }


def _prepare_free_canvas(
    canvas: dict,
    prepared_by_id: dict[str, dict],
    top_widget_ids: set[str],
    referenced: set[str],
) -> dict:
    frames = []
    for frame in canvas.get("frames", []):
        x = _safe_int(frame.get("x"), 0, 11, "free frame x")
        y = _safe_int(frame.get("y"), 0, 999, "free frame y")
        w = _safe_int(frame.get("w"), 1, 12, "free frame w")
        h = _safe_int(frame.get("h"), 1, 200, "free frame h")
        if x + w > 12:
            raise PageIrRenderError("Free frame out of range")
        widgets = _canvas_widgets(frame.get("widget_ids", []), prepared_by_id, top_widget_ids, referenced)
        frames.append({
            "id": frame["id"],
            "col": x + 1,
            "row": y + 1,
            "w": w,
            "h": h,
            "overflow": frame.get("overflow", "auto"),
            "widgets": widgets,
        })
    return {
        "min_width": _safe_int(canvas.get("min_width", 1280), 320, 4096, "free min_width"),
        "row_unit": _safe_int(canvas.get("row_unit", 60), 20, 200, "free row_unit"),
        "gap": _safe_int(canvas.get("gap", 8), 0, 64, "free gap"),
        "frames": frames,
    }

def _canvas_widgets(
    widget_ids: list[str],
    prepared_by_id: dict[str, dict],
    top_widget_ids: set[str],
    referenced: set[str],
) -> list[dict]:
    widgets = []
    for widget_id in widget_ids:
        if widget_id not in top_widget_ids:
            raise PageIrRenderError(f"Canvas widget ref does not resolve: {widget_id}")
        referenced.add(widget_id)
        widget = prepared_by_id.get(widget_id)
        if widget is not None:
            widgets.append(widget)
    return widgets


def _safe_int(value, minimum: int, maximum: int, label: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise PageIrRenderError(f"Invalid canvas integer: {label}")
    return min(max(number, minimum), maximum)


def _safe_float(value, minimum: float, maximum: float, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise PageIrRenderError(f"Invalid canvas number: {label}")
    return min(max(number, minimum), maximum)


def _format_fr(value: float) -> str:
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return f"{text}fr"



def _prepare_widget(widget: dict, widgets_by_id: dict[str, dict], *, responsive: bool = False) -> dict | None:
    ctx = get_render_context()
    shared_ref = widget.get("shared_ref")
    if shared_ref:
        world = ctx.get("world", "platform")
        resolver = get_shared_component_resolver(world)
        resolved = None
        if resolver is not None:
            try:
                resolved = resolver(shared_ref, ctx)
            except Exception:
                logger.exception(
                    "Page IR shared component resolver failed: widget=%s world=%s shared_ref=%s",
                    widget.get("id"),
                    world,
                    shared_ref,
                )
        if not isinstance(resolved, dict) or not resolved.get("type"):
            logger.warning(
                "Page IR shared component unresolved: widget=%s world=%s shared_ref=%s",
                widget.get("id"),
                world,
                shared_ref,
            )
            return None
        page_matrix = widget.get("access_matrix")
        widget = {**resolved, "id": widget["id"]}
        if page_matrix:
            widget["_page_access_matrix"] = page_matrix

    if not _widget_read_allowed(widget):
        return None

    dispatch = {
        "layout": _prepare_layout,
        "text": _prepare_text,
        "table": _prepare_table,
        "detail": _prepare_detail,
        "master_detail": _prepare_master_detail,
        "actions": _prepare_actions,
        "form": _prepare_form,
        "menu": _prepare_menu,
    }
    handler = dispatch.get(widget.get("type"))
    if handler is None:
        raise PageIrRenderError(f"Unknown widget type: {widget.get('type')}")
    if widget.get("type") == "layout":
        return _prepare_layout(widget, widgets_by_id, responsive)
    prepared = handler(widget, widgets_by_id)
    if prepared is None:
        return None
    # master_detail 的 master 區塊也是 .pir-detail，同樣要吃 720px 塌一欄的規則
    if prepared.get("type") in {"detail", "master_detail"}:
        prepared["responsive"] = responsive
    return prepared


def _widget_read_allowed(widget: dict) -> bool:
    matrices = [widget.get("access_matrix"), widget.get("_page_access_matrix")]
    ctx = get_render_context()
    world = ctx.get("world", "platform")
    if world == "platform":
        return True
    matrices = [matrix for matrix in matrices if matrix]
    if not matrices:
        return True
    evaluator = get_access_evaluator(world)
    if evaluator is None:
        return False
    for matrix in matrices:
        try:
            if not bool(evaluator(matrix, "read", ctx)):
                return False
        except Exception:
            logger.exception(
                "Page IR widget access evaluator failed: widget=%s world=%s",
                widget.get("id"),
                world,
            )
            return False
    return True


def _prepare_layout(widget: dict, widgets_by_id: dict[str, dict], responsive: bool) -> dict:
    return {
        "type": "layout",
        "id": widget["id"],
        "responsive": responsive,
        "columns": widget["columns"],
        "gap": widget.get("gap", 0),
        "children": [
            prepared_child
            for child in widget.get("children", [])
            if (prepared_child := _prepare_widget(child, widgets_by_id, responsive=responsive)) is not None
        ],
    }


def _prepare_text(widget: dict, widgets_by_id: dict[str, dict]) -> dict:
    del widgets_by_id
    return {
        "type": "text",
        "id": widget["id"],
        "level": widget["level"],
        "content": _i18n(widget["content_i18n"]),
    }


def _prepare_menu(widget: dict, widgets_by_id: dict[str, dict]) -> dict:
    ctx = get_render_context()
    world = ctx.get("world", "platform")
    provider = get_menu_provider(world)
    menu_widget = widget
    raw_items = widget.get("items", [])
    source_mode = menu_widget.get("source_mode") if menu_widget.get("source_mode") in {"manual", "auto"} else "manual"
    include_system_links = bool(menu_widget.get("include_system_links"))

    orientation = menu_widget.get("orientation") if menu_widget.get("orientation") in {"vertical", "horizontal"} else "vertical"
    item_gap = _clamped_int(menu_widget.get("item_gap", 6), 0, 32, 6)
    hover_expand = bool(menu_widget.get("hover_expand", True))
    nav_source = menu_widget.get("nav_source") if menu_widget.get("nav_source") in {"self", "parent_selection"} else "self"
    nav_key = menu_widget.get("nav_key") if _valid_menu_token(menu_widget.get("nav_key")) else "nav"
    items = _menu_items_for_nav(raw_items, nav_source, nav_key)
    entries = []
    if provider is not None:
        try:
            menu_ctx = {
                **ctx,
                "menu_nav_source": nav_source,
                "menu_nav_key": nav_key,
                "menu_nav_keys": _menu_nav_keys(widgets_by_id),
                "menu_source_mode": source_mode,
                "menu_include_system_links": include_system_links,
            }
            entries = provider(items, menu_ctx) or []
        except Exception:
            logger.exception(
                "Page IR menu provider failed: widget=%s world=%s",
                widget.get("id"),
                world,
            )
            entries = []
    return {
        "type": "menu",
        "id": widget["id"],
        "title": _i18n(widget["title_i18n"]) if widget.get("title_i18n") else None,
        "entries": entries,
        "orientation": orientation,
        "item_gap": item_gap,
        "hover_expand": hover_expand,
        "style": _menu_style(menu_widget),
        "style_css": _menu_style_css(menu_widget, item_gap),
    }


def _menu_nav_keys(widgets_by_id: dict[str, dict]) -> list[str]:
    """本頁所有 menu widget 用到的 nav 參數名。

    聯動連結只該沿用這些參數（讓同頁多組聯動的選擇並存），
    不能把整個 request.args 複製過去——那會把表格的分頁／排序參數
    一起帶到別的頁面，撞上目標頁同 id 的 widget。
    """
    keys = set()
    for widget in (widgets_by_id or {}).values():
        if widget.get("type") != "menu":
            continue
        nav_key = widget.get("nav_key")
        keys.add(nav_key if _valid_menu_token(nav_key) else "nav")
    return sorted(keys)


def _menu_items_for_nav(items: list[dict], nav_source: str, nav_key: str) -> list[dict]:
    if nav_source != "parent_selection":
        return items
    selected = request.args.get(nav_key)
    if not _valid_menu_token(selected):
        return []
    node = _find_menu_node(items, selected)
    if not node:
        return []
    children = node.get("children")
    return children if isinstance(children, list) else []


def _find_menu_node(items: list[dict], node_sc: str) -> dict | None:
    for item in items or []:
        if item.get("kind") != "node":
            continue
        if item.get("node") == node_sc:
            return item
        found = _find_menu_node(item.get("children") or [], node_sc)
        if found:
            return found
    return None


def _menu_style(widget: dict) -> dict:
    """把使用者自訂樣式收斂成安全值。

    值最後會輸出成 inline style，所以這裡是第二道防線（第一道是 schema pattern）：
    顏色只認 ^#[0-9a-fA-F]{6}$，數值 clamp 到範圍，列舉值只認白名單，
    任何不合的值一律丟棄回預設，不要嘗試修補。
    """
    raw = widget.get("style") if isinstance(widget.get("style"), dict) else {}
    style = dict(_MENU_STYLE_DEFAULTS)
    for key in (
        "bg_color",
        "item_bg_color",
        "item_text_color",
        "item_hover_bg_color",
        "item_hover_text_color",
        "accent_color",
        "border_color",
    ):
        value = raw.get(key)
        if isinstance(value, str) and _MENU_COLOR_RE.fullmatch(value):
            style[key] = value

    style["border_width"] = _clamped_int(raw.get("border_width"), 0, 8, style["border_width"])
    style["border_radius"] = _clamped_int(raw.get("border_radius"), 0, 32, style["border_radius"])

    if raw.get("background_size") in {"cover", "contain", "auto"}:
        style["background_size"] = raw["background_size"]
    if raw.get("background_repeat") in {"no-repeat", "repeat", "repeat-x", "repeat-y"}:
        style["background_repeat"] = raw["background_repeat"]
    if raw.get("background_position") in {"center", "top", "bottom", "left", "right"}:
        style["background_position"] = raw["background_position"]

    background_file = raw.get("background_file")
    if _valid_menu_token(background_file):
        background_url = _menu_background_url(background_file)
        if background_url:
            style["background_image"] = background_url
    return style


def _menu_background_url(secure_code: str) -> str | None:
    try:
        from app.services import file_service

        record = file_service.get_file_by_sc(secure_code)
        if not record or getattr(record, "is_deleted", False):
            return None
        if getattr(record, "context_type", None) != "nc_background":
            return None
        return f"{request.script_root}/api/files/{secure_code}/serve"
    except Exception:
        logger.exception("Page IR menu background lookup failed")
        return None


def _menu_style_css(widget: dict, item_gap: int) -> str:
    style = _menu_style(widget)
    pairs = [
        ("--pir-menu-bg", style["bg_color"]),
        ("--pir-menu-item-bg", style["item_bg_color"]),
        ("--pir-menu-item-text", style["item_text_color"]),
        ("--pir-menu-item-hover-bg", style["item_hover_bg_color"]),
        ("--pir-menu-item-hover-text", style["item_hover_text_color"]),
        ("--pir-menu-accent", style["accent_color"]),
        ("--pir-menu-border", style["border_color"]),
        ("--pir-menu-border-width", f"{style['border_width']}px"),
        ("--pir-menu-border-radius", f"{style['border_radius']}px"),
        ("--pir-menu-gap", f"{item_gap}px"),
    ]
    if style.get("background_image"):
        pairs.extend(
            [
                ("--pir-menu-bg-image", f'url("{_css_string_escape(style["background_image"])}")'),
                ("--pir-menu-bg-size", style["background_size"]),
                ("--pir-menu-bg-repeat", style["background_repeat"]),
                ("--pir-menu-bg-position", style["background_position"]),
            ]
        )
    return ";".join(f"{key}:{value}" for key, value in pairs) + ";"


def _css_string_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _valid_menu_token(value) -> bool:
    return isinstance(value, str) and bool(_MENU_TOKEN_RE.fullmatch(value))


def _clamped_int(value, minimum: int, maximum: int, default: int) -> int:
    if not isinstance(value, int):
        return default
    return min(max(value, minimum), maximum)


def _prepare_table(widget: dict, widgets_by_id: dict[str, dict]) -> dict:
    binding = widget["binding"]
    resource = _checked_resource(binding)
    fields = binding["fields"]
    columns = _visible_table_columns(widget, resource)
    caps = _widget_write_caps(widget, resource)
    form_fields = _table_form_fields(widget, resource) if caps["create"] or caps["update"] else []
    page_size = widget.get("page_size", 20)
    page = _positive_int(request.args.get(f"{widget['id']}__page"), 1)
    sort_field, sort_dir = _table_sort(widget)
    rows, total = resource["fetch_list"](fields, page, page_size, sort_field, sort_dir)
    _check_rows_have_sc(widget["id"], rows)
    rows = apply_row_masks(rows, widget["columns"])
    row_actions = _row_actions(widget, widgets_by_id)
    row_link_target = _row_link_target(widget, widgets_by_id)
    if row_link_target:
        rows = [
            {**row, "_link": _row_link_url(row_link_target, row["_sc"])}
            for row in rows
        ]

    return {
        "type": "table",
        "id": widget["id"],
        "columns": columns,
        "rows": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, ceil(total / page_size)) if page_size else 1,
        "prev_url": _page_url(widget["id"], page - 1) if page > 1 else None,
        "next_url": _page_url(widget["id"], page + 1) if page * page_size < total else None,
        "sort_field": sort_field,
        "sort_dir": sort_dir,
        "egress_resource": resource.get("egress_resource"),
        "row_actions": row_actions,
        "row_link_target": row_link_target,
        "caps": caps,
        "form_fields": form_fields,
    }


def _widget_write_caps(widget: dict, resource: dict) -> dict[str, bool]:
    caps = {"create": False, "update": False, "delete": False}
    ctx = get_render_context()
    world = ctx.get("world", "platform")
    if world != "portal":
        return caps

    matrix = widget.get("access_matrix")
    if not matrix:
        return caps

    crud = resource.get("crud") or {}
    evaluator = get_access_evaluator(world)
    if evaluator is None:
        return caps

    for action in caps:
        if not crud.get(action):
            continue
        try:
            caps[action] = bool(evaluator(matrix, action, ctx))
        except Exception:
            logger.exception(
                "Page IR widget write evaluator failed: widget=%s action=%s world=%s",
                widget.get("id"),
                action,
                world,
            )
            caps[action] = False
    return caps


def _table_form_fields(widget: dict, resource: dict) -> list[dict]:
    writable = set(resource.get("writable_fields") or [])
    masked = masked_fields(widget.get("columns", []))
    labels = {
        column["field"]: _i18n(column["label_i18n"])
        for column in widget.get("columns", [])
    }
    return [
        {"field": field, "label": labels.get(field, field)}
        for field in widget["binding"]["fields"]
        if field in writable and field not in masked
    ]


def _checked_resource(binding: dict) -> dict:
    resource = get_resource(binding["resource"])
    if resource is None:
        raise PageIrRenderError(f"Unregistered resource: {binding['resource']}")
    if binding["view"] not in set(resource.get("views", [])):
        raise PageIrRenderError(
            f"Unregistered view: {binding['resource']}.{binding['view']}"
        )
    allowed = set(resource.get("fields", []))
    if any(field not in allowed for field in binding["fields"]):
        raise PageIrRenderError(
            f"Binding fields exceed whitelist: {binding['resource']}"
        )
    return resource


def _visible_table_columns(widget: dict, resource: dict) -> list[dict]:
    allowed = set(resource.get("fields", []))
    binding_fields = set(widget["binding"]["fields"])
    columns = []
    for column in widget["columns"]:
        field = column["field"]
        if field not in allowed or field not in binding_fields:
            raise PageIrRenderError(f"Table column exceeds whitelist: {field}")
        egress_resource = resource.get("egress_resource")
        if (
            egress_resource
            and _egress_visibility(egress_resource, "list", field) == "hidden"
        ):
            continue
        masked = column.get("mask") is not None
        columns.append({
            "field": field,
            "label": _i18n(column["label_i18n"]),
            "sortable": False if masked else column.get("sortable", False),
            "masked": masked,
        })
    return columns


def _table_sort(widget: dict) -> tuple[str | None, str | None]:
    default_sort = widget.get("default_sort") or {}
    sortable = {
        column["field"]
        for column in widget["columns"]
        if column.get("sortable") is True and column.get("mask") is None
    }
    requested = request.args.get(f"{widget['id']}__sort")
    if requested in sortable:
        sort_field = requested
        sort_dir = request.args.get(
            f"{widget['id']}__dir",
            default_sort.get("dir", "asc"),
        )
    else:
        sort_field = default_sort.get("field")
        sort_dir = default_sort.get("dir")
        if sort_field in masked_fields(widget.get("columns", [])):
            sort_field = None
            sort_dir = None
    if sort_dir not in {"asc", "desc"}:
        sort_dir = default_sort.get("dir", "asc")
        if sort_field is None:
            sort_dir = None
    return sort_field, sort_dir


def _check_rows_have_sc(widget_id: str, rows: list[dict]) -> None:
    if any("_sc" not in row for row in rows):
        raise PageIrRenderError(f"Table rows missing _sc: {widget_id}")


def _row_actions(widget: dict, widgets_by_id: dict[str, dict]) -> list[dict]:
    ref = widget.get("row_actions_ref")
    if not ref:
        return []
    action_widget = widgets_by_id.get(ref)
    if not action_widget or action_widget.get("type") != "actions":
        raise PageIrRenderError(f"row_actions_ref does not resolve: {ref}")
    return _prepare_action_buttons(action_widget, row_context=True)


def _row_link_target(widget: dict, widgets_by_id: dict[str, dict]) -> str | None:
    """回傳列連結要指向的 widget id；未設定回 None。"""
    ref = widget.get("row_link_ref")
    if not ref:
        return None
    target = widgets_by_id.get(ref)
    if not target or target.get("type") not in {"detail", "form", "master_detail"}:
        raise PageIrRenderError(f"row_link_ref does not resolve: {ref}")
    return ref


def _prepare_detail(widget: dict, widgets_by_id: dict[str, dict]) -> dict:
    del widgets_by_id
    binding = widget["binding"]
    resource = _checked_resource(binding)
    allowed = set(resource.get("fields", []))
    if any(field_def["field"] not in allowed for field_def in widget["fields"]):
        raise PageIrRenderError(f"Detail fields exceed whitelist: {binding['resource']}")

    record_sc = request.args.get(f"{widget['id']}__sc", "").strip()
    record = resource["fetch_detail"](record_sc, binding["fields"]) if record_sc else None
    if record is not None and "_sc" not in record:
        record = {**record, "_sc": record_sc}
    record = apply_record_masks(record, widget["fields"])

    fields = []
    egress_resource = resource.get("egress_resource")
    for field_def in widget["fields"]:
        field = field_def["field"]
        if egress_resource and _egress_visibility(egress_resource, "detail", field) == "hidden":
            continue
        fields.append({"field": field, "label": _i18n(field_def["label_i18n"])})

    return {
        "type": "detail",
        "id": widget["id"],
        "layout_columns": widget.get("layout_columns", 1),
        "fields": fields,
        "record": record,
        "egress_resource": egress_resource,
    }


def _prepare_master_detail(widget: dict, widgets_by_id: dict[str, dict]) -> dict:
    del widgets_by_id
    master = widget["master"]
    detail = widget["detail"]
    master_binding = master["binding"]
    detail_binding = detail["binding"]
    master_resource = _checked_resource(master_binding)
    detail_resource = _checked_resource(detail_binding)

    master_allowed = set(master_resource.get("fields", []))
    if any(field_def["field"] not in master_allowed for field_def in master["fields"]):
        raise PageIrRenderError(
            f"Master-detail master fields exceed whitelist: {master_binding['resource']}"
        )

    detail_columns = _visible_table_columns(
        {"binding": detail_binding, "columns": detail["columns"]},
        detail_resource,
    )
    foreign_key = detail["foreign_key"]
    if foreign_key not in set(detail_resource.get("writable_fields") or []):
        raise PageIrRenderError(f"Master-detail foreign_key is not writable: {foreign_key}")

    ctx = get_render_context()
    master_sc = request.args.get(f"{widget['id']}__sc", "").strip()
    master_record = (
        master_resource["fetch_detail"](master_sc, master_binding["fields"])
        if master_sc
        else None
    )
    if master_record is not None and "_sc" not in master_record:
        master_record = {**master_record, "_sc": master_sc}

    can_update_master = bool(master.get("editable") is True and _widget_action_allowed(widget, "update"))
    if not master_sc or master_record is None:
        mode = "new"
        master_record = None
    elif can_update_master:
        mode = "edit"
    else:
        mode = "readonly"
    master_record = apply_record_masks(master_record, master["fields"])

    detail_crud = detail_resource.get("crud") or {}
    can_create_detail = bool(_widget_action_allowed(widget, "create") and detail_crud.get("create"))

    history = _prepare_master_detail_history(
        widget,
        detail_resource,
        detail_binding,
        master_sc,
        master_record,
    )

    return {
        "type": "master_detail",
        "id": widget["id"],
        "mode": mode,
        "master": {
            "fields": _master_detail_fields(master, master_resource),
            "record": master_record,
            "layout_columns": master.get("layout_columns", 1),
            "egress_resource": master_resource.get("egress_resource"),
        },
        "detail": {
            "columns": detail_columns,
            "foreign_key": foreign_key,
            "can_create": can_create_detail,
            "egress_resource": detail_resource.get("egress_resource"),
        },
        "history": history,
        "submit_url": _portal_master_detail_submit_url(widget, ctx) if can_create_detail else None,
    }


def _master_detail_fields(master: dict, resource: dict) -> list[dict]:
    fields = []
    egress_resource = resource.get("egress_resource")
    for field_def in master["fields"]:
        field = field_def["field"]
        if egress_resource and _egress_visibility(egress_resource, "detail", field) == "hidden":
            continue
        fields.append({"field": field, "label": _i18n(field_def["label_i18n"])})
    return fields


def _widget_action_allowed(widget: dict, action: str) -> bool:
    ctx = get_render_context()
    world = ctx.get("world", "platform")
    if world != "portal":
        return False
    evaluator = get_access_evaluator(world)
    if evaluator is None:
        return False
    try:
        return bool(evaluator(widget.get("access_matrix") or {}, action, ctx))
    except Exception:
        logger.exception(
            "Page IR widget action evaluator failed: widget=%s action=%s world=%s",
            widget.get("id"),
            action,
            world,
        )
        return False


def _prepare_master_detail_history(
    widget: dict,
    detail_resource: dict,
    detail_binding: dict,
    master_sc: str,
    master_record: dict | None,
) -> dict:
    detail = widget["detail"]
    history_cfg = widget.get("history") or {}
    page_size = history_cfg.get("page_size") or detail.get("page_size") or 20
    page = _positive_int(request.args.get(f"{widget['id']}__hpage"), 1)
    fetch_related = detail_resource.get("fetch_related")
    enabled = (
        history_cfg.get("enabled") is True
        and bool(master_sc)
        and master_record is not None
        and callable(fetch_related)
    )
    empty = {
        "enabled": False,
        "rows": [],
        "total": 0,
        "page": page,
        "pages": 1,
        "prev_url": None,
        "next_url": None,
    }
    if not enabled:
        return empty

    default_sort = history_cfg.get("default_sort") or {}
    sort_field = default_sort.get("field")
    sort_dir = default_sort.get("dir")
    if sort_field in masked_fields(detail.get("columns", [])):
        sort_field = None
        sort_dir = None
    rows, total = fetch_related(
        detail["foreign_key"],
        master_sc,
        detail_binding["fields"],
        page,
        page_size,
        sort_field,
        sort_dir,
    )
    rows = apply_row_masks(rows, detail["columns"])
    pages = max(1, ceil(total / page_size)) if page_size else 1
    return {
        "enabled": True,
        "rows": rows,
        "total": total,
        "page": page,
        "pages": pages,
        "prev_url": _history_page_url(widget["id"], page - 1) if page > 1 else None,
        "next_url": _history_page_url(widget["id"], page + 1) if page * page_size < total else None,
    }


def _prepare_actions(widget: dict, widgets_by_id: dict[str, dict]) -> dict:
    del widgets_by_id
    return {
        "type": "actions",
        "id": widget["id"],
        "buttons": _prepare_action_buttons(widget),
    }


def _prepare_action_buttons(widget: dict, *, row_context=False) -> list[dict]:
    from app.pageir.context import get_render_context
    from app.services.capability_service import user_can

    ctx = get_render_context()
    if ctx.get("world") == "portal":
        return _prepare_portal_action_buttons(widget, ctx, row_context)

    buttons = []
    for button in widget.get("buttons", []):
        permission = button.get("permission")
        if not permission:
            continue
        if not user_can(permission):
            continue
        action = get_action(button["action_ref"])
        if action is None:
            raise PageIrRenderError(f"Unregistered action: {button['action_ref']}")
        method = action.get("method", "POST")
        if method != "POST":
            raise PageIrRenderError(f"Unsupported action method: {button['action_ref']}")
        buttons.append({
            "id": button["id"],
            "label": _i18n(button["label_i18n"]),
            "style": button.get("style", "secondary"),
            "url": action["url"],
            "method": method,
            "confirm": bool(action.get("confirm", False)),
            "requires_record": False,
            "row_flag": None,
        })
    return buttons


def _prepare_portal_action_buttons(widget: dict, ctx: dict, row_context: bool) -> list[dict]:
    # actions widget 用 update 作為 widget 級寫入准入 key。
    if not _widget_action_allowed(widget, "update"):
        return []
    if not ctx.get("path_id") or not ctx.get("page_sc"):
        return []

    buttons = []
    for button in widget.get("buttons", []):
        action = get_portal_action(button["action_ref"])
        if action is None:
            logger.warning(
                "Page IR portal action unregistered, button skipped: widget=%s ref=%s",
                widget.get("id"),
                button.get("action_ref"),
            )
            continue
        if action.get("method", "POST") != "POST":
            logger.warning(
                "Page IR portal action unsupported method, button skipped: widget=%s ref=%s method=%s",
                widget.get("id"),
                button.get("action_ref"),
                action.get("method"),
            )
            continue
        endpoint = action.get("endpoint")
        if not endpoint:
            logger.warning(
                "Page IR portal action missing endpoint, button skipped: widget=%s ref=%s",
                widget.get("id"),
                button.get("action_ref"),
            )
            continue
        requires_record = bool(action.get("requires_record"))
        if requires_record and not row_context:
            logger.warning(
                "Page IR portal row action outside row context, button skipped: widget=%s ref=%s",
                widget.get("id"),
                button.get("action_ref"),
            )
            continue

        kwargs = {
            "path_id": ctx["path_id"],
            "page_sc": ctx["page_sc"],
            "widget_id": widget["id"],
        }
        if requires_record:
            kwargs["record_sc"] = PORTAL_RECORD_PLACEHOLDER
        try:
            url = url_for(endpoint, **kwargs)
        except Exception:
            logger.exception(
                "Page IR portal action endpoint unavailable: widget=%s ref=%s endpoint=%s",
                widget.get("id"),
                button.get("action_ref"),
                endpoint,
            )
            continue
        buttons.append({
            "id": button["id"],
            "label": _i18n(button["label_i18n"]),
            "style": button.get("style", "secondary"),
            "url": url,
            "method": "POST",
            "confirm": bool(action.get("confirm", False)),
            "requires_record": requires_record,
            "row_flag": action.get("row_flag") or None,
        })
    return buttons


def _prepare_form(widget: dict, widgets_by_id: dict[str, dict]) -> dict:
    del widgets_by_id
    ctx = get_render_context()
    world = ctx.get("world", "platform")
    submit_action_ref = widget.get("submit_action_ref")
    submit_url = None
    update_url = None
    mode = "new"
    record_data = None

    if submit_action_ref:
        if world == "portal":
            action = get_portal_action(submit_action_ref)
            record_sc = request.args.get(f"{widget['id']}__sc", "").strip()
            state = None
            if action is not None and record_sc:
                resolver = action.get("state_resolver")
                if callable(resolver):
                    try:
                        state = resolver(record_sc, ctx)
                    except Exception:
                        logger.exception(
                            "Page IR portal form state resolver failed: widget=%s ref=%s",
                            widget.get("id"),
                            submit_action_ref,
                        )
                        state = None
            if state is None:
                submit_url = _portal_form_submit_url(widget, submit_action_ref, ctx)
            else:
                record_data = state.get("form_data") if isinstance(state.get("form_data"), dict) else {}
                mode = "readonly"
                if state.get("editable") is True and _portal_form_update_allowed(widget, ctx):
                    update_url = _portal_form_update_url(widget, action, ctx, record_sc)
                    if update_url:
                        mode = "edit"
        else:
            action = get_action(submit_action_ref)
            if action is None:
                raise PageIrRenderError(
                    f"Unregistered form submit action: {submit_action_ref}")
            submit_url = action.get("url")

    return {
        "type": "form",
        "id": widget["id"],
        "schema": widget["formio_schema"],
        "submit_url": submit_url,
        "update_url": update_url,
        "mode": mode,
        "record_data": record_data,
    }


def _portal_form_submit_url(widget: dict, ref: str, ctx: dict) -> str | None:
    action = get_portal_action(ref)
    if action is None:
        return None
    if not widget.get("mapping_ref"):
        return None

    evaluator = get_access_evaluator("portal")
    if evaluator is None:
        return None
    try:
        allowed = bool(evaluator(widget.get("access_matrix") or {}, "create", ctx))
    except Exception:
        logger.exception(
            "Page IR portal form access evaluator failed: widget=%s ref=%s",
            widget.get("id"),
            ref,
        )
        return None
    if not allowed:
        return None

    if not ctx.get("path_id") or not ctx.get("page_sc"):
        return None

    try:
        return url_for(
            action["endpoint"],
            path_id=ctx["path_id"],
            page_sc=ctx["page_sc"],
            widget_id=widget["id"],
        )
    except Exception:
        logger.exception("Page IR portal form submit endpoint unavailable: ref=%s", ref)
        return None


def _portal_master_detail_submit_url(widget: dict, ctx: dict) -> str | None:
    if ctx.get("world") != "portal":
        return None
    if not _widget_action_allowed(widget, "create"):
        return None
    if not ctx.get("path_id") or not ctx.get("page_sc"):
        return None
    try:
        return url_for(
            "nocode_public_portal.portal_widget_master_detail_submit",
            path_id=ctx["path_id"],
            page_sc=ctx["page_sc"],
            widget_id=widget["id"],
        )
    except Exception:
        logger.exception(
            "Page IR portal master-detail submit endpoint unavailable: widget=%s",
            widget.get("id"),
        )
        return None


def _portal_form_update_allowed(widget: dict, ctx: dict) -> bool:
    evaluator = get_access_evaluator("portal")
    if evaluator is None:
        return False
    try:
        return bool(evaluator(widget.get("access_matrix") or {}, "update", ctx))
    except Exception:
        logger.exception(
            "Page IR portal form update access evaluator failed: widget=%s",
            widget.get("id"),
        )
        return False


def _portal_form_update_url(widget: dict, action: dict, ctx: dict, record_sc: str) -> str | None:
    if not widget.get("mapping_ref"):
        return None
    if not ctx.get("path_id") or not ctx.get("page_sc"):
        return None
    endpoint = action.get("update_endpoint")
    if not endpoint:
        return None
    try:
        return url_for(
            endpoint,
            path_id=ctx["path_id"],
            page_sc=ctx["page_sc"],
            widget_id=widget["id"],
            record_sc=record_sc,
        )
    except Exception:
        logger.exception(
            "Page IR portal form update endpoint unavailable: widget=%s",
            widget.get("id"),
        )
        return None


def _i18n(values: dict[str, str]) -> str:
    locale = _current_locale()
    return values.get(locale) or values.get("zh-TW") or next(iter(values.values()), "")


def _current_locale() -> str:
    try:
        from flask import g
        from flask_babel import get_locale

        return str(getattr(g, "locale", None) or get_locale() or "zh-TW")
    except Exception:
        return "zh-TW"


def _positive_int(value: str | None, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _self_url(args: dict) -> str:
    """組出指向本頁的網址。

    必須帶 `request.script_root`：本 app 掛在 nginx 的 `/beakplatform` 前綴下，
    而 Flask 的 `request.path` **不含**該前綴。只用 request.path 產生的
    `/public/portal/...` 在瀏覽器上會解析成缺前綴的絕對路徑而 404。
    """
    return f"{request.script_root}{request.path}?{urlencode(args, doseq=True)}"


def _page_url(widget_id: str, page: int) -> str:
    args = request.args.to_dict(flat=False)
    args[f"{widget_id}__page"] = [str(page)]
    return _self_url(args)


def _history_page_url(widget_id: str, page: int) -> str:
    args = request.args.to_dict(flat=False)
    args[f"{widget_id}__hpage"] = [str(page)]
    return _self_url(args)


def _row_link_url(target_id: str, row_sc: str) -> str:
    args = request.args.to_dict(flat=False)
    args[f"{target_id}__sc"] = [row_sc]
    return _self_url(args)


def _sort_url(
    widget_id: str,
    field: str,
    current_field: str | None,
    current_dir: str | None,
) -> str:
    args = request.args.to_dict(flat=False)
    args[f"{widget_id}__sort"] = [field]
    args[f"{widget_id}__dir"] = [
        "desc" if current_field == field and current_dir == "asc" else "asc"
    ]
    args[f"{widget_id}__page"] = ["1"]
    return _self_url(args)


def _action_url(url: str, record_sc: str) -> str:
    """列動作的網址；portal 動作用 path placeholder，平台動作沿用 ?sc=。"""
    if url and PORTAL_RECORD_PLACEHOLDER in url:
        return url.replace(PORTAL_RECORD_PLACEHOLDER, quote(str(record_sc or ""), safe=""))
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode({'sc': record_sc})}"


def _egress_visibility(resource: str, context: str, field: str) -> str:
    return current_app.jinja_env.globals["egress_visibility"](resource, context, field)


def _is_datetime(value) -> bool:
    return isinstance(value, datetime)
