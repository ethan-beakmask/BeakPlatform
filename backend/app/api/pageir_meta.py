"""Page IR 設計器平台 meta API。"""
from __future__ import annotations

from flask import Blueprint, jsonify

from app.pageir.registry import list_actions, list_resources
from app.security.decorators import admin_required


pageir_meta_bp = Blueprint("pageir_meta", __name__, url_prefix="/api/pageir")


@pageir_meta_bp.route("/meta")
@admin_required
def meta():
    """回傳 Page IR 設計器可用資源與動作。"""
    return jsonify({
        "success": True,
        "resources": list_resources(),
        "actions": list_actions(),
    })
