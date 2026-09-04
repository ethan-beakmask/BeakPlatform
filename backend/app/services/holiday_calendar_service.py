"""Enterprise holiday calendar service."""
from __future__ import annotations

import csv
import io
import json
import logging
from datetime import date, datetime

import requests
from sqlalchemy import or_

from app import db
from app.models import (
    HolidayCalendar,
    HolidayCalendarEntry,
    HolidayCalendarSource,
    HolidayCalendarStatus,
    HolidayEntryStage,
    ScheduleAdjustment,
    ScheduleHoliday,
    User,
    WorkSchedule,
)
from app.utils.work_periods import validate_time_periods


logger = logging.getLogger(__name__)

TW_GOV_CALENDAR_URL = 'https://cdn.jsdelivr.net/gh/ruyut/TaiwanCalendar/data/{year}.json'
TW_GOV_DATASET_URL = 'https://data.gov.tw/dataset/14718'
TW_GOV_CURATOR_URL = 'https://github.com/ruyut/TaiwanCalendar'
DEFAULT_WORKDAY_DESCRIPTION = '補班'
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
HOLIDAY_TYPES = ('HOLIDAY', 'COMP_OFF', 'WORKDAY')
_DAY_KEYS = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')


class HolidayCalendarError(Exception):
    """code 是機器可讀裸字串；detail 是給 API 層組翻譯訊息用的結構（不含使用者文字）。"""

    def __init__(self, code: str, message: str | None = None, detail: dict | None = None):
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        self.detail = detail or {}


def parse_taiwan_gov_json(raw: bytes) -> list[dict]:
    try:
        payload = json.loads(raw.decode('utf-8-sig'))
    except Exception as exc:
        raise HolidayCalendarError('parse_failed') from exc
    if not isinstance(payload, list):
        raise HolidayCalendarError('parse_failed')

    entries = []
    for item in payload:
        if not isinstance(item, dict):
            raise HolidayCalendarError('parse_failed')
        raw_date = item.get('date')
        is_holiday = item.get('isHoliday')
        description = item.get('description')
        if (
            not isinstance(raw_date, str)
            or len(raw_date) != 8
            or not raw_date.isdigit()
            or not isinstance(is_holiday, bool)
            or not isinstance(description, str)
        ):
            raise HolidayCalendarError('parse_failed')
        try:
            entry_date = datetime.strptime(raw_date, '%Y%m%d').date()
        except ValueError as exc:
            raise HolidayCalendarError('parse_failed') from exc
        desc = description.strip()
        if is_holiday and desc == '補假':
            entries.append(_entry(entry_date, 'COMP_OFF', None, desc))
        elif is_holiday and desc:
            entries.append(_entry(entry_date, 'HOLIDAY', None, desc))
        elif is_holiday:
            continue
        elif entry_date.weekday() >= 5:
            entries.append(_entry(entry_date, 'WORKDAY', None, desc or DEFAULT_WORKDAY_DESCRIPTION))
    return sorted(entries, key=lambda row: row['entry_date'])


def parse_custom_upload(raw: bytes, filename: str) -> list[dict]:
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HolidayCalendarError('file_too_large')
    raw = raw.lstrip(b'\xef\xbb\xbf')
    if not raw.strip():
        raise HolidayCalendarError('parse_failed')
    if raw.lstrip()[:1] == b'[':
        entries = parse_taiwan_gov_json(raw)
        if not entries:
            raise HolidayCalendarError('parse_failed')
        _reject_duplicate_dates(entries)
        return entries

    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise HolidayCalendarError('parse_failed') from exc
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise HolidayCalendarError('parse_failed') from exc
    if [h.strip().lower() for h in header] != ['date', 'type', 'description', 'work_periods']:
        raise HolidayCalendarError('parse_failed', detail={'reason': 'bad_header'})

    entries = []
    seen = set()
    for line_no, row in enumerate(reader, start=2):
        if not row or all(not str(cell).strip() for cell in row):
            continue
        if len(row) != 4:
            raise HolidayCalendarError('parse_failed', detail={'reason': 'bad_columns', 'line': line_no})
        try:
            entry_date = _parse_upload_date(row[0].strip())
            holiday_type = row[1].strip().upper()
            if holiday_type not in HOLIDAY_TYPES:
                raise ValueError
            if entry_date in seen:
                raise HolidayCalendarError('parse_failed', detail={'reason': 'duplicate_date', 'line': line_no})
            seen.add(entry_date)
            work_periods = _parse_work_periods(row[3].strip()) if holiday_type == 'WORKDAY' else None
            entries.append(_entry(entry_date, holiday_type, work_periods, row[2].strip()))
        except HolidayCalendarError:
            raise
        except Exception as exc:
            raise HolidayCalendarError('parse_failed', detail={'reason': 'bad_row', 'line': line_no}) from exc
    if not entries:
        raise HolidayCalendarError('parse_failed')
    return sorted(entries, key=lambda row: row['entry_date'])


def fetch_taiwan_gov_calendar(year: int) -> bytes:
    if not isinstance(year, int) or year < 2000 or year > 2100:
        raise HolidayCalendarError('invalid_year')
    url = TW_GOV_CALENDAR_URL.format(year=year)
    try:
        response = requests.get(url, timeout=15)
    except requests.RequestException as exc:
        logger.warning('Taiwan calendar fetch failed: %s', exc.__class__.__name__)
        raise HolidayCalendarError('fetch_failed') from exc
    if response.status_code != 200:
        logger.warning('Taiwan calendar fetch failed: status=%s', response.status_code)
        raise HolidayCalendarError('fetch_failed')
    return response.content


def create_or_replace_draft(org, source, entries, *, year=None, name=None, source_ref=None, calendar=None) -> HolidayCalendar:
    if source not in HolidayCalendarSource.ALL:
        raise HolidayCalendarError('invalid_source')
    if not entries:
        raise HolidayCalendarError('parse_failed')
    if calendar is not None and calendar.source != source:
        raise HolidayCalendarError('invalid_source')
    if source == HolidayCalendarSource.TW_GOV:
        if not isinstance(year, int):
            raise HolidayCalendarError('invalid_year')
        calendar = calendar or HolidayCalendar.query.filter(
            HolidayCalendar.org_secure_code == org.secure_code,
            HolidayCalendar.source == HolidayCalendarSource.TW_GOV,
            HolidayCalendar.year == year,
            HolidayCalendar.is_deleted == False,  # noqa: E712
        ).first()
        if calendar is None:
            calendar = HolidayCalendar(
                org_secure_code=org.secure_code,
                source=source,
                year=year,
                name=name or f'{year} 台灣政府行政機關辦公日曆表',
                status=HolidayCalendarStatus.DRAFT,
                source_ref=source_ref,
            )
            db.session.add(calendar)
            db.session.flush()
        else:
            calendar.source_ref = source_ref or calendar.source_ref
    else:
        if calendar is None:
            clean_name = (name or '').strip()
            if not clean_name:
                raise HolidayCalendarError('name_required')
            years = {row['entry_date'].year for row in entries}
            calendar = HolidayCalendar(
                org_secure_code=org.secure_code,
                source=source,
                year=years.pop() if len(years) == 1 else None,
                name=clean_name,
                status=HolidayCalendarStatus.DRAFT,
                source_ref=source_ref,
            )
            db.session.add(calendar)
            db.session.flush()
        else:
            years = {row['entry_date'].year for row in entries}
            calendar.year = years.pop() if len(years) == 1 else None
            calendar.source_ref = source_ref or calendar.source_ref

    _replace_entries(org, calendar, HolidayEntryStage.DRAFT, entries)
    _decorate_calendar(calendar)
    return calendar


def rename(org, calendar, name, note):
    _assert_calendar_org(org, calendar)
    clean_name = (name or '').strip()
    if not clean_name:
        raise HolidayCalendarError('name_required')
    calendar.name = clean_name
    calendar.note = note
    return calendar


def add_draft_entry(org, calendar, payload: dict) -> HolidayCalendarEntry:
    _assert_calendar_org(org, calendar)
    data = _normalize_entry_payload(payload)
    existing = HolidayCalendarEntry.query.filter_by(
        calendar_secure_code=calendar.secure_code,
        stage=HolidayEntryStage.DRAFT,
        entry_date=data['entry_date'],
    ).first()
    if existing:
        raise HolidayCalendarError('duplicate_date')
    row = HolidayCalendarEntry(org_secure_code=org.secure_code, calendar_secure_code=calendar.secure_code, stage=HolidayEntryStage.DRAFT, **data)
    db.session.add(row)
    return row


def update_draft_entry(org, calendar, entry, payload: dict) -> HolidayCalendarEntry:
    _assert_calendar_org(org, calendar)
    if entry.calendar_secure_code != calendar.secure_code or entry.stage != HolidayEntryStage.DRAFT:
        raise HolidayCalendarError('not_found')
    data = _normalize_entry_payload(payload)
    existing = HolidayCalendarEntry.query.filter(
        HolidayCalendarEntry.calendar_secure_code == calendar.secure_code,
        HolidayCalendarEntry.stage == HolidayEntryStage.DRAFT,
        HolidayCalendarEntry.entry_date == data['entry_date'],
        HolidayCalendarEntry.secure_code != entry.secure_code,
    ).first()
    if existing:
        raise HolidayCalendarError('duplicate_date')
    entry.entry_date = data['entry_date']
    entry.holiday_type = data['holiday_type']
    entry.work_periods = data['work_periods']
    entry.description = data['description']
    return entry


def delete_draft_entry(org, calendar, entry) -> None:
    _assert_calendar_org(org, calendar)
    if entry.calendar_secure_code != calendar.secure_code or entry.stage != HolidayEntryStage.DRAFT:
        raise HolidayCalendarError('not_found')
    db.session.delete(entry)


def has_unpublished_changes(calendar) -> bool:
    rows = HolidayCalendarEntry.query.filter(
        HolidayCalendarEntry.calendar_secure_code == calendar.secure_code,
    ).all()
    draft = {_entry_key(r) for r in rows if r.stage == HolidayEntryStage.DRAFT}
    published = {_entry_key(r) for r in rows if r.stage == HolidayEntryStage.PUBLISHED}
    return draft != published


def publish(org, calendar, target_schedule_secure_codes: list[str]) -> dict:
    _assert_calendar_org(org, calendar)
    if not target_schedule_secure_codes:
        raise HolidayCalendarError('no_targets')
    targets = WorkSchedule.query.filter(
        WorkSchedule.org_secure_code == org.secure_code,
        WorkSchedule.secure_code.in_(target_schedule_secure_codes),
        WorkSchedule.is_deleted == False,  # noqa: E712
    ).all()
    by_sc = {row.secure_code: row for row in targets}
    if set(by_sc) != set(target_schedule_secure_codes):
        raise HolidayCalendarError('schedule_not_found')

    old_targets = list(calendar.published_targets or [])
    old_dates = {row.entry_date for row in _entries(calendar, HolidayEntryStage.PUBLISHED)}
    draft_entries = _entries(calendar, HolidayEntryStage.DRAFT)
    _replace_entries(org, calendar, HolidayEntryStage.PUBLISHED, [_entry_from_row(row) for row in draft_entries])
    published_entries = _entries(calendar, HolidayEntryStage.PUBLISHED)
    now = datetime.utcnow()
    ScheduleHoliday.query.filter(
        ScheduleHoliday.holiday_calendar_secure_code == calendar.secure_code,
        ScheduleHoliday.is_deleted == False,  # noqa: E712
    ).update({'is_deleted': True, 'deleted_at': now}, synchronize_session=False)

    summary_targets = []
    for sc in target_schedule_secure_codes:
        schedule = by_sc[sc]
        counts = {
            'schedule_secure_code': sc,
            'name': schedule.name,
            'inserted': 0,
            'replaced': 0,
            'skipped_manual': 0,
            'skipped_lower_priority': 0,
            'skipped_no_periods': 0,
        }
        for entry in published_entries:
            action = _publish_entry_to_schedule(org, calendar, schedule, entry, now)
            counts[action] += 1
        summary_targets.append(counts)

    calendar.status = HolidayCalendarStatus.PUBLISHED
    calendar.published_at = now
    calendar.published_targets = list(target_schedule_secure_codes)
    resynced = _resync_affected_leave_adjustments(org, set(old_targets) | set(target_schedule_secure_codes), old_dates | {row.entry_date for row in published_entries})
    return {'published_entries': len(published_entries), 'targets': summary_targets, 'resynced_users': resynced}


def unpublish(org, calendar) -> dict:
    _assert_calendar_org(org, calendar)
    if calendar.status != HolidayCalendarStatus.PUBLISHED:
        raise HolidayCalendarError('not_published')
    old_targets = list(calendar.published_targets or [])
    old_dates = {row.entry_date for row in _entries(calendar, HolidayEntryStage.PUBLISHED)}
    now = datetime.utcnow()
    removed = ScheduleHoliday.query.filter(
        ScheduleHoliday.holiday_calendar_secure_code == calendar.secure_code,
        ScheduleHoliday.is_deleted == False,  # noqa: E712
    ).update({'is_deleted': True, 'deleted_at': now}, synchronize_session=False)
    for row in _entries(calendar, HolidayEntryStage.PUBLISHED):
        db.session.delete(row)
    calendar.status = HolidayCalendarStatus.DRAFT
    calendar.published_at = None
    calendar.published_targets = None
    resynced = _resync_affected_leave_adjustments(org, set(old_targets), old_dates)
    return {'removed': removed, 'resynced_users': resynced}


def delete_calendar(org, calendar) -> None:
    _assert_calendar_org(org, calendar)
    if calendar.status != HolidayCalendarStatus.DRAFT:
        raise HolidayCalendarError('published')
    for row in list(calendar.entries):
        db.session.delete(row)
    calendar.is_deleted = True
    calendar.deleted_at = datetime.utcnow()


def decorate_calendars(calendars: list[HolidayCalendar]) -> list[HolidayCalendar]:
    for calendar in calendars:
        _decorate_calendar(calendar)
    return calendars


def _publish_entry_to_schedule(org, calendar, schedule, entry, now) -> str:
    all_rows = ScheduleHoliday.query.filter(
        ScheduleHoliday.schedule_secure_code == schedule.secure_code,
        ScheduleHoliday.holiday_date == entry.entry_date,
    ).all()
    existing_rows = [row for row in all_rows if not row.is_deleted]
    manual = [row for row in existing_rows if row.holiday_calendar_secure_code is None]
    if manual:
        return 'skipped_manual'
    target_row = None
    action = 'inserted'
    for row in existing_rows:
        if _source_priority(calendar.source) >= _source_priority(_calendar_source(org, row.holiday_calendar_secure_code)):
            target_row = row
            action = 'replaced'
        else:
            return 'skipped_lower_priority'
    work_periods = entry.work_periods
    if entry.holiday_type == 'WORKDAY' and not work_periods:
        work_periods = _default_work_periods(schedule)
        if not work_periods:
            return 'skipped_no_periods'
    if target_row is None:
        target_row = next((row for row in all_rows if row.is_deleted), None)
    if target_row is None:
        target_row = ScheduleHoliday(schedule_secure_code=schedule.secure_code, holiday_date=entry.entry_date)
        db.session.add(target_row)
    target_row.is_deleted = False
    target_row.deleted_at = None
    target_row.holiday_type = entry.holiday_type
    target_row.work_periods = work_periods if entry.holiday_type == 'WORKDAY' else None
    target_row.description = entry.description
    target_row.holiday_calendar_secure_code = calendar.secure_code
    return action


def _resync_affected_leave_adjustments(org, affected_schedule_scs: set[str], affected_dates: set[date]) -> int:
    if not affected_schedule_scs or not affected_dates:
        return 0
    default_schedule = WorkSchedule.query.filter(
        WorkSchedule.org_secure_code == org.secure_code,
        WorkSchedule.is_default == True,  # noqa: E712
        WorkSchedule.is_deleted == False,  # noqa: E712
    ).first()
    users_query = User.query.filter(
        User.org_secure_code == org.secure_code,
        User.is_deleted == False,  # noqa: E712
        User.is_active == True,  # noqa: E712
    )
    if default_schedule and default_schedule.secure_code in affected_schedule_scs:
        users_query = users_query.filter(or_(User.work_schedule_secure_code.in_(affected_schedule_scs), User.work_schedule_secure_code.is_(None)))
    else:
        users_query = users_query.filter(User.work_schedule_secure_code.in_(affected_schedule_scs))
    users = users_query.all()
    from app.services.calendar_event_service import CalendarEventService
    count = 0
    for user in users:
        rows = ScheduleAdjustment.query.filter(
            ScheduleAdjustment.org_secure_code == org.secure_code,
            ScheduleAdjustment.user_secure_code == user.secure_code,
            ScheduleAdjustment.calendar_event_secure_code.isnot(None),
            ScheduleAdjustment.adjust_type == 'LEAVE',
            ScheduleAdjustment.is_deleted == False,  # noqa: E712
            ScheduleAdjustment.adjust_date.in_(affected_dates),
        ).all()
        dates = {row.adjust_date for row in rows}
        if dates:
            CalendarEventService.resync_leave_adjustments(org, user.secure_code, dates)
            count += 1
    return count


def _replace_entries(org, calendar, stage, entries):
    for row in _entries(calendar, stage):
        db.session.delete(row)
    db.session.flush()
    for item in entries:
        db.session.add(HolidayCalendarEntry(
            org_secure_code=org.secure_code,
            calendar_secure_code=calendar.secure_code,
            stage=stage,
            entry_date=item['entry_date'],
            holiday_type=item['holiday_type'],
            work_periods=item.get('work_periods') if item['holiday_type'] == 'WORKDAY' else None,
            description=item.get('description'),
        ))
    db.session.flush()


def _entries(calendar, stage):
    return HolidayCalendarEntry.query.filter(
        HolidayCalendarEntry.calendar_secure_code == calendar.secure_code,
        HolidayCalendarEntry.stage == stage,
    ).order_by(HolidayCalendarEntry.entry_date.asc()).all()


def _decorate_calendar(calendar):
    rows = HolidayCalendarEntry.query.filter(HolidayCalendarEntry.calendar_secure_code == calendar.secure_code).all()
    calendar.draft_count = sum(1 for row in rows if row.stage == HolidayEntryStage.DRAFT)
    calendar.published_count = sum(1 for row in rows if row.stage == HolidayEntryStage.PUBLISHED)
    calendar.has_unpublished_changes = has_unpublished_changes(calendar)
    targets = calendar.published_targets or []
    if targets:
        schedules = WorkSchedule.query.filter(WorkSchedule.secure_code.in_(targets), WorkSchedule.is_deleted == False).all()  # noqa: E712
        name_by_sc = {row.secure_code: row.name for row in schedules}
        calendar.published_target_names = [name_by_sc[sc] for sc in targets if sc in name_by_sc]
    else:
        calendar.published_target_names = []


def _normalize_entry_payload(payload: dict) -> dict:
    try:
        entry_date = _parse_upload_date(str(payload.get('entry_date') or payload.get('holiday_date') or ''))
    except Exception as exc:
        raise HolidayCalendarError('invalid_date') from exc
    holiday_type = str(payload.get('holiday_type') or '').upper()
    if holiday_type not in HOLIDAY_TYPES:
        raise HolidayCalendarError('invalid_type')
    work_periods = payload.get('work_periods') if holiday_type == 'WORKDAY' else None
    if work_periods is not None and not validate_time_periods(work_periods):
        raise HolidayCalendarError('invalid_work_periods')
    description = (payload.get('description') or '').strip() or None
    return {'entry_date': entry_date, 'holiday_type': holiday_type, 'work_periods': work_periods, 'description': description}


def _parse_upload_date(value: str) -> date:
    value = value.strip()
    fmt = '%Y%m%d' if len(value) == 8 and value.isdigit() else '%Y-%m-%d'
    return datetime.strptime(value, fmt).date()


def _parse_work_periods(value: str):
    if not value:
        return None
    periods = [part.strip() for part in value.replace(';', '|').split('|') if part.strip()]
    if not validate_time_periods(periods):
        raise ValueError
    return periods


def _entry(entry_date, holiday_type, work_periods, description):
    return {'entry_date': entry_date, 'holiday_type': holiday_type, 'work_periods': work_periods, 'description': description}


def _entry_from_row(row):
    return _entry(row.entry_date, row.holiday_type, row.work_periods, row.description)


def _entry_key(row):
    return (row.entry_date, row.holiday_type, tuple(row.work_periods or []), row.description or '')


def _reject_duplicate_dates(entries):
    seen = set()
    for entry in entries:
        if entry['entry_date'] in seen:
            raise HolidayCalendarError('parse_failed')
        seen.add(entry['entry_date'])


def _assert_calendar_org(org, calendar):
    if not calendar or calendar.org_secure_code != org.secure_code or calendar.is_deleted:
        raise HolidayCalendarError('not_found')


def _source_priority(source):
    return 2 if source == HolidayCalendarSource.CUSTOM else 1


def _calendar_source(org, secure_code):
    row = HolidayCalendar.query.filter(
        HolidayCalendar.org_secure_code == org.secure_code,
        HolidayCalendar.secure_code == secure_code,
        HolidayCalendar.is_deleted == False,  # noqa: E712
    ).first()
    return row.source if row else HolidayCalendarSource.TW_GOV


def _default_work_periods(schedule):
    weekly = schedule.weekly_hours or {}
    if weekly.get('mon'):
        return weekly['mon']
    for key in _DAY_KEYS:
        if weekly.get(key):
            return weekly[key]
    return None
