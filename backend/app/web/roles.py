"""
BeakMask Role Management Web Routes
角色權限管理網頁路由
"""
from flask import Blueprint, render_template, abort, request, flash, redirect, url_for
from flask_login import current_user
from sqlalchemy import func

from ..security.decorators import system_admin_required
from ..security.resource_gateway import ResourceGateway
from ..models import Role, RoleType, ScopeType, UserRoleAssignment, User
from .. import db

roles_bp = Blueprint('roles', __name__)


@roles_bp.route('/')
def list_roles():
    """角色列表頁面"""
    result = ResourceGateway.list(
        Role,
        is_deleted=False,
        order_by='sort_order',
        per_page=100,
        require_permission='role:read'
    )

    # 查詢每個角色的使用次數（排除已刪除的用戶）
    role_codes = [r.secure_code for r in result['items']]
    usage_counts = {}

    if role_codes:
        counts = db.session.query(
            UserRoleAssignment.role_secure_code,
            func.count(UserRoleAssignment.id)
        ).join(
            User,
            User.secure_code == UserRoleAssignment.user_secure_code
        ).filter(
            UserRoleAssignment.role_secure_code.in_(role_codes),
            UserRoleAssignment.is_deleted == False,
            User.is_deleted == False
        ).group_by(UserRoleAssignment.role_secure_code).all()

        usage_counts = {code: count for code, count in counts}

    return render_template(
        'pages/roles/list.html',
        roles=result['items'],
        usage_counts=usage_counts,
        RoleType=RoleType,
        ScopeType=ScopeType
    )


@roles_bp.route('/<secure_code>')
def view_role(secure_code: str):
    """查看角色詳情 - 重定向到編輯頁"""
    return redirect(url_for('roles.edit_role', secure_code=secure_code))


@roles_bp.route('/create', methods=['GET', 'POST'])
def create_role():
    """建立角色頁面"""
    if request.method == 'POST':
        # Handle form submission via API
        pass
    return render_template(
        'pages/roles/create.html',
        RoleType=RoleType,
        ScopeType=ScopeType
    )


@roles_bp.route('/<secure_code>/edit', methods=['GET', 'POST'])
def edit_role(secure_code: str):
    """編輯角色頁面（含查看功能）"""
    role = ResourceGateway.get(Role, secure_code, raise_on_not_found=False)
    if not role:
        abort(404)

    # 查詢使用此角色的用戶
    assigned_users = db.session.query(User).join(
        UserRoleAssignment,
        User.secure_code == UserRoleAssignment.user_secure_code
    ).filter(
        UserRoleAssignment.role_secure_code == secure_code,
        UserRoleAssignment.is_deleted == False,
        User.is_deleted == False
    ).all()

    return render_template(
        'pages/roles/edit.html',
        role=role,
        assigned_users=assigned_users,
        is_editable=not role.is_system_role,
        RoleType=RoleType,
        ScopeType=ScopeType
    )
