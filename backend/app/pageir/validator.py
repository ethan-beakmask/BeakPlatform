"""Page IR v3 JSON Schema 與語意驗證器。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError


_SCHEMA_PATH = Path(__file__).with_name("schema_v3.json")
with _SCHEMA_PATH.open("r", encoding="utf-8") as schema_file:
    _SCHEMA = json.load(schema_file)
_VALIDATOR = Draft202012Validator(_SCHEMA)


def validate_page_ir(doc) -> tuple[bool, list[dict]]:
    """回傳 (ok, errors)；errors 項目含 path、message、code。"""
    try:
        if not isinstance(doc, dict):
            return False, [_error("", "Page IR document must be an object", "not_object")]

        if doc.get("version") == 2:
            return False, [
                _error(
                    "",
                    "Page IR v2 is deprecated; rebuild the page as Page IR v3",
                    "legacy_v2",
                )
            ]

        validation_errors = []
        for err in _VALIDATOR.iter_errors(doc):
            validation_errors.extend(_flatten_schema_errors(err))
        schema_errors = [
            _schema_error(err)
            for err in sorted(validation_errors, key=_schema_error_sort_key)
        ]
        if schema_errors:
            return False, schema_errors

        semantic_errors = _semantic_errors(doc)
        return not semantic_errors, semantic_errors
    except (RecursionError, SchemaError, ValidationError, TypeError, ValueError) as exc:
        return False, [_error("", f"Page IR validation failed: {exc}", "validation_error")]


def _schema_error_sort_key(err: ValidationError) -> tuple[str, str]:
    return (_format_path(err.absolute_path), err.message)


def _schema_error(err: ValidationError) -> dict:
    return _error(_format_path(err.absolute_path), err.message, err.validator)


def _flatten_schema_errors(err: ValidationError) -> list[ValidationError]:
    context = _relevant_context(err)
    # 已經指出是哪一支不合時，oneOf 自己那句「不符合任何 schema」只是噪音
    narrowed = err.validator == "oneOf" and 0 < len(context) < len(err.context)
    errors = [] if narrowed else [err]
    for child in context:
        errors.extend(_flatten_schema_errors(child))
    return errors


def _relevant_context(err: ValidationError) -> list[ValidationError]:
    """oneOf 錯誤只保留「型別相符」的那個分支。

    widget 是 `oneOf` 的一堆分支（每支用 `type` 的 const 區分），jsonschema 會把
    每一支的失敗全部塞進 err.context。全展開的話，放一個空 items 的 menu widget
    會冒出 28 條錯誤（其他分支的 'binding' is required、additionalProperties 等），
    真正那條 `items should be non-empty` 淹沒在裡面。
    分支中出現 `type` 的 const 失敗 = 這個 widget 根本不是那一支，整組丟棄。
    僅影響錯誤呈現，不影響通過與否。
    """
    if err.validator != "oneOf" or not err.context:
        return list(err.context)

    branches: dict[object, list[ValidationError]] = {}
    for child in err.context:
        branch_key = child.schema_path[0] if child.schema_path else None
        branches.setdefault(branch_key, []).append(child)

    relevant: list[ValidationError] = []
    for children in branches.values():
        if any(_is_type_const_mismatch(child) for child in children):
            continue
        relevant.extend(children)
    return relevant or list(err.context)


def _is_type_const_mismatch(err: ValidationError) -> bool:
    return err.validator == "const" and list(err.absolute_path)[-1:] == ["type"]


def _error(path: str, message: str, code: str) -> dict:
    return {"path": path, "message": message, "code": code}


def _format_path(path_parts) -> str:
    path = ""
    for part in path_parts:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path = f"{path}.{part}" if path else str(part)
    return path


def _semantic_errors(doc: dict[str, Any]) -> list[dict]:
    page = doc.get("page", {})
    widgets = page.get("widgets", [])
    errors: list[dict] = []
    seen_ids: dict[str, str] = {}
    actions_ids: set[str] = set()
    widget_types_by_id: dict[str, str] = {}
    refs: list[tuple[str, str]] = []
    top_widget_ids: set[str] = set()
    nested_widget_ids: set[str] = set()

    for widget, path, layout_depth in _iter_widgets(widgets, "page.widgets", 0):
        widget_id = widget.get("id")
        widget_type = widget.get("type")

        _check_unique_id(widget_id, path, seen_ids, errors)
        if widget_type == "actions":
            actions_ids.add(widget_id)
        widget_types_by_id[widget_id] = widget_type
        if ".children" not in path:
            top_widget_ids.add(widget_id)
        else:
            nested_widget_ids.add(widget_id)

        if widget_type == "layout" and layout_depth > 4:
            errors.append(
                _error(
                    path,
                    "Layout nesting depth exceeds the maximum of 4",
                    "nesting_depth",
                )
            )

        if widget_type == "actions":
            for index, button in enumerate(widget.get("buttons", [])):
                _check_unique_id(
                    button.get("id"),
                    f"{path}.buttons[{index}]",
                    seen_ids,
                    errors,
                )

        if widget_type == "table":
            _check_table_fields(widget, path, errors)
            if "row_actions_ref" in widget:
                refs.append((f"{path}.row_actions_ref", widget["row_actions_ref"]))

        if widget_type == "detail":
            _check_detail_fields(widget, path, errors)

        if widget_type == "menu":
            _check_menu(widget, path, errors)

        # form.submit_action_ref 是 L2 action registry 參照（渲染期 fail-closed 解析），
        # 不是頁內 actions widget 參照，故不列入 dangling_ref 檢查。

    _check_canvas(page, seen_ids, top_widget_ids, nested_widget_ids, errors)

    for path, ref_id in refs:
        if ref_id not in actions_ids:
            ref_type = widget_types_by_id.get(ref_id)
            if ref_type is None:
                message = f"Reference '{ref_id}' does not point to an actions widget"
            else:
                message = (
                    f"Reference '{ref_id}' points to widget type '{ref_type}', "
                    "not an actions widget"
                )
            errors.append(_error(path, message, "dangling_ref"))

    return errors


def _check_canvas(
    page: dict[str, Any],
    seen_ids: dict[str, str],
    top_widget_ids: set[str],
    nested_widget_ids: set[str],
    errors: list[dict],
) -> None:
    engine = page.get("engine", "flow")
    if engine == "flow":
        return

    canvas = page.get("canvas") or {}
    used_widget_ids: dict[str, str] = {}
    if engine == "grid":
        col_count = len(canvas.get("col_widths", []))
        row_count = len(canvas.get("row_heights", []))
        occupied: dict[tuple[int, int], str] = {}
        for index, zone in enumerate(canvas.get("zones", [])):
            path = f"page.canvas.zones[{index}]"
            _check_unique_id(zone.get("id"), path, seen_ids, errors)
            row = zone.get("row", 0)
            col = zone.get("col", 0)
            row_span = zone.get("row_span", 0)
            col_span = zone.get("col_span", 0)
            if row < 1 or col < 1 or row + row_span - 1 > row_count or col + col_span - 1 > col_count:
                errors.append(_error(path, "Grid zone exceeds canvas bounds", "zone_out_of_range"))
                continue
            for r in range(row, row + row_span):
                for c in range(col, col + col_span):
                    key = (r, c)
                    if key in occupied:
                        errors.append(_error(path, f"Grid zone overlaps {occupied[key]}", "zone_overlap"))
                    else:
                        occupied[key] = zone.get("id")
            _check_canvas_widget_refs(zone.get("widget_ids", []), path, top_widget_ids, nested_widget_ids, used_widget_ids, errors)
    elif engine == "free":
        occupied: dict[tuple[int, int], str] = {}
        for index, frame in enumerate(canvas.get("frames", [])):
            path = f"page.canvas.frames[{index}]"
            _check_unique_id(frame.get("id"), path, seen_ids, errors)
            x = frame.get("x", 0)
            y = frame.get("y", 0)
            w = frame.get("w", 0)
            h = frame.get("h", 0)
            if x < 0 or y < 0 or w < 1 or h < 1 or x + w > 12:
                errors.append(_error(path, "Free frame exceeds canvas bounds", "frame_out_of_range"))
                continue
            for row in range(y, y + h):
                for col in range(x, x + w):
                    key = (row, col)
                    if key in occupied:
                        errors.append(_error(path, f"Free frame overlaps {occupied[key]}", "frame_overlap"))
                    else:
                        occupied[key] = frame.get("id")
            _check_canvas_widget_refs(frame.get("widget_ids", []), path, top_widget_ids, nested_widget_ids, used_widget_ids, errors)

def _check_canvas_widget_refs(
    widget_ids: list[str],
    path: str,
    top_widget_ids: set[str],
    nested_widget_ids: set[str],
    used_widget_ids: dict[str, str],
    errors: list[dict],
) -> None:
    for index, widget_id in enumerate(widget_ids):
        ref_path = f"{path}.widget_ids[{index}]"
        if widget_id in nested_widget_ids:
            errors.append(_error(ref_path, f"Widget ref {widget_id} points to a nested widget", "nested_widget_ref"))
            continue
        if widget_id not in top_widget_ids:
            errors.append(_error(ref_path, f"Widget ref {widget_id} does not exist", "dangling_widget_ref"))
            continue
        if widget_id in used_widget_ids:
            errors.append(_error(ref_path, f"Widget ref {widget_id} duplicates ref at {used_widget_ids[widget_id]}", "duplicate_widget_ref"))
        else:
            used_widget_ids[widget_id] = ref_path

# canvas semantic validation helpers
def _iter_widgets(widgets: list[dict], path: str, layout_depth: int):
    for index, widget in enumerate(widgets):
        widget_path = f"{path}[{index}]"
        current_depth = layout_depth + 1 if widget.get("type") == "layout" else layout_depth
        yield widget, widget_path, current_depth
        if widget.get("type") == "layout":
            yield from _iter_widgets(widget.get("children", []), f"{widget_path}.children", current_depth)


def _check_unique_id(
    item_id: str | None,
    path: str,
    seen_ids: dict[str, str],
    errors: list[dict],
) -> None:
    if not item_id:
        return
    id_path = f"{path}.id"
    if item_id in seen_ids:
        errors.append(
            _error(
                id_path,
                f"ID '{item_id}' duplicates ID at {seen_ids[item_id]}",
                "unique_id",
            )
        )
    else:
        seen_ids[item_id] = id_path


def _check_table_fields(widget: dict[str, Any], path: str, errors: list[dict]) -> None:
    binding_fields = set(widget.get("binding", {}).get("fields", []))
    for index, column in enumerate(widget.get("columns", [])):
        field = column.get("field")
        if field not in binding_fields:
            errors.append(
                _error(
                    f"{path}.columns[{index}].field",
                    f"Field '{field}' is not declared in binding.fields",
                    "field_not_in_binding",
                )
            )

    default_sort = widget.get("default_sort")
    if default_sort and default_sort.get("field") not in binding_fields:
        errors.append(
            _error(
                f"{path}.default_sort.field",
                f"Field '{default_sort.get('field')}' is not declared in binding.fields",
                "field_not_in_binding",
            )
        )


def _check_detail_fields(widget: dict[str, Any], path: str, errors: list[dict]) -> None:
    binding_fields = set(widget.get("binding", {}).get("fields", []))
    for index, field_def in enumerate(widget.get("fields", [])):
        field = field_def.get("field")
        if field not in binding_fields:
            errors.append(
                _error(
                    f"{path}.fields[{index}].field",
                    f"Field '{field}' is not declared in binding.fields",
                    "field_not_in_binding",
                )
            )


def _check_menu(widget: dict[str, Any], path: str, errors: list[dict]) -> None:
    if widget.get("shared_ref"):
        return

    seen_nodes: dict[str, str] = {}
    has_node_with_children = False

    def walk(items: list[dict], item_path: str, depth: int) -> None:
        nonlocal has_node_with_children
        if depth > 5:
            errors.append(
                _error(
                    item_path,
                    "Menu nesting depth exceeds the maximum of 5",
                    "menu_depth",
                )
            )
            return
        for index, item in enumerate(items or []):
            current_path = f"{item_path}[{index}]"
            if item.get("kind") != "node":
                continue
            node_sc = item.get("node")
            if node_sc:
                node_path = f"{current_path}.node"
                if node_sc in seen_nodes:
                    errors.append(
                        _error(
                            node_path,
                            f"Menu node '{node_sc}' duplicates node at {seen_nodes[node_sc]}",
                            "menu_duplicate_node",
                        )
                    )
                else:
                    seen_nodes[node_sc] = node_path
            children = item.get("children") or []
            if children:
                has_node_with_children = True
                walk(children, f"{current_path}.children", depth + 1)

    walk(widget.get("items", []), f"{path}.items", 1)

    if widget.get("nav_source") == "parent_selection" and not has_node_with_children:
        errors.append(
            _error(
                f"{path}.nav_source",
                "Menu parent_selection requires at least one node with children",
                "menu_nav_no_children",
            )
        )
