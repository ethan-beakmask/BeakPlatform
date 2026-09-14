"""Page IR NoCode portal shared component resolver."""
from __future__ import annotations

from app.pageir.registry import register_shared_component_resolver

from ..models.shared_component import DcSharedComponent


def init_portal_shared_components() -> None:
    register_shared_component_resolver("portal", _resolve_shared_component)


def _resolve_shared_component(shared_ref, ctx):
    sub_system_sc = (ctx.get("sub_system_sc") or "").strip()
    org_sc = (ctx.get("org_secure_code") or "").strip()
    if not sub_system_sc or not org_sc:
        return None
    row = DcSharedComponent.query.filter_by(
        secure_code=shared_ref,
        org_secure_code=org_sc,
        sub_system_secure_code=sub_system_sc,
        is_deleted=False,
        is_active=True,
    ).first()
    if not row or not isinstance(row.widget_json, dict):
        return None
    return dict(row.widget_json)
