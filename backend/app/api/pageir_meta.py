"""Page IR 設計器平台 meta API。"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.pageir.registry import (
    list_actions,
    list_portal_actions,
    list_prefixed_resources,
    list_resources,
)
from app.security.decorators import admin_required


pageir_meta_bp = Blueprint("pageir_meta", __name__, url_prefix="/api/pageir")


@pageir_meta_bp.route("/meta")
@admin_required
def meta():
    """回傳 Page IR 設計器可用資源與動作。"""
    sub_system_sc = request.args.get("sub_system", "").strip()
    return jsonify({
        "success": True,
        "resources": list_resources(),
        "portal_resources": list_prefixed_resources(sub_system_sc) if sub_system_sc else [],
        "actions": list_actions(),
        "portal_actions": list_portal_actions(),
    })
