"""Page IR v3 伺服器端渲染器。"""
from __future__ import annotations

import logging
from datetime import datetime
from math import ceil
from urllib.parse import urlencode

from flask import current_app, render_template, request, url_for

from app.pageir.context import get_render_context
from app.pageir.masking import apply_record_masks, apply_row_masks, masked_fields
from app.pageir.registry import (
    get_access_evaluator,
    get_action,
    get_portal_action,
    get_resource,
)
from app.pageir.validator import validate_page_ir

logger = logging.getLogger(__name__)


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

    widgets_by_id = _index_widgets(doc["page"].get("widgets", []))
    prepared = [
        prepared_widget
        for widget in doc["page"].get("widgets", [])
        if (prepared_widget := _prepare_widget(widget, widgets_by_id)) is not None
    ]
    return {
        "html": render_template("pageir/_page_ir.html", widgets=prepared),
        "has_form": _has_widget_type(prepared, "form"),
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


def _prepare_widget(widget: dict, widgets_by_id: dict[str, dict]) -> dict | None:
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
    }
    handler = dispatch.get(widget.get("type"))
    if handler is None:
        raise PageIrRenderError(f"Unknown widget type: {widget.get('type')}")
    return handler(widget, widgets_by_id)


def _widget_read_allowed(widget: dict) -> bool:
    matrix = widget.get("access_matrix")
    ctx = get_render_context()
    world = ctx.get("world", "platform")
    if world == "platform":
        return True
    if not matrix:
        return True
    evaluator = get_access_evaluator(world)
    if evaluator is None:
        return False
    try:
        return bool(evaluator(matrix, "read", ctx))
    except Exception:
        logger.exception(
            "Page IR widget access evaluator failed: widget=%s world=%s",
            widget.get("id"),
            world,
        )
        return False


def _prepare_layout(widget: dict, widgets_by_id: dict[str, dict]) -> dict:
    return {
        "type": "layout",
        "id": widget["id"],
        "columns": widget["columns"],
        "gap": widget.get("gap", 0),
        "children": [
            prepared_child
            for child in widget.get("children", [])
            if (prepared_child := _prepare_widget(child, widgets_by_id)) is not None
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
    return _prepare_action_buttons(action_widget)


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


def _prepare_action_buttons(widget: dict) -> list[dict]:
    from app.pageir.context import get_render_context
    from app.services.capability_service import user_can

    if get_render_context().get("world") == "portal":
        return []

    buttons = []
    for button in widget.get("buttons", []):
        if not user_can(button["permission"]):
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
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode({'sc': record_sc})}"


def _egress_visibility(resource: str, context: str, field: str) -> str:
    return current_app.jinja_env.globals["egress_visibility"](resource, context, field)


def _is_datetime(value) -> bool:
    return isinstance(value, datetime)
