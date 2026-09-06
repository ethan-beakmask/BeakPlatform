"""
Role assignment service for Access Center.
"""
import logging
from datetime import date, datetime

from flask_babel import gettext as _
from flask_login import current_user

from .. import db
from ..models.associations import AssignmentKind, UserRoleAssignment
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
        'DEPT_HEAD': _('部門主管'),
        'DEPT_MANAGER': _('正主管'),
        'DEPT_DEPUTY': _('副主管'),
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


def ensure_role_layer_compatible(user, role):
    """
    PERM-01 層界檢查（PF-145 階段三之二，2026-09-01 起）。

    EXTERNAL 帳號只能持有 scope_type=EXTERNAL 的角色；
    內部帳號（EMPLOYEE / ORG_ADMIN / SYSTEM_ADMIN）不得持有 EXTERNAL 範圍角色。
    層界維度沿用既有的 roles.scope_type，不另建 user_type 欄位——
    ScopeType.EXTERNAL 的語意本來就是「外部人員（非雇傭關係，受限存取）」。

    在此之前任何角色都能指派給任何身分：EXTERNAL 帳號拿到內部角色後，
    角色制的模組 API（/api/ 不吃雙鑰匙 Key1）整組打得進去（PERM-03）。
    """
    is_external_user = str(user.user_type) == UserType.EXTERNAL
    is_external_role = role.scope_type == ScopeType.EXTERNAL
    if is_external_user and not is_external_role:
        raise ValueError(_(
            '無法指派「%(role)s」：外部廠商帳號只能指派外部範圍的角色',
            role=role.name,
        ))
    if is_external_role and not is_external_user:
        raise ValueError(_(
            '無法指派「%(role)s」：外部範圍角色只能指派給外部廠商帳號',
            role=role.name,
        ))


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
        'assignable_roles_for_grant': _list_assignable_roles(org_sc, kind='proxy'),
        'units': _list_units(org_sc),
    }


def assign_role(
    org_sc,
    user_sc,
    role_sc,
    unit_sc=None,
    *,
    kind='regular',
    acting_for_sc=None,
    valid_from=None,
    valid_until=None,
    allowed_form_templates=None,
    grant_reason=None,
    operator=None,
    source_ref=None,
):
    """Assign a role to a user with tenant, duplicate, and exclusivity checks."""
    if operator is None:
        operator = current_user._get_current_object()
    operator_sc = getattr(operator, 'secure_code', None)
    if not operator_sc:
        raise ValueError(_('缺少操作者資訊'))

    kind = (kind or AssignmentKind.REGULAR).strip()
    if kind not in AssignmentKind.ALL:
        raise ValueError(_('無效的指派性質'))

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

    ensure_role_layer_compatible(user, role)

    unit_sc = (unit_sc or '').strip() or None
    _validate_unit_scope(org_sc, role, unit_sc)
    _assert_can_grant(operator, org_sc, role, unit_sc, kind)

    valid_from = _parse_date(valid_from, 'valid_from')
    valid_until = _parse_date(valid_until, 'valid_until')
    normalized_templates = _normalize_allowed_form_templates(allowed_form_templates)
    reason = (grant_reason or '').strip() or None
    source_ref = source_ref or f'admin:{operator_sc}'
    acting_for_sc = (acting_for_sc or '').strip() or None

    dup_query = UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org_sc,
        UserRoleAssignment.user_secure_code == user_sc,
        UserRoleAssignment.role_secure_code == role_sc,
        UserRoleAssignment.assignment_kind == kind,
        UserRoleAssignment.is_deleted == False,
    )
    if unit_sc:
        dup_query = dup_query.filter(UserRoleAssignment.unit_secure_code == unit_sc)
    else:
        dup_query = dup_query.filter(UserRoleAssignment.unit_secure_code.is_(None))

    if kind == AssignmentKind.REGULAR:
        if dup_query.first():
            raise ValueError(_('用戶已擁有「%(role)s」角色', role=role.name))
        _check_exclusive_group(org_sc, user_sc, role, unit_sc)
        valid_from = None
        valid_until = None
        normalized_templates = None
        acting_for_sc = None
        reason = None
    elif kind == AssignmentKind.PROXY:
        if not acting_for_sc:
            raise ValueError(_('代理指派必須選擇被代理人'))
        if acting_for_sc == user_sc:
            raise ValueError(_('代理人不可代理自己'))
        if not valid_from or not valid_until:
            raise ValueError(_('代理指派必須設定起迄日'))
        if valid_from > valid_until:
            raise ValueError(_('起始日不可晚於結束日'))
        if not reason:
            raise ValueError(_('請填寫指派事由'))
        _assert_regular_holder(org_sc, role_sc, unit_sc, acting_for_sc, _('被代理人必須是此角色的正式持有者'))
        dup_query = dup_query.filter(UserRoleAssignment.acting_for_user_secure_code == acting_for_sc)
        dup_query = _filter_overlapping(dup_query, valid_from, valid_until)
        if dup_query.first():
            raise ValueError(_('已有重疊效期的代理指派'))
    else:
        if valid_from and valid_until and valid_from > valid_until:
            raise ValueError(_('起始日不可晚於結束日'))
        if not reason:
            raise ValueError(_('請填寫指派事由'))
        if acting_for_sc:
            if acting_for_sc == user_sc:
                raise ValueError(_('代理人不可代理自己'))
            _assert_regular_holder(org_sc, role_sc, unit_sc, acting_for_sc, _('被代理人必須是此角色的正式持有者'))
        if dup_query.first():
            raise ValueError(_('已是此角色的候補'))

    assignment = UserRoleAssignment(
        org_secure_code=org_sc,
        user_secure_code=user_sc,
        role_secure_code=role_sc,
        unit_secure_code=unit_sc,
        valid_from=valid_from,
        valid_until=valid_until,
        assigned_by=operator_sc,
        assignment_kind=kind,
        acting_for_user_secure_code=acting_for_sc,
        allowed_form_templates=normalized_templates,
        source_ref=source_ref,
        grant_reason=reason,
    )
    db.session.add(assignment)
    db.session.commit()

    logger.info(
        "Role assigned: %s <- %s by %s",
        user.display_name,
        role.name,
        getattr(operator, 'display_name', operator_sc),
    )
    return {
        'message': _('已將「%(role)s」指派給 %(user)s', role=role.name, user=user.display_name),
        'assignment_secure_code': assignment.secure_code,
    }


def revoke_assignment(org_sc, assignment_sc):
    """Soft-delete a role assignment."""
    assignment = UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org_sc,
        UserRoleAssignment.secure_code == assignment_sc,
        UserRoleAssignment.is_deleted == False,
    ).first()

    if not assignment:
        raise ValueError(_('找不到此角色指派'))

    role = Role.query.filter(
        Role.secure_code == assignment.role_secure_code,
        Role.org_secure_code == org_sc,
    ).first()
    user = User.query.filter(
        User.secure_code == assignment.user_secure_code,
        User.org_secure_code == org_sc,
    ).first()

    assignment.is_deleted = True
    assignment.deleted_at = datetime.utcnow()
    db.session.commit()

    role_name = role.name if role else assignment.role_secure_code
    user_name = user.display_name if user else assignment.user_secure_code
    logger.info("Role revoked: %s -x- %s by %s", user_name, role_name, _current_actor_label())
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
        Role.code.in_(['DEPT_HEAD', 'DEPT_MANAGER', 'DEPT_DEPUTY']),
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
                key = (assignment.user_secure_code, assignment.unit_secure_code)
                current = user_unit_role.get(key)
                if role_code in ('DEPT_MANAGER', 'DEPT_DEPUTY') or not current:
                    user_unit_role[key] = label

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
    today = _org_today(org_sc)
    acting_for_codes = {a.acting_for_user_secure_code for a in assignments if a.acting_for_user_secure_code}
    acting_for_map = {}
    if acting_for_codes:
        acting_for_users = User.query.filter(
            User.org_secure_code == org_sc,
            User.secure_code.in_(acting_for_codes),
            User.is_deleted == False,
        ).all()
        acting_for_map = {user.secure_code: user.display_name for user in acting_for_users}

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
            'assignment_kind': assignment.assignment_kind or AssignmentKind.REGULAR,
            'valid_from': assignment.valid_from.isoformat() if assignment.valid_from else None,
            'valid_until': assignment.valid_until.isoformat() if assignment.valid_until else None,
            'acting_for_secure_code': assignment.acting_for_user_secure_code,
            'acting_for_name': acting_for_map.get(assignment.acting_for_user_secure_code, ''),
            'allowed_form_templates_count': (
                len(assignment.allowed_form_templates)
                if isinstance(assignment.allowed_form_templates, list)
                else 0
            ),
            'is_valid': assignment.is_valid_on(today),
        })

    kind_order = {
        AssignmentKind.REGULAR: 0,
        AssignmentKind.PROXY: 1,
        AssignmentKind.STANDBY: 2,
    }
    for roles_list in user_roles.values():
        roles_list.sort(key=lambda r: (
            r['is_system_role'],
            r['name'],
            r['unit_name'],
            kind_order.get(r['assignment_kind'], 99),
        ))
    return user_roles


def _list_assignable_roles(org_sc, kind='regular'):
    scopes = [ScopeType.GLOBAL, ScopeType.EXTERNAL]
    if kind in (AssignmentKind.PROXY, AssignmentKind.STANDBY):
        scopes = [ScopeType.GLOBAL, ScopeType.EXTERNAL, ScopeType.DEPARTMENT, ScopeType.GROUP]
    roles = Role.query.filter(
        Role.org_secure_code == org_sc,
        Role.is_deleted == False,
        Role.is_active == True,
        Role.scope_type.in_(scopes),
        ~Role.code.in_(['DEPT_PROXY1', 'DEPT_PROXY2']),
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
        UserRoleAssignment.assignment_kind == AssignmentKind.REGULAR,
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


def _org_today(org_sc):
    from .unit_resolver import org_local_today
    return org_local_today(org_sc)


def _parse_date(value, field_name):
    if value in (None, ''):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(_('日期格式不正確')) from exc
    raise ValueError(_('%(field)s 日期格式不正確', field=field_name))


def _normalize_allowed_form_templates(value):
    if value in (None, ''):
        return None
    if not isinstance(value, list):
        raise ValueError(_('限定表單格式不正確'))
    normalized = []
    seen = set()
    for item in value:
        item = str(item).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized or None


def _assert_regular_holder(org_sc, role_sc, unit_sc, user_sc, message):
    from .unit_resolver import resolve_role_holders
    holders = resolve_role_holders(
        role_sc,
        org_sc,
        unit_sc,
        kinds=(AssignmentKind.REGULAR,),
    )
    if user_sc not in holders:
        raise ValueError(message)


def _assert_can_grant(operator, org_sc, role, unit_sc, kind):
    user_type = str(getattr(operator, 'user_type', '') or '')
    if user_type in (UserType.ORG_ADMIN, UserType.SYSTEM_ADMIN):
        return
    if getattr(operator, 'org_secure_code', None) != org_sc:
        raise ValueError(_('無權限指派此角色'))
    if kind == AssignmentKind.REGULAR:
        raise ValueError(_('只有企業管理員可以指派正式角色'))
    _assert_regular_holder(
        org_sc,
        role.secure_code,
        unit_sc,
        operator.secure_code,
        _('只有此角色的正式持有者可以授出代理或候補'),
    )


def _filter_overlapping(query, valid_from, valid_until):
    return query.filter(
        db.or_(
            UserRoleAssignment.valid_until.is_(None),
            UserRoleAssignment.valid_until >= valid_from,
        ),
        db.or_(
            UserRoleAssignment.valid_from.is_(None),
            UserRoleAssignment.valid_from <= valid_until,
        ),
    )


def _current_actor_label():
    try:
        return getattr(current_user, 'display_name', None) or 'system'
    except RuntimeError:
        return 'system'
