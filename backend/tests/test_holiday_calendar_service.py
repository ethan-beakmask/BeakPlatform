from datetime import date

import pytest

from app import db
from app.models import (
    HolidayCalendarEntry,
    HolidayCalendarSource,
    HolidayCalendarStatus,
    HolidayEntryStage,
    ScheduleAdjustment,
    ScheduleHoliday,
    User,
    WorkSchedule,
)
from app.services import holiday_calendar_service as svc
from app.services.holiday_calendar_service import HolidayCalendarError


def _schedule(org, code, name='Standard', weekly=None, is_default=False):
    row = WorkSchedule(
        org_secure_code=org.secure_code,
        schedule_code=code,
        name=name,
        timezone='Asia/Taipei',
        weekly_hours=weekly or {
            'mon': ['09:00-12:00'], 'tue': ['09:00-12:00'], 'wed': ['09:00-12:00'],
            'thu': ['09:00-12:00'], 'fri': ['09:00-12:00'], 'sat': None, 'sun': None,
        },
        is_default=is_default,
        is_active=True,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _entries():
    return [
        {'entry_date': date(2026, 1, 1), 'holiday_type': 'HOLIDAY', 'work_periods': None, 'description': '元旦'},
        {'entry_date': date(2026, 1, 2), 'holiday_type': 'COMP_OFF', 'work_periods': None, 'description': '補假'},
        {'entry_date': date(2026, 1, 3), 'holiday_type': 'WORKDAY', 'work_periods': None, 'description': '補班'},
    ]


def test_parse_taiwan_gov_json_rules():
    raw = '''[
      {"date":"20260103","week":"六","isHoliday":true,"description":""},
      {"date":"20260102","week":"五","isHoliday":true,"description":"補假"},
      {"date":"20260101","week":"四","isHoliday":true,"description":"開國紀念日"},
      {"date":"20260214","week":"六","isHoliday":true,"description":"春節"},
      {"date":"20260110","week":"六","isHoliday":false,"description":""},
      {"date":"20260105","week":"一","isHoliday":false,"description":""}
    ]'''.encode('utf-8')
    rows = svc.parse_taiwan_gov_json(raw)
    assert [(r['entry_date'], r['holiday_type'], r['description']) for r in rows] == [
        (date(2026, 1, 1), 'HOLIDAY', '開國紀念日'),
        (date(2026, 1, 2), 'COMP_OFF', '補假'),
        (date(2026, 1, 10), 'WORKDAY', '補班'),
        (date(2026, 2, 14), 'HOLIDAY', '春節'),
    ]
    with pytest.raises(HolidayCalendarError) as exc:
        svc.parse_taiwan_gov_json(b'{}')
    assert exc.value.code == 'parse_failed'


def test_parse_custom_upload_csv_and_fail_closed():
    raw = b'date,type,description,work_periods\n20260101,holiday,New Year,\n2026-01-03,workday,Make up,09:00-12:00|13:00-17:00\n'
    rows = svc.parse_custom_upload(raw, 'x.csv')
    assert rows[1]['work_periods'] == ['09:00-12:00', '13:00-17:00']
    with pytest.raises(HolidayCalendarError) as exc:
        svc.parse_custom_upload(b'date,type,description,work_periods\nbad,HOLIDAY,x,\n', 'bad.csv')
    assert exc.value.code == 'parse_failed'
    assert exc.value.detail == {'reason': 'bad_row', 'line': 2}
    with pytest.raises(HolidayCalendarError):
        svc.parse_custom_upload(b'date,type,description,work_periods\n', 'empty.csv')
    with pytest.raises(HolidayCalendarError):
        svc.parse_custom_upload(b'date,type,description,work_periods\n20260101,HOLIDAY,x,\n20260101,HOLIDAY,y,\n', 'dup.csv')


def test_create_or_replace_draft_preserves_published_and_custom_year(test_org):
    cal = svc.create_or_replace_draft(test_org, HolidayCalendarSource.TW_GOV, _entries(), year=2026, source_ref='url')
    db.session.flush()
    svc.publish(test_org, cal, [_schedule(test_org, 'STD').secure_code])
    db.session.flush()
    published_count = HolidayCalendarEntry.query.filter_by(calendar_secure_code=cal.secure_code, stage=HolidayEntryStage.PUBLISHED).count()
    svc.create_or_replace_draft(test_org, HolidayCalendarSource.TW_GOV, [_entries()[0]], year=2026, source_ref='url2')
    assert HolidayCalendarEntry.query.filter_by(calendar_secure_code=cal.secure_code, stage=HolidayEntryStage.DRAFT).count() == 1
    assert HolidayCalendarEntry.query.filter_by(calendar_secure_code=cal.secure_code, stage=HolidayEntryStage.PUBLISHED).count() == published_count

    custom = svc.create_or_replace_draft(test_org, HolidayCalendarSource.CUSTOM, _entries()[:2], name='Custom')
    assert custom.year == 2026
    mixed = svc.create_or_replace_draft(test_org, HolidayCalendarSource.CUSTOM, [_entries()[0], {'entry_date': date(2027, 1, 1), 'holiday_type': 'HOLIDAY', 'work_periods': None, 'description': 'x'}], name='Mixed')
    assert mixed.year is None


def test_publish_priority_workday_and_retarget(test_org):
    a = _schedule(test_org, 'A', is_default=True)
    b = _schedule(test_org, 'B')
    db.session.add(ScheduleHoliday(schedule_secure_code=a.secure_code, holiday_date=date(2026, 1, 1), holiday_type='HOLIDAY', description='Manual'))
    tw = svc.create_or_replace_draft(test_org, HolidayCalendarSource.TW_GOV, _entries(), year=2026)
    custom = svc.create_or_replace_draft(test_org, HolidayCalendarSource.CUSTOM, [{'entry_date': date(2026, 1, 2), 'holiday_type': 'HOLIDAY', 'work_periods': None, 'description': 'Custom'}], name='Custom')
    db.session.flush()
    s1 = svc.publish(test_org, tw, [a.secure_code])
    assert s1['targets'][0]['skipped_manual'] == 1
    workday = ScheduleHoliday.query.filter_by(schedule_secure_code=a.secure_code, holiday_date=date(2026, 1, 3), holiday_calendar_secure_code=tw.secure_code, is_deleted=False).first()
    assert workday.work_periods == ['09:00-12:00']
    svc.publish(test_org, custom, [a.secure_code])
    assert ScheduleHoliday.query.filter_by(schedule_secure_code=a.secure_code, holiday_date=date(2026, 1, 2), holiday_calendar_secure_code=custom.secure_code, is_deleted=False).count() == 1
    lower = svc.publish(test_org, tw, [a.secure_code])
    assert lower['targets'][0]['skipped_lower_priority'] == 1
    svc.publish(test_org, tw, [b.secure_code])
    assert ScheduleHoliday.query.filter_by(schedule_secure_code=a.secure_code, holiday_calendar_secure_code=tw.secure_code, is_deleted=False).count() == 0
    assert ScheduleHoliday.query.filter_by(schedule_secure_code=b.secure_code, holiday_calendar_secure_code=tw.secure_code, is_deleted=False).count() > 0


def test_publish_skips_workday_when_no_periods(test_org):
    empty = _schedule(test_org, 'EMPTY', weekly={'mon': None, 'tue': None, 'wed': None, 'thu': None, 'fri': None, 'sat': None, 'sun': None})
    cal = svc.create_or_replace_draft(test_org, HolidayCalendarSource.CUSTOM, [{'entry_date': date(2026, 1, 3), 'holiday_type': 'WORKDAY', 'work_periods': None, 'description': '補班'}], name='No periods')
    summary = svc.publish(test_org, cal, [empty.secure_code])
    assert summary['targets'][0]['skipped_no_periods'] == 1


def test_unpublish_and_delete_calendar(test_org):
    schedule = _schedule(test_org, 'STD')
    cal = svc.create_or_replace_draft(test_org, HolidayCalendarSource.CUSTOM, _entries()[:1], name='Custom')
    other = svc.create_or_replace_draft(test_org, HolidayCalendarSource.CUSTOM, [{'entry_date': date(2026, 1, 2), 'holiday_type': 'HOLIDAY', 'work_periods': None, 'description': 'Other'}], name='Other')
    db.session.flush()
    svc.publish(test_org, cal, [schedule.secure_code])
    svc.publish(test_org, other, [schedule.secure_code])
    with pytest.raises(HolidayCalendarError):
        svc.delete_calendar(test_org, cal)
    svc.unpublish(test_org, cal)
    assert cal.status == HolidayCalendarStatus.DRAFT
    assert ScheduleHoliday.query.filter_by(holiday_calendar_secure_code=other.secure_code, is_deleted=False).count() == 1
    svc.delete_calendar(test_org, cal)
    assert cal.is_deleted is True
    assert HolidayCalendarEntry.query.filter_by(calendar_secure_code=cal.secure_code).count() == 0


def test_publish_resyncs_leave_adjustments(test_org, test_user, monkeypatch):
    schedule = _schedule(test_org, 'STD', is_default=True)
    test_user.work_schedule_secure_code = None
    db.session.add(ScheduleAdjustment(
        org_secure_code=test_org.secure_code,
        user_secure_code=test_user.secure_code,
        adjust_date=date(2026, 1, 1),
        adjust_type='LEAVE',
        calendar_event_secure_code='event_sc',
        status='APPROVED',
    ))
    other = User(org_secure_code=test_org.secure_code, username='other', email='other@example.com', display_name='Other', is_active=True, is_deleted=False)
    other.set_password('password123')
    db.session.add(other)
    db.session.flush()
    calls = []
    monkeypatch.setattr('app.services.calendar_event_service.CalendarEventService.resync_leave_adjustments', lambda org, user_sc, dates: calls.append((org.secure_code, user_sc, dates)))
    cal = svc.create_or_replace_draft(test_org, HolidayCalendarSource.CUSTOM, _entries()[:1], name='Custom')
    svc.publish(test_org, cal, [schedule.secure_code])
    assert calls == [(test_org.secure_code, test_user.secure_code, {date(2026, 1, 1)})]


def test_reimport_into_calendar_of_other_source_is_rejected(test_org):
    gov = svc.create_or_replace_draft(test_org, HolidayCalendarSource.TW_GOV, _entries()[:1], year=2026)
    db.session.flush()
    with pytest.raises(HolidayCalendarError) as exc:
        svc.create_or_replace_draft(test_org, HolidayCalendarSource.CUSTOM, _entries()[:1], name='X', calendar=gov)
    assert exc.value.code == 'invalid_source'


def test_parse_csv_errors_carry_structured_detail():
    with pytest.raises(HolidayCalendarError) as exc:
        svc.parse_custom_upload(b'day,kind,description,work_periods\n', 'x.csv')
    assert exc.value.detail == {'reason': 'bad_header'}
    with pytest.raises(HolidayCalendarError) as exc:
        svc.parse_custom_upload(b'date,type,description,work_periods\n2026-01-01,HOLIDAY,a,\n2026-01-01,HOLIDAY,b,\n', 'x.csv')
    assert exc.value.detail == {'reason': 'duplicate_date', 'line': 3}
    with pytest.raises(HolidayCalendarError) as exc:
        svc.parse_custom_upload(b'date,type,description,work_periods\n2026-13-01,HOLIDAY,a,\n', 'x.csv')
    assert exc.value.detail == {'reason': 'bad_row', 'line': 2}
