"""
PERM-01 層界：角色指派不得跨 EXTERNAL 邊界（PF-145 階段三之二，2026-09-01）

EXTERNAL 帳號只能持有 scope_type=EXTERNAL 的角色，內部帳號不得持有外部範圍角色。
唯一實作：app.services.role_assignment_service.ensure_role_layer_compatible()。

organizational_units 三支部門 POST 端點的守門在測試庫驗不了
（ResourceGateway 需要 RBAC seed，TENANT-02），依 VERIFY-01 用實際帳號實測，
留證 /opt/tmp/verify/20260901-pf145-stage32.log。
"""
import pytest
from flask_login import login_user

from app import db
from app.models.associations import UserRoleAssignment
from app.models.organization import Organization
from app.models.role import Role, ScopeType
from app.models.user import User, UserType
from app.services.role_assignment_service import (
    assign_role,
    ensure_role_layer_compatible,
)


def _create_org(code='LAYERORG'):
    org = Organization(
        code=code,
        name=f'{code} Organization',
        domain_name=f'{code.lower()}.local',
        is_active=True,
        is_deleted=False,
    )
    db.session.add(org)
    db.session.flush()
    return org


def _create_user(org, username, user_type=UserType.EMPLOYEE):
    user = User(
        org_secure_code=org.secure_code,
        username=username,
        email=f'{username}@{org.domain_name}',
        display_name=username,
        password_hash='test-password-hash',
        user_type=user_type,
        is_active=True,
        is_deleted=False,
    )
    db.session.add(user)
    db.session.flush()
    return user


def _create_role(org, code, scope_type=ScopeType.GLOBAL):
    role = Role(
        org_secure_code=org.secure_code,
        code=code,
        name=code.title(),
        scope_type=scope_type,
        is_active=True,
        is_deleted=False,
    )
    db.session.add(role)
    db.session.flush()
    return role


def test_helper_blocks_internal_role_for_external_user(app, db_session):
    org = _create_org()
    vendor = _create_user(org, 'vendor', UserType.EXTERNAL)
    internal_role = _create_role(org, 'FLOW_DESIGNER')

    with app.test_request_context():
        with pytest.raises(ValueError):
            ensure_role_layer_compatible(vendor, internal_role)


def test_helper_blocks_external_role_for_internal_user(app, db_session):
    org = _create_org()
    employee = _create_user(org, 'employee', UserType.EMPLOYEE)
    external_role = _create_role(org, 'EXTERNAL_USERS', ScopeType.EXTERNAL)

    with app.test_request_context():
        with pytest.raises(ValueError):
            ensure_role_layer_compatible(employee, external_role)


def test_helper_allows_matching_layers(app, db_session):
    org = _create_org()
    vendor = _create_user(org, 'vendor', UserType.EXTERNAL)
    employee = _create_user(org, 'employee', UserType.EMPLOYEE)
    admin = _create_user(org, 'orgadmin', UserType.ORG_ADMIN)
    internal_role = _create_role(org, 'FLOW_DESIGNER')
    external_role = _create_role(org, 'EXTERNAL_USERS', ScopeType.EXTERNAL)

    with app.test_request_context():
        ensure_role_layer_compatible(vendor, external_role)
        ensure_role_layer_compatible(employee, internal_role)
        ensure_role_layer_compatible(admin, internal_role)


def test_assign_role_rejects_cross_layer_and_writes_nothing(app, db_session):
    org = _create_org()
    operator = _create_user(org, 'operator', UserType.ORG_ADMIN)
    vendor = _create_user(org, 'vendor', UserType.EXTERNAL)
    internal_role = _create_role(org, 'FLOW_DESIGNER')
    db.session.commit()

    with app.test_request_context():
        login_user(operator)
        with pytest.raises(ValueError):
            assign_role(org.secure_code, vendor.secure_code, internal_role.secure_code)

    count = UserRoleAssignment.query.filter_by(
        user_secure_code=vendor.secure_code,
        is_deleted=False,
    ).count()
    assert count == 0


def test_assign_role_allows_same_layer(app, db_session):
    org = _create_org()
    operator = _create_user(org, 'operator', UserType.ORG_ADMIN)
    employee = _create_user(org, 'employee', UserType.EMPLOYEE)
    vendor = _create_user(org, 'vendor', UserType.EXTERNAL)
    internal_role = _create_role(org, 'FLOW_DESIGNER')
    external_role = _create_role(org, 'VENDOR_PORTAL', ScopeType.EXTERNAL)
    db.session.commit()

    with app.test_request_context():
        login_user(operator)
        assign_role(org.secure_code, employee.secure_code, internal_role.secure_code)
        assign_role(org.secure_code, vendor.secure_code, external_role.secure_code)

    assert UserRoleAssignment.query.filter_by(
        user_secure_code=employee.secure_code,
        role_secure_code=internal_role.secure_code,
        is_deleted=False,
    ).count() == 1
    assert UserRoleAssignment.query.filter_by(
        user_secure_code=vendor.secure_code,
        role_secure_code=external_role.secure_code,
        is_deleted=False,
    ).count() == 1
