from app import db
from app.models import CustomerType, Organization, WorkSchedule
from app.services.organization_service import OrganizationService
from app.services.schedule_service import ScheduleService


def test_create_organization_seeds_default_schedule(app):
    org, admin = OrganizationService.create_organization(
        code='seedorg',
        name='Seed Org',
        domain_name='seed.example',
        customer_type=CustomerType.TRIAL,
        create_admin=False,
    )
    db.session.commit()

    assert admin is None
    schedules = WorkSchedule.query.filter_by(
        org_secure_code=org.secure_code,
        is_default=True,
        is_deleted=False,
    ).all()
    assert len(schedules) == 1
    assert schedules[0].schedule_code == 'DEFAULT'
    assert schedules[0].weekly_hours['sat'] is None
    assert schedules[0].weekly_hours['sun'] is None


def test_ensure_default_schedule_is_idempotent(test_org):
    first = ScheduleService.ensure_default_schedule(test_org)
    second = ScheduleService.ensure_default_schedule(test_org)
    db.session.commit()

    assert second.secure_code == first.secure_code
    assert WorkSchedule.query.filter_by(
        org_secure_code=test_org.secure_code,
        is_default=True,
        is_deleted=False,
    ).count() == 1


def test_ensure_default_schedule_uses_country_weekend(test_org):
    test_org.set_setting('country', 'SA')
    schedule = ScheduleService.ensure_default_schedule(test_org)
    db.session.commit()

    assert schedule.weekly_hours['fri'] is None
    assert schedule.weekly_hours['sat'] is None
    assert schedule.weekly_hours['sun'] == ['09:00-12:00', '13:00-18:00']


def test_ensure_default_schedule_avoids_existing_default_code(test_org):
    db.session.add(WorkSchedule(
        org_secure_code=test_org.secure_code,
        schedule_code='DEFAULT',
        name='Existing Non Default',
        timezone='Asia/Taipei',
        weekly_hours={'mon': ['09:00-12:00']},
        is_default=False,
        is_active=True,
    ))
    db.session.flush()

    schedule = ScheduleService.ensure_default_schedule(test_org)
    db.session.commit()

    assert schedule.schedule_code == 'DEFAULT-2'
    assert schedule.is_default is True


def test_ensure_default_schedule_also_creates_for_system_org(app):
    """2026-09-13 起系統企業不再提早 return None，也要有一張預設班表（定案）。"""
    org = Organization(
        code='SYSTEM_TEST',
        name='System Test',
        domain_name='system-test.local',
        is_active=True,
        is_deleted=False,
        is_system_org=True,
    )
    db.session.add(org)
    db.session.flush()

    schedule = ScheduleService.ensure_default_schedule(org)
    db.session.commit()

    assert schedule is not None
    assert schedule.is_default is True
    assert schedule.weekly_hours['sat'] is None
    assert schedule.weekly_hours['sun'] is None
    assert WorkSchedule.query.filter_by(
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).count() == 1
