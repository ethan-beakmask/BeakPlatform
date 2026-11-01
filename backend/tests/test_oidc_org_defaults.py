"""OIDC organization defaults and protected project group tests."""
from app import db
from app.models import OrganizationalUnit, Role, UserRoleAssignment, UnitType
from app.services.oidc_org_defaults import (
    ensure_projects_group_class,
    ensure_scribe_org_defaults,
)
from app.services.organization_service import OrganizationService


APP_PREFIX = '/beakplatform'


def test_projects_group_class_is_idempotent_and_has_required_fields(app, test_org):
    first = ensure_projects_group_class(test_org)
    second = ensure_projects_group_class(test_org)
    db.session.commit()

    rows = OrganizationalUnit.query.filter_by(
        org_secure_code=test_org.secure_code,
        code='PROJECTS_GROUPCLASS',
        is_deleted=False,
    ).all()
    assert first is second
    assert len(rows) == 1
    assert rows[0].unit_type == UnitType.GROUP
    assert rows[0].parent_secure_code is None
    assert rows[0].name == '專案類'
    assert rows[0].description == '專案群組的上層分類；專案群組建立在它下面'
    assert rows[0].is_system_unit is True
    assert rows[0].is_active is True
    assert rows[0].full_path == '/專案類'


def test_new_organization_includes_projects_group_class(app):
    org, _ = OrganizationService.create_organization(
        code='OIDC_NEW',
        name='OIDC New Organization',
        domain_name='oidc-new.local',
        admin_password='StrongPassword123!',
    )
    db.session.commit()

    assert OrganizationalUnit.query.filter_by(
        org_secure_code=org.secure_code,
        code='PROJECTS_GROUPCLASS',
        is_deleted=False,
    ).count() == 1


def test_projects_group_protection_is_specific_to_project_class(
    app, admin_client, test_org
):
    project = ensure_projects_group_class(test_org)
    external = OrganizationalUnit(
        org_secure_code=test_org.secure_code,
        unit_type=UnitType.GROUP,
        code='EXTERNAL_VENDORS',
        name='External',
        is_system_unit=True,
        is_active=True,
    )
    external.update_full_path()
    db.session.add(external)
    db.session.commit()

    move = admin_client.put(
        f'{APP_PREFIX}/api/units/{project.secure_code}', json={'parent_id': None})
    disable = admin_client.put(
        f'{APP_PREFIX}/api/units/{project.secure_code}', json={'is_active': False})
    rename = admin_client.put(
        f'{APP_PREFIX}/api/units/{project.secure_code}', json={'name': '專案分類'})
    external_disable = admin_client.put(
        f'{APP_PREFIX}/api/units/{external.secure_code}', json={'is_active': False})

    assert move.status_code == 400
    assert disable.status_code == 400
    assert rename.status_code == 200
    assert rename.get_json()['unit']['name'] == '專案分類'
    assert external_disable.status_code == 200
    assert external_disable.get_json()['unit']['is_active'] is False


def test_scribe_defaults_are_idempotent_without_assignments(app, test_org):
    first = ensure_scribe_org_defaults(test_org)
    second = ensure_scribe_org_defaults(test_org)
    db.session.commit()

    roles = Role.query.filter_by(
        org_secure_code=test_org.secure_code,
        code='SCRIBE_ADMIN',
        is_deleted=False,
    ).all()
    assert first is second
    assert len(roles) == 1
    assert roles[0].name == 'BeakScribe 筆記管理員'
    assert roles[0].is_manager is False
    assert roles[0].is_system_role is True
    assert UserRoleAssignment.query.filter_by(
        org_secure_code=test_org.secure_code,
        role_secure_code=roles[0].secure_code,
    ).count() == 0
