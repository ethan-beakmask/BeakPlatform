"""Page IR NoCode portal SQLite resource resolver."""
from __future__ import annotations

import logging

from app.pageir import PageIrRenderError
from app.pageir.registry import register_resource_lister, register_resource_provider

from ..models.crud_view import DcCrudView
from ..models.sub_system import DcSubSystem
from .data_source_manager import DataSourceManager
from .db_connector import is_sqlite_source
from .sqlite_crud_service import (
    PortalFilterNotSupported,
    SqliteCrudService,
    _find_row_id_column,
    _get_visible_columns,
    _get_writable_columns,
)

logger = logging.getLogger(__name__)


# 敏感欄位硬排除：不信任 columns_config 對這類欄位的 visible 設定（2026-07-28 用戶裁決）
_SENSITIVE_COLUMN_TOKENS = (
    'password', 'passwd', 'pw_hash', 'secret', 'token', 'salt',
    'api_key', 'apikey', 'credential', 'private_key',
)


def _strip_sensitive_columns(columns: list[str]) -> list[str]:
    return [
        col for col in columns
        if not any(tok in (col or '').lower() for tok in _SENSITIVE_COLUMN_TOKENS)
    ]


def init_portal_pageir_resources() -> None:
    """Register portal-prefixed Page IR resources."""
    register_resource_provider("portal", _resolve_portal_resource)
    register_resource_lister(_list_portal_resources)


def _resolve_portal_resource(code: str, ctx: dict) -> dict | None:
    parts = code.split(":", 1)
    if len(parts) != 2 or not parts[1]:
        return None

    view_sc = parts[1]
    sub_sc = ctx.get("sub_system_sc")
    if not sub_sc:
        return None

    view = DcCrudView.query.filter_by(
        secure_code=view_sc,
        is_deleted=False,
        is_active=True,
    ).first()
    if not view or not is_sqlite_source(view.data_source):
        return None

    sub_system = DcSubSystem.query.filter_by(
        secure_code=sub_sc,
        is_deleted=False,
    ).first()
    if not sub_system or view.org_secure_code != sub_system.org_secure_code:
        return None

    fields = _strip_sensitive_columns(_get_visible_columns(view))
    writable_fields = _strip_sensitive_columns(_get_writable_columns(view))

    def fetch_list(fields_arg, page, page_size, sort_field, sort_dir):
        return _fetch_list(view, sub_sc, fields, fields_arg, page, page_size, sort_field, sort_dir)

    def fetch_detail(record_sc, fields_arg):
        return _fetch_detail(view, sub_sc, fields, record_sc, fields_arg)

    def create_row(payload):
        return _create_row(view, sub_sc, payload)

    def update_row(record_sc, payload):
        return _update_row(view, sub_sc, record_sc, payload)

    def delete_row(record_sc):
        return _delete_row(view, sub_sc, record_sc)

    return {
        "fields": fields,
        "writable_fields": writable_fields,
        "crud": {
            "create": bool(getattr(view, "allow_create", False)),
            "update": bool(getattr(view, "allow_edit", False)),
            "delete": bool(getattr(view, "allow_delete", False)),
        },
        "egress_resource": None,
        "views": ["list", "detail"],
        "fetch_list": fetch_list,
        "fetch_detail": fetch_detail,
        "create_row": create_row,
        "update_row": update_row,
        "delete_row": delete_row,
    }


def _fetch_list(view, sub_sc, whitelist, fields, page, page_size, sort_field, sort_dir):
    sort_column = sort_field if sort_field in whitelist else view.default_sort_column
    try:
        with DataSourceManager().get_session(sub_sc, view.data_source) as session:
            result = SqliteCrudService.query_rows(
                session=session,
                view=view,
                page=page,
                per_page=page_size,
                search="",
                sort_column=sort_column,
                sort_dir=sort_dir or view.default_sort_dir,
            )
    except FileNotFoundError:
        return [], 0
    except PortalFilterNotSupported:
        logger.warning(
            "Portal list query rejected because fixed_filters contains unsupported variables: view=%s sub_system=%s",
            getattr(view, "secure_code", None),
            sub_sc,
        )
        raise PageIrRenderError("portal_fixed_filter_variable_not_supported")

    requested = [field for field in fields if field in whitelist]
    rows = [
        _portal_row(view, row, requested)
        for row in result.get("rows", [])
    ]
    return rows, result.get("total", 0)


def _fetch_detail(view, sub_sc, whitelist, record_sc, fields):
    try:
        with DataSourceManager().get_session(sub_sc, view.data_source) as session:
            result = SqliteCrudService.get_row(session=session, view=view, row_id=record_sc)
    except FileNotFoundError:
        return None
    except PortalFilterNotSupported:
        logger.warning(
            "Portal detail query rejected because fixed_filters contains unsupported variables: view=%s sub_system=%s record=%s",
            getattr(view, "secure_code", None),
            sub_sc,
            record_sc,
        )
        raise PageIrRenderError("portal_fixed_filter_variable_not_supported")

    if not result.get("success"):
        return None
    requested = [field for field in fields if field in whitelist]
    return _portal_row(view, result.get("data") or {}, requested)


def _create_row(view, sub_sc, payload):
    try:
        with DataSourceManager().get_session(sub_sc, view.data_source) as session:
            result = SqliteCrudService.create_row(
                session=session,
                view=view,
                row_data=payload,
            )
    except FileNotFoundError:
        return False, "portal_db_missing"

    return bool(result.get("success")), result.get("error") or ""


def _update_row(view, sub_sc, record_sc, payload):
    try:
        with DataSourceManager().get_session(sub_sc, view.data_source) as session:
            result = SqliteCrudService.update_row(
                session=session,
                view=view,
                row_id=record_sc,
                row_data=payload,
            )
    except FileNotFoundError:
        return False, "portal_db_missing"

    return bool(result.get("success")), result.get("error") or ""


def _delete_row(view, sub_sc, record_sc):
    try:
        with DataSourceManager().get_session(sub_sc, view.data_source) as session:
            result = SqliteCrudService.delete_row(
                session=session,
                view=view,
                row_id=record_sc,
            )
    except FileNotFoundError:
        return False, "portal_db_missing"

    return bool(result.get("success")), result.get("error") or ""


def _portal_row(view, source_row: dict, fields: list[str]) -> dict:
    row = {field: source_row.get(field) for field in fields if field in source_row}
    row_id_col = _find_row_id_column(view)
    row_id = source_row.get("_row_id")
    if row_id is None and row_id_col:
        row_id = source_row.get(row_id_col)
    if row_id is not None:
        row["_sc"] = str(row_id)
    return row


def _list_portal_resources(sub_system_sc: str) -> list[dict]:
    sub_system = DcSubSystem.query.filter_by(
        secure_code=sub_system_sc,
        is_deleted=False,
    ).first()
    if not sub_system:
        return []

    views = DcCrudView.query.filter_by(
        org_secure_code=sub_system.org_secure_code,
        is_deleted=False,
        is_active=True,
    ).all()

    resources = []
    for view in views:
        if not is_sqlite_source(view.data_source):
            continue
        resources.append({
            "code": f"portal:{view.secure_code}",
            "name": view.name,
            "views": ["list", "detail"],
            "fields": _strip_sensitive_columns(_get_visible_columns(view)),
            "writable_fields": _strip_sensitive_columns(_get_writable_columns(view)),
            "crud": {
                "create": bool(getattr(view, "allow_create", False)),
                "update": bool(getattr(view, "allow_edit", False)),
                "delete": bool(getattr(view, "allow_delete", False)),
            },
            "egress_resource": None,
        })
    return resources
