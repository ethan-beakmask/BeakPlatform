"""企業行事曆唯讀投影服務。"""
import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from flask import has_request_context, request
from flask_babel import gettext as _

from app import db
from app.models import (
    CalendarEvent,
    CalendarKind,
    CalendarVisibility,
    Delegation,
    DelegationStatus,
    EmployeePosition,
    LookupItem,
    ScheduleHoliday,
    User,
    WorkSchedule,
)
from app.models.employee_position import PositionType
from app.services.calendar_visibility import apply_visibility
from app.services.schedule_service import ScheduleService

logger = logging.getLogger(__name__)

WEEKDAY_KEYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']


class CalendarProjectionService:
    MAX_RANGE_DAYS = 62

    @classmethod
    def build(cls, org, viewer, scope: str, start: date, end: date) -> dict:
        """scope: 'org' | 'me'；start/end 是企業時區的當地日曆日（含）。"""
        if scope not in ('org', 'me'):
            raise ValueError('invalid scope')
        if end < start:
            raise ValueError('invalid range')
        if (end - start).days + 1 > cls.MAX_RANGE_DAYS:
            raise ValueError('range too large')

        tz_name = org.get_setting('timezone', 'Asia/Taipei')
        start_utc = _local_date_to_utc(tz_name, start)
        end_utc = _local_date_to_utc(tz_name, end + timedelta(days=1))
        prefix = request.script_root if has_request_context() else ''

        schedule = cls._schedule_for_scope(org, viewer, scope)
        holidays = cls._schedule_holidays(schedule, start, end)
        days = cls._build_days(org, start, end, schedule, holidays)

        events = []
        events.extend(cls._manual_events(org, viewer, scope, tz_name, start_utc, end_utc))
        events.extend(cls._holiday_events(holidays))
        events.extend(cls._delegation_events(org, viewer, start, end, prefix))
        events.extend(cls._position_events(org, viewer, scope, start, end))
        events.extend(cls._broadcast_events(org, viewer, tz_name, start_utc, end_utc))
        events.extend(cls._workflow_events(org, viewer, scope, tz_name, start_utc, end_utc, prefix))

        visible = []
        for event in events:
            item = apply_visibility(event, viewer)
            if item is not None:
                visible.append(item)
        visible.sort(key=lambda item: (item.get('start_local') or '', item.get('title') or ''))

        return {
            'timezone': tz_name,
            'range': {'start': start.isoformat(), 'end': end.isoformat()},
            'days': days,
            'events': visible,
        }

    @classmethod
    def _schedule_for_scope(cls, org, viewer, scope):
        if scope == 'me':
            return ScheduleService.get_user_schedule(viewer)
        return WorkSchedule.query.filter(
            WorkSchedule.org_secure_code == org.secure_code,
            WorkSchedule.is_default == True,  # noqa: E712
            WorkSchedule.is_active == True,  # noqa: E712
            WorkSchedule.is_deleted == False,  # noqa: E712
        ).first()

    @classmethod
    def _schedule_holidays(cls, schedule, start, end):
        if not schedule:
            return {}
        rows = ScheduleHoliday.query.filter(
            ScheduleHoliday.schedule_secure_code == schedule.secure_code,
            ScheduleHoliday.holiday_date >= start,
            ScheduleHoliday.holiday_date <= end,
            ScheduleHoliday.is_deleted == False,  # noqa: E712
        ).all()
        return {row.holiday_date: row for row in rows}

    @classmethod
    def _build_days(cls, org, start, end, schedule, holidays):
        today = org.local_today()
        current = start
        days = []
        while current <= end:
            holiday = holidays.get(current)
            is_workday = None
            holiday_data = None
            if schedule:
                if holiday:
                    holiday_data = {
                        'type': holiday.holiday_type,
                        'description': holiday.description,
                    }
                    is_workday = holiday.holiday_type == 'WORKDAY'
                    if holiday.holiday_type in ('HOLIDAY', 'COMP_OFF'):
                        is_workday = False
                else:
                    periods = (schedule.weekly_hours or {}).get(WEEKDAY_KEYS[current.weekday()])
                    is_workday = bool(periods)
            days.append({
                'date': current.isoformat(),
                'weekday': (current.weekday() + 1) % 7,
                'is_workday': is_workday,
                'holiday': holiday_data,
                'is_today': current == today,
            })
            current += timedelta(days=1)
        return days

    @classmethod
    def _manual_events(cls, org, viewer, scope, tz_name, start_utc, end_utc):
        query = CalendarEvent.query.filter(
            CalendarEvent.org_secure_code == org.secure_code,
            CalendarEvent.is_deleted == False,  # noqa: E712
            CalendarEvent.starts_at < end_utc,
            CalendarEvent.ends_at >= start_utc,
        )
        if scope == 'me':
            query = query.filter(
                db.or_(
                    CalendarEvent.calendar_kind == CalendarKind.ORG,
                    CalendarEvent.owner_user_secure_code == viewer.secure_code,
                )
            )

        rows = query.all()
        owner_map = _active_user_map(
            org.secure_code,
            {row.owner_user_secure_code for row in rows if row.owner_user_secure_code},
        )

        events = []
        for row in rows:
            start_local = _utc_to_local(tz_name, row.starts_at)
            end_local = _utc_to_local(tz_name, row.ends_at)
            start_date, end_date = _event_local_dates(row.all_day, start_local, end_local)
            owner = owner_map.get(row.owner_user_secure_code)
            events.append({
                'key': f'manual:{row.secure_code}',
                'source_type': 'manual',
                'source_secure_code': row.secure_code,
                'calendar_kind': row.calendar_kind,
                'owner_user_secure_code': row.owner_user_secure_code,
                'owner_name': owner.display_name if owner else None,
                'event_type': row.event_type,
                'title': row.title,
                'note': row.note,
                'all_day': row.all_day,
                'start_local': _format_local(start_local),
                'end_local': _format_local(end_local),
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'visibility': row.visibility,
                'link': None,
                'audience': None,
            })
        return events

    @classmethod
    def _holiday_events(cls, holidays):
        events = []
        for holiday in holidays.values():
            desc = holiday.description or ''
            if holiday.holiday_type == 'WORKDAY':
                title = _('補班：%(desc)s', desc=desc) if desc else _('補班')
                event_type = 'WORKDAY'
            else:
                title = desc or (_('補假') if holiday.holiday_type == 'COMP_OFF' else _('假日'))
                event_type = 'HOLIDAY'
            local_start = datetime.combine(holiday.holiday_date, time.min)
            local_end = local_start
            events.append({
                'key': f'holiday:{holiday.secure_code}',
                'source_type': 'holiday',
                'source_secure_code': holiday.secure_code,
                'calendar_kind': 'ORG',
                'owner_user_secure_code': None,
                'owner_name': None,
                'event_type': event_type,
                'title': title,
                'note': holiday.description,
                'all_day': True,
                'start_local': _format_local(local_start),
                'end_local': _format_local(local_end),
                'start_date': holiday.holiday_date.isoformat(),
                'end_date': holiday.holiday_date.isoformat(),
                'visibility': CalendarVisibility.PUBLIC,
                'link': None,
                'audience': None,
            })
        return events

    @classmethod
    def _delegation_events(cls, org, viewer, start, end, prefix):
        rows = Delegation.query.filter(
            Delegation.org_secure_code == org.secure_code,
            Delegation.is_deleted == False,  # noqa: E712
            Delegation.status != DelegationStatus.REVOKED,
            Delegation.effective_from <= end,
            Delegation.effective_until >= start,
        ).all()
        user_map = _active_user_map(
            org.secure_code,
            {row.delegator_secure_code for row in rows} | {row.delegate_secure_code for row in rows},
        )
        events = []
        for row in rows:
            delegator = user_map.get(row.delegator_secure_code)
            delegate = user_map.get(row.delegate_secure_code)
            delegator_name = delegator.display_name if delegator else ''
            delegate_name = delegate.display_name if delegate else ''
            events.append({
                'key': f'delegation:{row.secure_code}',
                'source_type': 'delegation',
                'source_secure_code': row.secure_code,
                'calendar_kind': 'PERSONAL',
                'owner_user_secure_code': row.delegator_secure_code,
                'owner_name': delegator_name or None,
                'event_type': 'DELEGATION',
                'title': _('代理：%(a)s → %(b)s', a=delegator_name, b=delegate_name),
                'note': row.reason,
                'all_day': True,
                'start_local': _format_local(datetime.combine(row.effective_from, time.min)),
                'end_local': _format_local(datetime.combine(row.effective_until, time.min)),
                'start_date': row.effective_from.isoformat(),
                'end_date': row.effective_until.isoformat(),
                'visibility': CalendarVisibility.PRIVATE,
                'link': f'{prefix}/delegations/{row.secure_code}' if viewer.is_org_admin else None,
                'audience': {
                    'users': [row.delegator_secure_code, row.delegate_secure_code],
                    'org_admin': True,
                },
            })
        return events

    @classmethod
    def _position_events(cls, org, viewer, scope, start, end):
        query = EmployeePosition.query.filter(
            EmployeePosition.org_secure_code == org.secure_code,
            EmployeePosition.is_active == True,  # noqa: E712
            EmployeePosition.is_deleted == False,  # noqa: E712
            EmployeePosition.effective_until.isnot(None),
            EmployeePosition.effective_from <= end,
            EmployeePosition.effective_until >= start,
        )
        if scope == 'me':
            query = query.filter(EmployeePosition.user_secure_code == viewer.secure_code)

        type_names = {
            PositionType.PRIMARY: _('主要'),
            PositionType.CONCURRENT: _('兼任'),
            PositionType.ACTING: _('代理'),
            PositionType.TEMPORARY: _('臨時'),
        }
        rows = query.all()
        user_map = _active_user_map(org.secure_code, {row.user_secure_code for row in rows})
        events = []
        for row in rows:
            owner = user_map.get(row.user_secure_code)
            owner_name = owner.display_name if owner else None
            title_name = row.job_title.name if row.job_title else ''
            unit_name = row.unit.name if row.unit else ''
            position_type = type_names.get(row.position_type, row.position_type)
            events.append({
                'key': f'position:{row.secure_code}',
                'source_type': 'position',
                'source_secure_code': row.secure_code,
                'calendar_kind': 'PERSONAL',
                'owner_user_secure_code': row.user_secure_code,
                'owner_name': owner_name,
                'event_type': 'POSITION',
                'title': _('職位：%(type)s %(title)s（%(unit)s）',
                           type=position_type, title=title_name, unit=unit_name),
                'note': row.remarks,
                'all_day': True,
                'start_local': _format_local(datetime.combine(row.effective_from, time.min)),
                'end_local': _format_local(datetime.combine(row.effective_until, time.min)),
                'start_date': row.effective_from.isoformat(),
                'end_date': row.effective_until.isoformat(),
                'visibility': CalendarVisibility.PRIVATE,
                'link': None,
                'audience': {'users': [row.user_secure_code], 'org_admin': True},
            })
        return events

    @classmethod
    def _broadcast_events(cls, org, viewer, tz_name, start_utc, end_utc):
        from app.api.broadcasts import _user_in_target

        db.session.execute(
            db.text("SELECT set_config('app.current_org', :org, true)"),
            {'org': org.secure_code},
        )
        rows = LookupItem.query.filter_by(
            org_secure_code=org.secure_code,
            category_code='broadcast',
            is_active=True,
            is_deleted=False,
        ).all()
        events = []
        for item in rows:
            value = item.value or {}
            btype = value.get('type')
            starts_at = item.created_at
            ends_at = starts_at
            title = None
            if btype == 'navbar':
                expires_at_str = value.get('expires_at')
                if not expires_at_str:
                    continue
                try:
                    ends_at = datetime.fromisoformat(expires_at_str)
                except (ValueError, TypeError):
                    logger.warning("Invalid broadcast expires_at: %s", item.secure_code)
                    continue
                message = value.get('message') or ''
                title = _('公告：%(m)s', m=message[:60])
            elif btype == 'alert':
                if not _user_in_target(viewer, value.get('target', {})):
                    continue
                title = _('緊急廣播：%(t)s', t=value.get('title') or '')
            else:
                continue
            if not _overlaps(starts_at, ends_at, start_utc, end_utc):
                continue
            start_local = _utc_to_local(tz_name, starts_at)
            end_local = _utc_to_local(tz_name, ends_at)
            start_date, end_date = _event_local_dates(False, start_local, end_local)
            events.append({
                'key': f'broadcast:{item.secure_code}',
                'source_type': 'broadcast',
                'source_secure_code': item.secure_code,
                'calendar_kind': 'ORG',
                'owner_user_secure_code': None,
                'owner_name': None,
                'event_type': 'BROADCAST',
                'title': title,
                'note': value.get('message'),
                'all_day': False,
                'start_local': _format_local(start_local),
                'end_local': _format_local(end_local),
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'visibility': CalendarVisibility.PUBLIC,
                'link': None,
                'audience': None,
            })
        return events

    @classmethod
    def _workflow_events(cls, org, viewer, scope, tz_name, start_utc, end_utc, prefix):
        try:
            from modules.form_workflow.models import (
                FwFormInstance,
                FwNodeExecutionQueue,
                FwWorkflowInstance,
            )
            from modules.form_workflow.services.task_authorizer import (
                build_actor,
                can_act_on_task,
            )
        except ImportError:
            return []

        events = []
        if scope == 'me':
            tasks = FwNodeExecutionQueue.query.filter(
                FwNodeExecutionQueue.org_secure_code == org.secure_code,
                FwNodeExecutionQueue.status == 'WAITING',
                FwNodeExecutionQueue.node_type.in_(('Approve', 'FormAdapter', 'FORMADAPTER')),
                FwNodeExecutionQueue.scheduled_at >= start_utc,
                FwNodeExecutionQueue.scheduled_at < end_utc,
                FwNodeExecutionQueue.is_deleted == False,  # noqa: E712
            ).all()
            form_codes = {t.form_instance_secure_code for t in tasks if t.form_instance_secure_code}
            forms = FwFormInstance.query.filter(
                FwFormInstance.org_secure_code == org.secure_code,
                FwFormInstance.secure_code.in_(form_codes),
                FwFormInstance.is_deleted == False,  # noqa: E712
            ).all() if form_codes else []
            form_map = {f.secure_code: f for f in forms}
            actor = build_actor(viewer.secure_code, org.secure_code)
            for task in tasks:
                if not can_act_on_task(task, viewer.secure_code, org.secure_code, actor):
                    continue
                form = form_map.get(task.form_instance_secure_code)
                local_dt = _utc_to_local(tz_name, task.scheduled_at)
                form_name = form.form_name if form else ''
                serial_number = form.serial_number if form else ''
                events.append(_point_event(
                    key=f'approval:{task.secure_code}',
                    source_type='approval_task',
                    source_secure_code=task.secure_code,
                    calendar_kind='PERSONAL',
                    owner_user_secure_code=viewer.secure_code,
                    owner_name=viewer.display_name,
                    event_type='APPROVAL',
                    title=_('待簽核：%(form)s（%(sn)s）', form=form_name or '', sn=serial_number or ''),
                    local_dt=local_dt,
                    visibility=CalendarVisibility.PRIVATE,
                    link=f'{prefix}/forms/center',
                    audience={'users': [viewer.secure_code]},
                ))

        if scope == 'org' and viewer.is_org_admin:
            tasks = FwNodeExecutionQueue.query.filter(
                FwNodeExecutionQueue.org_secure_code == org.secure_code,
                FwNodeExecutionQueue.status == 'WAITING',
                FwNodeExecutionQueue.node_type == 'Delay',
                FwNodeExecutionQueue.scheduled_at >= start_utc,
                FwNodeExecutionQueue.scheduled_at < end_utc,
                FwNodeExecutionQueue.is_deleted == False,  # noqa: E712
            ).all()
            wf_codes = {t.workflow_instance_secure_code for t in tasks if t.workflow_instance_secure_code}
            workflows = FwWorkflowInstance.query.filter(
                FwWorkflowInstance.org_secure_code == org.secure_code,
                FwWorkflowInstance.secure_code.in_(wf_codes),
                FwWorkflowInstance.is_deleted == False,  # noqa: E712
            ).all() if wf_codes else []
            wf_map = {w.secure_code: w for w in workflows}
            for task in tasks:
                local_dt = _utc_to_local(tz_name, task.scheduled_at)
                workflow = wf_map.get(task.workflow_instance_secure_code)
                events.append(_point_event(
                    key=f'delay:{task.secure_code}',
                    source_type='flow_delay',
                    source_secure_code=task.secure_code,
                    calendar_kind='ORG',
                    owner_user_secure_code=None,
                    owner_name=None,
                    event_type='FLOW',
                    title=_('流程等待到期：%(node)s（%(code)s）',
                            node=task.node_name or task.node_id,
                            code=workflow.execution_code if workflow else ''),
                    local_dt=local_dt,
                    visibility=CalendarVisibility.PUBLIC,
                    link=None,
                    audience={'org_admin': True},
                ))
        return events


def _local_date_to_utc(tz_name: str, d: date) -> datetime:
    return (
        datetime.combine(d, time.min)
        .replace(tzinfo=ZoneInfo(tz_name))
        .astimezone(ZoneInfo('UTC'))
        .replace(tzinfo=None)
    )


def _utc_to_local(tz_name: str, dt: datetime) -> datetime:
    return dt.replace(tzinfo=ZoneInfo('UTC')).astimezone(ZoneInfo(tz_name))


def _format_local(dt: datetime) -> str:
    return dt.strftime('%Y-%m-%dT%H:%M')


def _event_local_dates(all_day: bool, start_local: datetime, end_local: datetime) -> tuple[date, date]:
    start_date = start_local.date()
    end_date = end_local.date()
    if all_day and end_local.time() == time.min and end_local.date() > start_date:
        end_date = end_local.date() - timedelta(days=1)
    return start_date, end_date


def _overlaps(starts_at: datetime, ends_at: datetime, start_utc: datetime, end_utc: datetime) -> bool:
    return starts_at < end_utc and ends_at >= start_utc


def _point_event(**kwargs):
    local_dt = kwargs.pop('local_dt')
    local_date = local_dt.date().isoformat()
    return {
        **kwargs,
        'note': None,
        'all_day': False,
        'start_local': _format_local(local_dt),
        'end_local': _format_local(local_dt),
        'start_date': local_date,
        'end_date': local_date,
    }


def _active_user_map(org_secure_code: str, secure_codes: set[str]) -> dict:
    if not secure_codes:
        return {}
    users = User.query.filter(
        User.org_secure_code == org_secure_code,
        User.secure_code.in_(secure_codes),
        User.is_deleted == False,  # noqa: E712
        User.is_active == True,  # noqa: E712
    ).all()
    return {user.secure_code: user for user in users}
