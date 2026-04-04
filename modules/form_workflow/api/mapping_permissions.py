"""
FormWorkflow Module - Mapping Permissions API
配對填寫權限管理 API
"""
from flask import Blueprint, jsonify, request
from flask_login import current_user

from app.security.decorators import module_access_required
from app.platform.data import get_current_org
from app import db, csrf

mapping_permissions_bp = Blueprint(
    'form_workflow_mapping_permissions',
    __name__,
    url_prefix='/api/mapping-permissions'
)


# =============================================================================
# GET -- 取得配對的權限列表
# =============================================================================

@mapping_permissions_bp.route('/<mapping_secure_code>', methods=['GET'])
@module_access_required('form_workflow')
def list_permissions(mapping_secure_code):
    """取得指定配對的填寫權限列表"""
    from ..models import FwMappingPermission, FwFormWorkflowMapping

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    # 驗證配對存在且屬於此企業
    mapping = FwFormWorkflowMapping.query.filter_by(
        secure_code=mapping_secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()
    if not mapping:
        return jsonify({'success': False, 'message': '配對不存在'}), 404

    permissions = FwMappingPermission.query.filter_by(
        mapping_secure_code=mapping_secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).order_by(FwMappingPermission.grant_type, FwMappingPermission.created_at).all()

    return jsonify({
        'success': True,
        'data': [p.to_dict() for p in permissions]
    })


# =============================================================================
# POST -- 新增權限規則
# =============================================================================

@mapping_permissions_bp.route('/<mapping_secure_code>', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow')
def create_permission(mapping_secure_code):
    """
    新增填寫權限規則

    Body:
        grant_type: department / group / user
        grant_target: 目標 secure_code
        grant_target_name: 顯示名稱
        include_children: boolean (僅 department 有效)
    """
    from ..models import FwMappingPermission, FwFormWorkflowMapping

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    mapping = FwFormWorkflowMapping.query.filter_by(
        secure_code=mapping_secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()
    if not mapping:
        return jsonify({'success': False, 'message': '配對不存在'}), 404

    data = request.get_json() or {}
    grant_type = data.get('grant_type', '')
    grant_target = data.get('grant_target', '')
    grant_target_name = data.get('grant_target_name', '')

    if grant_type not in ('department', 'group', 'user'):
        return jsonify({'success': False, 'message': 'grant_type 必須為 department / group / user'}), 400

    if not grant_target:
        return jsonify({'success': False, 'message': 'grant_target 為必填'}), 400

    # 檢查重複
    existing = FwMappingPermission.query.filter_by(
        mapping_secure_code=mapping_secure_code,
        org_secure_code=org.secure_code,
        grant_type=grant_type,
        grant_target=grant_target,
        is_deleted=False
    ).first()
    if existing:
        return jsonify({'success': False, 'message': '此規則已存在'}), 400

    include_children = bool(data.get('include_children', False)) if grant_type == 'department' else False
    user_name = getattr(current_user, 'display_name', '') or getattr(current_user, 'native_name', '') or ''

    perm = FwMappingPermission(
        org_secure_code=org.secure_code,
        mapping_secure_code=mapping_secure_code,
        grant_type=grant_type,
        grant_target=grant_target,
        grant_target_name=grant_target_name,
        include_children=include_children,
        created_by_name=user_name,
    )

    db.session.add(perm)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': '權限規則已新增',
        'data': perm.to_dict()
    }), 201


# =============================================================================
# DELETE -- 刪除權限規則
# =============================================================================

@mapping_permissions_bp.route('/rule/<secure_code>', methods=['DELETE'])
@csrf.exempt
@module_access_required('form_workflow')
def delete_permission(secure_code):
    """刪除填寫權限規則"""
    from ..models import FwMappingPermission

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    perm = FwMappingPermission.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()
    if not perm:
        return jsonify({'success': False, 'message': '規則不存在'}), 404

    perm.is_deleted = True
    db.session.commit()

    return jsonify({
        'success': True,
        'message': '權限規則已刪除'
    })
