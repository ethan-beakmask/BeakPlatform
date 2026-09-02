"""
BeakMask WorkSchedule Model
共用班表 - 企業+地區+時區的標準工時

參考：dev-notes/knowledge/time-management-spec.md
"""
from typing import Dict, Any, List, Optional
from datetime import date, time, datetime

from sqlalchemy import Column, String, Boolean, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import TenantBaseModel


class WorkSchedule(TenantBaseModel):
    """
    共用班表 Model

    定義企業的標準工時模式，包含：
    - 時區設定
    - 週間預設工時（週一到週日）
    - 企業預設班表標記

    優先級：個人排班 > 共用班表
    """
    __tablename__ = 'work_schedules'

    # 班表代碼 (如: TW-STANDARD, JP-REMOTE)
    schedule_code = Column(String(50), nullable=False, index=True)

    # 班表名稱
    name = Column(String(100), nullable=False)

    # 時區 (如: Asia/Taipei, Asia/Tokyo)
    timezone = Column(String(50), nullable=False, default='Asia/Taipei')

    # 週間預設工時 JSON
    # {"mon": ["09:00-12:00", "13:00-18:00"], "tue": [...], "sat": null, "sun": null}
    weekly_hours = Column(JSONB, nullable=False, default=dict)

    # 是否為企業預設班表
    is_default = Column(Boolean, default=False, nullable=False)

    # 是否啟用
    is_active = Column(Boolean, default=True, nullable=False)

    # 描述
    description = Column(Text, nullable=True)

    # 關聯：班表假日
    holidays = relationship(
        'ScheduleHoliday',
        back_populates='schedule',
        cascade='all, delete-orphan'
    )

    # 關聯：使用此班表的用戶
    users = relationship('User', back_populates='work_schedule')

    def get_day_periods(self, target_date: date) -> List[str]:
        """
        取得指定日期的工作時段

        Args:
            target_date: 目標日期

        Returns:
            工作時段列表，如 ["09:00-12:00", "13:00-18:00"]
            休息日返回空列表；COMP_OFF 補假視同休假
        """
        # 先檢查假日/補班
        from .schedule_holiday import ScheduleHoliday
        holiday = ScheduleHoliday.query.filter_by(
            schedule_secure_code=self.secure_code,
            holiday_date=target_date,
            is_deleted=False
        ).first()

        if holiday:
            if holiday.holiday_type in ('HOLIDAY', 'COMP_OFF'):
                return []
            else:  # WORKDAY 補班
                return holiday.work_periods or []

        # 週間預設
        weekday_map = {
            0: 'mon', 1: 'tue', 2: 'wed', 3: 'thu',
            4: 'fri', 5: 'sat', 6: 'sun'
        }
        weekday = weekday_map.get(target_date.weekday(), 'mon')
        periods = self.weekly_hours.get(weekday)

        return periods if periods else []

    def is_working_day(self, target_date: date) -> bool:
        """檢查指定日期是否為工作日"""
        return len(self.get_day_periods(target_date)) > 0

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'schedule_code': self.schedule_code,
            'name': self.name,
            'timezone': self.timezone,
            'weekly_hours': self.weekly_hours,
            'is_default': self.is_default,
            'is_active': self.is_active,
            'description': self.description,
        })
        return base

    def __repr__(self):
        return f'<WorkSchedule {self.schedule_code}: {self.name}>'


# 預設班表資料 (供 seed 使用)
DEFAULT_WORK_SCHEDULES = [
    {
        'schedule_code': 'TW-STANDARD',
        'name': '台灣標準班表',
        'timezone': 'Asia/Taipei',
        'weekly_hours': {
            'mon': ['09:00-12:00', '13:00-18:00'],
            'tue': ['09:00-12:00', '13:00-18:00'],
            'wed': ['09:00-12:00', '13:00-18:00'],
            'thu': ['09:00-12:00', '13:00-18:00'],
            'fri': ['09:00-12:00', '13:00-18:00'],
            'sat': None,
            'sun': None,
        },
        'is_default': True,
        'description': '週一至週五 09:00-18:00，中午休息一小時',
    },
]
