from io import BytesIO

from app import db
from app.models import HolidayCalendar, HolidayCalendarSource, Organization, UserType, WorkSchedule
from app.services import holiday_calendar_service as svc


PREFIX = '/beakplatform/api/admin/holiday-calendars'


def _schedule(org):
    row = WorkSchedule(
        org_secure_code=org.secure_code,
        schedule_code='STD',
        name='Standard',
        timezone='Asia/Taipei',
        weekly_hours={'mon': ['09:00-12:00'], 'tue': ['09:00-12:00'], 'wed': ['09:00-12:00'], 'thu': ['09:00-12:00'], 'fri': ['09:00-12:00'], 'sat': None, 'sun': None},
        is_default=True,
        is_active=True,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _calendar(org):
    cal = svc.create_or_replace_draft(org, HolidayCalendarSource.CUSTOM, [
        {'entry_date': __import__('datetime').date(2026, 1, 1), 'holiday_type': 'HOLIDAY', 'work_periods': None, 'description': 'New Year'}
    ], name='Custom')
    db.session.commit()
    return cal


def test_calendar_crud_and_entries(admin_client, test_org):
    cal = _calendar(test_org)
    listed = admin_client.get(f'{PREFIX}/').get_json()
    assert listed['success'] is True
    assert listed['data'][0]['draft_count'] == 1
    detail = admin_client.get(f'{PREFIX}/{cal.secure_code}').get_json()
    assert detail['data']['draft_entries'][0]['description'] == 'New Year'
    renamed = admin_client.put(f'{PREFIX}/{cal.secure_code}', json={'name': 'Renamed', 'note': 'Note'}).get_json()
    assert renamed['data']['name'] == 'Renamed'
    added = admin_client.post(f'{PREFIX}/{cal.secure_code}/draft-entries', json={'entry_date': '2026-01-02', 'holiday_type': 'COMP_OFF', 'description': '補假'}).get_json()
    assert added['success'] is True
    entry_sc = added['data']['secure_code']
    updated = admin_client.put(f'{PREFIX}/{cal.secure_code}/draft-entries/{entry_sc}', json={'entry_date': '2026-01-03', 'holiday_type': 'WORKDAY', 'work_periods': ['09:00-12:00']}).get_json()
    assert updated['data']['holiday_type'] == 'WORKDAY'
    assert admin_client.delete(f'{PREFIX}/{cal.secure_code}/draft-entries/{entry_sc}').status_code == 200
    assert admin_client.delete(f'{PREFIX}/{cal.secure_code}').status_code == 200


def test_fetch_taiwan_success_and_failure(admin_client, monkeypatch):
    class Resp:
        status_code = 200
        content = '[{"date":"20260101","week":"四","isHoliday":true,"description":"開國紀念日"}]'.encode('utf-8')
    monkeypatch.setattr(svc.requests, 'get', lambda *args, **kwargs: Resp())
    ok = admin_client.post(f'{PREFIX}/fetch-taiwan', json={'year': 2026})
    assert ok.status_code == 201
    assert ok.get_json()['data']['draft_count'] == 1

    class Bad:
        status_code = 404
        content = b''
    monkeypatch.setattr(svc.requests, 'get', lambda *args, **kwargs: Bad())
    bad = admin_client.post(f'{PREFIX}/fetch-taiwan', json={'year': 2027})
    assert bad.status_code == 502
    assert bad.get_json()['error'] == 'fetch_failed'


def test_import_multipart_csv_success_and_bad_file(admin_client):
    data = {
        'source': 'CUSTOM',
        'name': 'Uploaded',
        'file': (BytesIO(b'date,type,description,work_periods\n20260101,HOLIDAY,New Year,\n'), 'holidays.csv'),
    }
    ok = admin_client.post(f'{PREFIX}/import', data=data, content_type='multipart/form-data')
    assert ok.status_code == 201
    bad = admin_client.post(f'{PREFIX}/import', data={
        'source': 'CUSTOM',
        'name': 'Bad',
        'file': (BytesIO(b'bad'), 'bad.csv'),
    }, content_type='multipart/form-data')
    assert bad.status_code == 400
    assert bad.get_json()['error'] == 'parse_failed'


def test_employee_forbidden(auth_client, test_user):
    test_user.user_type = UserType.EMPLOYEE
    db.session.commit()
    assert auth_client.get(f'{PREFIX}/').status_code == 403


def test_other_org_404_and_delete_published_rejected(admin_client, test_org):
    cal = _calendar(test_org)
    other = Organization(code='OTHER', name='Other', domain_name='other.local', is_active=True, is_deleted=False)
    db.session.add(other)
    db.session.flush()
    other_cal = svc.create_or_replace_draft(other, HolidayCalendarSource.CUSTOM, [
        {'entry_date': __import__('datetime').date(2026, 1, 1), 'holiday_type': 'HOLIDAY', 'work_periods': None, 'description': 'x'}
    ], name='Other')
    db.session.commit()
    assert admin_client.get(f'{PREFIX}/{other_cal.secure_code}').status_code == 404
    assert admin_client.post(f'{PREFIX}/fetch-taiwan', json={'year': 1999}).status_code == 400
    sched = _schedule(test_org)
    assert admin_client.post(f'{PREFIX}/{cal.secure_code}/publish', json={'schedule_secure_codes': [sched.secure_code]}).status_code == 200
    deleted = admin_client.delete(f'{PREFIX}/{cal.secure_code}')
    assert deleted.status_code == 400
    assert deleted.get_json()['error'] == 'published'


def test_import_rejects_oversized_upload_with_413(admin_client, monkeypatch):
    import app.api.holiday_calendars as api_module
    monkeypatch.setattr(api_module, 'MAX_UPLOAD_BYTES', 10)
    resp = admin_client.post(f'{PREFIX}/import', data={
        'source': 'CUSTOM',
        'name': 'Big',
        'file': (BytesIO(b'date,type,description,work_periods\n20260101,HOLIDAY,New Year,\n'), 'big.csv'),
    }, content_type='multipart/form-data')
    assert resp.status_code == 413
    assert resp.get_json()['error'] == 'file_too_large'


def test_import_bad_header_message_is_translated_text(admin_client):
    resp = admin_client.post(f'{PREFIX}/import', data={
        'source': 'CUSTOM',
        'name': 'Bad header',
        'file': (BytesIO(b'day,kind\n2026-01-01,HOLIDAY\n'), 'bad.csv'),
    }, content_type='multipart/form-data')
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload['error'] == 'parse_failed'
    assert 'date,type,description,work_periods' in payload['message']
