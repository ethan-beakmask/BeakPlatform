"""
NoCode Builder - Shared Component API
子系統層級共用元件 CRUD
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from flask import jsonify, request
from flask_babel import gettext as _

from app import csrf, db
from app.pageir import validate_page_ir
from app.security.decorators import admin_required
from app.security.resource_gateway import ResourceGateway
from app.security.tenant_isolation import get_current_tenant
from app.services.capability_service import permission_required

from . import api_bp
from ..services.page_ownership_service import get_owner_sub_system_codes

logger = logging.getLogger(__name__)

_WIDGET_TYPES = {"menu", "table", "detail", "form", "actions", "text", "layout", "master_detail"}


def _sub_system_or_404(sub_system_sc: str):
    from ..models import DcSubSystem

    sub_system = ResourceGateway.get(
        DcSubSystem,
        sub_system_sc,
        raise_on_not_found=False,
        check_permission=False,
    )
    if not sub_system or sub_system.is_deleted:
        return None
    return sub_system


def _find_shared_component(sub_system_sc: str, shared_component_sc: str):
    from ..models import DcSharedComponent

    rows = ResourceGateway.filter(
        DcSharedComponent,
        check_permission=False,
        sub_system_secure_code=sub_system_sc,
        secure_code=(shared_component_sc or "").strip(),
        is_deleted=False,
    )
    return rows[0] if rows else None


def _name_exists(sub_system_sc: str, name: str, exclude_sc: str = "") -> bool:
    from ..models import DcSharedComponent

    rows = ResourceGateway.filter(
        DcSharedComponent,
        check_permission=False,
        sub_system_secure_code=sub_system_sc,
        name=name,
        is_deleted=False,
    )
    return any(row.secure_code != exclude_sc for row in rows)


def _normalize_widget_json(widget_json: Any) -> Any:
    """「不使用底圖」在 UI 上是空字串，但 schema 的 background_file 有 pattern，
    空字串會被擋成 400。與前端 normalizeMenuOnSave 同語意：沒選底圖就不留這個 key。"""
    if not isinstance(widget_json, dict):
        return widget_json
    if widget_json.get("type") == "menu":
        style = widget_json.get("style")
        if isinstance(style, dict) and not style.get("background_file"):
            style.pop("background_file", None)
    for child in widget_json.get("children") or []:
        _normalize_widget_json(child)
    return widget_json


def _validate_widget_json(widget_json: Any) -> tuple[bool, str, list[dict]]:
    if not isinstance(widget_json, dict):
        return False, "", [{"path": "widget_json", "message": _("widget_json 必須是物件"), "code": "type"}]
    _normalize_widget_json(widget_json)
    if "id" in widget_json:
        return False, "", [{"path": "widget_json.id", "message": _("共用元件組態不可包含 id"), "code": "additional_property"}]
    widget_type = widget_json.get("type")
    if widget_type not in _WIDGET_TYPES:
        return False, "", [{"path": "widget_json.type", "message": _("元件型別不支援"), "code": "enum"}]

    widget = dict(widget_json)
    widget["id"] = "shared-check"
    doc = {
        "ir_version": 3,
        "page": {
            "id": "shared-component-check",
            "title_i18n": {"zh-TW": "Shared Component Check"},
            "widgets": [widget],
        },
    }
    ok, errors = validate_page_ir(doc)
    return ok, widget_type, errors


def _iter_widgets(widgets):
    for widget in widgets or []:
        if not isinstance(widget, dict):
            continue
        yield widget
        if widget.get("type") == "layout":
            yield from _iter_widgets(widget.get("children") or [])


def _shared_component_usages(sub_system_sc: str, shared_component_sc: str) -> list[dict]:
    from ..models import DcPageLayout

    pages = ResourceGateway.filter(
        DcPageLayout,
        check_permission=False,
        is_deleted=False,
        order_by="name",
    )
    usages = []
    seen = set()
    for page in pages:
        if sub_system_sc not in get_owner_sub_system_codes(page.secure_code):
            continue
        layout_json = page.layout_json if isinstance(page.layout_json, dict) else {}
        widgets = ((layout_json.get("page") or {}).get("widgets") or [])
        if any(widget.get("shared_ref") == shared_component_sc for widget in _iter_widgets(widgets)):
            if page.secure_code in seen:
                continue
            seen.add(page.secure_code)
            usages.append({
                "page_secure_code": page.secure_code,
                "page_name": page.name or "",
            })
    return usages


@api_bp.route("/sub-systems/<sub_system_sc>/shared-components", methods=["GET"])
@csrf.exempt
@admin_required
@permission_required("nocode_builder.manage")
def list_shared_components(sub_system_sc):
    """列出子系統共用元件。"""
    try:
        from ..models import DcSharedComponent

        sub_system = _sub_system_or_404(sub_system_sc)
        if not sub_system:
            return jsonify({"success": False, "error": _("子系統不存在")}), 404

        widget_type = (request.args.get("widget_type") or "").strip()
        if widget_type and widget_type not in _WIDGET_TYPES:
            return jsonify({"success": False, "error": _("元件型別不支援")}), 400

        filters = {
            "sub_system_secure_code": sub_system.secure_code,
            "is_deleted": False,
        }
        if widget_type:
            filters["widget_type"] = widget_type
        rows = ResourceGateway.filter(
            DcSharedComponent,
            check_permission=False,
            order_by="name",
            **filters,
        )
        return jsonify({"success": True, "data": [row.to_dict() for row in rows]})
    except Exception as e:
        db.session.rollback()
        logger.exception("[SharedComponent] list error")
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/sub-systems/<sub_system_sc>/shared-components", methods=["POST"])
@csrf.exempt
@admin_required
@permission_required("nocode_builder.manage")
def create_shared_component(sub_system_sc):
    """建立子系統共用元件。"""
    try:
        from ..models import DcSharedComponent

        sub_system = _sub_system_or_404(sub_system_sc)
        if not sub_system:
            return jsonify({"success": False, "error": _("子系統不存在")}), 404

        data = request.get_json() or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"success": False, "error": _("共用元件名稱為必填")}), 400
        if _name_exists(sub_system.secure_code, name):
            return jsonify({"success": False, "error": _("同一子系統已有相同名稱的共用元件")}), 409

        widget_json = data.get("widget_json")
        ok, widget_type, errors = _validate_widget_json(widget_json)
        if not ok:
            return jsonify({"success": False, "error": _("共用元件組態格式不正確"), "errors": errors}), 400

        row = ResourceGateway.create(
            DcSharedComponent,
            check_permission=False,
            org_secure_code=get_current_tenant(),
            sub_system_secure_code=sub_system.secure_code,
            name=name,
            widget_type=widget_type,
            widget_json=widget_json,
            is_active=True,
        )
        ResourceGateway.commit()
        return jsonify({"success": True, "data": row.to_dict()})
    except Exception as e:
        db.session.rollback()
        logger.exception("[SharedComponent] create error")
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/sub-systems/<sub_system_sc>/shared-components/<shared_component_sc>", methods=["PUT"])
@csrf.exempt
@admin_required
@permission_required("nocode_builder.manage")
def update_shared_component(sub_system_sc, shared_component_sc):
    """更新子系統共用元件。"""
    try:
        sub_system = _sub_system_or_404(sub_system_sc)
        if not sub_system:
            return jsonify({"success": False, "error": _("子系統不存在")}), 404

        row = _find_shared_component(sub_system.secure_code, shared_component_sc)
        if not row:
            return jsonify({"success": False, "error": _("共用元件不存在")}), 404

        data = request.get_json() or {}
        update_fields = {}
        if "name" in data:
            name = (data.get("name") or "").strip()
            if not name:
                return jsonify({"success": False, "error": _("共用元件名稱為必填")}), 400
            if _name_exists(sub_system.secure_code, name, exclude_sc=row.secure_code):
                return jsonify({"success": False, "error": _("同一子系統已有相同名稱的共用元件")}), 409
            update_fields["name"] = name
        if "widget_json" in data:
            ok, widget_type, errors = _validate_widget_json(data.get("widget_json"))
            if not ok:
                return jsonify({"success": False, "error": _("共用元件組態格式不正確"), "errors": errors}), 400
            update_fields["widget_json"] = data.get("widget_json")
            update_fields["widget_type"] = widget_type
        if "is_active" in data:
            update_fields["is_active"] = bool(data.get("is_active"))

        if update_fields:
            ResourceGateway.update(row, check_permission=False, **update_fields)
            ResourceGateway.commit()
        return jsonify({"success": True, "data": row.to_dict()})
    except Exception as e:
        db.session.rollback()
        logger.exception("[SharedComponent] update error")
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/sub-systems/<sub_system_sc>/shared-components/<shared_component_sc>", methods=["DELETE"])
@csrf.exempt
@admin_required
@permission_required("nocode_builder.manage")
def delete_shared_component(sub_system_sc, shared_component_sc):
    """刪除子系統共用元件；被頁面引用時拒絕。"""
    try:
        sub_system = _sub_system_or_404(sub_system_sc)
        if not sub_system:
            return jsonify({"success": False, "error": _("子系統不存在")}), 404

        row = _find_shared_component(sub_system.secure_code, shared_component_sc)
        if not row:
            return jsonify({"success": False, "error": _("共用元件不存在")}), 404

        usages = _shared_component_usages(sub_system.secure_code, row.secure_code)
        if usages:
            return jsonify({
                "success": False,
                "error": _("共用元件仍被頁面引用，請先解除引用"),
                "data": {"usages": usages},
            }), 409

        ResourceGateway.update(
            row,
            check_permission=False,
            is_deleted=True,
            deleted_at=datetime.utcnow(),
        )
        ResourceGateway.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        logger.exception("[SharedComponent] delete error")
        return jsonify({"success": False, "error": str(e)}), 500
