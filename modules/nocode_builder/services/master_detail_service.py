"""Master-detail portal_data writes in one SQLite transaction."""
from __future__ import annotations

from typing import Any

from .data_source_manager import DataSourceManager
from .sqlite_crud_service import SqliteCrudService


class MasterDetailWriteError(Exception):
    """Raised when a master-detail transaction fails with a safe service error."""

    def __init__(self, error: str):
        super().__init__(error)
        self.error = error


def save_master_detail(
    *,
    sub_system_sc: str,
    master_view,
    detail_view,
    master_sc: str | None,
    master_payload: dict[str, Any],
    detail_payloads: list[dict[str, Any]],
    foreign_key: str,
    update_master: bool,
) -> dict[str, Any]:
    """Create/update a master row and create detail rows in one portal_data transaction."""
    with DataSourceManager().get_session(sub_system_sc, 'portal_data') as session:
        if master_sc is None:
            result = SqliteCrudService.create_row(session, master_view, master_payload)
            if not result.get('success'):
                raise MasterDetailWriteError(result.get('error') or 'write_failed')
            master_sc = result.get('row_id')
            if master_sc is None:
                raise MasterDetailWriteError('row_identifier_missing')
        elif update_master and master_payload:
            result = SqliteCrudService.update_row(session, master_view, master_sc, master_payload)
            if not result.get('success'):
                raise MasterDetailWriteError(result.get('error') or 'write_failed')

        for source_payload in detail_payloads:
            detail_payload = dict(source_payload)
            detail_payload.pop(foreign_key, None)
            detail_payload[foreign_key] = master_sc
            result = SqliteCrudService.create_row(session, detail_view, detail_payload)
            if not result.get('success'):
                raise MasterDetailWriteError(result.get('error') or 'write_failed')

    return {
        'master_sc': str(master_sc),
        'detail_count': len(detail_payloads),
    }
