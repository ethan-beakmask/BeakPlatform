"""
PERM-04 模組 ACL fail-closed（PF-145 階段三之一，2026-09-01）

check_user_access() 零筆 ACL 記錄 = 拒絕（此前是 fail-open 不限制）。
配套：模組 MODULE_INFO 宣告 default_acl_roles，合約建立與 flask module sync
經 ModuleRoleService.seed_org_module_roles → ModuleAccessService.seed_org_module_acl
種入；該 (企業, 模組) 已有任何未刪除記錄則整組跳過。

decorator 層的 ORG_ADMIN 放行與各身分實測依 VERIFY-01 走瀏覽器/curl，
留證 /opt/tmp/verify/20260901-pf145-stage31-acl.log。
"""
from types import SimpleNamespace

from app import db
from app.models.module_access_control import ModuleAccessControl, TargetType
from app.models.associations import UserRoleAssignment
from app.models.organization import Organization
from app.models.role import Role
from app.models.user import User, UserType
from app.services.module_access_service import ModuleAccessService
from app.services.module_role_service import ModuleRoleService


def _create_org(code='ACLORG'):
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


def _create_role(org, code):
    role = Role(
        org_secure_code=org.secure_code,
        code=code,
        name=code.title(),
        is_active=True,
        is_deleted=False,
    )
    db.session.add(role)
    db.session.flush()
    return role


def _assign_role(user, role):
    assignment = UserRoleAssignment(
        user_secure_code=user.secure_code,
        role_secure_code=role.secure_code,
        org_secure_code=user.org_secure_code,
    )
    db.session.add(assignment)
    db.session.flush()
    return assignment


def _fake_module(name='form_workflow', acl_roles=None):
    return SimpleNamespace(
        name=name,
        default_acl_roles=acl_roles or [],
        default_roles=[],
        default_menu_role_requirements={},
        enabled=True,
    )


# ---------------------------------------------------------------------------
# check_user_access：fail-closed 判定
# ---------------------------------------------------------------------------

def test_zero_acl_records_denied(app, db_session):
    """零筆 ACL = 拒絕（fail-closed 核心，改版前這裡回 True）"""
    org = _create_org()
    employee = _create_user(org, 'emp1')

    assert ModuleAccessService.check_user_access(
        employee, 'form_workflow') is False


def test_role_match_allowed(app, db_session):
    org = _create_org()
    designer_role = _create_role(org, 'FLOW_DESIGNER')
    designer = _create_user(org, 'designer1')
    _assign_role(designer, designer_role)

    db.session.add(ModuleAccessControl(
        org_secure_code=org.secure_code,
        module_code='form_workflow',
        target_type=TargetType.ROLE,
        target_secure_code=designer_role.secure_code,
    ))
    db.session.flush()

    assert ModuleAccessService.check_user_access(
        designer, 'form_workflow') is True


def test_has_records_but_no_match_denied(app, db_session):
    """有 ACL 記錄但使用者不匹配 = 拒絕（原行為，確認未被改壞）"""
    org = _create_org()
    designer_role = _create_role(org, 'FLOW_DESIGNER')
    outsider = _create_user(org, 'outsider1')

    db.session.add(ModuleAccessControl(
        org_secure_code=org.secure_code,
        module_code='form_workflow',
        target_type=TargetType.ROLE,
        target_secure_code=designer_role.secure_code,
    ))
    db.session.flush()

    assert ModuleAccessService.check_user_access(
        outsider, 'form_workflow') is False


def test_soft_deleted_records_count_as_zero(app, db_session):
    """全數軟刪除視同零筆 = 拒絕（企業清空 ACL 後僅 ORG_ADMIN 可用）"""
    org = _create_org()
    designer_role = _create_role(org, 'FLOW_DESIGNER')
    designer = _create_user(org, 'designer2')
    _assign_role(designer, designer_role)

    db.session.add(ModuleAccessControl(
        org_secure_code=org.secure_code,
        module_code='form_workflow',
        target_type=TargetType.ROLE,
        target_secure_code=designer_role.secure_code,
        is_deleted=True,
    ))
    db.session.flush()

    assert ModuleAccessService.check_user_access(
        designer, 'form_workflow') is False


# ---------------------------------------------------------------------------
# seed_org_module_acl：預設 ACL 種入
# ---------------------------------------------------------------------------

def test_seed_creates_role_records(app, db_session):
    org = _create_org()
    _create_role(org, 'FLOW_DESIGNER')
    _create_role(org, 'FORM_DESIGNER')
    module = _fake_module(acl_roles=['FLOW_DESIGNER', 'FORM_DESIGNER'])

    result = ModuleAccessService.seed_org_module_acl(org.secure_code, module)

    assert result['acl_created'] == 2
    records = ModuleAccessControl.query.filter_by(
        org_secure_code=org.secure_code,
        module_code='form_workflow',
        is_deleted=False,
    ).all()
    assert len(records) == 2
    assert {r.target_type for r in records} == {TargetType.ROLE}


def test_seed_skips_org_with_existing_records(app, db_session):
    """已有任何未刪除記錄的 (企業, 模組) 整組跳過，不覆蓋企業自行設定"""
    org = _create_org()
    _create_role(org, 'FLOW_DESIGNER')
    account_user = _create_user(org, 'acl-account')
    db.session.add(ModuleAccessControl(
        org_secure_code=org.secure_code,
        module_code='form_workflow',
        target_type=TargetType.ACCOUNT,
        target_secure_code=account_user.secure_code,
    ))
    db.session.flush()
    module = _fake_module(acl_roles=['FLOW_DESIGNER'])

    result = ModuleAccessService.seed_org_module_acl(org.secure_code, module)

    assert result['acl_created'] == 0
    count = ModuleAccessControl.query.filter_by(
        org_secure_code=org.secure_code,
        module_code='form_workflow',
        is_deleted=False,
    ).count()
    assert count == 1  # 只有原本那筆 ACCOUNT


def test_seed_is_idempotent(app, db_session):
    org = _create_org()
    _create_role(org, 'FLOW_DESIGNER')
    module = _fake_module(acl_roles=['FLOW_DESIGNER'])

    first = ModuleAccessService.seed_org_module_acl(org.secure_code, module)
    second = ModuleAccessService.seed_org_module_acl(org.secure_code, module)

    assert first['acl_created'] == 1
    assert second['acl_created'] == 0
    count = ModuleAccessControl.query.filter_by(
        org_secure_code=org.secure_code,
        module_code='form_workflow',
        is_deleted=False,
    ).count()
    assert count == 1


def test_seed_missing_role_skipped_without_error(app, db_session):
    """宣告的角色在企業內不存在時記 warning 跳過，不拋錯"""
    org = _create_org()
    module = _fake_module(acl_roles=['NO_SUCH_ROLE'])

    result = ModuleAccessService.seed_org_module_acl(org.secure_code, module)

    assert result['acl_created'] == 0
    assert result['acl_skipped'] == 1


def test_seed_resolves_role_within_org_only(app, db_session):
    """roles.code 跨企業不唯一：只能綁到自己企業的角色 secure_code"""
    org_a = _create_org('ACLORGA')
    org_b = _create_org('ACLORGB')
    role_a = _create_role(org_a, 'FLOW_DESIGNER')
    role_b = _create_role(org_b, 'FLOW_DESIGNER')
    module = _fake_module(acl_roles=['FLOW_DESIGNER'])

    ModuleAccessService.seed_org_module_acl(org_b.secure_code, module)

    record = ModuleAccessControl.query.filter_by(
        org_secure_code=org_b.secure_code,
        module_code='form_workflow',
        is_deleted=False,
    ).one()
    assert record.target_secure_code == role_b.secure_code
    assert record.target_secure_code != role_a.secure_code


# ---------------------------------------------------------------------------
# ModuleRoleService 掛載點：只宣告 default_acl_roles 的模組不能被 early return 跳過
# ---------------------------------------------------------------------------

def test_seed_org_module_roles_handles_acl_only_module(app, db_session):
    org = _create_org()
    _create_role(org, 'FLOW_DESIGNER')
    module = _fake_module(acl_roles=['FLOW_DESIGNER'])

    result = ModuleRoleService.seed_org_module_roles(org.secure_code, module)

    assert result['acl_created'] == 1
    assert result['roles_created'] == 0
