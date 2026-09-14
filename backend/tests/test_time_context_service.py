"""TimeContext 起步（PF-229 第三期第 3 項）：who_on_duty / who_on_leave / snapshot 與 ORG_ADMIN 專用 API。"""
from datetime import date, datetime

from app import db
from app.models import Organization, ScheduleAdjustment, User, UserType, WorkSchedule
from app.services.calendar_event_service import CalendarEventService
from app.services.time_context_service import TimeContextService


# 台北 2026-09-08（週二）10:00 / 14:00 / 17:00 / 20:00 與週六 10:00 → naive UTC
TUE_10 = datetime(2026, 9, 8, 2, 0)
TUE_14 = datetime(2026, 9, 8, 6, 0)
TUE_17 = datetime(2026, 9, 8, 9, 0)
TUE_20 = datetime(2026, 9, 8, 12, 0)
SAT_10 = datetime(2026, 9, 12, 2, 0)


def _schedule(org):
    schedule = WorkSchedule(
        secure_code=f'tc_sched_{org.secure_code[-8:]}',
        org_secure_code=org.secure_code,
        schedule_code='TC_STD',
        name='TimeContext Standard',
        timezone='Asia/Taipei',
        weekly_hours={
            'mon': ['09:00-12:00', '13:00-18:00'],
            'tue': ['09:00-12:00', '13:00-18:00'],
            'wed': ['09:00-12:00', '13:00-18:00'],
            'thu': ['09:00-12:00', '13:00-18:00'],
            'fri': ['09:00-12:00', '13:00-18:00'],
            'sat': None,
            'sun': None,
        },
        is_default=True,
        is_active=True,
    )
    db.session.add(schedule)
    db.session.commit()
    return schedule


def _user(sc, org, username, name, user_type=UserType.EMPLOYEE, is_active=True, is_service_account=False):
    user = User(
        secure_code=sc,
        org_secure_code=org.secure_code,
        username=username,
        email=f'{username}@example.com',
        display_name=name,
        user_type=user_type,
        is_active=is_active,
        is_deleted=False,
        is_service_account=is_service_account,
    )
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()
    return user


def _setup(test_org, test_user, test_admin):
    test_org.set_setting('timezone', 'Asia/Taipei')
    db.session.commit()
    _schedule(test_org)
    alice = test_user
    alice.display_name = 'Alice'
    bob = _user('tc_bob_000000000001', test_org, 'tc-bob', 'Bob')
    _user('tc_vendor_00000000001', test_org, 'tc-vendor', 'Vendor', user_type=UserType.EXTERNAL)
    _user('tc_dormant_0000000001', test_org, 'tc-dormant', 'Dormant', is_active=False)
    _user('tc_svc_0000000000001', test_org, 'tc-svc', 'Svc', is_service_account=True)
    other = Organization(
        secure_code='tc_other_org_00000001',
        code='TC_OTHER',
        name='Other',
        domain_name='tc-other.local',
        is_active=True,
        is_deleted=False,
    )
    db.session.add(other)
    db.session.commit()
    _user('tc_stranger_000000001', other, 'tc-stranger', 'Stranger')
    db.session.commit()
    return alice, bob


def _codes(items):
    return [item['secure_code'] for item in items]


def test_on_duty_lists_internal_active_members_only(test_org, test_user, test_admin):
    alice, bob = _setup(test_org, test_user, test_admin)

    on_duty = TimeContextService.who_on_duty(test_org, TUE_10)
    on_leave = TimeContextService.who_on_leave(test_org, TUE_10)

    assert _codes(on_duty) == [alice.secure_code, bob.secure_code, test_admin.secure_code]
    assert [item['display_name'] for item in on_duty] == ['Alice', 'Bob', 'Test Admin']
    assert on_leave == []
    assert not {'tc_vendor_00000000001', 'tc_dormant_0000000001', 'tc_svc_0000000000001', 'tc_stranger_000000001'} & set(_codes(on_duty))


def test_calendar_leave_moves_member_from_duty_to_leave_only_during_the_event(test_org, test_user, test_admin):
    alice, bob = _setup(test_org, test_user, test_admin)
    CalendarEventService.create(test_org, alice, {
        'calendar_kind': 'PERSONAL', 'event_type': 'LEAVE', 'title': 'Dentist', 'all_day': False,
        'start': '2026-09-08T09:00', 'end': '2026-09-08T12:00', 'visibility': 'PRIVATE',
    })
    db.session.commit()

    leave_10 = TimeContextService.who_on_leave(test_org, TUE_10)
    duty_10 = TimeContextService.who_on_duty(test_org, TUE_10)
    leave_14 = TimeContextService.who_on_leave(test_org, TUE_14)
    duty_14 = TimeContextService.who_on_duty(test_org, TUE_14)

    assert _codes(leave_10) == [alice.secure_code]
    assert leave_10[0]['source'] == 'calendar' and leave_10[0]['until_local'] == '2026-09-08T12:00'
    assert alice.secure_code not in _codes(duty_10) and bob.secure_code in _codes(duty_10)
    assert leave_14 == [] and alice.secure_code in _codes(duty_14)


def test_manual_leave_row_counts_as_whole_day(test_org, test_user, test_admin):
    alice, bob = _setup(test_org, test_user, test_admin)
    db.session.add(ScheduleAdjustment(
        org_secure_code=test_org.secure_code,
        user_secure_code=bob.secure_code,
        adjust_date=date(2026, 9, 8),
        adjust_type='LEAVE',
        status='APPROVED',
        calendar_event_secure_code=None,
        adjusted_periods=None,
    ))
    db.session.commit()

    leave_10 = TimeContextService.who_on_leave(test_org, TUE_10)
    leave_17 = TimeContextService.who_on_leave(test_org, TUE_17)

    assert _codes(leave_10) == [bob.secure_code] and _codes(leave_17) == [bob.secure_code]
    assert leave_10[0]['source'] == 'manual' and leave_10[0]['until_local'] == '2026-09-09T00:00'
    assert bob.secure_code not in _codes(TimeContextService.who_on_duty(test_org, TUE_10))


def test_nobody_on_duty_after_hours_or_on_weekend(test_org, test_user, test_admin):
    _setup(test_org, test_user, test_admin)

    assert TimeContextService.who_on_duty(test_org, TUE_20) == []
    assert TimeContextService.who_on_duty(test_org, SAT_10) == []


def test_duty_uses_org_timezone_for_local_conversion(test_org, test_user, test_admin):
    _setup(test_org, test_user, test_admin)
    assert TimeContextService.who_on_duty(test_org, TUE_10) != []

    test_org.set_setting('timezone', 'America/New_York')   # UTC 02:00 → 紐約前一天 22:00
    db.session.commit()

    snap = TimeContextService.snapshot(test_org, TUE_10)
    assert snap['who_on_duty'] == []
    assert snap['timezone'] == 'America/New_York' and snap['instant_local'] == '2026-09-07T22:00'


def test_snapshot_fields_and_default_instant(test_org, test_user, test_admin):
    _setup(test_org, test_user, test_admin)

    snap = TimeContextService.snapshot(test_org, TUE_10)
    now_snap = TimeContextService.snapshot(test_org, None)

    assert snap['instant_utc'] == '2026-09-08T02:00:00' and snap['instant_local'] == '2026-09-08T10:00'
    assert snap['timezone'] == 'Asia/Taipei'
    assert datetime.fromisoformat(snap['computed_at']) is not None
    assert set(now_snap) == {'instant_utc', 'instant_local', 'timezone', 'who_on_duty', 'who_on_leave', 'computed_at'}


def test_api_is_admin_only_and_parses_local_at(admin_client, test_org, test_user, test_admin):
    _setup(test_org, test_user, test_admin)

    ok = admin_client.get('/beakplatform/api/calendar/time-context?at=2026-09-08T10:00')
    bad = admin_client.get('/beakplatform/api/calendar/time-context?at=2026/09/08')

    assert ok.status_code == 200
    body = ok.get_json()
    assert body['success'] is True and body['instant_local'] == '2026-09-08T10:00'
    assert _codes(body['who_on_duty']) == _codes(TimeContextService.who_on_duty(test_org, TUE_10))
    assert bad.status_code == 400 and bad.get_json()['error'] == 'invalid_at'


def test_api_rejects_employee(auth_client, test_org, test_user, test_admin):
    _setup(test_org, test_user, test_admin)

    employee = auth_client.get('/beakplatform/api/calendar/time-context')

    assert employee.status_code == 403


def test_api_rejects_anonymous(client):
    anonymous = client.get('/beakplatform/api/calendar/time-context')

    assert anonymous.status_code in (302, 401)
