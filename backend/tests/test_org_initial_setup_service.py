import pytest

from app import db
from app.models import Organization, Role, User
from app.models.role import RoleLevel, RoleType, ScopeType
from app.models.user import UserType
from app.models.user_numbering_rule import (
    NumberingDefaultFor,
    NumberingElementType,
    NumberingUsageScope,
    UserNumberingRule,
)
from app.services.numbering_service import NumberingService
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


def _create_default_employee_numbering_rule(org):
    """建一條與 OrganizationService._create_default_numbering_rules 同構的
    企業成員預設編號規則（4 位序號，無前後綴）。"""
    rule = UserNumberingRule(
        org_secure_code=org.secure_code,
        name='測試用企業成員編號',
        description='4 位數序號',
        elements={
            'components': [
                {'type': NumberingElementType.SEQUENCE, 'order': 1,
                 'start': 1, 'digits': 4, 'reset_period': 'never'},
            ],
            'total_length': 4,
        },
        usage_scope=NumberingUsageScope.INTERNAL_ONLY,
        default_for=NumberingDefaultFor.EMPLOYEE,
        is_active=True,
    )
    db.session.add(rule)
    db.session.flush()
    return rule


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


def test_complete_initial_setup_auto_generates_employee_id_when_left_blank(app):
    """用戶編號留空 + 企業有 EMPLOYEE 預設編號規則時，由 service 自動取號完成設定。

    對應 f5065b1f 回歸：精靈 view 曾在呼叫 service 之前就先擋掉空白用戶編號，
    導致這個（表單預設用法）永遠到不了這裡的自動取號邏輯。
    """
    org, original_admin, _roles = _make_org_with_roles()
    rule = _create_default_employee_numbering_rule(org)
    db.session.commit()

    expected_id = NumberingService.get_next_number(rule, consume=False)

    result = complete_initial_setup(
        org,
        original_admin,
        'angel',
        '晧安琪',
        'Angel Hao',
        'DemoCorp2026#Pass',
        employee_id=None,
    )
    db.session.commit()

    employee = result['employee']
    assert employee.employee_id == expected_id
    assert employee.email == 'angel@init-setup.example'


def test_complete_initial_setup_rejects_blank_employee_id_without_default_rule(app):
    """留空用戶編號、且企業沒有可用的 EMPLOYEE 預設編號規則時，service 必須
    以 ValueError 擋下（訊息供 view flash 顯示），不能靜默通過或 500。"""
    org, original_admin, _roles = _make_org_with_roles()

    with pytest.raises(ValueError, match='用戶編號為必填，且無可用的預設編號規則'):
        complete_initial_setup(
            org,
            original_admin,
            'angel',
            '晧安琪',
            'Angel Hao',
            'DemoCorp2026#Pass',
            employee_id=None,
        )
