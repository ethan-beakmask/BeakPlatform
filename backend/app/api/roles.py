"""
BeakMask Role API
角色/職務 API
"""
import logging
from datetime import datetime

from flask import Blueprint, request, jsonify
from flask_babel import gettext as _
from flask_login import current_user

from ..security.decorators import admin_required, login_required
from ..security.resource_gateway import ResourceGateway
from ..models import (
    Role, RoleType, ScopeType, ExclusiveGroup,
    OrganizationalUnit, UserRoleAssignment, User
)
from ..services.code_generator import get_code_generator
from .. import db, csrf

logger = logging.getLogger(__name__)

roles_bp = Blueprint('api_roles', __name__, url_prefix='/api/roles')


def _is_sys_admin() -> bool:
    return bool(getattr(current_user, 'is_system_admin', False))


def _request_data() -> dict:
    return request.get_json(silent=True) or {}


def _resolve_org_code(data: dict = None) -> str:
    if _is_sys_admin():
        payload = data if data is not None else _request_data()
        return request.args.get('org_code') or payload.get('org_code') or current_user.org_secure_code
    return current_user.org_secure_code


def _role_filters(org_code: str, **filters) -> dict:
    next_filters = {'org_secure_code': org_code}
    next_filters.update(filters)
    return next_filters


def _find_role(identifier: str, org_code: str) -> Role:
    role = ResourceGateway.get_by(
        Role,
        skip_tenant_filter=_is_sys_admin(),
        **_role_filters(org_code, secure_code=identifier, is_deleted=False)
    )
    if role:
        return role

    roles = ResourceGateway.filter(
        Role,
        skip_tenant_filter=_is_sys_admin(),
        **_role_filters(org_code, is_deleted=False)
    )
    return next((r for r in roles if r.code == identifier), None)


def _valid_exclusive_group(value) -> bool:
    return value in (
        None,
        '',
        ExclusiveGroup.IDENTITY_TYPE,
        ExclusiveGroup.DEPT_POSITION,
        ExclusiveGroup.GROUP_POSITION
    )


def _normalize_exclusive_group(value):
    return None if value == '' else value


def _role_holder_users(role_secure_code: str, org_code: str):
    assignments = ResourceGateway.filter(
        UserRoleAssignment,
        skip_tenant_filter=_is_sys_admin(),
        role_secure_code=role_secure_code,
        org_secure_code=org_code,
        is_deleted=False
    )
    users = []
    seen = set()
    for assignment in assignments:
        user = ResourceGateway.get_by(
            User,
            skip_tenant_filter=_is_sys_admin(),
            secure_code=assignment.user_secure_code,
            org_secure_code=org_code,
            is_deleted=False
        )
        if user and user.secure_code not in seen:
            seen.add(user.secure_code)
            users.append(user)
    return users


def _serialize_role(role: Role, include_children: bool = False) -> dict:
    data = role.to_dict(include_children=include_children)
    data.update({
        'exclusive_group': role.exclusive_group,
        'is_system_role': role.is_system_role,
        'is_active': role.is_active,
        'holder_count': len(_role_holder_users(role.secure_code, role.org_secure_code)),
    })
    return data


@roles_bp.route('/', methods=['GET'])
@admin_required
def list_roles():
    """
    取得角色列表

    GET /api/roles
    Query params:
        - type: POSITION / ROLE (篩選)
        - scope: GLOBAL / DEPARTMENT / GROUP (篩選)
        - tree: true = 返回樹狀結構
    """
    role_type = request.args.get('type')
    scope_type = request.args.get('scope')
    as_tree = request.args.get('tree', 'false').lower() == 'true'
    org_code = _resolve_org_code()

    filters = _role_filters(org_code, is_deleted=False)
    if role_type:
        filters['role_type'] = role_type
    if scope_type:
        filters['scope_type'] = scope_type

    roles = ResourceGateway.filter(
        Role,
        order_by='sort_order',
        skip_tenant_filter=_is_sys_admin(),
        **filters
    )

    if as_tree:
        root_roles = [r for r in roles if r.parent_secure_code is None]
        return jsonify({
            'roles': [_serialize_role(r, include_children=True) for r in root_roles]
        }), 200

    return jsonify({
        'roles': [_serialize_role(r) for r in roles]
    }), 200


@roles_bp.route('/<secure_code>', methods=['GET'])
@admin_required
def get_role(secure_code: str):
    """
    取得單一角色

    GET /api/roles/<secure_code>
    """
    org_code = _resolve_org_code()
    role = _find_role(secure_code, org_code)

    if not role:
        return jsonify({'error': _('角色不存在')}), 404

    return jsonify({
        'role': _serialize_role(role, include_children=True)
    }), 200


@roles_bp.route('/generate-code', methods=['POST'])
@csrf.exempt  # API endpoint
@admin_required
def generate_code():
    """
    預覽自動產生的代碼

    POST /api/roles/generate-code
    Body: { "name": "業務經理" }
    Response: { "code": "SALES_MANAGER", "suggestions": [...] }
    """
    data = _request_data()
    if not data or not data.get('name'):
        return jsonify({'error': _('請提供名稱')}), 400

    generator = get_code_generator()
    org_code = _resolve_org_code(data)

    def exists_checker(code: str) -> bool:
        roles = ResourceGateway.filter(
            Role,
            skip_tenant_filter=_is_sys_admin(),
            **_role_filters(org_code, is_deleted=False)
        )
        return any(r.code.upper() == code.upper() for r in roles)

    try:
        code = generator.generate(data['name'], exists_checker=exists_checker)
        suggestions = generator.suggest(data['name'], exists_checker=exists_checker, count=3)

        return jsonify({
            'code': code,
            'suggestions': suggestions
        }), 200

    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@roles_bp.route('/validate-code', methods=['POST'])
@csrf.exempt  # API endpoint
@admin_required
def validate_code():
    """
    驗證代碼格式與唯一性

    POST /api/roles/validate-code
    Body: { "code": "MY_CODE" }
    Response: { "valid": true } 或 { "valid": false, "error": "..." }
    """
    data = _request_data()
    if not data or not data.get('code'):
        return jsonify({'error': _('請提供代碼')}), 400

    generator = get_code_generator()
    org_code = _resolve_org_code(data)

    def exists_checker(code: str) -> bool:
        roles = ResourceGateway.filter(
            Role,
            skip_tenant_filter=_is_sys_admin(),
            **_role_filters(org_code, is_deleted=False)
        )
        return any(r.code.upper() == code.upper() for r in roles)

    is_valid, error = generator.validate_with_exists_check(
        data['code'],
        exists_checker
    )

    if is_valid:
        return jsonify({'valid': True}), 200
    else:
        return jsonify({'valid': False, 'error': error}), 200


@roles_bp.route('/', methods=['POST'])
@csrf.exempt  # API endpoint
@admin_required
def create_role():
    """
    建立角色

    POST /api/roles
    Body: {
        "code": "PROJECT_MANAGER",  // 選填，不提供則自動產生
        "name": "專案經理",          // 必填
        "role_type": "POSITION",
        "scope_type": "DEPARTMENT",
        "parent_id": null,
        "is_manager": true,
        "description": "專案管理職務"
    }
    """
    data = _request_data()
    if not data:
        return jsonify({'error': _('請提供角色資料')}), 400

    # 只有 name 是必填
    if not data.get('name'):
        return jsonify({'error': _('缺少必要欄位: name')}), 400
    if not _valid_exclusive_group(data.get('exclusive_group')):
        return jsonify({'error': _('互斥群組值無效')}), 400

    org_code = _resolve_org_code(data)

    generator = get_code_generator()

    def exists_checker(code: str) -> bool:
        roles = ResourceGateway.filter(
            Role,
            skip_tenant_filter=_is_sys_admin(),
            **_role_filters(org_code, is_deleted=False)
        )
        return any(r.code.upper() == code.upper() for r in roles)

    # 處理代碼：用戶輸入優先，否則自動產生
    if data.get('code'):
        # 用戶手動輸入，驗證格式
        code = data['code'].strip()
        is_valid, error = generator.validate(code)
        if not is_valid:
            return jsonify({'error': _('代碼格式錯誤: %(error)s', error=error)}), 400

        # 檢查重複 (case-insensitive)
        if exists_checker(code):
            return jsonify({'error': _('代碼 %(code)s 已存在', code=code)}), 400
    else:
        # 自動產生代碼
        try:
            code = generator.generate(data['name'], exists_checker=exists_checker)
        except ValueError as e:
            return jsonify({'error': _('無法自動產生代碼: %(error)s', error=e)}), 400

    # 檢查父層
    parent = None
    if data.get('parent_id'):
        parent = ResourceGateway.get_by(
            Role,
            skip_tenant_filter=_is_sys_admin(),
            **_role_filters(org_code, secure_code=data['parent_id'], is_deleted=False)
        )
        if not parent:
            return jsonify({'error': _('父層角色不存在')}), 400

    # 檢查綁定的組織單位
    bound_unit = None
    if data.get('bound_unit_id'):
        bound_unit = ResourceGateway.get_by(
            OrganizationalUnit,
            skip_tenant_filter=_is_sys_admin(),
            org_secure_code=org_code,
            secure_code=data['bound_unit_id'],
            is_deleted=False
        )
        if not bound_unit:
            return jsonify({'error': _('綁定的組織單位不存在')}), 400

    try:
        role = Role(
            org_secure_code=org_code,
            role_type=data.get('role_type', RoleType.ROLE),
            scope_type=data.get('scope_type', ScopeType.GLOBAL),
            code=code,  # 使用前面處理好的代碼（手動輸入或自動產生）
            name=data['name'],
            description=data.get('description'),
            parent_secure_code=parent.secure_code if parent else None,
            is_manager=data.get('is_manager', False),
            is_system_role=False,
            is_active=data.get('is_active', True),
            exclusive_group=_normalize_exclusive_group(data.get('exclusive_group')),
            bound_unit_secure_code=bound_unit.secure_code if bound_unit else None,
            sort_order=data.get('sort_order', 0)
        )
        role.update_full_path()
        db.session.add(role)
        db.session.commit()

        logger.info(f"Role created: {role.code} by {current_user.email}")

        return jsonify({
            'message': _('角色建立成功'),
            'role': _serialize_role(role)
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to create role: {e}")
        return jsonify({'error': _('建立角色失敗')}), 500


@roles_bp.route('/<secure_code>', methods=['PUT'])
@csrf.exempt  # API endpoint
@admin_required
def update_role(secure_code: str):
    """
    更新角色

    PUT /api/roles/<secure_code>
    """
    data = _request_data()
    org_code = _resolve_org_code(data)
    role = _find_role(secure_code, org_code)

    if not role:
        return jsonify({'error': _('角色不存在')}), 404

    # 系統角色只能修改部分欄位
    if role.is_system_role:
        allowed_fields = ['description', 'sort_order', 'is_active']
        for key in data.keys():
            if key not in allowed_fields and key != 'org_code':
                return jsonify({'error': _('系統角色不允許修改 %(field)s 欄位', field=key)}), 400

    if not data:
        return jsonify({'error': _('請提供更新資料')}), 400
    if 'exclusive_group' in data and not _valid_exclusive_group(data.get('exclusive_group')):
        return jsonify({'error': _('互斥群組值無效')}), 400

    try:
        old_name = role.name

        if 'name' in data and not role.is_system_role:
            role.name = data['name']
        if 'description' in data:
            role.description = data['description']
        if 'role_type' in data and not role.is_system_role:
            role.role_type = data['role_type']
        if 'scope_type' in data and not role.is_system_role:
            role.scope_type = data['scope_type']
        if 'is_manager' in data and not role.is_system_role:
            role.is_manager = data['is_manager']
        if 'sort_order' in data:
            role.sort_order = data['sort_order']
        if 'is_active' in data:
            role.is_active = data['is_active']
        if 'exclusive_group' in data and not role.is_system_role:
            role.exclusive_group = _normalize_exclusive_group(data.get('exclusive_group'))

        # 更新父層
        if 'parent_id' in data and not role.is_system_role:
            if data['parent_id']:
                if data['parent_id'] == role.secure_code:
                    return jsonify({'error': _('不能設定自己為父層')}), 400

                descendants = role.get_descendants()
                if any(d.secure_code == data['parent_id'] for d in descendants):
                    return jsonify({'error': _('不能設定子層為父層')}), 400

                parent = ResourceGateway.get_by(
                    Role,
                    skip_tenant_filter=_is_sys_admin(),
                    org_secure_code=org_code,
                    secure_code=data['parent_id'],
                    is_deleted=False
                )

                if not parent:
                    return jsonify({'error': _('父層角色不存在')}), 400

                role.parent_secure_code = parent.secure_code
            else:
                role.parent_secure_code = None

        # 更新路徑
        role.update_full_path()

        if role.name != old_name:
            role.update_children_paths()

        db.session.commit()

        return jsonify({
            'message': _('角色更新成功'),
            'role': _serialize_role(role)
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update role: {e}")
        return jsonify({'error': _('更新角色失敗')}), 500


@roles_bp.route('/<secure_code>', methods=['DELETE'])
@csrf.exempt  # API endpoint
@admin_required
def delete_role(secure_code: str):
    """
    刪除角色 (軟刪除)

    DELETE /api/roles/<secure_code>
    Query params:
        - force: true = 強制刪除（即使有用戶使用）
    """
    org_code = _resolve_org_code()
    role = _find_role(secure_code, org_code)

    if not role:
        return jsonify({'error': _('角色不存在')}), 404

    # 系統角色不可刪除
    if role.is_system_role:
        return jsonify({'error': _('系統角色不可刪除')}), 400

    # 檢查是否有子角色
    children = [c for c in role.children if not c.is_deleted]
    if children:
        return jsonify({'error': _('此角色有子角色，請先刪除子角色')}), 400

    # 檢查是否有用戶使用此角色
    assignments = ResourceGateway.filter(
        UserRoleAssignment,
        skip_tenant_filter=_is_sys_admin(),
        role_secure_code=role.secure_code,
        org_secure_code=org_code,
        is_deleted=False
    )
    if assignments and request.args.get('force', 'false').lower() != 'true':
        return jsonify({
            'error': _('此角色已有 %(count)s 位用戶使用，需強制刪除', count=len(assignments)),
            'holder_count': len(assignments),
            'requires_force': True
        }), 400

    # 如果有用戶使用，同時刪除指派關係
    if assignments:
        for assignment in assignments:
            assignment.is_deleted = True
            assignment.deleted_at = datetime.utcnow()

    try:
        role.is_deleted = True
        role.deleted_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            'message': _('角色已刪除')
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete role: {e}")
        return jsonify({'error': _('刪除角色失敗')}), 500


@roles_bp.route('/<secure_code>/users', methods=['GET'])
@admin_required
def list_role_users(secure_code: str):
    """取得角色持有用戶清單"""
    org_code = _resolve_org_code()
    role = _find_role(secure_code, org_code)

    if not role:
        return jsonify({'error': _('角色不存在')}), 404

    users = _role_holder_users(role.secure_code, org_code)
    return jsonify({
        'users': [
            {
                'secure_code': user.secure_code,
                'name': user.native_name or user.display_name or user.username,
                'email': user.email,
            }
            for user in users
        ]
    }), 200


@roles_bp.route('/batch-delete', methods=['POST'])
@csrf.exempt  # API endpoint
@admin_required
def batch_delete_roles():
    """
    批量刪除角色

    POST /api/roles/batch-delete
    Body: { "ids": ["secure_code1", "secure_code2", ...] }
    """
    data = request.get_json()
    if not data or not data.get('ids'):
        return jsonify({'error': _('請提供要刪除的角色 ID 列表')}), 400

    ids = data['ids']
    deleted = 0
    errors = []

    for secure_code in ids:
        role = ResourceGateway.get_by(Role, secure_code=secure_code, is_deleted=False)

        if not role:
            errors.append(_('%(code)s: 角色不存在', code=secure_code))
            continue

        if role.is_system_role:
            errors.append(_('%(name)s: 系統角色不可刪除', name=role.name))
            continue

        # 檢查是否有子角色
        children = [c for c in role.children if not c.is_deleted]
        if children:
            errors.append(_('%(name)s: 有子角色，請先刪除子角色', name=role.name))
            continue

        # 刪除相關指派
        assignments = ResourceGateway.filter(
            UserRoleAssignment,
            role_secure_code=secure_code,
            is_deleted=False
        )
        for assignment in assignments:
            assignment.is_deleted = True
            assignment.deleted_at = datetime.utcnow()

        # 刪除角色
        role.is_deleted = True
        role.deleted_at = datetime.utcnow()
        deleted += 1

    try:
        db.session.commit()
        return jsonify({
            'message': _('已刪除 %(count)s 個角色', count=deleted),
            'deleted': deleted,
            'errors': errors
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to batch delete roles: {e}")
        return jsonify({'error': _('批量刪除失敗')}), 500


# =====================================================
# 職務 API (便捷路由)
# =====================================================

@roles_bp.route('/positions', methods=['GET'])
@admin_required
def list_positions():
    """取得職務列表"""
    request.args = request.args.copy()
    request.args['type'] = RoleType.POSITION
    return list_roles()
