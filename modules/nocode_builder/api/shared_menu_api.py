"""
NoCode Builder - Shared Menu API
子系統層級共用選單 CRUD
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

_CONFIG_KEYS = {"orientation", "item_gap", "hover_expand", "nav_source", "nav_key", "style"}


def _shared_menu_config(value: Any) -> dict:
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in _CONFIG_KEYS if key in value}


def _validate_items(items: Any) -> tuple[bool, list[dict]]:
    if not isinstance(items, list):
        return False, [{"path": "items", "message": _("items 必須是陣列"), "code": "type"}]
    doc = {
        "ir_version": 3,
        "page": {
            "id": "shared-menu-check",
            "title_i18n": {"zh-TW": "Shared Menu Check"},
            "widgets": [
                {
                    "id": "shared-check",
                    "type": "menu",
                    "items": items,
                }
            ],
        },
    }
    return validate_page_ir(doc)


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


def _find_shared_menu(sub_system_sc: str, shared_menu_sc: str):
    from ..models import DcSharedMenu

    rows = ResourceGateway.filter(
        DcSharedMenu,
        check_permission=False,
        sub_system_secure_code=sub_system_sc,
        secure_code=(shared_menu_sc or "").strip(),
        is_deleted=False,
    )
    return rows[0] if rows else None


def _name_exists(sub_system_sc: str, name: str, exclude_sc: str = "") -> bool:
    from ..models import DcSharedMenu

    rows = ResourceGateway.filter(
        DcSharedMenu,
        check_permission=False,
        sub_system_secure_code=sub_system_sc,
        name=name,
        is_deleted=False,
    )
    return any(row.secure_code != exclude_sc for row in rows)


def _iter_widgets(widgets):
    for widget in widgets or []:
        if not isinstance(widget, dict):
            continue
        yield widget
        if widget.get("type") == "layout":
            yield from _iter_widgets(widget.get("children") or [])


def _shared_menu_usages(sub_system_sc: str, shared_menu_sc: str) -> list[dict]:
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
        if any(widget.get("shared_ref") == shared_menu_sc for widget in _iter_widgets(widgets)):
            if page.secure_code in seen:
                continue
            seen.add(page.secure_code)
            usages.append({
                "page_secure_code": page.secure_code,
                "page_name": page.name or "",
            })
    return usages


@api_bp.route("/sub-systems/<sub_system_sc>/shared-menus", methods=["GET"])
@csrf.exempt
@admin_required
@permission_required("nocode_builder.manage")
def list_shared_menus(sub_system_sc):
    """列出子系統共用選單。"""
    try:
        from ..models import DcSharedMenu

        sub_system = _sub_system_or_404(sub_system_sc)
        if not sub_system:
            return jsonify({"success": False, "error": _("子系統不存在")}), 404

        rows = ResourceGateway.filter(
            DcSharedMenu,
            check_permission=False,
            sub_system_secure_code=sub_system.secure_code,
            is_deleted=False,
            order_by="name",
        )
        return jsonify({"success": True, "data": [row.to_dict() for row in rows]})
    except Exception as e:
        db.session.rollback()
        logger.exception("[SharedMenu] list error")
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/sub-systems/<sub_system_sc>/shared-menus", methods=["POST"])
@csrf.exempt
@admin_required
@permission_required("nocode_builder.manage")
def create_shared_menu(sub_system_sc):
    """建立子系統共用選單。"""
    try:
        from ..models import DcSharedMenu

        sub_system = _sub_system_or_404(sub_system_sc)
        if not sub_system:
            return jsonify({"success": False, "error": _("子系統不存在")}), 404

        data = request.get_json() or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"success": False, "error": _("共用選單名稱為必填")}), 400
        if _name_exists(sub_system.secure_code, name):
            return jsonify({"success": False, "error": _("同一子系統已有相同名稱的共用選單")}), 400

        items = data.get("items")
        ok, errors = _validate_items(items)
        if not ok:
            return jsonify({"success": False, "error": _("選單項目格式不正確"), "errors": errors}), 400

        row = ResourceGateway.create(
            DcSharedMenu,
            check_permission=False,
            org_secure_code=get_current_tenant(),
            sub_system_secure_code=sub_system.secure_code,
            name=name,
            items=items,
            config=_shared_menu_config(data.get("config")),
            is_active=True,
        )
        ResourceGateway.commit()
        return jsonify({"success": True, "data": row.to_dict()})
    except Exception as e:
        db.session.rollback()
        logger.exception("[SharedMenu] create error")
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/sub-systems/<sub_system_sc>/shared-menus/<shared_menu_sc>", methods=["PUT"])
@csrf.exempt
@admin_required
@permission_required("nocode_builder.manage")
def update_shared_menu(sub_system_sc, shared_menu_sc):
    """更新子系統共用選單。"""
    try:
        sub_system = _sub_system_or_404(sub_system_sc)
        if not sub_system:
            return jsonify({"success": False, "error": _("子系統不存在")}), 404

        row = _find_shared_menu(sub_system.secure_code, shared_menu_sc)
        if not row:
            return jsonify({"success": False, "error": _("共用選單不存在")}), 404

        data = request.get_json() or {}
        update_fields = {}
        if "name" in data:
            name = (data.get("name") or "").strip()
            if not name:
                return jsonify({"success": False, "error": _("共用選單名稱為必填")}), 400
            if _name_exists(sub_system.secure_code, name, exclude_sc=row.secure_code):
                return jsonify({"success": False, "error": _("同一子系統已有相同名稱的共用選單")}), 400
            update_fields["name"] = name
        if "items" in data:
            ok, errors = _validate_items(data.get("items"))
            if not ok:
                return jsonify({"success": False, "error": _("選單項目格式不正確"), "errors": errors}), 400
            update_fields["items"] = data.get("items")
        if "config" in data:
            update_fields["config"] = _shared_menu_config(data.get("config"))

        if update_fields:
            ResourceGateway.update(row, check_permission=False, **update_fields)
            ResourceGateway.commit()
        return jsonify({"success": True, "data": row.to_dict()})
    except Exception as e:
        db.session.rollback()
        logger.exception("[SharedMenu] update error")
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/sub-systems/<sub_system_sc>/shared-menus/<shared_menu_sc>", methods=["DELETE"])
@csrf.exempt
@admin_required
@permission_required("nocode_builder.manage")
def delete_shared_menu(sub_system_sc, shared_menu_sc):
    """刪除子系統共用選單；被頁面引用時拒絕。"""
    try:
        sub_system = _sub_system_or_404(sub_system_sc)
        if not sub_system:
            return jsonify({"success": False, "error": _("子系統不存在")}), 404

        row = _find_shared_menu(sub_system.secure_code, shared_menu_sc)
        if not row:
            return jsonify({"success": False, "error": _("共用選單不存在")}), 404

        usages = _shared_menu_usages(sub_system.secure_code, row.secure_code)
        if usages:
            return jsonify({
                "success": False,
                "error": _("共用選單仍被頁面引用，請先解除引用"),
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
        logger.exception("[SharedMenu] delete error")
        return jsonify({"success": False, "error": str(e)}), 500
