"""PF-251 第 3a 期（併 PF-250）：部門管理層 API 走服務、正副主管連帶 DEPT_HEAD、候補代理人三列 standby。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db  # noqa: E402
from app.models import (  # noqa: E402
    AssignmentKind,
    OrganizationalUnit,
    Role,
    RoleType,
    UnitType,
    User,
    UserRoleAssignment,
    UserType,
)
from app.platform.data import _department_manager_code  # noqa: E402

BASE = '/beakplatform/api/units'


def _role(org, code, role_type):
    role = Role(org_secure_code=org.secure_code, code=code, name=code, role_type=role_type,
                scope_type='DEPARTMENT', is_active=True, is_deleted=False)
    db.session.add(role)
    return role


def _env(org):
    roles = {
        'member': _role(org, 'DEPT_MEMBER', RoleType.ROLE),
        'employee': _role(org, 'DEPT_EMPLOYEE', RoleType.ROLE),
        'head': _role(org, 'DEPT_HEAD', RoleType.POSITION),
        'manager': _role(org, 'DEPT_MANAGER', RoleType.POSITION),
        'deputy': _role(org, 'DEPT_DEPUTY', RoleType.POSITION),
    }
    unit = OrganizationalUnit(org_secure_code=org.secure_code, code='MKT', name='行銷部門',
                              unit_type=UnitType.DEPARTMENT, is_active=True, is_deleted=False)
    db.session.add(unit)
    db.session.commit()
    return roles, unit


def _user(org, sc, username, user_type=UserType.EMPLOYEE):
    user = User(secure_code=sc, org_secure_code=org.secure_code, username=username,
                email=f'{username}@example.com', display_name=username, user_type=user_type,
                is_active=True, is_deleted=False)
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()
    return user


def _codes(org, user, unit, kind=AssignmentKind.REGULAR):
    rows = UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org.secure_code,
        UserRoleAssignment.user_secure_code == user.secure_code,
        UserRoleAssignment.unit_secure_code == unit.secure_code,
        UserRoleAssignment.assignment_kind == kind,
        UserRoleAssignment.is_deleted == False,  # noqa: E712
    ).all()
    role_map = {r.secure_code: r.code for r in Role.query.filter(Role.org_secure_code == org.secure_code).all()}
    return sorted(role_map[r.role_secure_code] for r in rows)


def test_manager_and_deputy_carry_dept_head_and_drop_employee(admin_client, test_org):
    roles, unit = _env(test_org)
    boss = _user(test_org, 'ul_boss_0000000000001', 'ulboss')
    vice = _user(test_org, 'ul_vice_0000000000001', 'ulvice')

    res = admin_client.post(f'{BASE}/{unit.secure_code}/leadership/manager', json={'user_id': boss.secure_code})
    assert res.status_code == 200, res.get_json()
    res = admin_client.post(f'{BASE}/{unit.secure_code}/leadership/deputy', json={'user_id': vice.secure_code})
    assert res.status_code == 200, res.get_json()

    db.session.expire_all()
    assert _codes(test_org, boss, unit) == ['DEPT_HEAD', 'DEPT_MANAGER', 'DEPT_MEMBER']
    assert _codes(test_org, vice, unit) == ['DEPT_DEPUTY', 'DEPT_HEAD', 'DEPT_MEMBER']
    assert _department_manager_code(unit) == boss.secure_code

    body = admin_client.get(f'{BASE}/{unit.secure_code}/leadership').get_json()
    assert body['manager']['id'] == boss.secure_code
    assert body['deputy']['id'] == vice.secure_code
    assert body['standby'] == []

    # 卸任正主管：HEAD 撤、EMPLOYEE 回；副主管不受影響
    res = admin_client.delete(f'{BASE}/{unit.secure_code}/leadership/manager')
    assert res.status_code == 200, res.get_json()
    db.session.expire_all()
    assert _codes(test_org, boss, unit) == ['DEPT_EMPLOYEE', 'DEPT_MEMBER']
    assert _codes(test_org, vice, unit) == ['DEPT_DEPUTY', 'DEPT_HEAD', 'DEPT_MEMBER']
    assert _department_manager_code(unit) is None


def test_standby_registers_three_rows_and_removes_per_user(admin_client, test_org):
    roles, unit = _env(test_org)
    backup = _user(test_org, 'ul_backup_00000000001', 'ulbackup')

    res = admin_client.post(f'{BASE}/{unit.secure_code}/leadership/standby', json={'user_id': backup.secure_code})
    assert res.status_code == 200, res.get_json()
    db.session.expire_all()
    assert _codes(test_org, backup, unit, AssignmentKind.STANDBY) == ['DEPT_DEPUTY', 'DEPT_HEAD', 'DEPT_MANAGER']
    assert _codes(test_org, backup, unit) == []   # 不是正式成員角色

    # 重複登記不多建
    res = admin_client.post(f'{BASE}/{unit.secure_code}/leadership/standby', json={'user_id': backup.secure_code})
    assert res.status_code == 200, res.get_json()
    db.session.expire_all()
    assert len(_codes(test_org, backup, unit, AssignmentKind.STANDBY)) == 3

    body = admin_client.get(f'{BASE}/{unit.secure_code}/leadership').get_json()
    assert [u['id'] for u in body['standby']] == [backup.secure_code]
    assert sorted(body['standby'][0]['standby_roles']) == ['DEPT_DEPUTY', 'DEPT_HEAD', 'DEPT_MANAGER']

    # 不帶使用者的 DELETE standby → 400；逐人移除 → 三列軟刪
    assert admin_client.delete(f'{BASE}/{unit.secure_code}/leadership/standby').status_code == 400
    res = admin_client.delete(f'{BASE}/{unit.secure_code}/leadership/standby/{backup.secure_code}')
    assert res.status_code == 200, res.get_json()
    assert res.get_json()['removed'] == 3
    db.session.expire_all()
    assert _codes(test_org, backup, unit, AssignmentKind.STANDBY) == []


def test_invalid_position_and_external_user_are_rejected(admin_client, test_org):
    roles, unit = _env(test_org)
    vendor = _user(test_org, 'ul_vendor_00000000001', 'ulvendor', UserType.EXTERNAL)
    staff = _user(test_org, 'ul_staff_000000000001', 'ulstaff')

    assert admin_client.post(f'{BASE}/{unit.secure_code}/leadership/proxy1', json={'user_id': staff.secure_code}).status_code == 400
    assert admin_client.post(f'{BASE}/{unit.secure_code}/leadership/standby', json={'user_id': vendor.secure_code}).status_code == 400
    assert admin_client.post(f'{BASE}/{unit.secure_code}/leadership/manager', json={}).status_code == 400
    db.session.expire_all()
    assert _codes(test_org, vendor, unit, AssignmentKind.STANDBY) == []
