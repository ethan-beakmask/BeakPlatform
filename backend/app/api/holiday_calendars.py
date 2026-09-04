"""Enterprise holiday calendar API.

HolidayCalendar models are intentionally not registered in ResourceGateway:
there is no platform-wide permission code for them, and registering would make
gateway checks fail closed for all identities. This API uses explicit
org_secure_code filters on every model query instead.
"""
from flask import Blueprint, jsonify, request
from flask_babel import gettext as _
from flask_login import current_user

from app import db
from app.models import HolidayCalendar, HolidayCalendarEntry, HolidayCalendarSource, HolidayEntryStage, WorkSchedule
from app.security.decorators import admin_required
from app.services import holiday_calendar_service as svc
from app.services.holiday_calendar_service import HolidayCalendarError, MAX_UPLOAD_BYTES


api_holiday_calendars = Blueprint('api_holiday_calendars', __name__, url_prefix='/api/admin/holiday-calendars')


@api_holiday_calendars.route('/', methods=['GET'])
@admin_required
def list_calendars():
    org = current_user.organization
    calendars = HolidayCalendar.query.filter(  # nosemgrep: beakplatform-direct-model-query-in-api
        HolidayCalendar.org_secure_code == org.secure_code,
        HolidayCalendar.is_deleted == False,  # noqa: E712
    ).order_by(HolidayCalendar.year.desc().nullslast(), HolidayCalendar.created_at.desc()).all()
    svc.decorate_calendars(calendars)
    return jsonify({'success': True, 'data': [row.to_dict() for row in calendars]})


@api_holiday_calendars.route('/fetch-taiwan', methods=['POST'])
@admin_required
def fetch_taiwan():
    org = current_user.organization
    data = request.get_json(silent=True) or {}
    try:
        year = int(data.get('year'))
        raw = svc.fetch_taiwan_gov_calendar(year)
        entries = svc.parse_taiwan_gov_json(raw)
        calendar = svc.create_or_replace_draft(
            org,
            HolidayCalendarSource.TW_GOV,
            entries,
            year=year,
            source_ref=svc.TW_GOV_CALENDAR_URL.format(year=year),
        )
        db.session.commit()
        return jsonify({'success': True, 'data': calendar.to_dict()}), 201
    except (TypeError, ValueError):
        db.session.rollback()
        return _error(HolidayCalendarError('invalid_year'))
    except HolidayCalendarError as exc:
        db.session.rollback()
        return _error(exc)


@api_holiday_calendars.route('/import', methods=['POST'])
@admin_required
def import_calendar():
    org = current_user.organization
    if request.content_length and request.content_length > MAX_UPLOAD_BYTES:
        return _error(HolidayCalendarError('file_too_large'))
    upload = request.files.get('file')
    if not upload:
        return _error(HolidayCalendarError('parse_failed'))
    try:
        source = (request.form.get('source') or '').upper()
        year = int(request.form.get('year')) if request.form.get('year') else None
        calendar = None
        if request.form.get('calendar_secure_code'):
            calendar = _get_calendar(request.form['calendar_secure_code'])
        entries = svc.parse_custom_upload(upload.read(), upload.filename or '')
        calendar = svc.create_or_replace_draft(
            org,
            source,
            entries,
            year=year,
            name=request.form.get('name'),
            source_ref=upload.filename,
            calendar=calendar,
        )
        db.session.commit()
        return jsonify({'success': True, 'data': calendar.to_dict()}), 201
    except (TypeError, ValueError):
        db.session.rollback()
        return _error(HolidayCalendarError('invalid_year'))
    except HolidayCalendarError as exc:
        db.session.rollback()
        return _error(exc)


@api_holiday_calendars.route('/<secure_code>', methods=['GET'])
@admin_required
def get_calendar(secure_code):
    try:
        calendar = _get_calendar(secure_code)
        svc.decorate_calendars([calendar])
        draft = _entries(calendar, HolidayEntryStage.DRAFT)
        published = _entries(calendar, HolidayEntryStage.PUBLISHED)
        return jsonify({
            'success': True,
            'data': {
                'calendar': calendar.to_dict(),
                'draft_entries': [row.to_dict() for row in draft],
                'published_entries': [row.to_dict() for row in published],
            },
        })
    except HolidayCalendarError as exc:
        return _error(exc)


@api_holiday_calendars.route('/<secure_code>', methods=['PUT'])
@admin_required
def update_calendar(secure_code):
    try:
        calendar = _get_calendar(secure_code)
        data = request.get_json(silent=True) or {}
        svc.rename(current_user.organization, calendar, data.get('name'), data.get('note'))
        db.session.commit()
        svc.decorate_calendars([calendar])
        return jsonify({'success': True, 'data': calendar.to_dict(), 'message': _('已更新')})
    except HolidayCalendarError as exc:
        db.session.rollback()
        return _error(exc)


@api_holiday_calendars.route('/<secure_code>', methods=['DELETE'])
@admin_required
def delete_calendar(secure_code):
    try:
        svc.delete_calendar(current_user.organization, _get_calendar(secure_code))
        db.session.commit()
        return jsonify({'success': True, 'message': _('已刪除')})
    except HolidayCalendarError as exc:
        db.session.rollback()
        return _error(exc)


@api_holiday_calendars.route('/<secure_code>/draft-entries', methods=['POST'])
@admin_required
def add_entry(secure_code):
    try:
        row = svc.add_draft_entry(current_user.organization, _get_calendar(secure_code), request.get_json(silent=True) or {})
        db.session.commit()
        return jsonify({'success': True, 'data': row.to_dict(), 'message': _('已新增')}), 201
    except HolidayCalendarError as exc:
        db.session.rollback()
        return _error(exc)


@api_holiday_calendars.route('/<secure_code>/draft-entries/<entry_secure_code>', methods=['PUT'])
@admin_required
def update_entry(secure_code, entry_secure_code):
    try:
        calendar = _get_calendar(secure_code)
        row = _get_entry(calendar, entry_secure_code)
        svc.update_draft_entry(current_user.organization, calendar, row, request.get_json(silent=True) or {})
        db.session.commit()
        return jsonify({'success': True, 'data': row.to_dict(), 'message': _('已更新')})
    except HolidayCalendarError as exc:
        db.session.rollback()
        return _error(exc)


@api_holiday_calendars.route('/<secure_code>/draft-entries/<entry_secure_code>', methods=['DELETE'])
@admin_required
def delete_entry(secure_code, entry_secure_code):
    try:
        calendar = _get_calendar(secure_code)
        svc.delete_draft_entry(current_user.organization, calendar, _get_entry(calendar, entry_secure_code))
        db.session.commit()
        return jsonify({'success': True, 'message': _('已刪除')})
    except HolidayCalendarError as exc:
        db.session.rollback()
        return _error(exc)


@api_holiday_calendars.route('/<secure_code>/publish', methods=['POST'])
@admin_required
def publish_calendar(secure_code):
    try:
        data = request.get_json(silent=True) or {}
        summary = svc.publish(current_user.organization, _get_calendar(secure_code), data.get('schedule_secure_codes') or [])
        db.session.commit()
        return jsonify({'success': True, 'data': summary, 'message': _('已發佈')})
    except HolidayCalendarError as exc:
        db.session.rollback()
        return _error(exc)


@api_holiday_calendars.route('/<secure_code>/unpublish', methods=['POST'])
@admin_required
def unpublish_calendar(secure_code):
    try:
        summary = svc.unpublish(current_user.organization, _get_calendar(secure_code))
        db.session.commit()
        return jsonify({'success': True, 'data': summary, 'message': _('已下架')})
    except HolidayCalendarError as exc:
        db.session.rollback()
        return _error(exc)


def _get_calendar(secure_code):
    row = HolidayCalendar.query.filter(  # nosemgrep: beakplatform-direct-model-query-in-api
        HolidayCalendar.org_secure_code == current_user.org_secure_code,
        HolidayCalendar.secure_code == secure_code,
        HolidayCalendar.is_deleted == False,  # noqa: E712
    ).first()
    if not row:
        raise HolidayCalendarError('not_found')
    return row


def _get_entry(calendar, secure_code):
    row = HolidayCalendarEntry.query.filter(  # nosemgrep: beakplatform-direct-model-query-in-api
        HolidayCalendarEntry.org_secure_code == current_user.org_secure_code,
        HolidayCalendarEntry.calendar_secure_code == calendar.secure_code,
        HolidayCalendarEntry.secure_code == secure_code,
        HolidayCalendarEntry.stage == HolidayEntryStage.DRAFT,
    ).first()
    if not row:
        raise HolidayCalendarError('not_found')
    return row


def _entries(calendar, stage):
    return HolidayCalendarEntry.query.filter(  # nosemgrep: beakplatform-direct-model-query-in-api
        HolidayCalendarEntry.org_secure_code == current_user.org_secure_code,
        HolidayCalendarEntry.calendar_secure_code == calendar.secure_code,
        HolidayCalendarEntry.stage == stage,
    ).order_by(HolidayCalendarEntry.entry_date.asc()).all()


def _error(exc):
    messages = {
        'fetch_failed': _('無法連線至資料來源，請改用上傳檔案'),
        'file_too_large': _('檔案超過大小限制'),
        'invalid_year': _('年度不合法'),
        'invalid_source': _('資料來源不合法'),
        'name_required': _('請輸入名稱'),
        'parse_failed': _parse_failed_message(exc.detail),
        'duplicate_date': _('日期已存在'),
        'invalid_date': _('日期格式錯誤'),
        'invalid_type': _('類型不合法'),
        'invalid_work_periods': _('工作時段格式錯誤'),
        'no_targets': _('請選擇發佈目標班表'),
        'schedule_not_found': _('班表不存在'),
        'not_published': _('假日表尚未發佈'),
        'published': _('已發佈的假日表需先下架才能刪除'),
        'not_found': _('假日表不存在'),
    }
    if exc.code == 'fetch_failed':
        status = 502
    elif exc.code == 'file_too_large':
        status = 413
    elif exc.code in ('schedule_not_found', 'not_found'):
        status = 404
    else:
        status = 400
    return jsonify({'success': False, 'error': exc.code, 'message': messages.get(exc.code, _('操作失敗'))}), status


def _parse_failed_message(detail):
    reason = (detail or {}).get('reason')
    line = (detail or {}).get('line')
    if reason == 'bad_header':
        return _('CSV 表頭必須是 date,type,description,work_periods')
    if reason == 'bad_columns':
        return _('第 %(n)s 列欄位數錯誤', n=line)
    if reason == 'duplicate_date':
        return _('第 %(n)s 列日期重複', n=line)
    if reason == 'bad_row':
        return _('第 %(n)s 列格式錯誤', n=line)
    return _('檔案格式錯誤')
