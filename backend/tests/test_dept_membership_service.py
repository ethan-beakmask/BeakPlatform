from datetime import datetime

import pytest

from app import db
from app.models import (
    OrganizationalUnit,
    Role,
    RoleType,
    UnitType,
    User,
    UserRoleAssignment,
    UserType,
    UserUnitMembership,
    MembershipType,
)
from app.services.dept_membership_service import (
    ensure_dept_membership,
    remove_dept_membership,
    set_dept_manager,
)


def _user(sc, org, username, name):
    user = User(
        secure_code=sc,
        org_secure_code=org.secure_code,
        username=username,
        email=f'{username}@example.com',
        display_name=name,
        user_type=UserType.EMPLOYEE,
        is_active=True,
        is_deleted=False,
    )
    user.set_password('password123')
    db.session.add(user)
    db.session.flush()
    return user


def _unit(org, code='RD', name='研發部'):
    unit = OrganizationalUnit(
        secure_code=f'unit_{code.lower()}_deptsvc',
        org_secure_code=org.secure_code,
        code=code,
        name=name,
        unit_type=UnitType.DEPARTMENT,
        full_path=f'/{name}',
        level=1,
        is_active=True,
        is_deleted=False,
    )
    db.session.add(unit)
    db.session.flush()
    return unit


def _role(org, code, role_type='ROLE'):
    role = Role(
        secure_code=f'role_{code.lower()}_deptsvc',
        org_secure_code=org.secure_code,
        code=code,
        name=code,
        role_type=role_type,
        scope_type='DEPARTMENT',
        is_active=True,
        is_deleted=False,
    )
    db.session.add(role)
    db.session.flush()
    return role


def _roles(org, include_manager=True):
    roles = {
        'member': _role(org, 'DEPT_MEMBER'),
        'employee': _role(org, 'DEPT_EMPLOYEE', RoleType.POSITION),
    }
    if include_manager:
        roles['manager'] = _role(org, 'DEPT_MANAGER', RoleType.POSITION)
    return roles


def _active_assignment(user, role, unit):
    return UserRoleAssignment.query.filter_by(
        org_secure_code=user.org_secure_code,
        user_secure_code=user.secure_code,
        role_secure_code=role.secure_code,
        unit_secure_code=unit.secure_code,
        is_deleted=False,
    ).first()


def test_membership_service_creates_membership_and_roles_idempotently(test_org):
    user = _user('deptsvc_member', test_org, 'deptsvcmember', 'Member')
    unit = _unit(test_org)
    roles = _roles(test_org)

    ensure_dept_membership(user, unit, 'tester')
    db.session.flush()
    first_counts = (
        UserUnitMembership.query.count(),
        UserRoleAssignment.query.count(),
    )
    ensure_dept_membership(user, unit, 'tester')
    db.session.flush()

    membership = UserUnitMembership.query.filter_by(
        user_secure_code=user.secure_code,
        unit_secure_code=unit.secure_code,
        membership_type=MembershipType.SOLID,
        is_deleted=False,
    ).one()
    assert membership.role_type == 'MEMBER'
    assert _active_assignment(user, roles['member'], unit) is not None
    assert _active_assignment(user, roles['employee'], unit) is not None
    assert (UserUnitMembership.query.count(), UserRoleAssignment.query.count()) == first_counts


def test_membership_service_revives_soft_deleted_rows(test_org):
    user = _user('deptsvc_revive', test_org, 'deptsvcrevive', 'Revive')
    unit = _unit(test_org, 'RV', '復活部')
    roles = _roles(test_org)
    ensure_dept_membership(user, unit, 'tester')
    db.session.flush()
    membership = UserUnitMembership.query.filter_by(user_secure_code=user.secure_code).one()
    assignment = _active_assignment(user, roles['member'], unit)
    membership_id = membership.id
    assignment_id = assignment.id
    membership.is_deleted = True
    membership.deleted_at = datetime.utcnow()
    assignment.is_deleted = True
    assignment.deleted_at = datetime.utcnow()
    db.session.flush()

    ensure_dept_membership(user, unit, 'tester')
    db.session.flush()

    assert UserUnitMembership.query.get(membership_id).is_deleted is False
    assert UserRoleAssignment.query.get(assignment_id).is_deleted is False
    assert UserUnitMembership.query.filter_by(user_secure_code=user.secure_code).count() == 1
    assert UserRoleAssignment.query.filter_by(
        user_secure_code=user.secure_code,
        role_secure_code=roles['member'].secure_code,
    ).count() == 1


def test_set_dept_manager_switches_roles_and_primary_unit(test_org):
    old = _user('deptsvc_oldmgr', test_org, 'deptsvcold', 'Old Manager')
    new = _user('deptsvc_newmgr', test_org, 'deptsvcnew', 'New Manager')
    unit = _unit(test_org, 'MG', '管理部')
    roles = _roles(test_org)
    ensure_dept_membership(old, unit, 'tester')
    ensure_dept_membership(new, unit, 'tester')
    db.session.add(UserRoleAssignment(
        org_secure_code=test_org.secure_code,
        user_secure_code=old.secure_code,
        role_secure_code=roles['manager'].secure_code,
        unit_secure_code=unit.secure_code,
        is_deleted=False,
    ))
    db.session.flush()

    set_dept_manager(new, unit, 'tester')
    db.session.flush()

    assert _active_assignment(old, roles['manager'], unit) is None
    assert _active_assignment(old, roles['employee'], unit) is not None
    assert _active_assignment(new, roles['employee'], unit) is None
    assert _active_assignment(new, roles['manager'], unit) is not None
    assert new.primary_unit_secure_code == unit.secure_code


def test_remove_membership_soft_deletes_rows_and_missing_manager_role_raises(test_org):
    user = _user('deptsvc_remove', test_org, 'deptsvcremove', 'Remove')
    unit = _unit(test_org, 'RM', '移除部')
    roles = _roles(test_org)
    ensure_dept_membership(user, unit, 'tester')
    set_dept_manager(user, unit, 'tester')
    db.session.flush()

    remove_dept_membership(user, unit)
    db.session.flush()

    membership = UserUnitMembership.query.filter_by(user_secure_code=user.secure_code).one()
    assert membership.is_deleted is True
    for role in roles.values():
        assignment = UserRoleAssignment.query.filter_by(
            user_secure_code=user.secure_code,
            role_secure_code=role.secure_code,
            unit_secure_code=unit.secure_code,
        ).first()
        assert assignment is None or assignment.is_deleted is True

    roles['manager'].is_deleted = True
    db.session.flush()
    with pytest.raises(LookupError):
        set_dept_manager(user, unit, 'tester')
