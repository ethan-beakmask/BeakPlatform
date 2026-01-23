"""
Sample Module - API Routes
"""
from flask import Blueprint, jsonify
from app.security.decorators import public_route

# 建立 API Blueprint
api_bp = Blueprint(
    'sample_module_api',
    __name__,
    url_prefix='/api/sample-module'
)


@api_bp.route('/info')
@public_route
def module_info():
    """取得模組資訊（公開）"""
    from .. import MODULE_INFO
    return jsonify({
        'success': True,
        'data': {
            'name': MODULE_INFO['name'],
            'display_name': MODULE_INFO['display_name'],
            'version': MODULE_INFO['version'],
            'description': MODULE_INFO['description'],
        }
    })


@api_bp.route('/demo')
def demo():
    """展示模組可以存取平台 API"""
    from app.platform.auth import current_user, has_permission
    from app.platform.data import get_current_org

    org = get_current_org()

    return jsonify({
        'success': True,
        'data': {
            'message': '模組 API 運作正常',
            'user': current_user.display_name if current_user.is_authenticated else None,
            'org': org.name if org else None,
            'has_view_permission': has_permission('sample_module.view'),
        }
    })
