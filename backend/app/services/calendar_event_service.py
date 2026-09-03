"""行事曆事件寫入服務。"""
from datetime import datetime, timedelta

from flask_babel import gettext as _

from app import db
from app.models import (
    CalendarEvent,
    CalendarKind,
    CalendarVisibility,
    ScheduleAdjustment,
    User,
)
from app.models.calendar_event import LEAVE_LIKE_TYPES, ORG_EVENT_TYPES, PERSONAL_EVENT_TYPES
from app.services.approver_exposure_service import ApproverExposureService
from app.services.schedule_service import ScheduleService
from app.utils.calendar_time import (
    event_local_dates,
    local_date_to_utc,
    local_naive_to_utc,
    utc_to_local,
)


class CalendarEventError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class CalendarEventService:
    MAX_SPAN_DAYS = 366

    @classmethod
    def create(cls, org, actor, payload: dict) -> CalendarEvent:
        data = cls._normalize_payload(org, payload, None)
        row = CalendarEvent(
            org_secure_code=org.secure_code,
            calendar_kind=data['calendar_kind'],
            owner_user_secure_code=actor.secure_code if data['calendar_kind'] == CalendarKind.PERSONAL else None,
            event_type=data['event_type'],
            title=data['title'],
            starts_at=data['starts_at'],
            ends_at=data['ends_at'],
            all_day=data['all_day'],
            visibility=data['visibility'],
            note=data['note'],
            created_by=actor.secure_code,
        )
        if row.calendar_kind == CalendarKind.ORG and not actor.is_org_admin:
            raise CalendarEventError('forbidden', _('沒有權限建立企業事件'), 403)
        db.session.add(row)
        db.session.flush()
        if row.calendar_kind == CalendarKind.PERSONAL and row.event_type in LEAVE_LIKE_TYPES:
            cls.resync_leave_adjustments(org, row.owner_user_secure_code, cls._local_dates(org, row))
        db.session.flush()
        return row

    @classmethod
    def update(cls, org, actor, secure_code: str, payload: dict) -> CalendarEvent:
        row = cls._get_editable_event(org, actor, secure_code)
        old_kind = row.calendar_kind
        old_type = row.event_type
        old_dates = cls._local_dates(org, row)
        data = cls._normalize_payload(org, payload, row)
        row.event_type = data['event_type']
        row.title = data['title']
        row.starts_at = data['starts_at']
        row.ends_at = data['ends_at']
        row.all_day = data['all_day']
        row.visibility = data['visibility']
        row.note = data['note']
        db.session.flush()

        if old_kind == CalendarKind.PERSONAL and (old_type in LEAVE_LIKE_TYPES or row.event_type in LEAVE_LIKE_TYPES):
            cls.resync_leave_adjustments(org, row.owner_user_secure_code, old_dates | cls._local_dates(org, row))
        db.session.flush()
        return row

    @classmethod
    def delete(cls, org, actor, secure_code: str) -> None:
        row = cls._get_editable_event(org, actor, secure_code)
        old_dates = cls._local_dates(org, row)
        old_kind = row.calendar_kind
        old_type = row.event_type
        row.is_deleted = True
        row.deleted_at = datetime.utcnow()
        db.session.flush()
        if old_kind == CalendarKind.PERSONAL and old_type in LEAVE_LIKE_TYPES:
            cls.resync_leave_adjustments(org, row.owner_user_secure_code, old_dates)
        db.session.flush()

    @classmethod
    def delegation_hint(cls, org, actor, row) -> dict | None:
        """PERSONAL leave-like events may need an approval-delegation hint."""
        if row.calendar_kind != CalendarKind.PERSONAL or row.event_type not in LEAVE_LIKE_TYPES:
            return None
        dates = cls._local_dates(org, row)
        if not dates:
            return None
        start_date = min(dates)
        end_date = max(dates)
        description = ApproverExposureService.describe(org, actor, start_date, end_date)
        description.update({
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
        })
        return description

    @classmethod
    def resync_leave_adjustments(cls, org, owner_user_secure_code: str, dates: set) -> None:
        if not dates:
            return
        owner = User.query.filter(
            User.org_secure_code == org.secure_code,
            User.secure_code == owner_user_secure_code,
            User.is_deleted == False,  # noqa: E712
        ).first()
        if not owner:
            raise CalendarEventError('not_found', _('找不到事件擁有者'), 404)

        tz_name = org.get_setting('timezone', 'Asia/Taipei')
        range_start = min(dates)
        range_end = max(dates)
        rows = CalendarEvent.query.filter(
            CalendarEvent.org_secure_code == org.secure_code,
            CalendarEvent.owner_user_secure_code == owner_user_secure_code,
            CalendarEvent.calendar_kind == CalendarKind.PERSONAL,
            CalendarEvent.event_type.in_(LEAVE_LIKE_TYPES),
            CalendarEvent.source_type.is_(None),
            CalendarEvent.is_deleted == False,  # noqa: E712
            CalendarEvent.starts_at < local_date_to_utc(tz_name, range_end + timedelta(days=1)),
            CalendarEvent.ends_at >= local_date_to_utc(tz_name, range_start),
        ).order_by(CalendarEvent.starts_at.asc(), CalendarEvent.id.asc()).all()

        covered = {}
        titles = {}
        for event in rows:
            for d in sorted(cls._local_dates(org, event) & dates):
                if d not in covered:
                    covered[d] = event.secure_code
                    titles[d] = event.title

        adjustments = ScheduleAdjustment.query.filter(
            ScheduleAdjustment.org_secure_code == org.secure_code,
            ScheduleAdjustment.user_secure_code == owner_user_secure_code,
            ScheduleAdjustment.adjust_type == 'LEAVE',
            ScheduleAdjustment.adjust_date.in_(dates),
        ).all()
        by_date = {row.adjust_date: row for row in adjustments}
        now = datetime.utcnow()
        for d in sorted(dates):
            row = by_date.get(d)
            if d in covered:
                if row is None:
                    db.session.add(ScheduleAdjustment(
                        org_secure_code=org.secure_code,
                        user_secure_code=owner_user_secure_code,
                        adjust_date=d,
                        adjust_type='LEAVE',
                        original_periods=ScheduleService.get_work_periods(owner, d),
                        adjusted_periods=None,
                        status='APPROVED',
                        approved_at=now,
                        approved_by=owner_user_secure_code,
                        calendar_event_secure_code=covered[d],
                        note=titles[d],
                    ))
                elif row.is_deleted:
                    row.is_deleted = False
                    row.deleted_at = None
                    row.status = 'APPROVED'
                    row.approved_at = now
                    row.approved_by = owner_user_secure_code
                    row.calendar_event_secure_code = covered[d]
                    row.note = titles[d]
                elif row.calendar_event_secure_code is not None:
                    row.calendar_event_secure_code = covered[d]
                    row.note = titles[d]
            elif row and not row.is_deleted and row.calendar_event_secure_code is not None:
                row.is_deleted = True
                row.deleted_at = now

    @classmethod
    def _get_editable_event(cls, org, actor, secure_code: str) -> CalendarEvent:
        row = CalendarEvent.query.filter(
            CalendarEvent.org_secure_code == org.secure_code,
            CalendarEvent.secure_code == secure_code,
            CalendarEvent.is_deleted == False,  # noqa: E712
        ).first()
        if not row:
            raise CalendarEventError('not_found', _('找不到事件'), 404)
        # 授權先於「可不可編輯」：非 owner 一律 404，不洩漏事件存在與否
        if row.calendar_kind == CalendarKind.PERSONAL:
            if row.owner_user_secure_code != actor.secure_code:
                raise CalendarEventError('not_found', _('找不到事件'), 404)
        elif row.calendar_kind == CalendarKind.ORG:
            if not actor.is_org_admin:
                raise CalendarEventError('forbidden', _('沒有權限編輯企業事件'), 403)
        else:
            raise CalendarEventError('not_editable', _('此事件不能編輯'), 400)
        if row.source_type is not None:
            raise CalendarEventError('not_editable', _('此事件不能編輯'), 400)
        return row

    @classmethod
    def _normalize_payload(cls, org, payload: dict, existing: CalendarEvent | None) -> dict:
        if not isinstance(payload, dict):
            raise CalendarEventError('validation', _('請求格式錯誤'), 400)
        kind = payload.get('calendar_kind') if existing is None else existing.calendar_kind
        if existing is None and kind not in (CalendarKind.PERSONAL, CalendarKind.ORG):
            raise CalendarEventError('validation', _('calendar_kind 欄位不合法'), 400)
        if existing is not None and payload.get('calendar_kind') and payload.get('calendar_kind') != existing.calendar_kind:
            raise CalendarEventError('kind_immutable', _('calendar_kind 欄位不能變更'), 400)

        event_type = str(payload.get('event_type') or '').strip()
        allowed = PERSONAL_EVENT_TYPES if kind == CalendarKind.PERSONAL else ORG_EVENT_TYPES
        if event_type not in allowed:
            raise CalendarEventError('validation', _('event_type 欄位不合法'), 400)

        title = str(payload.get('title') or '').strip()
        if not title:
            raise CalendarEventError('validation', _('title 欄位必填'), 400)
        if len(title) > 200:
            raise CalendarEventError('validation', _('title 欄位最多 200 字'), 400)

        all_day = bool(payload.get('all_day', False))
        starts_at, ends_at = cls._parse_range(org, payload.get('start'), payload.get('end'), all_day)
        visibility = payload.get('visibility') or CalendarVisibility.BUSY
        if kind == CalendarKind.ORG:
            visibility = CalendarVisibility.PUBLIC
        elif visibility not in (CalendarVisibility.PUBLIC, CalendarVisibility.BUSY, CalendarVisibility.PRIVATE):
            raise CalendarEventError('validation', _('visibility 欄位不合法'), 400)

        note_value = payload.get('note')
        note = None if note_value is None else str(note_value).strip()
        if note == '':
            note = None
        if note is not None and len(note) > 2000:
            raise CalendarEventError('validation', _('note 欄位最多 2000 字'), 400)

        return {
            'calendar_kind': kind,
            'event_type': event_type,
            'title': title,
            'all_day': all_day,
            'starts_at': starts_at,
            'ends_at': ends_at,
            'visibility': visibility,
            'note': note,
        }

    @classmethod
    def _parse_range(cls, org, start_value, end_value, all_day: bool):
        if not start_value or not end_value:
            raise CalendarEventError('validation', _('start 與 end 欄位必填'), 400)
        tz_name = org.get_setting('timezone', 'Asia/Taipei')
        if all_day:
            try:
                start_date = datetime.strptime(str(start_value), '%Y-%m-%d').date()
                end_date = datetime.strptime(str(end_value), '%Y-%m-%d').date()
            except ValueError:
                raise CalendarEventError('validation', _('start/end 欄位格式須為 YYYY-MM-DD'), 400)
            if end_date < start_date:
                raise CalendarEventError('validation', _('end 欄位不能早於 start'), 400)
            if (end_date - start_date).days + 1 > cls.MAX_SPAN_DAYS:
                raise CalendarEventError('validation', _('start/end 欄位跨度過長'), 400)
            return (
                local_date_to_utc(tz_name, start_date),
                local_date_to_utc(tz_name, end_date + timedelta(days=1)),
            )
        try:
            start_local = datetime.strptime(str(start_value), '%Y-%m-%dT%H:%M')
            end_local = datetime.strptime(str(end_value), '%Y-%m-%dT%H:%M')
        except ValueError:
            raise CalendarEventError('validation', _('start/end 欄位格式須為 YYYY-MM-DDTHH:MM'), 400)
        if end_local < start_local:
            raise CalendarEventError('validation', _('end 欄位不能早於 start'), 400)
        if (end_local.date() - start_local.date()).days + 1 > cls.MAX_SPAN_DAYS:
            raise CalendarEventError('validation', _('start/end 欄位跨度過長'), 400)
        return local_naive_to_utc(tz_name, start_local), local_naive_to_utc(tz_name, end_local)

    @classmethod
    def _local_dates(cls, org, row: CalendarEvent) -> set:
        tz_name = org.get_setting('timezone', 'Asia/Taipei')
        start_local = utc_to_local(tz_name, row.starts_at)
        end_local = utc_to_local(tz_name, row.ends_at)
        start_date, end_date = event_local_dates(row.all_day, start_local, end_local)
        dates = set()
        current = start_date
        while current <= end_date:
            dates.add(current)
            current += timedelta(days=1)
        return dates
