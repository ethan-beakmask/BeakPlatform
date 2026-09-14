"""
BeakMask ScheduleHoliday Model
班表假日/補班日

參考：dev-notes/knowledge/time-management-spec.md
"""
from typing import Dict, Any, List
from datetime import date

from sqlalchemy import Column, String, Date, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import TenantBaseModel
from .. import db


class ScheduleHoliday(TenantBaseModel):
    """
    班表假日 Model

    用於覆蓋共用班表的特定日期：
    - HOLIDAY: 國定假日、公司特休
    - COMP_OFF: 補假
    - WORKDAY: 補班日

    優先級：假日設定 > 週間預設
    holiday_calendar_secure_code 為 NULL 代表手動設定；有值代表由企業假日表發佈寫入。
    """
    __tablename__ = 'schedule_holidays'

    # 所屬班表
    schedule_secure_code = Column(
        String(32),
        ForeignKey('work_schedules.secure_code'),
        nullable=False,
        index=True
    )

    # 假日日期
    holiday_date = Column(Date, nullable=False, index=True)

    # 類型：HOLIDAY=休假, COMP_OFF=補假, WORKDAY=補班
    holiday_type = Column(String(20), nullable=False)

    # 補班日的工作時段 (HOLIDAY/COMP_OFF 時為 null)
    work_periods = Column(JSONB, nullable=True)

    # 說明 (如: 中秋節, 補班日)
    description = Column(String(200), nullable=True)

    # 來源假日表；NULL 表示手動設定。不設 FK，避免刪除假日表時產生順序耦合。
    holiday_calendar_secure_code = Column(String(32), nullable=True, index=True)

    # 關聯：所屬班表
    schedule = relationship('WorkSchedule', back_populates='holidays')

    @property
    def org_secure_code(self):
        """從關聯的班表取得企業代碼"""
        if self.schedule:
            return self.schedule.org_secure_code
        return None

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'schedule_secure_code': self.schedule_secure_code,
            'holiday_date': self.holiday_date.isoformat() if self.holiday_date else None,
            'holiday_type': self.holiday_type,
            'work_periods': self.work_periods,
            'description': self.description,
            'holiday_calendar_secure_code': self.holiday_calendar_secure_code,
        })
        return base

    def __repr__(self):
        return f'<ScheduleHoliday {self.holiday_date}: {self.holiday_type}>'
