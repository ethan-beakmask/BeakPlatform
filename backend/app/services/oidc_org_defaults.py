"""Idempotent organization defaults required by OIDC/BeakScribe."""
from app import db
from app.models import (
    OrganizationalUnit,
    Role,
    RoleType,
    ScopeType,
    UnitType,
)


def ensure_projects_group_class(org):
    existing = OrganizationalUnit.query.filter(
        OrganizationalUnit.org_secure_code == org.secure_code,
        OrganizationalUnit.code == 'PROJECTS_GROUPCLASS',
        OrganizationalUnit.is_deleted.is_(False),
    ).first()
    if existing is not None:
        return existing

    group = OrganizationalUnit(
        org_secure_code=org.secure_code,
        unit_type=UnitType.GROUP,
        code='PROJECTS_GROUPCLASS',
        name='專案類',
        description='專案群組的上層分類；專案群組建立在它下面',
        parent_secure_code=None,
        is_system_unit=True,
        is_active=True,
    )
    group.update_full_path()
    db.session.add(group)
    return group


def ensure_scribe_org_defaults(org):
    existing = Role.query.filter(
        Role.org_secure_code == org.secure_code,
        Role.code == 'SCRIBE_ADMIN',
        Role.is_deleted.is_(False),
    ).first()
    if existing is not None:
        return existing

    role = Role(
        org_secure_code=org.secure_code,
        role_type=RoleType.ROLE,
        scope_type=ScopeType.GLOBAL,
        code='SCRIBE_ADMIN',
        name='BeakScribe 筆記管理員',
        description='可處理 BeakScribe 中同企業離職者的資料轉移與刪除',
        is_manager=False,
        is_system_role=True,
        is_active=True,
    )
    role.update_full_path()
    db.session.add(role)
    return role
