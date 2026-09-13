"""系統企業出廠預設班表（PF-xx，2026-09-13 Ethan 定案）。

ScheduleService.ensure_default_schedule() 此前對 is_system_org 提早 return None，
而 ensure_system_org() 直接建構 Organization、不走 OrganizationService.create_organization()，
所以全新安裝的系統企業一張班表都沒有。這裡驗證：拿掉早退之後，系統企業也能拿到
一張當地時區（Asia/Taipei）、週休二日的預設班表，且呼叫兩次仍只有一張（冪等）。
"""
from app import db
from app.models import Organization, WorkSchedule
from app.services.schedule_service import ScheduleService


def _make_system_org():
    org = Organization(
        secure_code='sys_org_schedule_test',
        code='SYSTEM',
        name='系統企業',
        domain_name='sys-schedule.example',
        is_system_org=True,
        is_active=True,
        is_deleted=False,
    )
    db.session.add(org)
    db.session.commit()
    return org


def test_ensure_default_schedule_creates_schedule_for_system_org(app):
    org = _make_system_org()

    schedule = ScheduleService.ensure_default_schedule(org)
    db.session.commit()

    assert schedule is not None
    assert schedule.org_secure_code == org.secure_code
    assert schedule.is_default is True
    assert schedule.timezone == 'Asia/Taipei'

    weekly_hours = schedule.weekly_hours
    # 台灣（org 未設定 country，回退 DEFAULT_SETTINGS 的 TW）預設週休二日：
    # 週六、週日沒有工作時段，週一到週五有。
    assert weekly_hours['sat'] is None
    assert weekly_hours['sun'] is None
    for day_key in ('mon', 'tue', 'wed', 'thu', 'fri'):
        assert weekly_hours[day_key], f'{day_key} 應有工作時段'

    assert WorkSchedule.query.filter_by(
        org_secure_code=org.secure_code, is_deleted=False
    ).count() == 1


def test_ensure_default_schedule_is_idempotent_for_system_org(app):
    org = _make_system_org()

    first = ScheduleService.ensure_default_schedule(org)
    db.session.commit()

    second = ScheduleService.ensure_default_schedule(org)
    db.session.commit()

    assert second.secure_code == first.secure_code
    assert WorkSchedule.query.filter_by(
        org_secure_code=org.secure_code, is_deleted=False
    ).count() == 1
