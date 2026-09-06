"""PF-251 第 3a 期：角色指派性質 regular／proxy／standby 的 service 規則。"""
from datetime import timedelta

import pytest

from app import db
from app.models import (
    AssignmentKind,
    ExclusiveGroup,
    OrganizationalUnit,
    Role,
    RoleType,
    ScopeType,
    UnitType,
    User,
    UserRoleAssignment,
    UserType,
)
from app.services.role_assignment_service import (
    _build_user_roles,
    _list_assignable_roles,
    assign_role,
    revoke_assignment,
)


def _user(org, sc, username, user_type=UserType.EMPLOYEE):
    user = User(
        secure_code=sc,
        org_secure_code=org.secure_code,
        username=username,
        email=f'{username}@example.com',
        display_name=username,
        user_type=user_type,
        is_active=True,
        is_deleted=False,
    )
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()
    return user


def _unit(org):
    unit = OrganizationalUnit(
        secure_code='rak_unit_0000000000001',
        org_secure_code=org.secure_code,
        code='RAK',
        name='Role Assignment Kind Dept',
        unit_type=UnitType.DEPARTMENT,
        is_active=True,
        is_deleted=False,
    )
    db.session.add(unit)
    db.session.commit()
    return unit


def _role(org, code, scope=ScopeType.GLOBAL, role_type=RoleType.ROLE, exclusive_group=None):
    role = Role(
        secure_code=f'rak_role_{code.lower()}',
        org_secure_code=org.secure_code,
        code=code,
        name=code,
        scope_type=scope,
        role_type=role_type,
        exclusive_group=exclusive_group,
        is_active=True,
        is_deleted=False,
    )
    db.session.add(role)
    db.session.commit()
    return role


def _regular(org, user, role, unit=None, valid_until=None):
    row = UserRoleAssignment(
        org_secure_code=org.secure_code,
        user_secure_code=user.secure_code,
        role_secure_code=role.secure_code,
        unit_secure_code=unit.secure_code if unit else None,
        assignment_kind=AssignmentKind.REGULAR,
        valid_until=valid_until,
        is_deleted=False,
    )
    db.session.add(row)
    db.session.commit()
    return row


def test_proxy_requires_acting_for_dates_reason_and_valid_regular_holder(test_org, test_admin):
    role = _role(test_org, 'RAK_APPROVER')
    holder = _user(test_org, 'rak_holder_00000000001', 'rakholder')
    other = _user(test_org, 'rak_other_000000000001', 'rakother')
    proxy = _user(test_org, 'rak_proxy_000000000001', 'rakproxy')
    _regular(test_org, holder, role)
    today = test_org.local_today()
    base = {
        'kind': 'proxy',
        'acting_for_sc': holder.secure_code,
        'valid_from': today.isoformat(),
        'valid_until': (today + timedelta(days=2)).isoformat(),
        'grant_reason': '出差代理',
        'operator': test_admin,
    }

    with pytest.raises(ValueError):
        assign_role(test_org.secure_code, proxy.secure_code, role.secure_code, **{**base, 'acting_for_sc': None})
    with pytest.raises(ValueError):
        assign_role(test_org.secure_code, proxy.secure_code, role.secure_code, **{**base, 'valid_from': None})
    with pytest.raises(ValueError):
        assign_role(test_org.secure_code, proxy.secure_code, role.secure_code, **{**base, 'grant_reason': '  '})
    with pytest.raises(ValueError):
        assign_role(
            test_org.secure_code, proxy.secure_code, role.secure_code,
            **{**base, 'valid_from': today.isoformat(), 'valid_until': (today - timedelta(days=1)).isoformat()}
        )
    with pytest.raises(ValueError):
        assign_role(test_org.secure_code, proxy.secure_code, role.secure_code, **{**base, 'acting_for_sc': other.secure_code})
    with pytest.raises(ValueError):
        assign_role(test_org.secure_code, proxy.secure_code, role.secure_code, **{**base, 'acting_for_sc': proxy.secure_code})


def test_proxy_success_fields_overlap_duplicate_and_revoke_by_assignment_sc(test_org, test_admin):
    role = _role(test_org, 'RAK_SIGNER')
    holder = _user(test_org, 'rak_signer_holder_0001', 'raksignerholder')
    proxy = _user(test_org, 'rak_signer_proxy_00001', 'raksignerproxy')
    _regular(test_org, holder, role)
    today = test_org.local_today()

    result = assign_role(
        test_org.secure_code,
        proxy.secure_code,
        role.secure_code,
        kind='proxy',
        acting_for_sc=holder.secure_code,
        valid_from=today,
        valid_until=today + timedelta(days=5),
        allowed_form_templates=['TPL_A', '', 'TPL_A', 'TPL_B'],
        grant_reason='代理簽核',
        operator=test_admin,
    )

    row = UserRoleAssignment.query.filter_by(secure_code=result['assignment_secure_code']).one()
    assert row.assignment_kind == AssignmentKind.PROXY
    assert row.acting_for_user_secure_code == holder.secure_code
    assert row.valid_from == today
    assert row.valid_until == today + timedelta(days=5)
    assert row.allowed_form_templates == ['TPL_A', 'TPL_B']
    assert row.grant_reason == '代理簽核'
    assert row.source_ref == f'admin:{test_admin.secure_code}'

    with pytest.raises(ValueError):
        assign_role(
            test_org.secure_code,
            proxy.secure_code,
            role.secure_code,
            kind='proxy',
            acting_for_sc=holder.secure_code,
            valid_from=today + timedelta(days=3),
            valid_until=today + timedelta(days=7),
            grant_reason='重疊',
            operator=test_admin,
        )

    revoke_assignment(test_org.secure_code, row.secure_code)
    db.session.expire_all()
    assert UserRoleAssignment.query.filter_by(secure_code=row.secure_code).one().is_deleted is True


def test_standby_duplicate_and_no_exclusive_group_check(test_org, test_admin):
    unit = _unit(test_org)
    employee_role = _role(
        test_org, 'DEPT_EMPLOYEE', ScopeType.DEPARTMENT, RoleType.ROLE, ExclusiveGroup.DEPT_POSITION
    )
    manager_role = _role(
        test_org, 'DEPT_MANAGER', ScopeType.DEPARTMENT, RoleType.POSITION, ExclusiveGroup.DEPT_POSITION
    )
    user = _user(test_org, 'rak_standby_user_0001', 'rakstandby')
    _regular(test_org, user, employee_role, unit)

    result = assign_role(
        test_org.secure_code,
        user.secure_code,
        manager_role.secure_code,
        unit_sc=unit.secure_code,
        kind='standby',
        grant_reason='候補',
        operator=test_admin,
    )
    row = UserRoleAssignment.query.filter_by(secure_code=result['assignment_secure_code']).one()
    assert row.assignment_kind == AssignmentKind.STANDBY
    assert row.acting_for_user_secure_code is None

    with pytest.raises(ValueError):
        assign_role(
            test_org.secure_code,
            user.secure_code,
            manager_role.secure_code,
            unit_sc=unit.secure_code,
            kind='standby',
            grant_reason='重複',
            operator=test_admin,
        )


def test_grant_authorizer_regular_holder_proxy_holder_and_regular_restrictions(test_org, test_admin):
    role = _role(test_org, 'RAK_GRANTABLE')
    holder = _user(test_org, 'rak_grant_holder_0001', 'rakgrantholder')
    outsider = _user(test_org, 'rak_grant_outsider01', 'rakgrantoutsider')
    proxy = _user(test_org, 'rak_grant_proxy_00001', 'rakgrantproxy')
    next_proxy = _user(test_org, 'rak_grant_next_000001', 'rakgrantnext')
    _regular(test_org, holder, role)
    today = test_org.local_today()

    with pytest.raises(ValueError):
        assign_role(
            test_org.secure_code, outsider.secure_code, role.secure_code,
            kind='proxy', acting_for_sc=holder.secure_code,
            valid_from=today, valid_until=today + timedelta(days=1),
            grant_reason='x', operator=outsider,
        )

    ok = assign_role(
        test_org.secure_code, proxy.secure_code, role.secure_code,
        kind='proxy', acting_for_sc=holder.secure_code,
        valid_from=today, valid_until=today + timedelta(days=1),
        grant_reason='x', operator=holder,
    )
    assert ok['assignment_secure_code']

    with pytest.raises(ValueError):
        assign_role(
            test_org.secure_code, next_proxy.secure_code, role.secure_code,
            kind='proxy', acting_for_sc=holder.secure_code,
            valid_from=today, valid_until=today + timedelta(days=1),
            grant_reason='x', operator=proxy,
        )
    with pytest.raises(ValueError):
        assign_role(test_org.secure_code, outsider.secure_code, role.secure_code, kind='regular', operator=holder)


def test_external_proxy_rejected_by_layer_check(test_org, test_admin):
    unit = _unit(test_org)
    role = _role(test_org, 'DEPT_REVIEWER', ScopeType.DEPARTMENT, RoleType.POSITION)
    holder = _user(test_org, 'rak_ext_holder_000001', 'rakextholder')
    external = _user(test_org, 'rak_ext_user_0000001', 'rakexternal', UserType.EXTERNAL)
    _regular(test_org, holder, role, unit)
    today = test_org.local_today()

    with pytest.raises(ValueError):
        assign_role(
            test_org.secure_code, external.secure_code, role.secure_code,
            unit_sc=unit.secure_code,
            kind='proxy', acting_for_sc=holder.secure_code,
            valid_from=today, valid_until=today + timedelta(days=1),
            grant_reason='x', operator=test_admin,
        )


def test_build_user_roles_and_proxy_assignable_role_list(test_org, test_admin):
    unit = _unit(test_org)
    global_role = _role(test_org, 'RAK_GLOBAL', ScopeType.GLOBAL)
    dept_role = _role(test_org, 'DEPT_HEAD', ScopeType.DEPARTMENT, RoleType.POSITION)
    proxy_role = _role(test_org, 'DEPT_PROXY1', ScopeType.DEPARTMENT, RoleType.POSITION)
    holder = _user(test_org, 'rak_list_holder_00001', 'raklistholder')
    proxy = _user(test_org, 'rak_list_proxy_000001', 'raklistproxy')
    _regular(test_org, holder, global_role)
    today = test_org.local_today()
    result = assign_role(
        test_org.secure_code,
        proxy.secure_code,
        global_role.secure_code,
        kind='proxy',
        acting_for_sc=holder.secure_code,
        valid_from=today,
        valid_until=today + timedelta(days=1),
        allowed_form_templates=['TPL_A'],
        grant_reason='列表',
        operator=test_admin,
    )

    roles_by_user = _build_user_roles(test_org.secure_code, [proxy.secure_code])
    row = next(role for role in roles_by_user[proxy.secure_code] if role['assignment_secure_code'] == result['assignment_secure_code'])
    assert row['assignment_kind'] == 'proxy'
    assert row['valid_from'] == today.isoformat()
    assert row['valid_until'] == (today + timedelta(days=1)).isoformat()
    assert row['acting_for_secure_code'] == holder.secure_code
    assert row['acting_for_name'] == holder.display_name
    assert row['allowed_form_templates_count'] == 1
    assert row['is_valid'] is True

    proxy_options = _list_assignable_roles(test_org.secure_code, kind='proxy')
    codes = {role['code'] for role in proxy_options}
    assert global_role.code in codes
    assert dept_role.code in codes
    assert proxy_role.code not in codes
