"""
BeakPlatform Account Roles Overview
帳號角色權限表

提供企業管理員查看所有帳號的社群歸屬與角色指派總覽，
並支援角色指派與移除操作。
"""
import logging
from datetime import datetime
from flask import Blueprint, render_template, jsonify, request
from flask_babel import gettext as _
from flask_login import current_user

from ..security.resource_gateway import ResourceGateway
from ..models.user import User, UserType
from ..models.user_unit_membership import UserUnitMembership, MembershipType, MembershipRole
from ..models.organizational_unit import OrganizationalUnit
from ..models.associations import UserRoleAssignment
from ..models.role import Role, ExclusiveGroup
from .. import db, csrf

logger = logging.getLogger(__name__)

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
def index():
    """帳號角色權限表主頁"""
    org_sc = current_user.org_secure_code

    # 篩選條件
    filter_user_type = request.args.get('user_type', '')
    filter_q = request.args.get('q', '').strip()

    # 查詢所有帳號（排除已刪除、已停用、系統管理員）
    query = User.query.filter(
        User.org_secure_code == org_sc,
        User.is_deleted == False,
        User.is_active == True,
        User.user_type != UserType.SYSTEM_ADMIN,
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

    # 批次查詢部門歸屬（SOLID=主要部門, DOTTED=跨部門）
    dept_memberships = []
    if user_codes:
        dept_memberships = UserUnitMembership.query.filter(
            UserUnitMembership.user_secure_code.in_(user_codes),
            UserUnitMembership.membership_type.in_([MembershipType.SOLID, MembershipType.DOTTED]),
            UserUnitMembership.is_deleted == False,
        ).all()

    # 批次查詢部門名稱
    dept_unit_codes = list({m.unit_secure_code for m in dept_memberships})
    dept_unit_map = {}
    if dept_unit_codes:
        dept_units = OrganizationalUnit.query.filter(
            OrganizationalUnit.secure_code.in_(dept_unit_codes),
            OrganizationalUnit.is_deleted == False,
        ).all()
        dept_unit_map = {u.secure_code: u.name for u in dept_units}

    # 批次查詢部門職務角色（DEPT_MANAGER 等）
    dept_role_codes = ['DEPT_MANAGER', 'DEPT_DEPUTY', 'DEPT_PROXY1', 'DEPT_PROXY2']
    dept_roles = Role.query.filter(
        Role.org_secure_code == org_sc,
        Role.code.in_(dept_role_codes),
        Role.is_deleted == False,
    ).all()
    dept_role_sc_map = {r.secure_code: r.code for r in dept_roles}
    dept_role_scs = list(dept_role_sc_map.keys())

    # 查詢部門級角色指派
    dept_role_assignments = []
    if user_codes and dept_role_scs:
        dept_role_assignments = UserRoleAssignment.query.filter(
            UserRoleAssignment.user_secure_code.in_(user_codes),
            UserRoleAssignment.role_secure_code.in_(dept_role_scs),
            UserRoleAssignment.is_deleted == False,
        ).all()

    # 建立 (user_sc, unit_sc) → role_code 對照
    _dept_role_label_map = {
        'DEPT_MANAGER': '\u4E3B\u7BA1',
        'DEPT_DEPUTY': '\u526F\u4E3B\u7BA1',
        'DEPT_PROXY1': '\u4EE3\u7406\u4EBA(\u4E00)',
        'DEPT_PROXY2': '\u4EE3\u7406\u4EBA(\u4E8C)',
    }
    user_unit_role = {}
    for a in dept_role_assignments:
        if a.unit_secure_code:
            role_code = dept_role_sc_map.get(a.role_secure_code, '')
            label = _dept_role_label_map.get(role_code, '')
            if label:
                user_unit_role[(a.user_secure_code, a.unit_secure_code)] = label

    # 組裝部門資料：user_sc -> [{name, role, is_cross}]
    user_depts = {}
    _cross_role_label = {
        'MANAGER': '\u4EE3\u7406',
        'DEPUTY': '\u4EE3\u7406',
        'PROXY1': '\u4EE3\u7406',
        'PROXY2': '\u4EE3\u7406',
        'MEMBER': '\u54E1\u5DE5',
    }
    for m in dept_memberships:
        dept_name = dept_unit_map.get(m.unit_secure_code)
        if not dept_name:
            continue
        is_cross = m.membership_type == MembershipType.DOTTED
        if is_cross:
            role_label = _cross_role_label.get(m.role_type, '\u54E1\u5DE5')
        else:
            role_label = user_unit_role.get(
                (m.user_secure_code, m.unit_secure_code), '\u54E1\u5DE5'
            )
        user_depts.setdefault(m.user_secure_code, []).append({
            'name': dept_name,
            'role': role_label,
            'is_cross': is_cross,
        })

    # 排序：主要部門優先，再按名稱
    for depts in user_depts.values():
        depts.sort(key=lambda d: (d['is_cross'], d['name']))

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
            'secure_code': role.secure_code,
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
        UserType.EMPLOYEE: '企業成員',
        UserType.EXTERNAL: '外部廠商',
        UserType.SYSTEM_ADMIN: '系統管理員',
    }

    # 查詢可指派角色（GLOBAL + EXTERNAL scope，排除部門/社群專屬）
    assignable_roles = Role.query.filter(
        Role.org_secure_code == org_sc,
        Role.is_deleted == False,
        Role.is_active == True,
        Role.scope_type.in_(['GLOBAL', 'EXTERNAL']),
    ).order_by(Role.is_system_role.desc(), Role.name).all()

    return render_template(
        'pages/account_roles.html',
        users=users,
        user_depts=user_depts,
        user_groups=user_groups,
        user_roles=user_roles,
        user_type_labels=user_type_labels,
        filter_user_type=filter_user_type,
        filter_q=filter_q,
        assignable_roles=assignable_roles,
    )


# =============================================================================
# 角色指派 API
# =============================================================================

@account_roles_bp.route('/api/assign', methods=['POST'])
@csrf.exempt
def assign_role():
    """指派角色給用戶"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': _('缺少請求資料')}), 400

    user_sc = data.get('user_secure_code')
    role_sc = data.get('role_secure_code')

    if not user_sc or not role_sc:
        return jsonify({'success': False, 'error': _('缺少必要參數')}), 400

    org_sc = current_user.org_secure_code

    # 驗證用戶
    user = User.query.filter_by(
        secure_code=user_sc,
        org_secure_code=org_sc,
        is_deleted=False,
    ).first()
    if not user:
        return jsonify({'success': False, 'error': _('用戶不存在')}), 404

    # 驗證角色
    role = Role.query.filter_by(
        secure_code=role_sc,
        org_secure_code=org_sc,
        is_deleted=False,
    ).first()
    if not role:
        return jsonify({'success': False, 'error': _('角色不存在')}), 404

    # 檢查重複（per-unit 角色需考慮 unit_secure_code）
    dup_query = UserRoleAssignment.query.filter(
        UserRoleAssignment.user_secure_code == user_sc,
        UserRoleAssignment.role_secure_code == role_sc,
        UserRoleAssignment.is_deleted == False,
    )
    req_unit_sc = data.get('unit_secure_code')
    if req_unit_sc:
        dup_query = dup_query.filter(
            UserRoleAssignment.unit_secure_code == req_unit_sc
        )
    existing = dup_query.first()
    if existing:
        return jsonify({'success': False, 'error': _('用戶已擁有「%(role)s」角色', role=role.name)}), 409

    # 互斥群組檢查：同一 exclusive_group 的角色只能擇一
    if role.exclusive_group:
        conflict_query = db.session.query(Role).join(
            UserRoleAssignment,
            UserRoleAssignment.role_secure_code == Role.secure_code,
        ).filter(
            UserRoleAssignment.user_secure_code == user_sc,
            UserRoleAssignment.is_deleted == False,
            Role.exclusive_group == role.exclusive_group,
            Role.is_deleted == False,
        )

        # per-unit 範圍互斥：僅在同一 unit_secure_code 下檢查
        unit_sc = data.get('unit_secure_code')
        if role.exclusive_group in ExclusiveGroup.UNIT_SCOPED:
            if unit_sc:
                conflict_query = conflict_query.filter(
                    UserRoleAssignment.unit_secure_code == unit_sc
                )
            else:
                # DEPT_POSITION 等 per-unit 互斥群組必須提供 unit_secure_code
                conflict_query = conflict_query.filter(
                    UserRoleAssignment.unit_secure_code.is_(None)
                )

        conflict_role = conflict_query.first()
        if conflict_role:
            return jsonify({
                'success': False,
                'error': _('無法指派「%(role)s」：與現有角色「%(conflict)s」互斥，請先移除後再指派', role=role.name, conflict=conflict_role.name),
            }), 409

    unit_sc = data.get('unit_secure_code')
    assignment = UserRoleAssignment(
        org_secure_code=org_sc,
        user_secure_code=user_sc,
        role_secure_code=role_sc,
        unit_secure_code=unit_sc,
        assigned_by=current_user.secure_code,
    )
    db.session.add(assignment)
    db.session.commit()

    logger.info(f"Role assigned: {user.display_name} <- {role.name} by {current_user.display_name}")

    return jsonify({
        'success': True,
        'message': _('已將「%(role)s」指派給 %(user)s', role=role.name, user=user.display_name),
    })


@account_roles_bp.route('/api/revoke', methods=['POST'])
@csrf.exempt
def revoke_role():
    """移除用戶的角色"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': _('缺少請求資料')}), 400

    user_sc = data.get('user_secure_code')
    role_sc = data.get('role_secure_code')

    if not user_sc or not role_sc:
        return jsonify({'success': False, 'error': _('缺少必要參數')}), 400

    org_sc = current_user.org_secure_code

    assignment = UserRoleAssignment.query.filter(
        UserRoleAssignment.user_secure_code == user_sc,
        UserRoleAssignment.role_secure_code == role_sc,
        UserRoleAssignment.org_secure_code == org_sc,
        UserRoleAssignment.is_deleted == False,
    ).first()

    if not assignment:
        return jsonify({'success': False, 'error': _('找不到此角色指派')}), 404

    role = Role.query.filter_by(secure_code=role_sc).first()
    user = User.query.filter_by(secure_code=user_sc).first()

    assignment.is_deleted = True
    assignment.deleted_at = datetime.utcnow()
    db.session.commit()

    role_name = role.name if role else role_sc
    user_name = user.display_name if user else user_sc
    logger.info(f"Role revoked: {user_name} -x- {role_name} by {current_user.display_name}")

    return jsonify({
        'success': True,
        'message': _('已移除 %(user)s 的「%(role)s」角色', user=user_name, role=role_name),
    })
