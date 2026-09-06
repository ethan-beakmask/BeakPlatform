from datetime import date, datetime, timedelta
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db  # noqa: E402
from app.models import (  # noqa: E402
    AssignmentKind,
    OrganizationalUnit,
    Role,
    RoleType,
    ScheduleAdjustment,
    UnitType,
    User,
    UserRoleAssignment,
    UserType,
)
from app.services.role_holding_service import (  # noqa: E402
    effective_holders,
    has_available_holder,
    holds,
)


def _user(sc, org, username, active=True):
    user = User(
        secure_code=sc,
        org_secure_code=org.secure_code,
        username=username,
        email=f'{username}@example.com',
        display_name=username,
        user_type=UserType.EMPLOYEE,
        is_active=active,
        is_deleted=False,
    )
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()
    return user


def _role(org, code, role_type=RoleType.ROLE):
    role = Role(
        org_secure_code=org.secure_code,
        code=code,
        name=code,
        role_type=role_type,
        scope_type='DEPARTMENT',
        is_active=True,
        is_deleted=False,
    )
    db.session.add(role)
    db.session.commit()
    return role


def _unit(org, code, name, parent=None):
    unit = OrganizationalUnit(
        org_secure_code=org.secure_code,
        code=code,
        name=name,
        unit_type=UnitType.DEPARTMENT,
        parent_secure_code=parent.secure_code if parent else None,
        level=(parent.level + 1) if parent else 1,
        full_path=f'{parent.full_path}/{name}' if parent else f'/{name}',
        is_active=True,
        is_deleted=False,
    )
    db.session.add(unit)
    db.session.commit()
    return unit


def _assign(user, role, unit=None, *, kind='regular', valid_from=None, valid_until=None):
    row = UserRoleAssignment(
        org_secure_code=user.org_secure_code,
        user_secure_code=user.secure_code,
        role_secure_code=role.secure_code,
        unit_secure_code=unit.secure_code if unit else None,
        assignment_kind=kind,
        valid_from=valid_from,
        valid_until=valid_until,
        is_deleted=False,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _leave(user, adjust_date, adjusted_periods, original_periods=None):
    row = ScheduleAdjustment(
        org_secure_code=user.org_secure_code,
        user_secure_code=user.secure_code,
        adjust_date=adjust_date,
        adjust_type='LEAVE',
        original_periods=original_periods,
        adjusted_periods=adjusted_periods,
        status='APPROVED',
        is_deleted=False,
    )
    db.session.add(row)
    db.session.commit()
    return row


def test_has_available_holder_checks_user_status_validity_leave_and_global(test_org):
    role = _role(test_org, 'RHS_MANAGER', RoleType.POSITION)
    unit = _unit(test_org, 'RHS_U', 'RHS Unit')
    today = date(2026, 9, 5)
    local_now = datetime(2026, 9, 5, 14, 0)
    user = _user('rhs_available_user', test_org, 'rhsavailable')
    assignment = _assign(user, role, unit)

    assert has_available_holder(role.secure_code, test_org.secure_code, unit.secure_code, today=today, local_now=local_now) is True

    user.is_active = False
    db.session.commit()
    assert has_available_holder(role.secure_code, test_org.secure_code, unit.secure_code, today=today, local_now=local_now) is False

    user.is_active = True
    assignment.valid_until = today - timedelta(days=1)
    db.session.commit()
    assert has_available_holder(role.secure_code, test_org.secure_code, unit.secure_code, today=today, local_now=local_now) is False

    assignment.valid_until = None
    _leave(user, today, [])
    db.session.commit()
    assert has_available_holder(role.secure_code, test_org.secure_code, unit.secure_code, today=today, local_now=local_now) is False

    ScheduleAdjustment.query.filter_by(user_secure_code=user.secure_code).delete()
    _leave(user, today, ['09:00-12:00'], ['09:00-12:00', '13:00-18:00'])
    db.session.commit()
    assert has_available_holder(role.secure_code, test_org.secure_code, unit.secure_code, today=today, local_now=local_now) is False
    assert has_available_holder(
        role.secure_code,
        test_org.secure_code,
        unit.secure_code,
        today=today,
        local_now=datetime(2026, 9, 5, 10, 0),
    ) is True

    assignment.unit_secure_code = None
    ScheduleAdjustment.query.filter_by(user_secure_code=user.secure_code).delete()
    db.session.commit()
    assert has_available_holder(role.secure_code, test_org.secure_code, unit.secure_code, today=today, local_now=local_now) is True
    assert has_available_holder(role.secure_code, test_org.secure_code, None, today=today, local_now=local_now) is True


def test_effective_holders_regular_proxy_standby_descendants_sort_and_dedupe(test_org):
    role = _role(test_org, 'RHS_MEMBER', RoleType.ROLE)
    root = _unit(test_org, 'RHS_ROOT', 'RHS Root')
    child = _unit(test_org, 'RHS_CHILD', 'RHS Child', root)
    regular = _user('rhs_eff_regular', test_org, 'rhseffregular')
    proxy = _user('rhs_eff_proxy', test_org, 'rhseffproxy')
    standby = _user('rhs_eff_standby', test_org, 'rhseffstandby')
    duplicate = _user('rhs_eff_dup', test_org, 'rhseffdup')
    today = date(2026, 9, 5)
    local_now = datetime(2026, 9, 5, 14, 0)
    _assign(regular, role, root)
    _assign(proxy, role, root, kind='proxy')
    _assign(standby, role, root, kind='standby')
    _assign(duplicate, role, child)
    _assign(duplicate, role, root, kind='proxy')

    assert effective_holders(
        role.secure_code, test_org.secure_code, root.secure_code,
        today=today, local_now=local_now,
    ) == [regular.secure_code, proxy.secure_code, duplicate.secure_code]

    UserRoleAssignment.query.filter(
        UserRoleAssignment.role_secure_code == role.secure_code,
        UserRoleAssignment.assignment_kind.in_(AssignmentKind.HOLDING),
    ).update({'is_deleted': True})
    db.session.commit()
    assert effective_holders(
        role.secure_code, test_org.secure_code, root.secure_code,
        include_descendant_units=True, today=today, local_now=local_now,
    ) == [standby.secure_code]


def test_effective_holders_descendant_regular_proxy_but_not_standby(test_org):
    role = _role(test_org, 'RHS_DESC_ROLE', RoleType.ROLE)
    root = _unit(test_org, 'RHS_DESC_ROOT', 'RHS Desc Root')
    child = _unit(test_org, 'RHS_DESC_CHILD', 'RHS Desc Child', root)
    proxy = _user('rhs_desc_proxy', test_org, 'rhsdescproxy')
    standby = _user('rhs_desc_standby', test_org, 'rhsdescstandby')
    _assign(proxy, role, child, kind='proxy')
    _assign(standby, role, child, kind='standby')

    assert effective_holders(
        role.secure_code,
        test_org.secure_code,
        root.secure_code,
        include_descendant_units=True,
        today=date(2026, 9, 5),
        local_now=datetime(2026, 9, 5, 14, 0),
    ) == [proxy.secure_code]


def test_holds_priority_scope_lazy_and_fail_closed():
    calls = {'count': 0}

    def form_template():
        calls['count'] += 1
        return 'A'

    assignments = [
        {'role_sc': 'R', 'unit_sc': 'U', 'kind': 'regular', 'scope': None, 'acting_for': None},
        {'role_sc': 'R', 'unit_sc': 'U', 'kind': 'proxy', 'scope': {'A'}, 'acting_for': 'boss'},
    ]
    assert holds(
        assignments, 'R', 'U',
        is_position=False,
        ancestors_of=lambda u: [],
        is_available=lambda r, u: False,
        form_template_sc_of=form_template,
    ) == ('regular', None)
    assert calls['count'] == 0

    assert holds(
        [{'role_sc': 'R', 'unit_sc': 'U', 'kind': 'proxy', 'scope': set(), 'acting_for': 'boss'}],
        'R', 'U',
        is_position=False,
        ancestors_of=lambda u: [],
        is_available=lambda r, u: False,
        form_template_sc_of=form_template,
    ) is None
    assert calls['count'] == 1


def test_holds_standby_and_position_do_not_bubble_but_null_unit_matches():
    standby = [{'role_sc': 'R', 'unit_sc': 'CHILD', 'kind': 'standby', 'scope': None, 'acting_for': None}]
    assert holds(
        standby, 'R', 'ROOT',
        is_position=False,
        ancestors_of=lambda u: ['ROOT'],
        is_available=lambda r, u: False,
        form_template_sc_of=lambda: None,
    ) is None
    assert holds(
        standby, 'R', None,
        is_position=False,
        ancestors_of=lambda u: [],
        is_available=lambda r, u: False,
        form_template_sc_of=lambda: None,
    ) == ('standby', None)

    proxy = [{'role_sc': 'R', 'unit_sc': 'CHILD', 'kind': 'proxy', 'scope': None, 'acting_for': 'boss'}]
    assert holds(
        proxy, 'R', 'ROOT',
        is_position=True,
        ancestors_of=lambda u: ['ROOT'],
        is_available=lambda r, u: False,
        form_template_sc_of=lambda: None,
    ) is None
    assert holds(
        proxy, 'R', 'ROOT',
        is_position=False,
        ancestors_of=lambda u: ['ROOT'],
        is_available=lambda r, u: False,
        form_template_sc_of=lambda: None,
    ) == ('proxy', 'boss')
