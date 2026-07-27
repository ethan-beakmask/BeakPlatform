"""Page IR NoCode portal SQLite resource resolver."""
from __future__ import annotations

from app.pageir.registry import register_resource_lister, register_resource_provider

from ..models.crud_view import DcCrudView
from ..models.sub_system import DcSubSystem
from .data_source_manager import DataSourceManager
from .db_connector import is_sqlite_source
from .sqlite_crud_service import (
    SqliteCrudService,
    _find_row_id_column,
    _get_visible_columns,
)


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

    fields = _get_visible_columns(view)

    def fetch_list(fields_arg, page, page_size, sort_field, sort_dir):
        return _fetch_list(view, sub_sc, fields, fields_arg, page, page_size, sort_field, sort_dir)

    def fetch_detail(record_sc, fields_arg):
        return _fetch_detail(view, sub_sc, fields, record_sc, fields_arg)

    return {
        "fields": fields,
        "egress_resource": None,
        "views": ["list", "detail"],
        "fetch_list": fetch_list,
        "fetch_detail": fetch_detail,
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

    if not result.get("success"):
        return None
    requested = [field for field in fields if field in whitelist]
    return _portal_row(view, result.get("data") or {}, requested)


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
            "fields": _get_visible_columns(view),
            "egress_resource": None,
        })
    return resources
