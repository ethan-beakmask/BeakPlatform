"""
FormWorkflow Module - Mapping Permissions API
配對填寫權限管理 API
"""
from flask import Blueprint, jsonify, request
from flask_login import current_user

from app.security.decorators import module_access_required, page_keys_required
from app.platform.auth import require_any_permission
from app.platform.data import get_current_org
from app import db, csrf
from flask_babel import gettext as _

mapping_permissions_bp = Blueprint(
    'form_workflow_mapping_permissions',
    __name__,
    url_prefix='/api/mapping-permissions'
)


# =============================================================================
# GET -- 取得可授權角色列表
# =============================================================================

@mapping_permissions_bp.route('/roles', methods=['GET'])
@module_access_required('form_workflow')
@page_keys_required('form_workflow.mappings')
@require_any_permission('form_workflow.workflow.manage', 'form_workflow.template.manage')
def list_assignable_roles():
    """取得本企業可用於填寫權限規則的角色列表"""
    from app.models.role import Role

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    roles = Role.query.filter(
        Role.org_secure_code == org.secure_code,
        Role.is_deleted == False,
        Role.is_active == True,
        Role.code != 'EXTERNAL_USERS',
    ).order_by(Role.sort_order, Role.code).all()

    return jsonify({
        'success': True,
        'data': [{'code': r.code, 'name': r.name} for r in roles]
    })


# =============================================================================
# GET -- 取得可授權部門/社群樹
# =============================================================================

@mapping_permissions_bp.route('/units', methods=['GET'])
@module_access_required('form_workflow')
@page_keys_required('form_workflow.mappings')
@require_any_permission('form_workflow.workflow.manage', 'form_workflow.template.manage')
def list_assignable_units():
    """取得本企業可用於填寫權限規則的部門或社群樹"""
    from app.models.organizational_unit import OrganizationalUnit, UnitType
    from app.security.resource_gateway import ResourceGateway

    unit_kind = request.args.get('type', '')
    unit_type_map = {
        'department': UnitType.DEPARTMENT,
        'group': UnitType.GROUP,
    }
    unit_type = unit_type_map.get(unit_kind)
    if not unit_type:
        return jsonify({'success': False, 'message': _('type 必須為 department 或 group')}), 400

    # 設計者不持有 department:read；此端點的授權由上方 require_any_permission
    # （form_workflow.workflow.manage / template.manage）負責，資料範圍仍受 gateway 的
    # org 隔離限制，且只回名稱層級欄位。
    units = ResourceGateway.filter(
        OrganizationalUnit,
        is_deleted=False,
        unit_type=unit_type,
        order_by='sort_order',
        check_permission=False,
    )

    nodes_by_sc = {
        unit.secure_code: {
            'secure_code': unit.secure_code,
            'code': unit.code,
            'name': unit.name,
            'full_path': unit.full_path,
            'children': [],
        }
        for unit in units
    }

    roots = []
    for unit in units:
        node = nodes_by_sc[unit.secure_code]
        parent = nodes_by_sc.get(unit.parent_secure_code)
        if parent:
            parent['children'].append(node)
        else:
            roots.append(node)

    return jsonify({'success': True, 'data': roots})


# =============================================================================
# GET -- 取得可授權使用者列表
# =============================================================================

@mapping_permissions_bp.route('/users', methods=['GET'])
@module_access_required('form_workflow')
@page_keys_required('form_workflow.mappings')
@require_any_permission('form_workflow.workflow.manage', 'form_workflow.template.manage')
def list_assignable_users():
    """取得本企業可用於填寫權限規則的使用者列表"""
    from app.models.user import User
    from app.security.resource_gateway import ResourceGateway

    # 設計者不持有 user:read；此端點的授權由上方 require_any_permission
    # （form_workflow.workflow.manage / template.manage）負責，資料範圍仍受 gateway 的
    # org 隔離限制，且只回名稱層級欄位。
    users = ResourceGateway.filter(
        User,
        is_deleted=False,
        is_active=True,
        order_by='display_name',
        check_permission=False,
    )

    return jsonify({
        'success': True,
        'data': [
            {
                'secure_code': user.secure_code,
                'name': user.display_name or user.native_name or user.username,
            }
            for user in users
        ],
    })


# =============================================================================
# GET -- 取得配對的權限列表
# =============================================================================

@mapping_permissions_bp.route('/<mapping_secure_code>', methods=['GET'])
@module_access_required('form_workflow')
@page_keys_required('form_workflow.mappings')
@require_any_permission('form_workflow.workflow.manage', 'form_workflow.template.manage')
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
        return jsonify({'success': False, 'message': _('配對不存在')}), 404

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
@page_keys_required('form_workflow.mappings')
@require_any_permission('form_workflow.workflow.manage', 'form_workflow.template.manage')
def create_permission(mapping_secure_code):
    """
    新增填寫權限規則

    Body:
        grant_type: department / group / user / role
        grant_target: 目標 secure_code
        grant_target_name: 顯示名稱
        include_children: boolean (僅 department 有效)
    """
    from ..models import FwMappingPermission, FwFormWorkflowMapping
    from app.models.role import Role

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    mapping = FwFormWorkflowMapping.query.filter_by(
        secure_code=mapping_secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()
    if not mapping:
        return jsonify({'success': False, 'message': _('配對不存在')}), 404

    data = request.get_json() or {}
    grant_type = data.get('grant_type', '')
    grant_target = data.get('grant_target', '')
    grant_target_name = data.get('grant_target_name', '')

    if grant_type not in ('department', 'group', 'user', 'role'):
        return jsonify({'success': False, 'message': _('grant_type 必須為 department / group / user / role')}), 400

    if not grant_target:
        return jsonify({'success': False, 'message': _('grant_target 為必填')}), 400

    if grant_type == 'role':
        if grant_target == 'EXTERNAL_USERS':
            return jsonify({'success': False, 'message': _('外部廠商請改用「社群」類型授權')}), 400

        role = Role.query.filter_by(
            org_secure_code=org.secure_code,
            code=grant_target,
            is_deleted=False,
            is_active=True
        ).first()
        if not role:
            return jsonify({'success': False, 'message': _('指定的角色不存在或已停用')}), 400
        if not grant_target_name:
            grant_target_name = role.name

    # 檢查重複
    existing = FwMappingPermission.query.filter_by(
        mapping_secure_code=mapping_secure_code,
        org_secure_code=org.secure_code,
        grant_type=grant_type,
        grant_target=grant_target,
        is_deleted=False
    ).first()
    if existing:
        return jsonify({'success': False, 'message': _('此規則已存在')}), 400

    include_children = bool(data.get('include_children', False)) if grant_type in ('department', 'group') else False
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
        'message': _('權限規則已新增'),
        'data': perm.to_dict()
    }), 201


# =============================================================================
# DELETE -- 刪除權限規則
# =============================================================================

@mapping_permissions_bp.route('/rule/<secure_code>', methods=['DELETE'])
@csrf.exempt
@module_access_required('form_workflow')
@page_keys_required('form_workflow.mappings')
@require_any_permission('form_workflow.workflow.manage', 'form_workflow.template.manage')
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
        return jsonify({'success': False, 'message': _('規則不存在')}), 404

    perm.is_deleted = True
    db.session.commit()

    return jsonify({
        'success': True,
        'message': _('權限規則已刪除')
    })
