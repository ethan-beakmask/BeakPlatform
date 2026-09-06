"""Self-service proxy assignment helpers.

代理指派只代理職務角色，不代理 user_type 對應的層界身分角色。EMPLOYEE
雙方通常都有，代理它是雜訊；ORG_ADMIN 若被代理會把管理員選單與權限整包交給代理人，
比舊 FULL delegation 的簽核語意更寬。
"""
from datetime import date

from flask_babel import gettext as _

from app import db
from app.models import Organization, Role, User
from app.models.associations import AssignmentKind, UserRoleAssignment
from app.models.organizational_unit import OrganizationalUnit
from app.models.user import UserType
from app.services import role_assignment_service

IDENTITY_ROLE_CODES = ('SYSTEM_ADMIN', 'ORG_ADMIN', 'EMPLOYEE', 'EXTERNAL_USERS')


def _org_today(org_sc: str) -> date:
    org = Organization.query.filter(
        Organization.secure_code == org_sc,
        Organization.is_deleted == False,  # noqa: E712
    ).first()
    if not org:
        raise ValueError(_('企業不存在'))
    return org.local_today()


def proxyable_regular_assignments(org_sc, user_sc, today) -> list[UserRoleAssignment]:
    """本人今天有效、可代理出去的 regular 角色指派。"""
    rows = UserRoleAssignment.query.join(
        Role,
        db.and_(
            Role.secure_code == UserRoleAssignment.role_secure_code,
            Role.org_secure_code == org_sc,
            Role.is_deleted == False,  # noqa: E712
            ~Role.code.in_(IDENTITY_ROLE_CODES),
        ),
    ).outerjoin(
        OrganizationalUnit,
        db.and_(
            OrganizationalUnit.secure_code == UserRoleAssignment.unit_secure_code,
            OrganizationalUnit.org_secure_code == org_sc,
            OrganizationalUnit.is_deleted == False,  # noqa: E712
        ),
    ).filter(
        UserRoleAssignment.org_secure_code == org_sc,
        UserRoleAssignment.user_secure_code == user_sc,
        UserRoleAssignment.assignment_kind == AssignmentKind.REGULAR,
        UserRoleAssignment.is_deleted == False,  # noqa: E712
    ).order_by(
        Role.name.asc(),
        OrganizationalUnit.name.asc().nullsfirst(),
        UserRoleAssignment.id.asc(),
    ).all()
    return [row for row in rows if row.is_valid_on(today)]


def list_proxy_assignments(org_sc, user_sc) -> dict:
    today = _org_today(org_sc)
    rows = UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org_sc,
        UserRoleAssignment.assignment_kind == AssignmentKind.PROXY,
        UserRoleAssignment.is_deleted == False,  # noqa: E712
        db.or_(
            UserRoleAssignment.acting_for_user_secure_code == user_sc,
            UserRoleAssignment.user_secure_code == user_sc,
        ),
    ).all()

    role_map = _role_map(org_sc, {row.role_secure_code for row in rows})
    unit_map = _unit_map(org_sc, {row.unit_secure_code for row in rows if row.unit_secure_code})
    counterpart_codes = set()
    for row in rows:
        if row.acting_for_user_secure_code == user_sc:
            counterpart_codes.add(row.user_secure_code)
        if row.user_secure_code == user_sc:
            counterpart_codes.add(row.acting_for_user_secure_code)
    user_map = _user_map(org_sc, counterpart_codes)

    given = []
    received = []
    for row in rows:
        if row.acting_for_user_secure_code == user_sc:
            given.append(_assignment_payload(row, role_map, unit_map, user_map.get(row.user_secure_code), today))
        if row.user_secure_code == user_sc:
            received.append(_assignment_payload(
                row, role_map, unit_map, user_map.get(row.acting_for_user_secure_code), today))

    given.sort(key=_sort_key)
    received.sort(key=_sort_key)
    return {'given': given, 'received': received, 'today': today.isoformat()}


def create_full_proxy(org_sc, operator_user, delegate_sc, valid_from, valid_until, reason) -> dict:
    operator_sc = operator_user.secure_code
    if delegate_sc == operator_sc:
        raise ValueError(_('代理人不可代理自己'))
    delegate = User.query.filter(
        User.org_secure_code == org_sc,
        User.secure_code == delegate_sc,
        User.is_deleted == False,  # noqa: E712
        User.is_active == True,  # noqa: E712
    ).first()
    if not delegate or delegate.user_type not in (UserType.EMPLOYEE, UserType.ORG_ADMIN):
        raise ValueError(_('代理人無效'))

    today = _org_today(org_sc)
    sources = proxyable_regular_assignments(org_sc, operator_sc, today)
    if not sources:
        raise ValueError(_('你目前沒有可代理的角色'))

    created = 0
    skipped = 0
    assignment_scs = []
    try:
        for source in sources:
            overlap = UserRoleAssignment.query.filter(
                UserRoleAssignment.org_secure_code == org_sc,
                UserRoleAssignment.user_secure_code == delegate_sc,
                UserRoleAssignment.role_secure_code == source.role_secure_code,
                UserRoleAssignment.assignment_kind == AssignmentKind.PROXY,
                UserRoleAssignment.acting_for_user_secure_code == operator_sc,
                UserRoleAssignment.is_deleted == False,  # noqa: E712
            )
            if source.unit_secure_code:
                overlap = overlap.filter(UserRoleAssignment.unit_secure_code == source.unit_secure_code)
            else:
                overlap = overlap.filter(UserRoleAssignment.unit_secure_code.is_(None))
            if role_assignment_service.filter_overlapping(overlap, valid_from, valid_until).first():
                skipped += 1
                continue

            result = role_assignment_service.assign_role(
                org_sc,
                delegate_sc,
                source.role_secure_code,
                source.unit_secure_code,
                kind=AssignmentKind.PROXY,
                acting_for_sc=operator_sc,
                valid_from=valid_from,
                valid_until=valid_until,
                grant_reason=reason,
                operator=operator_user,
                source_ref=f'self:{operator_sc}',
                commit=False,
            )
            created += 1
            assignment_scs.append(result['assignment_secure_code'])
        if created == 0:
            db.session.rollback()
            raise ValueError(_('這位代理人在這段期間已經代理你全部的角色'))
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return {'created': created, 'skipped': skipped, 'assignment_secure_codes': assignment_scs}


def revoke_own_proxy(org_sc, user_sc, assignment_sc) -> dict:
    row = UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org_sc,
        UserRoleAssignment.secure_code == assignment_sc,
        UserRoleAssignment.assignment_kind == AssignmentKind.PROXY,
        UserRoleAssignment.is_deleted == False,  # noqa: E712
        db.or_(
            UserRoleAssignment.acting_for_user_secure_code == user_sc,
            UserRoleAssignment.user_secure_code == user_sc,
        ),
    ).first()
    if not row:
        raise LookupError(assignment_sc)
    return role_assignment_service.revoke_assignment(org_sc, assignment_sc)


def has_covering_proxy(org_sc, user_sc, start_date, end_date) -> bool:
    sources = UserRoleAssignment.query.join(
        Role,
        db.and_(
            Role.secure_code == UserRoleAssignment.role_secure_code,
            Role.org_secure_code == org_sc,
            Role.is_deleted == False,  # noqa: E712
            ~Role.code.in_(IDENTITY_ROLE_CODES),
        ),
    ).filter(
        UserRoleAssignment.org_secure_code == org_sc,
        UserRoleAssignment.user_secure_code == user_sc,
        UserRoleAssignment.assignment_kind == AssignmentKind.REGULAR,
        UserRoleAssignment.is_deleted == False,  # noqa: E712
        db.or_(UserRoleAssignment.valid_from.is_(None), UserRoleAssignment.valid_from <= end_date),
        db.or_(UserRoleAssignment.valid_until.is_(None), UserRoleAssignment.valid_until >= start_date),
    ).all()
    if not sources:
        return False

    for source in sources:
        query = UserRoleAssignment.query.filter(
            UserRoleAssignment.org_secure_code == org_sc,
            UserRoleAssignment.role_secure_code == source.role_secure_code,
            UserRoleAssignment.assignment_kind == AssignmentKind.PROXY,
            UserRoleAssignment.acting_for_user_secure_code == user_sc,
            UserRoleAssignment.is_deleted == False,  # noqa: E712
            UserRoleAssignment.valid_from <= start_date,
            UserRoleAssignment.valid_until >= end_date,
        )
        if source.unit_secure_code:
            query = query.filter(UserRoleAssignment.unit_secure_code == source.unit_secure_code)
        else:
            query = query.filter(UserRoleAssignment.unit_secure_code.is_(None))
        if not query.first():
            return False
    return True


def _assignment_payload(row, role_map, unit_map, counterpart, today) -> dict:
    role = role_map.get(row.role_secure_code)
    return {
        'assignment_secure_code': row.secure_code,
        'role_secure_code': row.role_secure_code,
        'role_name': role.name if role else row.role_secure_code,
        'role_code': role.code if role else '',
        'unit_secure_code': row.unit_secure_code,
        'unit_name': unit_map.get(row.unit_secure_code, ''),
        'counterpart': {
            'secure_code': counterpart.secure_code if counterpart else '',
            'display_name': _display_name(counterpart) if counterpart else '',
        },
        'valid_from': row.valid_from.isoformat() if row.valid_from else None,
        'valid_until': row.valid_until.isoformat() if row.valid_until else None,
        'status': _status(row, today),
        'grant_reason': row.grant_reason or '',
        'allowed_form_templates_count': (
            len(row.allowed_form_templates) if isinstance(row.allowed_form_templates, list) else 0
        ),
        'source_ref': row.source_ref or '',
        'can_revoke': True,
    }


def _status(row, today) -> str:
    if row.valid_from and today < row.valid_from:
        return 'PENDING'
    if row.valid_until and today > row.valid_until:
        return 'EXPIRED'
    return 'ACTIVE'


def _sort_key(item):
    status_order = {'ACTIVE': 0, 'PENDING': 1, 'EXPIRED': 2}
    return (
        status_order.get(item.get('status'), 99),
        item.get('valid_from') or '',
        item.get('role_name') or '',
    )


def _role_map(org_sc, role_scs) -> dict:
    if not role_scs:
        return {}
    roles = Role.query.filter(
        Role.org_secure_code == org_sc,
        Role.secure_code.in_(role_scs),
        Role.is_deleted == False,  # noqa: E712
    ).all()
    return {role.secure_code: role for role in roles}


def _unit_map(org_sc, unit_scs) -> dict:
    if not unit_scs:
        return {}
    units = OrganizationalUnit.query.filter(
        OrganizationalUnit.org_secure_code == org_sc,
        OrganizationalUnit.secure_code.in_(unit_scs),
        OrganizationalUnit.is_deleted == False,  # noqa: E712
    ).all()
    return {unit.secure_code: unit.name for unit in units}


def _user_map(org_sc, user_scs) -> dict:
    if not user_scs:
        return {}
    users = User.query.filter(
        User.org_secure_code == org_sc,
        User.secure_code.in_(user_scs),
        User.is_deleted == False,  # noqa: E712
    ).all()
    return {user.secure_code: user for user in users}


def _display_name(user) -> str:
    return user.display_name or user.username or user.secure_code
