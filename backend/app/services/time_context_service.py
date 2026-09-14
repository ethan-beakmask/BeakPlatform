"""TimeContext 起步（PF-229 第三期第 3 項）：給一個時間點，回答「誰在值班、誰在假中」。

設計來源 dev-notes/knowledge/time-context-architecture.md：應用層即時組裝、不預存。
本檔是唯一實作；之後的 open_defense 事件路由與簽核者解析都應該呼叫這裡，不要各自再查班表。

兩個查詢看的來源刻意不同：

- ``who_on_duty``：逐人問 ``ScheduleService.is_working_time()``——它讀的 ``get_work_periods()``
  已含時段級請假（LEAVE 列的 ``adjusted_periods``），所以「這一刻在假中」的人自然不在值班名單。
  逐人查是 N+1（每人最多 3 個查詢）；企業人數上限預設 50（``DEFAULT_ORG_USER_LIMIT``），
  起步階段可接受，要優化就把 ``get_work_periods`` 批次化，不要在這裡加快取。
- ``who_on_leave``：直接看行事曆 LEAVE／TRIP 事件是否涵蓋這一刻，加上人工建的 LEAVE 調整列
  （``calendar_event_secure_code IS NULL``，整天視為請假）。**刻意不看** ``schedule_adjustments``
  的 ``adjusted_periods``——那存的是「剩餘工作時段」，沒有班表的企業底是 ``[]``、扣完也是 ``[]``，
  從那張表判不出此刻在不在假中；事件本身才是請假區間的權威。

時間一律以 naive UTC 進出（與 DB 一致），當地換算只走 ``app.utils.calendar_time``。
"""
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from typing import Dict, List, Optional

from app.models import CalendarEvent, CalendarKind, ScheduleAdjustment, User, UserType
from app.models.calendar_event import LEAVE_LIKE_TYPES
from app.services.schedule_service import ScheduleService
from app.utils.calendar_time import format_local, utc_to_local

MEMBER_USER_TYPES = (UserType.EMPLOYEE, UserType.ORG_ADMIN)


class TimeContextService:
    """時間情境查詢（唯一實作）。"""

    @staticmethod
    def _normalize_instant(instant_utc: Optional[datetime]) -> datetime:
        if instant_utc is None:
            return datetime.utcnow().replace(microsecond=0)
        if instant_utc.tzinfo is not None:
            return instant_utc.astimezone(dt_timezone.utc).replace(tzinfo=None)
        return instant_utc

    @staticmethod
    def _tz_name(org) -> str:
        return org.get_setting('timezone', 'Asia/Taipei')

    @staticmethod
    def _members(org) -> List[User]:
        """時間軸上的成員：同企業、啟用中、未刪除、非服務帳號、內部身分（EXTERNAL／SYSTEM_ADMIN 不算）。"""
        return User.query.filter(
            User.org_secure_code == org.secure_code,
            User.is_deleted == False,  # noqa: E712
            User.is_active == True,  # noqa: E712
            User.is_service_account == False,  # noqa: E712
            User.user_type.in_(MEMBER_USER_TYPES),
        ).order_by(User.display_name.asc(), User.secure_code.asc()).all()

    @staticmethod
    def _member_payload(user: User) -> Dict:
        return {
            'secure_code': user.secure_code,
            'display_name': user.display_name,
            'employee_id': user.employee_id,
        }

    @classmethod
    def who_on_duty(cls, org, instant_utc: Optional[datetime] = None) -> List[Dict]:
        """此刻依班表（含時段級請假）在工作時段內的成員。"""
        instant = cls._normalize_instant(instant_utc)
        local_naive = utc_to_local(cls._tz_name(org), instant).replace(tzinfo=None)
        return [
            cls._member_payload(user)
            for user in cls._members(org)
            if ScheduleService.is_working_time(user, local_naive)
        ]

    @classmethod
    def who_on_leave(cls, org, instant_utc: Optional[datetime] = None) -> List[Dict]:
        """此刻在假中的成員：行事曆 LEAVE／TRIP 事件涵蓋這一刻，或當地日有人工 LEAVE 調整列。"""
        instant = cls._normalize_instant(instant_utc)
        tz_name = cls._tz_name(org)
        local = utc_to_local(tz_name, instant)
        local_date: date = local.date()
        members = {user.secure_code: user for user in cls._members(org)}
        if not members:
            return []
        member_codes = list(members)

        found: Dict[str, Dict] = {}

        events = CalendarEvent.query.filter(
            CalendarEvent.org_secure_code == org.secure_code,
            CalendarEvent.calendar_kind == CalendarKind.PERSONAL,
            CalendarEvent.event_type.in_(LEAVE_LIKE_TYPES),
            CalendarEvent.source_type.is_(None),
            CalendarEvent.is_deleted == False,  # noqa: E712
            CalendarEvent.starts_at <= instant,
            CalendarEvent.ends_at > instant,
            CalendarEvent.owner_user_secure_code.in_(member_codes),
        ).all()
        for event in events:
            until_local = format_local(utc_to_local(tz_name, event.ends_at))
            current = found.get(event.owner_user_secure_code)
            if current is None or until_local > current['until_local']:
                found[event.owner_user_secure_code] = {'source': 'calendar', 'until_local': until_local}

        manual_rows = ScheduleAdjustment.query.filter(
            ScheduleAdjustment.org_secure_code == org.secure_code,
            ScheduleAdjustment.adjust_type == 'LEAVE',
            ScheduleAdjustment.status == 'APPROVED',
            ScheduleAdjustment.is_deleted == False,  # noqa: E712
            ScheduleAdjustment.calendar_event_secure_code.is_(None),
            ScheduleAdjustment.adjust_date == local_date,
            ScheduleAdjustment.user_secure_code.in_(member_codes),
        ).all()
        day_end_local = format_local(datetime.combine(local_date + timedelta(days=1), time.min))
        for row in manual_rows:
            current = found.get(row.user_secure_code)
            if current is None or day_end_local > current['until_local']:
                found[row.user_secure_code] = {'source': 'manual', 'until_local': day_end_local}

        result = []
        for secure_code, user in members.items():   # members 已依 display_name 排序
            info = found.get(secure_code)
            if info is None:
                continue
            payload = cls._member_payload(user)
            payload.update(info)
            result.append(payload)
        return result

    @classmethod
    def snapshot(cls, org, instant_utc: Optional[datetime] = None) -> Dict:
        instant = cls._normalize_instant(instant_utc)
        tz_name = cls._tz_name(org)
        return {
            'instant_utc': instant.isoformat(timespec='seconds'),
            'instant_local': format_local(utc_to_local(tz_name, instant)),
            'timezone': tz_name,
            'who_on_duty': cls.who_on_duty(org, instant),
            'who_on_leave': cls.who_on_leave(org, instant),
            'computed_at': datetime.utcnow().isoformat(timespec='seconds'),
        }
