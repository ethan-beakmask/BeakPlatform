"""
Data CRUD Module - Project API
開發案管理 API
"""
import logging

from flask import jsonify, request
from flask_login import current_user

from app import csrf
from app.security.decorators import admin_required

from . import api_bp

logger = logging.getLogger(__name__)


# =============================================================================
# 開發案列表 / CRUD
# =============================================================================

@api_bp.route('/projects')
def list_projects():
    """我的開發案列表"""
    from ..services.project_service import ProjectService

    items = ProjectService.list_projects(current_user)
    return jsonify({'success': True, 'data': items})


@api_bp.route('/projects', methods=['POST'])
@csrf.exempt
def create_project():
    """建立開發案"""
    from ..services.project_service import ProjectService

    data = request.get_json() or {}
    result = ProjectService.create_project(current_user, data)

    if not result['success']:
        return jsonify(result), 400
    return jsonify(result)


@api_bp.route('/projects/<secure_code>', methods=['PUT'])
@csrf.exempt
def update_project(secure_code):
    """更新開發案"""
    from ..services.project_service import ProjectService

    if not _check_developer_access(secure_code):
        return jsonify({'success': False, 'error': '無權限'}), 403

    data = request.get_json() or {}
    result = ProjectService.update_project(secure_code, data)

    if not result['success']:
        return jsonify(result), 400
    return jsonify(result)


@api_bp.route('/projects/<secure_code>', methods=['DELETE'])
@csrf.exempt
def delete_project(secure_code):
    """刪除開發案"""
    from ..services.project_service import ProjectService

    if not _check_developer_access(secure_code):
        return jsonify({'success': False, 'error': '無權限'}), 403

    result = ProjectService.delete_project(secure_code)

    if not result['success']:
        return jsonify(result), 400
    return jsonify(result)


# =============================================================================
# 上線 / 下線
# =============================================================================

@api_bp.route('/projects/<secure_code>/publish', methods=['POST'])
@csrf.exempt
def publish_project(secure_code):
    """上線開發案"""
    from ..services.project_service import ProjectService

    if not _check_developer_access(secure_code):
        return jsonify({'success': False, 'error': '無權限'}), 403

    result = ProjectService.publish(secure_code)

    if not result['success']:
        return jsonify(result), 400
    return jsonify(result)


@api_bp.route('/projects/<secure_code>/unpublish', methods=['POST'])
@csrf.exempt
def unpublish_project(secure_code):
    """下線開發案"""
    from ..services.project_service import ProjectService

    if not _check_developer_access(secure_code):
        return jsonify({'success': False, 'error': '無權限'}), 403

    result = ProjectService.unpublish(secure_code)

    if not result['success']:
        return jsonify(result), 400
    return jsonify(result)


# =============================================================================
# 開發者管理
# =============================================================================

@api_bp.route('/projects/<secure_code>/developers')
def list_developers(secure_code):
    """開發者名單"""
    from ..services.project_service import ProjectService

    if not _check_developer_access(secure_code):
        return jsonify({'success': False, 'error': '無權限'}), 403

    result = ProjectService.get_developers(secure_code)

    if not result['success']:
        return jsonify(result), 400
    return jsonify(result)


@api_bp.route('/projects/<secure_code>/developers', methods=['POST'])
@csrf.exempt
def add_developer(secure_code):
    """新增開發者"""
    from ..services.project_service import ProjectService

    if not _check_developer_access(secure_code):
        return jsonify({'success': False, 'error': '無權限'}), 403

    data = request.get_json() or {}
    user_sc = data.get('user_secure_code', '').strip()
    if not user_sc:
        return jsonify({'success': False, 'error': 'user_secure_code is required'}), 400

    result = ProjectService.add_developer(secure_code, user_sc)

    if not result['success']:
        return jsonify(result), 400
    return jsonify(result)


@api_bp.route('/projects/<secure_code>/developers/<user_sc>', methods=['DELETE'])
@csrf.exempt
def remove_developer(secure_code, user_sc):
    """移除開發者"""
    from ..services.project_service import ProjectService

    if not _check_developer_access(secure_code):
        return jsonify({'success': False, 'error': '無權限'}), 403

    result = ProjectService.remove_developer(secure_code, user_sc)

    if not result['success']:
        return jsonify(result), 400
    return jsonify(result)


# =============================================================================
# 內部輔助
# =============================================================================

def _check_developer_access(secure_code: str) -> bool:
    """檢查當前用戶是否為開發者或管理員"""
    from ..models import DcSubSystem
    from ..services.project_service import ProjectService
    from app.security.resource_gateway import ResourceGateway

    ss = ResourceGateway.get(
        DcSubSystem, secure_code,
        raise_on_not_found=False,
        check_permission=False,
    )
    if not ss or ss.is_deleted:
        return False

    return ProjectService.is_developer(current_user, ss)
