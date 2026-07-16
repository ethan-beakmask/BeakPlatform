"""
BeakPlatform Access Center API
權限管理中心 API
"""
from flask import Blueprint, jsonify

from ..security.decorators import admin_required


access_center_api_bp = Blueprint(
    'access_center_api',
    __name__,
    url_prefix='/api/access',
)


@access_center_api_bp.route('/ping', methods=['GET'])
@admin_required
def ping():
    """Access Center API smoke check."""
    return jsonify({'ok': True})
