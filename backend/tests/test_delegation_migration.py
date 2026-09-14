from datetime import date, timedelta

from app import db
from app.models import (
    AssignmentKind,
    Delegation,
    DelegationStatus,
    DelegationType,
    MenuItem,
    OrganizationalUnit,
    PermissionCondition,
    Role,
    RoleType,
    ScopeType,
    UnitType,
    User,
    UserRoleAssignment,
    UserType,
)
from app.services.delegation_migration import migrate_org_delegations, retire_delegation_globals


def _user(org, sc, username, user_type=UserType.EMPLOYEE, active=True):
    user = User(
        secure_code=sc,
        org_secure_code=org.secure_code,
        username=username,
        email=f'{username}@example.com',
        display_name=username,
        user_type=user_type,
        is_active=active,
        is_deleted=False,
    )
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()
    return user


def _role(org, code, scope_type=ScopeType.DEPARTMENT):
    role = Role(
        org_secure_code=org.secure_code,
        code=code,
        name=code,
        role_type=RoleType.POSITION if code.startswith('DEPT_') else RoleType.ROLE,
        scope_type=scope_type,
        is_active=True,
        is_deleted=False,
    )
    db.session.add(role)
    db.session.commit()
    return role


def _unit(org):
    unit = OrganizationalUnit(
        org_secure_code=org.secure_code,
        code='MIG',
        name='Migration Dept',
        unit_type=UnitType.DEPARTMENT,
        is_active=True,
        is_deleted=False,
    )
    db.session.add(unit)
    db.session.commit()
    return unit


def _assign(org, user, role, unit=None):
    row = UserRoleAssignment(
        org_secure_code=org.secure_code,
        user_secure_code=user.secure_code,
        role_secure_code=role.secure_code,
        unit_secure_code=unit.secure_code if unit else None,
        assignment_kind=AssignmentKind.REGULAR,
        is_deleted=False,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _delegation(org, sc, delegator, delegate, *, dtype=DelegationType.FULL,
                status=DelegationStatus.PENDING, start=None, end=None,
                approval_limit=None, allowed=None, reason='Migrated reason'):
    today = org.local_today()
    row = Delegation(
        secure_code=sc,
        org_secure_code=org.secure_code,
        delegator_secure_code=delegator.secure_code,
        delegate_secure_code=delegate.secure_code,
        delegation_type=dtype,
        status=status,
        effective_from=start or today,
        effective_until=end or (today + timedelta(days=5)),
        approval_limit=approval_limit,
        reason=reason,
        created_by='test',
    )
    if allowed is not None:
        row.set_allowed_form_templates(allowed)
    db.session.add(row)
    db.session.commit()
    return row


def _proxy_rows(org, user):
    return UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org.secure_code,
        UserRoleAssignment.user_secure_code == user.secure_code,
        UserRoleAssignment.assignment_kind == AssignmentKind.PROXY,
        UserRoleAssignment.is_deleted == False,  # noqa: E712
    ).order_by(UserRoleAssignment.role_secure_code.asc()).all()


def test_full_delegation_migrates_regular_roles_except_identity_role(test_org):
    unit = _unit(test_org)
    delegator = _user(test_org, 'mig_delegator_00001', 'mig_delegator')
    delegate = _user(test_org, 'mig_delegate_000001', 'mig_delegate')
    manager = _role(test_org, 'DEPT_MANAGER')
    head = _role(test_org, 'DEPT_HEAD')
    employee = _role(test_org, 'EMPLOYEE', ScopeType.GLOBAL)
    _assign(test_org, delegator, manager, unit)
    _assign(test_org, delegator, head, unit)
    _assign(test_org, delegator, employee)
    delegation = _delegation(test_org, 'mig_full_000000001', delegator, delegate)

    counts = migrate_org_delegations(test_org)

    rows = _proxy_rows(test_org, delegate)
    assert counts['delegation_migrated'] == 1
    assert counts['proxy_created'] == 2
    assert len(rows) == 2
    assert {row.role_secure_code for row in rows} == {manager.secure_code, head.secure_code}
    assert all(row.source_ref == f'migration:pf251:{delegation.secure_code}' for row in rows)
    assert all(row.valid_from == delegation.effective_from and row.valid_until == delegation.effective_until for row in rows)
    assert all(row.grant_reason == 'Migrated reason' for row in rows)

    assert migrate_org_delegations(test_org) == {
        'delegation_migrated': 0,
        'delegation_skipped_empty_scope': 0,
        'delegation_skipped_approval_limit': 0,
        'delegation_skipped_type': 0,
        'delegation_skipped_delegate_inactive': 0,
        'delegation_skipped_no_roles': 0,
        'proxy_rows_layer_skipped': 0,
        'proxy_created': 0,
        'proxy_revived': 0,
        'proxy_skipped': 0,
    }


def test_specific_scope_and_empty_scope(test_org):
    unit = _unit(test_org)
    delegator = _user(test_org, 'mig_spec_giver001', 'mig_spec_giver')
    delegate = _user(test_org, 'mig_spec_del00001', 'mig_spec_del')
    role = _role(test_org, 'DEPT_MANAGER')
    _assign(test_org, delegator, role, unit)
    _delegation(test_org, 'mig_spec_000000001', delegator, delegate,
                dtype=DelegationType.SPECIFIC, allowed=['FORM_B', 'FORM_A'])
    _delegation(test_org, 'mig_spec_empty001', delegator, delegate,
                dtype=DelegationType.SPECIFIC, allowed=[])

    counts = migrate_org_delegations(test_org)

    rows = _proxy_rows(test_org, delegate)
    assert counts['proxy_created'] == 1
    assert counts['delegation_skipped_empty_scope'] == 1
    assert rows[0].allowed_form_templates == ['FORM_A', 'FORM_B']


def test_revoked_expired_and_approval_limit_rules(test_org):
    unit = _unit(test_org)
    delegator = _user(test_org, 'mig_rule_giver001', 'mig_rule_giver')
    delegate = _user(test_org, 'mig_rule_del00001', 'mig_rule_del')
    role = _role(test_org, 'DEPT_MANAGER')
    _assign(test_org, delegator, role, unit)
    today = test_org.local_today()
    _delegation(test_org, 'mig_revoked0000001', delegator, delegate, status=DelegationStatus.REVOKED)
    _delegation(test_org, 'mig_expired0000001', delegator, delegate,
                start=today - timedelta(days=5), end=today - timedelta(days=1))
    _delegation(test_org, 'mig_limit00000001', delegator, delegate,
                dtype=DelegationType.APPROVAL, approval_limit=100)
    _delegation(test_org, 'mig_nolimit000001', delegator, delegate,
                dtype=DelegationType.APPROVAL, approval_limit=None)

    counts = migrate_org_delegations(test_org)

    assert counts['proxy_created'] == 1
    assert counts['delegation_migrated'] == 1
    assert counts['delegation_skipped_approval_limit'] == 1


def test_delegate_layer_incompatible_skips_rows(test_org):
    unit = _unit(test_org)
    delegator = _user(test_org, 'mig_layer_giver01', 'mig_layer_giver')
    delegate = _user(test_org, 'mig_layer_ext0001', 'mig_layer_ext', UserType.EXTERNAL)
    role = _role(test_org, 'DEPT_MANAGER')
    _assign(test_org, delegator, role, unit)
    _delegation(test_org, 'mig_layer00000001', delegator, delegate)

    counts = migrate_org_delegations(test_org)

    assert counts['proxy_rows_layer_skipped'] == 1
    assert counts['proxy_created'] == 0
    assert counts['delegation_migrated'] == 0


def test_no_regular_roles_and_inactive_delegate_skip(test_org):
    delegator = _user(test_org, 'mig_skip_giver001', 'mig_skip_giver')
    delegate = _user(test_org, 'mig_skip_del00001', 'mig_skip_del')
    inactive = _user(test_org, 'mig_skip_off00001', 'mig_skip_off', active=False)
    _delegation(test_org, 'mig_noroles000001', delegator, delegate)
    _delegation(test_org, 'mig_inactive000001', delegator, inactive)

    counts = migrate_org_delegations(test_org)

    assert counts['delegation_skipped_no_roles'] == 1
    assert counts['delegation_skipped_delegate_inactive'] == 1


def test_retire_delegation_globals_is_idempotent(test_org):
    menu = MenuItem(
        org_secure_code=test_org.secure_code,
        code='delegations',
        title='代理授權',
        link_type='route',
        link_target='delegations.list_delegations',
        is_deleted=False,
    )
    condition = PermissionCondition(
        code='DELEGATED',
        name='被代理',
        description='old',
        condition_type='DELEGATE',
        expression='{}',
        is_deleted=False,
    )
    db.session.add_all([menu, condition])
    db.session.commit()

    first = retire_delegation_globals()
    second = retire_delegation_globals()

    assert first == {'menu_retired': 1, 'condition_retired': 1}
    assert second == {'menu_retired': 0, 'condition_retired': 0}
    assert menu.is_deleted is True
    assert condition.is_deleted is True
