"""
Role assignment service for Access Center.
"""
import logging
from datetime import datetime

from flask_babel import gettext as _
from flask_login import current_user

from .. import db
from ..models.associations import UserRoleAssignment
from ..models.organizational_unit import OrganizationalUnit, UnitType
from ..models.role import ExclusiveGroup, Role, ScopeType
from ..models.user import User, UserType
from ..models.user_unit_membership import (
    MembershipRole,
    MembershipType,
    UserUnitMembership,
)

logger = logging.getLogger(__name__)


def _membership_role_labels():
    return {
        MembershipRole.MANAGER: _('團長'),
        MembershipRole.DEPUTY: _('副團長'),
        MembershipRole.PROXY1: _('代理人(一)'),
        MembershipRole.PROXY2: _('代理人(二)'),
        MembershipRole.MEMBER: _('團員'),
        None: _('團員'),
    }


def _dept_role_labels():
    return {
        'DEPT_MANAGER': _('主管'),
        'DEPT_DEPUTY': _('副主管'),
        'DEPT_PROXY1': _('代理人(一)'),
        'DEPT_PROXY2': _('代理人(二)'),
    }


def _cross_role_labels():
    return {
        MembershipRole.MANAGER: _('代理'),
        MembershipRole.DEPUTY: _('代理'),
        MembershipRole.PROXY1: _('代理'),
        MembershipRole.PROXY2: _('代理'),
        MembershipRole.MEMBER: _('員工'),
    }


def _user_type_labels():
    return {
        UserType.ORG_ADMIN: _('企業管理員'),
        UserType.EMPLOYEE: _('企業成員'),
        UserType.EXTERNAL: _('外部廠商'),
        UserType.SYSTEM_ADMIN: _('系統管理員'),
    }


def list_account_roles(org_sc, account_type=None, keyword=None, page=1, per_page=50):
    """Return account role overview data for one organization."""
    page = max(int(page or 1), 1)
    per_page = min(max(int(per_page or 50), 1), 100)
    keyword = (keyword or '').strip()
    account_type = (account_type or '').strip()

    query = User.query.filter(
        User.org_secure_code == org_sc,
        User.is_deleted == False,
        User.user_type != UserType.SYSTEM_ADMIN,
    )

    if account_type:
        query = query.filter(User.user_type == account_type)

    if keyword:
        like_keyword = f'%{keyword}%'
        query = query.filter(
            db.or_(
                User.display_name.ilike(like_keyword),
                User.username.ilike(like_keyword),
                User.email.ilike(like_keyword),
                User.employee_id.ilike(like_keyword),
            )
        )

    pagination = query.order_by(User.user_type, User.display_name).paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )
    users = pagination.items
    user_codes = [u.secure_code for u in users]

    user_depts = _build_user_departments(org_sc, user_codes)
    user_groups = _build_user_groups(org_sc, user_codes)
    user_roles = _build_user_roles(org_sc, user_codes)
    user_type_labels = _user_type_labels()

    return {
        'users': [
            {
                'secure_code': user.secure_code,
                'display_name': user.display_name,
                'email': user.email,
                'username': user.username,
                'account_type': user.user_type,
                'account_type_label': user_type_labels.get(user.user_type, user.user_type),
                'employee_id': user.employee_id or '',
                'is_active': bool(user.is_active),
                'departments': user_depts.get(user.secure_code, []),
                'groups': user_groups.get(user.secure_code, []),
                'roles': user_roles.get(user.secure_code, []),
            }
            for user in users
        ],
        'pagination': {
            'page': pagination.page,
            'per_page': pagination.per_page,
            'total': pagination.total,
            'pages': pagination.pages,
            'has_prev': pagination.has_prev,
            'has_next': pagination.has_next,
        },
        'assignable_roles': _list_assignable_roles(org_sc),
        'units': _list_units(org_sc),
    }


def assign_role(org_sc, user_sc, role_sc, unit_sc=None):
    """Assign a role to a user with tenant, duplicate, and exclusivity checks."""
    user = User.query.filter_by(
        secure_code=user_sc,
        org_secure_code=org_sc,
        is_deleted=False,
    ).first()
    if not user:
        raise ValueError(_('用戶不存在'))

    role = Role.query.filter_by(
        secure_code=role_sc,
        org_secure_code=org_sc,
        is_deleted=False,
    ).first()
    if not role:
        raise ValueError(_('角色不存在'))

    unit_sc = (unit_sc or '').strip() or None
    _validate_unit_scope(org_sc, role, unit_sc)

    dup_query = UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org_sc,
        UserRoleAssignment.user_secure_code == user_sc,
        UserRoleAssignment.role_secure_code == role_sc,
        UserRoleAssignment.is_deleted == False,
    )
    if unit_sc:
        dup_query = dup_query.filter(UserRoleAssignment.unit_secure_code == unit_sc)
    else:
        dup_query = dup_query.filter(UserRoleAssignment.unit_secure_code.is_(None))

    if dup_query.first():
        raise ValueError(_('用戶已擁有「%(role)s」角色', role=role.name))

    _check_exclusive_group(org_sc, user_sc, role, unit_sc)

    assignment = UserRoleAssignment(
        org_secure_code=org_sc,
        user_secure_code=user_sc,
        role_secure_code=role_sc,
        unit_secure_code=unit_sc,
        assigned_by=current_user.secure_code,
    )
    db.session.add(assignment)
    db.session.commit()

    logger.info(
        "Role assigned: %s <- %s by %s",
        user.display_name,
        role.name,
        current_user.display_name,
    )
    return {
        'message': _('已將「%(role)s」指派給 %(user)s', role=role.name, user=user.display_name)
    }


def revoke_assignment(org_sc, user_sc, role_sc):
    """Soft-delete a role assignment."""
    assignment = UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org_sc,
        UserRoleAssignment.user_secure_code == user_sc,
        UserRoleAssignment.role_secure_code == role_sc,
        UserRoleAssignment.is_deleted == False,
    ).first()

    if not assignment:
        raise ValueError(_('找不到此角色指派'))

    role = Role.query.filter(
        Role.secure_code == role_sc,
        Role.org_secure_code == org_sc,
    ).first()
    user = User.query.filter(
        User.secure_code == user_sc,
        User.org_secure_code == org_sc,
    ).first()

    assignment.is_deleted = True
    assignment.deleted_at = datetime.utcnow()
    db.session.commit()

    role_name = role.name if role else role_sc
    user_name = user.display_name if user else user_sc
    logger.info("Role revoked: %s -x- %s by %s", user_name, role_name, current_user.display_name)
    return {
        'message': _('已移除 %(user)s 的「%(role)s」角色', user=user_name, role=role_name)
    }


def _build_user_departments(org_sc, user_codes):
    dept_memberships = []
    if user_codes:
        dept_memberships = UserUnitMembership.query.filter(
            UserUnitMembership.org_secure_code == org_sc,
            UserUnitMembership.user_secure_code.in_(user_codes),
            UserUnitMembership.membership_type.in_([MembershipType.SOLID, MembershipType.DOTTED]),
            UserUnitMembership.is_deleted == False,
        ).all()

    dept_unit_map = _unit_name_map(org_sc, {m.unit_secure_code for m in dept_memberships})

    dept_roles = Role.query.filter(
        Role.org_secure_code == org_sc,
        Role.code.in_(['DEPT_MANAGER', 'DEPT_DEPUTY', 'DEPT_PROXY1', 'DEPT_PROXY2']),
        Role.is_deleted == False,
    ).all()
    dept_role_sc_map = {r.secure_code: r.code for r in dept_roles}

    dept_role_assignments = []
    if user_codes and dept_role_sc_map:
        dept_role_assignments = UserRoleAssignment.query.filter(
            UserRoleAssignment.org_secure_code == org_sc,
            UserRoleAssignment.user_secure_code.in_(user_codes),
            UserRoleAssignment.role_secure_code.in_(dept_role_sc_map.keys()),
            UserRoleAssignment.is_deleted == False,
        ).all()

    user_unit_role = {}
    dept_role_labels = _dept_role_labels()
    for assignment in dept_role_assignments:
        if assignment.unit_secure_code:
            role_code = dept_role_sc_map.get(assignment.role_secure_code, '')
            label = dept_role_labels.get(role_code, '')
            if label:
                user_unit_role[(assignment.user_secure_code, assignment.unit_secure_code)] = label

    user_depts = {}
    cross_role_labels = _cross_role_labels()
    for membership in dept_memberships:
        dept_name = dept_unit_map.get(membership.unit_secure_code)
        if not dept_name:
            continue
        is_cross = membership.membership_type == MembershipType.DOTTED
        role_label = (
            cross_role_labels.get(membership.role_type, _('員工'))
            if is_cross
            else user_unit_role.get((membership.user_secure_code, membership.unit_secure_code), _('員工'))
        )
        user_depts.setdefault(membership.user_secure_code, []).append({
            'secure_code': membership.unit_secure_code,
            'name': dept_name,
            'role': role_label,
            'is_cross': is_cross,
        })

    for depts in user_depts.values():
        depts.sort(key=lambda d: (d['is_cross'], d['name']))
    return user_depts


def _build_user_groups(org_sc, user_codes):
    memberships = []
    if user_codes:
        memberships = UserUnitMembership.query.filter(
            UserUnitMembership.org_secure_code == org_sc,
            UserUnitMembership.user_secure_code.in_(user_codes),
            UserUnitMembership.membership_type == MembershipType.MEMBER,
            UserUnitMembership.is_deleted == False,
        ).all()

    unit_map = _unit_name_map(org_sc, {m.unit_secure_code for m in memberships})
    user_groups = {}
    membership_role_labels = _membership_role_labels()
    for membership in memberships:
        group_name = unit_map.get(membership.unit_secure_code)
        if not group_name:
            continue
        user_groups.setdefault(membership.user_secure_code, []).append({
            'secure_code': membership.unit_secure_code,
            'name': group_name,
            'role': membership_role_labels.get(membership.role_type, _('團員')),
            'is_leader': membership.is_leader,
        })

    for groups in user_groups.values():
        groups.sort(key=lambda g: (not g['is_leader'], g['name']))
    return user_groups


def _build_user_roles(org_sc, user_codes):
    assignments = []
    if user_codes:
        assignments = UserRoleAssignment.query.filter(
            UserRoleAssignment.org_secure_code == org_sc,
            UserRoleAssignment.user_secure_code.in_(user_codes),
            UserRoleAssignment.is_deleted == False,
        ).all()

    role_map = {}
    role_codes = {a.role_secure_code for a in assignments}
    if role_codes:
        roles = Role.query.filter(
            Role.org_secure_code == org_sc,
            Role.secure_code.in_(role_codes),
            Role.is_deleted == False,
        ).all()
        role_map = {r.secure_code: r for r in roles}

    unit_map = _unit_name_map(org_sc, {a.unit_secure_code for a in assignments if a.unit_secure_code})

    user_roles = {}
    for assignment in assignments:
        role = role_map.get(assignment.role_secure_code)
        if not role:
            continue
        user_roles.setdefault(assignment.user_secure_code, []).append({
            'assignment_secure_code': assignment.secure_code,
            'secure_code': role.secure_code,
            'name': role.name,
            'code': role.code,
            'scope_type': role.scope_type,
            'unit_secure_code': assignment.unit_secure_code,
            'unit_name': unit_map.get(assignment.unit_secure_code, ''),
            'is_system_role': bool(role.is_system_role),
        })

    for roles_list in user_roles.values():
        roles_list.sort(key=lambda r: (r['is_system_role'], r['name'], r['unit_name']))
    return user_roles


def _list_assignable_roles(org_sc):
    roles = Role.query.filter(
        Role.org_secure_code == org_sc,
        Role.is_deleted == False,
        Role.is_active == True,
        Role.scope_type.in_([ScopeType.GLOBAL, ScopeType.EXTERNAL]),
    ).order_by(Role.is_system_role.desc(), Role.name).all()
    return [
        {
            'secure_code': role.secure_code,
            'name': role.name,
            'code': role.code,
            'scope_type': role.scope_type,
            'is_system_role': bool(role.is_system_role),
        }
        for role in roles
    ]


def _list_units(org_sc):
    units = OrganizationalUnit.query.filter(
        OrganizationalUnit.org_secure_code == org_sc,
        OrganizationalUnit.is_deleted == False,
        OrganizationalUnit.is_active == True,
    ).order_by(OrganizationalUnit.unit_type, OrganizationalUnit.sort_order, OrganizationalUnit.name).all()
    return [
        {
            'secure_code': unit.secure_code,
            'name': unit.name,
            'unit_type': unit.unit_type,
        }
        for unit in units
    ]


def _unit_name_map(org_sc, unit_codes):
    codes = [code for code in unit_codes if code]
    if not codes:
        return {}
    units = OrganizationalUnit.query.filter(
        OrganizationalUnit.org_secure_code == org_sc,
        OrganizationalUnit.secure_code.in_(codes),
        OrganizationalUnit.is_deleted == False,
    ).all()
    return {unit.secure_code: unit.name for unit in units}


def _validate_unit_scope(org_sc, role, unit_sc):
    if role.scope_type in (ScopeType.DEPARTMENT, ScopeType.GROUP):
        if not unit_sc:
            raise ValueError(_('此角色必須選擇單位'))
        expected_type = UnitType.DEPARTMENT if role.scope_type == ScopeType.DEPARTMENT else UnitType.GROUP
        unit = OrganizationalUnit.query.filter(
            OrganizationalUnit.org_secure_code == org_sc,
            OrganizationalUnit.secure_code == unit_sc,
            OrganizationalUnit.unit_type == expected_type,
            OrganizationalUnit.is_deleted == False,
        ).first()
        if not unit:
            raise ValueError(_('單位不存在或類型不符'))
        return

    if unit_sc:
        raise ValueError(_('此角色不可指定單位'))


def _check_exclusive_group(org_sc, user_sc, role, unit_sc):
    if not role.exclusive_group:
        return

    conflict_query = db.session.query(Role).join(
        UserRoleAssignment,
        UserRoleAssignment.role_secure_code == Role.secure_code,
    ).filter(
        UserRoleAssignment.org_secure_code == org_sc,
        UserRoleAssignment.user_secure_code == user_sc,
        UserRoleAssignment.is_deleted == False,
        Role.org_secure_code == org_sc,
        Role.exclusive_group == role.exclusive_group,
        Role.is_deleted == False,
    )

    if role.exclusive_group in ExclusiveGroup.UNIT_SCOPED:
        if unit_sc:
            conflict_query = conflict_query.filter(UserRoleAssignment.unit_secure_code == unit_sc)
        else:
            conflict_query = conflict_query.filter(UserRoleAssignment.unit_secure_code.is_(None))

    conflict_role = conflict_query.first()
    if conflict_role:
        raise ValueError(_(
            '無法指派「%(role)s」：與現有角色「%(conflict)s」互斥，請先移除後再指派',
            role=role.name,
            conflict=conflict_role.name,
        ))
