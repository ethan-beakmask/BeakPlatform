"""SYSTEM_ADMIN 角色出廠種入：全新安裝的系統管理員必須持有全部權限定義（2026-09-13 BeakPlatform-VM 撞到 403）。"""
from app import db
from app.defaults.permission_defaults import seed_system_permissions
from app.defaults.system_admin_role_defaults import seed_system_admin_role
from app.models import Organization, Permission, Role, User
from app.models.associations import UserRoleAssignment
from app.models.role_permission import RolePermission
from app.models.user import UserType


def _make_system_org_and_admin():
    org = Organization(
        secure_code='sys_admin_role_test',
        code='SYSTEM',
        name='系統企業',
        domain_name='sys-admin-role.example',
        is_system_org=True,
        is_active=True,
        is_deleted=False,
    )
    db.session.add(org)
    db.session.flush()
    admin = User(
        org_secure_code=org.secure_code,
        username='admin',
        email='admin@sys-admin-role.example',
        display_name='System Admin',
        user_type=UserType.SYSTEM_ADMIN,
        is_active=True,
        is_deleted=False,
    )
    admin.set_password('SysAdmin2026#Pass')
    db.session.add(admin)
    db.session.commit()
    return org, admin


def test_seed_creates_role_grants_all_permissions_and_assigns_admin(app):
    org, admin = _make_system_org_and_admin()
    seed_system_permissions(force=True)
    db.session.commit()

    result = seed_system_admin_role()
    db.session.commit()

    role = Role.query.filter_by(org_secure_code=org.secure_code, code='SYSTEM_ADMIN', is_deleted=False).one()
    assert result['role_created'] is True
    active_codes = {p.secure_code for p in Permission.query.filter_by(is_active=True, is_deleted=False).all()}
    granted = {rp.permission_secure_code for rp in RolePermission.query.filter_by(role_secure_code=role.secure_code, is_deleted=False).all()}
    assert active_codes and granted == active_codes
    assert UserRoleAssignment.query.filter_by(
        user_secure_code=admin.secure_code, role_secure_code=role.secure_code, is_deleted=False).count() == 1

    again = seed_system_admin_role()
    db.session.commit()
    assert again['role_created'] is False
    assert again['permissions_granted'] == 0
    assert again['assignments_created'] == 0


def test_seed_backfills_permissions_added_later(app):
    _make_system_org_and_admin()
    seed_system_permissions(force=True)
    db.session.commit()
    seed_system_admin_role()
    db.session.commit()

    db.session.add(Permission(code='demo_pack:read', name='示範', resource_type='demo_pack', action='read', is_active=True, permission_level='SYSTEM'))
    db.session.commit()

    result = seed_system_admin_role()
    db.session.commit()
    assert result['permissions_granted'] == 1
