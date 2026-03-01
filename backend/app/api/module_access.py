"""
BeakMask Module Access Control API
模組使用權控制 API

端點：
- GET    /<module_code>    取得指定模組的 ACL 列表
- POST   /                 新增 ACL
- DELETE /<secure_code>    軟刪除 ACL
- GET    /targets          取得可選 target 清單
"""
import logging

from flask import Blueprint, jsonify, request
from flask_login import current_user

from ..security.decorators import admin_required
from ..services.module_access_service import ModuleAccessService
from ..models.module_access_control import TargetType
from .. import csrf, db

logger = logging.getLogger(__name__)

module_access_bp = Blueprint(
    'module_access',
    __name__,
    url_prefix='/api/module-access'
)


@module_access_bp.route('/targets')
@admin_required
def get_targets():
    """
    取得可選 target 清單

    Query params:
        type: ROLE / DEPARTMENT / GROUP / ACCOUNT
        q: 搜尋關鍵字 (optional)
    """
    target_type = request.args.get('type', '').strip()
    query = request.args.get('q', '').strip()

    if target_type not in TargetType.ALL:
        return jsonify({
            'success': False,
            'error': f'Invalid type. Must be one of: {", ".join(TargetType.ALL)}'
        }), 400

    targets = ModuleAccessService.get_available_targets(
        current_user.org_secure_code,
        target_type,
        query
    )

    return jsonify({'success': True, 'data': targets})


@module_access_bp.route('/<module_code>')
@admin_required
def get_access_list(module_code):
    """取得指定模組的 ACL 列表"""
    acl_list = ModuleAccessService.get_access_list(
        current_user.org_secure_code,
        module_code
    )

    return jsonify({'success': True, 'data': acl_list})


@module_access_bp.route('/', methods=['POST'])
@csrf.exempt
@admin_required
def add_access():
    """
    新增 ACL

    Body:
        module_code: str
        target_type: ROLE / DEPARTMENT / GROUP / ACCOUNT
        target_secure_code: str
    """
    data = request.get_json() or {}
    module_code = data.get('module_code', '').strip()
    target_type = data.get('target_type', '').strip()
    target_sc = data.get('target_secure_code', '').strip()

    if not module_code:
        return jsonify({'success': False, 'error': '缺少 module_code'}), 400
    if target_type not in TargetType.ALL:
        return jsonify({'success': False, 'error': f'無效的 target_type: {target_type}'}), 400
    if not target_sc:
        return jsonify({'success': False, 'error': '缺少 target_secure_code'}), 400

    try:
        record = ModuleAccessService.add_access(
            current_user.org_secure_code,
            module_code,
            target_type,
            target_sc
        )

        if record is None:
            return jsonify({'success': False, 'error': '此指派已存在'}), 409

        db.session.commit()

        result = record.to_dict()
        result['target_name'] = ModuleAccessService._resolve_target_name(
            target_type, target_sc
        )

        return jsonify({
            'success': True,
            'data': result,
            'message': '已新增使用權指派'
        })

    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        logger.exception('[ModuleAccess] add_access error')
        return jsonify({'success': False, 'error': str(e)}), 500


@module_access_bp.route('/<secure_code>', methods=['DELETE'])
@csrf.exempt
@admin_required
def remove_access(secure_code):
    """軟刪除 ACL"""
    try:
        success = ModuleAccessService.remove_access(secure_code)
        if not success:
            return jsonify({'success': False, 'error': '記錄不存在'}), 404

        db.session.commit()
        return jsonify({'success': True, 'message': '已移除使用權指派'})

    except Exception as e:
        db.session.rollback()
        logger.exception('[ModuleAccess] remove_access error')
        return jsonify({'success': False, 'error': str(e)}), 500
