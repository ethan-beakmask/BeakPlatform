import pytest

from app import db
from app.models import Organization, Role, User
from app.models.role import RoleLevel, RoleType, ScopeType
from app.models.user import UserType
from app.services.org_initial_setup_service import complete_initial_setup


def _make_org_with_roles():
    org = Organization(
        secure_code='org_initial_setup_01',
        code='INITSETUP',
        name='Initial Setup Test',
        domain_name='init-setup.example',
        is_active=True,
        is_deleted=False,
    )
    db.session.add(org)
    db.session.flush()

    roles = []
    for code, name, level in (
        ('ORG_ADMIN', '企業管理員', RoleLevel.ORG),
        ('EMPLOYEE', '企業成員', RoleLevel.MEMBER),
    ):
        role = Role(
            org_secure_code=org.secure_code,
            code=code,
            name=name,
            role_type=RoleType.ROLE,
            scope_type=ScopeType.GLOBAL,
            role_level=level,
            is_system_role=True,
            is_active=True,
        )
        db.session.add(role)
        roles.append(role)
    db.session.flush()

    original_admin = User(
        org_secure_code=org.secure_code,
        username='admin',
        email='admin@init-setup.example',
        display_name='Original Admin',
        user_type=UserType.ORG_ADMIN,
        is_original_admin=True,
        is_active=True,
        is_deleted=False,
    )
    original_admin.set_password('Original2026#Pass')
    db.session.add(original_admin)
    db.session.commit()
    return org, original_admin, roles


def test_complete_initial_setup_creates_bound_accounts_and_deactivates_original(app):
    org, original_admin, _roles = _make_org_with_roles()

    result = complete_initial_setup(
        org,
        original_admin,
        'angel',
        '晧安琪',
        'Angel Hao',
        'DemoCorp2026#Pass',
        employee_id='E0001',
    )
    db.session.commit()

    employee = result['employee']
    admin = result['admin']
    assert employee.email == 'angel@init-setup.example'
    assert employee.user_type == UserType.EMPLOYEE
    assert admin.email == 'admin-angel@init-setup.example'
    assert admin.bound_employee_secure_code == employee.secure_code
    assert original_admin.is_active is False


def test_complete_initial_setup_rejects_duplicate_username(app):
    org, original_admin, _roles = _make_org_with_roles()
    existing = User(
        org_secure_code=org.secure_code,
        username='angel',
        email='angel@init-setup.example',
        display_name='Existing Angel',
        user_type=UserType.EMPLOYEE,
        is_active=True,
        is_deleted=False,
    )
    existing.set_password('Existing2026#Pass')
    db.session.add(existing)
    db.session.commit()

    with pytest.raises(ValueError, match='帳號 angel 已存在'):
        complete_initial_setup(
            org,
            original_admin,
            'angel',
            '晧安琪',
            'Angel Hao',
            'DemoCorp2026#Pass',
            employee_id='E0001',
        )


def test_complete_initial_setup_rejects_non_original_admin(app):
    org, _original_admin, _roles = _make_org_with_roles()
    admin = User(
        org_secure_code=org.secure_code,
        username='manager',
        email='manager@init-setup.example',
        display_name='Manager',
        user_type=UserType.ORG_ADMIN,
        is_original_admin=False,
        is_active=True,
        is_deleted=False,
    )
    admin.set_password('Manager2026#Pass')
    db.session.add(admin)
    db.session.commit()

    with pytest.raises(ValueError, match='只有原始管理員可以執行初始設定'):
        complete_initial_setup(
            org,
            admin,
            'angel',
            '晧安琪',
            'Angel Hao',
            'DemoCorp2026#Pass',
            employee_id='E0001',
        )
