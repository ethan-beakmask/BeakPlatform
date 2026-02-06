"""
Sample Module - API Routes

展示如何使用平台提供的權限接口。
"""
from flask import Blueprint, jsonify
from app.security.decorators import public_route
from app.platform.auth import (
    current_user,
    has_permission,
    require_permission,
    get_module_permissions,
    get_user_permissions,
)

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


@api_bp.route('/permissions')
@public_route
def module_permissions():
    """取得模組定義的權限列表（公開）"""
    perms = get_module_permissions('sample_module')
    return jsonify({
        'success': True,
        'data': {
            'permissions': perms
        }
    })


@api_bp.route('/demo')
@require_permission('sample_module.view')
def demo():
    """展示模組可以存取平台 API"""
    from app.platform.data import get_current_org

    org = get_current_org()

    return jsonify({
        'success': True,
        'data': {
            'message': '模組 API 運作正常',
            'user': current_user.display_name if current_user.is_authenticated else None,
            'org': org.name if org else None,
            'permissions': {
                'sample_module.view': has_permission('sample_module.view'),
                'sample_module.manage': has_permission('sample_module.manage'),
            }
        }
    })


@api_bp.route('/protected')
@require_permission('sample_module.view')
def protected_resource():
    """
    需要 sample_module.view 權限的 API

    使用 @require_permission 裝飾器，
    沒有權限的用戶會收到 403 錯誤。
    """
    return jsonify({
        'success': True,
        'data': {
            'message': '你有檢視權限，可以看到這個資源',
            'user': current_user.display_name,
        }
    })


@api_bp.route('/admin')
@require_permission('sample_module.manage')
def admin_resource():
    """
    需要 sample_module.manage 權限的 API

    只有管理者才能存取。
    """
    return jsonify({
        'success': True,
        'data': {
            'message': '你有管理權限，可以管理此模組',
            'user': current_user.display_name,
            'user_permissions': list(get_user_permissions()),
        }
    })
