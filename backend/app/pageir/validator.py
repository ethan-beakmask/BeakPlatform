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
    errors = [err]
    for child in err.context:
        errors.extend(_flatten_schema_errors(child))
    return errors


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
    widgets = doc.get("page", {}).get("widgets", [])
    errors: list[dict] = []
    seen_ids: dict[str, str] = {}
    actions_ids: set[str] = set()
    widget_types_by_id: dict[str, str] = {}
    refs: list[tuple[str, str]] = []

    for widget, path, layout_depth in _iter_widgets(widgets, "page.widgets", 0):
        widget_id = widget.get("id")
        widget_type = widget.get("type")

        _check_unique_id(widget_id, path, seen_ids, errors)
        if widget_type == "actions":
            actions_ids.add(widget_id)
        widget_types_by_id[widget_id] = widget_type

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

        # form.submit_action_ref 是 L2 action registry 參照（渲染期 fail-closed 解析），
        # 不是頁內 actions widget 參照，故不列入 dangling_ref 檢查。

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
