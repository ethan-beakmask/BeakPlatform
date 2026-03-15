"""
BeakPlatform Account Roles Overview
帳號角色權限表

提供企業管理員查看所有帳號的社群歸屬與角色指派總覽。
"""
from flask import Blueprint, render_template, jsonify, request
from flask_login import current_user

from ..security.decorators import admin_required
from ..models.user import User, UserType
from ..models.user_unit_membership import UserUnitMembership, MembershipType, MembershipRole
from ..models.organizational_unit import OrganizationalUnit
from ..models.associations import UserRoleAssignment
from ..models.role import Role
from .. import db

account_roles_bp = Blueprint('account_roles', __name__)

# 社群內身份對照表
_MEMBERSHIP_ROLE_LABELS = {
    MembershipRole.MANAGER: '團長',
    MembershipRole.DEPUTY: '副團長',
    MembershipRole.PROXY1: '代理人(一)',
    MembershipRole.PROXY2: '代理人(二)',
    MembershipRole.MEMBER: '團員',
    None: '團員',
}


@account_roles_bp.route('/')
@admin_required
def index():
    """帳號角色權限表主頁"""
    org_sc = current_user.org_secure_code

    # 篩選條件
    filter_user_type = request.args.get('user_type', '')
    filter_q = request.args.get('q', '').strip()

    # 查詢所有帳號（排除已刪除、已停用）
    query = User.query.filter(
        User.org_secure_code == org_sc,
        User.is_deleted == False,
        User.is_active == True,
    )

    if filter_user_type:
        query = query.filter(User.user_type == filter_user_type)

    if filter_q:
        query = query.filter(
            db.or_(
                User.display_name.ilike(f'%{filter_q}%'),
                User.username.ilike(f'%{filter_q}%'),
                User.employee_id.ilike(f'%{filter_q}%'),
            )
        )

    users = query.order_by(User.user_type, User.display_name).all()
    user_codes = [u.secure_code for u in users]

    # 批次查詢社群成員關係
    memberships = []
    if user_codes:
        memberships = UserUnitMembership.query.filter(
            UserUnitMembership.user_secure_code.in_(user_codes),
            UserUnitMembership.membership_type == MembershipType.MEMBER,
            UserUnitMembership.is_deleted == False,
        ).all()

    # 批次查詢社群名稱
    unit_codes = list({m.unit_secure_code for m in memberships})
    unit_map = {}
    if unit_codes:
        units = OrganizationalUnit.query.filter(
            OrganizationalUnit.secure_code.in_(unit_codes),
            OrganizationalUnit.is_deleted == False,
        ).all()
        unit_map = {u.secure_code: u.name for u in units}

    # 組裝社群資料：user_sc -> [{name, role}]
    user_groups = {}
    for m in memberships:
        if m.unit_secure_code not in unit_map:
            continue
        user_groups.setdefault(m.user_secure_code, []).append({
            'name': unit_map[m.unit_secure_code],
            'role': _MEMBERSHIP_ROLE_LABELS.get(m.role_type, '團員'),
            'is_leader': m.is_leader,
        })

    # 排序：管理層優先
    for groups in user_groups.values():
        groups.sort(key=lambda g: (not g['is_leader'], g['name']))

    # 批次查詢角色指派
    assignments = []
    if user_codes:
        assignments = UserRoleAssignment.query.filter(
            UserRoleAssignment.user_secure_code.in_(user_codes),
            UserRoleAssignment.is_deleted == False,
        ).all()

    # 批次查詢角色名稱
    role_codes = list({a.role_secure_code for a in assignments})
    role_map = {}
    if role_codes:
        roles = Role.query.filter(
            Role.secure_code.in_(role_codes),
            Role.is_deleted == False,
        ).all()
        role_map = {r.secure_code: r for r in roles}

    # 組裝角色資料：user_sc -> [{name, scope}]
    user_roles = {}
    for a in assignments:
        role = role_map.get(a.role_secure_code)
        if not role:
            continue
        user_roles.setdefault(a.user_secure_code, []).append({
            'name': role.name,
            'code': role.code,
            'scope_type': role.scope_type,
            'is_system_role': role.is_system_role,
        })

    for roles_list in user_roles.values():
        roles_list.sort(key=lambda r: (r['is_system_role'], r['name']))

    # user_type 標籤對照
    user_type_labels = {
        UserType.ORG_ADMIN: '企業管理員',
        UserType.EMPLOYEE: '員工',
        UserType.EXTERNAL: '外部廠商',
        UserType.SYSTEM_ADMIN: '系統管理員',
    }

    return render_template(
        'pages/account_roles.html',
        users=users,
        user_groups=user_groups,
        user_roles=user_roles,
        user_type_labels=user_type_labels,
        filter_user_type=filter_user_type,
        filter_q=filter_q,
    )
