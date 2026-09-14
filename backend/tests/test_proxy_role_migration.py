"""PF-251 第 3a 期：DEPT_PROXY1／2 指派遷成三列 standby、角色退役（決策點 K2）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db  # noqa: E402
from app.models import AssignmentKind, OrganizationalUnit, Role, RoleType, UnitType, User, UserRoleAssignment, UserType  # noqa: E402
from app.services.proxy_role_migration import migrate_org_proxy_roles  # noqa: E402


def _role(org, code, role_type=RoleType.POSITION):
    role = Role(org_secure_code=org.secure_code, code=code, name=code, role_type=role_type,
                scope_type='DEPARTMENT', is_active=True, is_deleted=False)
    db.session.add(role)
    return role


def _user(org, sc, username):
    user = User(secure_code=sc, org_secure_code=org.secure_code, username=username, email=f'{username}@example.com',
                display_name=username, user_type=UserType.EMPLOYEE, is_active=True, is_deleted=False)
    user.set_password('password123')
    db.session.add(user)
    return user


def _assign(org, user, role, unit=None, kind=AssignmentKind.REGULAR):
    row = UserRoleAssignment(org_secure_code=org.secure_code, user_secure_code=user.secure_code,
                             role_secure_code=role.secure_code, unit_secure_code=unit.secure_code if unit else None,
                             assignment_kind=kind, is_deleted=False)
    db.session.add(row)
    return row


def _standby_rows(org, user, unit):
    return UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org.secure_code,
        UserRoleAssignment.user_secure_code == user.secure_code,
        UserRoleAssignment.unit_secure_code == unit.secure_code,
        UserRoleAssignment.assignment_kind == AssignmentKind.STANDBY,
        UserRoleAssignment.is_deleted == False,  # noqa: E712
    ).all()


def test_proxy_rows_become_three_standby_rows_and_roles_retire(test_org):
    head, manager, deputy = _role(test_org, 'DEPT_HEAD'), _role(test_org, 'DEPT_MANAGER'), _role(test_org, 'DEPT_DEPUTY')
    proxy1, proxy2 = _role(test_org, 'DEPT_PROXY1'), _role(test_org, 'DEPT_PROXY2')
    unit = OrganizationalUnit(org_secure_code=test_org.secure_code, code='MKT', name='行銷部門',
                              unit_type=UnitType.DEPARTMENT, is_active=True, is_deleted=False)
    db.session.add(unit)
    db.session.flush()
    aaaa, ssss, orphan = _user(test_org, 'prm_aaaa_000000000001', 'prm_aaaa'), _user(test_org, 'prm_ssss_000000000001', 'prm_ssss'), _user(test_org, 'prm_orph_000000000001', 'prm_orph')
    db.session.flush()
    row1 = _assign(test_org, aaaa, proxy1, unit)
    row2 = _assign(test_org, ssss, proxy2, unit)
    row_no_unit = _assign(test_org, orphan, proxy1, None)
    _assign(test_org, ssss, manager, unit, kind=AssignmentKind.STANDBY)   # 已有一列 standby，應計 skipped
    db.session.commit()

    counts = migrate_org_proxy_roles(test_org)
    db.session.commit()

    assert counts == {
        'proxy_rows_migrated': 2,
        'proxy_rows_dropped_no_unit': 1,
        'standby_created': 5,
        'standby_revived': 0,
        'standby_skipped': 1,
        'proxy_roles_deleted': 2,
    }
    db.session.expire_all()
    assert {r.role_secure_code for r in _standby_rows(test_org, aaaa, unit)} == {head.secure_code, manager.secure_code, deputy.secure_code}
    assert {r.role_secure_code for r in _standby_rows(test_org, ssss, unit)} == {head.secure_code, manager.secure_code, deputy.secure_code}
    created = [r for r in _standby_rows(test_org, aaaa, unit)]
    assert all(r.source_ref == 'migration:pf251' and r.grant_reason and r.acting_for_user_secure_code is None for r in created)
    assert row1.is_deleted and row2.is_deleted and row_no_unit.is_deleted
    assert _standby_rows(test_org, orphan, unit) == []
    assert proxy1.is_deleted and proxy2.is_deleted

    # 冪等：PROXY 角色已退役，第二次全 0
    assert migrate_org_proxy_roles(test_org) == {
        'proxy_rows_migrated': 0, 'proxy_rows_dropped_no_unit': 0, 'standby_created': 0,
        'standby_revived': 0, 'standby_skipped': 0, 'proxy_roles_deleted': 0,
    }


def test_missing_target_role_fails_closed(test_org):
    _role(test_org, 'DEPT_PROXY1')
    _role(test_org, 'DEPT_MANAGER')
    db.session.commit()
    try:
        migrate_org_proxy_roles(test_org)
    except RuntimeError as exc:
        assert 'DEPT_HEAD' in str(exc)
    else:
        raise AssertionError('缺 DEPT_HEAD 應該拒絕遷移')
