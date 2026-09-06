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
from app.models.user_unit_membership import MembershipRole
from app.services.dept_membership_service import (
    count_unit_members,
    ensure_dept_membership,
    ensure_role_assignment,
    ensure_solid_membership,
    purge_unit_memberships,
    reconcile_dept_manager,
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


def _row(user, role, unit):
    return UserRoleAssignment.query.filter_by(
        org_secure_code=user.org_secure_code,
        user_secure_code=user.secure_code,
        role_secure_code=role.secure_code,
        unit_secure_code=unit.secure_code,
    ).one()


def test_reconcile_dept_manager_sets_manager_then_is_a_no_op(test_org):
    user = _user('deptsvc_reconcile', test_org, 'deptsvcreconcile', 'Reconcile')
    unit = _unit(test_org, 'RC', '同步部')
    roles = _roles(test_org)

    assert reconcile_dept_manager(user, unit, 'tester') is True
    db.session.flush()

    assert _active_assignment(user, roles['manager'], unit) is not None
    assert _active_assignment(user, roles['member'], unit) is not None
    assert _active_assignment(user, roles['employee'], unit) is None
    employee_row = _row(user, roles['employee'], unit)
    assert employee_row.is_deleted is True
    assert employee_row.deleted_at is not None
    assert UserUnitMembership.query.filter_by(
        user_secure_code=user.secure_code,
        unit_secure_code=unit.secure_code,
        membership_type=MembershipType.SOLID,
        is_deleted=False,
    ).count() == 1
    db.session.commit()

    manager_row = _row(user, roles['manager'], unit)
    before = (
        employee_row.id,
        employee_row.deleted_at,
        employee_row.updated_at,
        manager_row.updated_at,
        UserUnitMembership.query.count(),
        UserRoleAssignment.query.count(),
    )

    assert reconcile_dept_manager(user, unit, 'tester') is False
    dirty_types = {type(obj) for obj in db.session.dirty}
    assert UserRoleAssignment not in dirty_types
    assert UserUnitMembership not in dirty_types
    assert db.session.is_modified(employee_row) is False
    assert db.session.is_modified(manager_row) is False
    db.session.commit()

    employee_row = _row(user, roles['employee'], unit)
    manager_row = _row(user, roles['manager'], unit)
    after = (
        employee_row.id,
        employee_row.deleted_at,
        employee_row.updated_at,
        manager_row.updated_at,
        UserUnitMembership.query.count(),
        UserRoleAssignment.query.count(),
    )
    assert after == before
    assert employee_row.is_deleted is True


def test_reconcile_dept_manager_replaces_previous_manager(test_org):
    old = _user('deptsvc_rc_old', test_org, 'deptsvcrcold', 'Old Manager')
    new = _user('deptsvc_rc_new', test_org, 'deptsvcrcnew', 'New Manager')
    unit = _unit(test_org, 'RP', '交接部')
    roles = _roles(test_org)

    assert reconcile_dept_manager(old, unit, 'tester') is True
    db.session.flush()
    assert reconcile_dept_manager(new, unit, 'tester') is True
    db.session.flush()

    assert _active_assignment(old, roles['manager'], unit) is None
    assert _active_assignment(old, roles['employee'], unit) is not None
    assert _active_assignment(new, roles['manager'], unit) is not None
    assert _active_assignment(new, roles['employee'], unit) is None
    assert new.primary_unit_secure_code == unit.secure_code

    roles['manager'].is_deleted = True
    db.session.flush()
    with pytest.raises(LookupError):
        reconcile_dept_manager(new, unit, 'tester')


def test_ensure_solid_membership_only_touches_membership(test_org):
    user = _user('deptsvc_solid', test_org, 'deptsvcsolid', 'Solid')
    unit = _unit(test_org, 'SL', '純成員部')
    _roles(test_org)

    ensure_solid_membership(user, unit)
    db.session.flush()
    ensure_solid_membership(user, unit)
    db.session.flush()

    assert UserUnitMembership.query.filter_by(
        user_secure_code=user.secure_code,
        unit_secure_code=unit.secure_code,
        membership_type=MembershipType.SOLID,
        is_deleted=False,
    ).count() == 1
    assert UserRoleAssignment.query.filter_by(user_secure_code=user.secure_code).count() == 0


# ---------------------------------------------------------------------------
# PF-249：移除成員／刪除單位要收齊所有角色@單位與成員關係
# ---------------------------------------------------------------------------

def _position_roles(org):
    return {
        'deputy': _role(org, 'DEPT_DEPUTY', RoleType.POSITION),
        'proxy1': _role(org, 'DEPT_PROXY1', RoleType.POSITION),
        'proxy2': _role(org, 'DEPT_PROXY2', RoleType.POSITION),
    }


def test_remove_membership_also_revokes_deputy_and_proxy_roles(test_org):
    user = _user('deptsvc_deputy', test_org, 'deptsvcdeputy', 'Deputy')
    unit = _unit(test_org, 'DP', '副主管部')
    roles = _roles(test_org)
    positions = _position_roles(test_org)
    ensure_dept_membership(user, unit, 'tester')
    for role in positions.values():
        ensure_role_assignment(test_org.secure_code, user.secure_code, role.secure_code,
                               unit.secure_code, 'tester')
    db.session.flush()
    assert all(_active_assignment(user, role, unit) for role in positions.values())

    remove_dept_membership(user, unit)
    db.session.flush()

    for role in list(roles.values()) + list(positions.values()):
        assert _active_assignment(user, role, unit) is None


def test_count_unit_members_unions_membership_and_primary_unit(test_org):
    unit = _unit(test_org, 'CNT', '計數部')
    _roles(test_org)
    solid_only = _user('deptsvc_cnt1', test_org, 'deptsvccnt1', 'SolidOnly')
    primary_only = _user('deptsvc_cnt2', test_org, 'deptsvccnt2', 'PrimaryOnly')
    both = _user('deptsvc_cnt3', test_org, 'deptsvccnt3', 'Both')
    deleted = _user('deptsvc_cnt4', test_org, 'deptsvccnt4', 'Deleted')
    ensure_dept_membership(solid_only, unit, 'tester')
    primary_only.primary_unit_secure_code = unit.secure_code
    ensure_dept_membership(both, unit, 'tester')
    both.primary_unit_secure_code = unit.secure_code
    ensure_dept_membership(deleted, unit, 'tester')
    deleted.is_deleted = True
    db.session.flush()

    assert count_unit_members(unit) == 3


def test_purge_unit_memberships_soft_deletes_rows_only_for_that_unit(test_org):
    unit = _unit(test_org, 'PG', '清理部')
    other = _unit(test_org, 'OT', '其他部')
    roles = _roles(test_org)
    positions = _position_roles(test_org)
    manager = _user('deptsvc_pg1', test_org, 'deptsvcpg1', 'Manager')
    member = _user('deptsvc_pg2', test_org, 'deptsvcpg2', 'Member')
    ensure_dept_membership(member, unit, 'tester')
    set_dept_manager(manager, unit, 'tester')
    ensure_role_assignment(test_org.secure_code, member.secure_code, positions['deputy'].secure_code,
                           unit.secure_code, 'tester')
    db.session.add(UserUnitMembership(
        org_secure_code=test_org.secure_code, user_secure_code=manager.secure_code,
        unit_secure_code=unit.secure_code, membership_type=MembershipType.DOTTED,
        role_type=MembershipRole.MEMBER,
    ))
    ensure_dept_membership(member, other, 'tester')   # 別的單位的關係不得被動到
    db.session.flush()
    assert manager.primary_unit_secure_code == unit.secure_code

    result = purge_unit_memberships(unit)
    db.session.flush()

    # member：DEPT_MEMBER＋DEPT_EMPLOYEE＋DEPT_DEPUTY；manager：DEPT_MEMBER＋DEPT_MANAGER（DEPT_EMPLOYEE 已被 set_dept_manager 撤掉）
    assert result == {'members': 2, 'memberships': 3, 'assignments': 5}
    assert UserUnitMembership.query.filter_by(unit_secure_code=unit.secure_code, is_deleted=False).count() == 0
    assert UserRoleAssignment.query.filter_by(unit_secure_code=unit.secure_code, is_deleted=False).count() == 0
    assert manager.primary_unit_secure_code is None
    assert UserUnitMembership.query.filter_by(
        user_secure_code=member.secure_code, unit_secure_code=other.secure_code, is_deleted=False).count() == 1
    assert _active_assignment(member, roles['member'], other) is not None


def test_delete_unit_api_purges_unit_roles_and_memberships(admin_client, test_org):
    unit = _unit(test_org, 'API', 'API刪除部')
    _roles(test_org)
    manager = _user('deptsvc_api1', test_org, 'deptsvcapi1', 'ApiManager')
    member = _user('deptsvc_api2', test_org, 'deptsvcapi2', 'ApiMember')
    ensure_dept_membership(member, unit, 'tester')
    set_dept_manager(manager, unit, 'tester')
    db.session.commit()
    unit_sc = unit.secure_code
    manager_sc = manager.secure_code

    blocked = admin_client.delete(f'/beakplatform/api/units/{unit_sc}')
    assert blocked.status_code == 400, blocked.get_json()
    body = blocked.get_json()
    assert body['need_confirm_members'] is True
    # member 只有 membership、沒有 primary_unit；舊寫法只數 primary_unit 會回 1
    assert body['members_count'] == 2

    ok = admin_client.delete(f'/beakplatform/api/units/{unit_sc}?confirm_members=true')
    assert ok.status_code == 200, ok.get_json()

    db.session.expire_all()
    assert OrganizationalUnit.query.filter_by(secure_code=unit_sc).one().is_deleted is True
    assert UserUnitMembership.query.filter_by(unit_secure_code=unit_sc, is_deleted=False).count() == 0
    assert UserRoleAssignment.query.filter_by(unit_secure_code=unit_sc, is_deleted=False).count() == 0
    assert User.query.filter_by(secure_code=manager_sc).one().primary_unit_secure_code is None
