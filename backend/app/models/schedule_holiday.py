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
        })
        return base

    def __repr__(self):
        return f'<ScheduleHoliday {self.holiday_date}: {self.holiday_type}>'


# 2026 年台灣國定假日 (供 seed 使用)
DEFAULT_TW_HOLIDAYS_2026 = [
    {'date': '2026-01-01', 'type': 'HOLIDAY', 'desc': '中華民國開國紀念日'},
    {'date': '2026-01-02', 'type': 'HOLIDAY', 'desc': '彈性放假'},
    {'date': '2026-02-16', 'type': 'HOLIDAY', 'desc': '農曆除夕'},
    {'date': '2026-02-17', 'type': 'HOLIDAY', 'desc': '春節'},
    {'date': '2026-02-18', 'type': 'HOLIDAY', 'desc': '春節'},
    {'date': '2026-02-19', 'type': 'HOLIDAY', 'desc': '春節'},
    {'date': '2026-02-20', 'type': 'HOLIDAY', 'desc': '春節補假'},
    {'date': '2026-02-28', 'type': 'HOLIDAY', 'desc': '和平紀念日'},
    {'date': '2026-04-04', 'type': 'HOLIDAY', 'desc': '兒童節'},
    {'date': '2026-04-05', 'type': 'HOLIDAY', 'desc': '清明節'},
    {'date': '2026-04-06', 'type': 'HOLIDAY', 'desc': '彈性放假'},
    {'date': '2026-05-31', 'type': 'HOLIDAY', 'desc': '端午節'},
    {'date': '2026-10-04', 'type': 'HOLIDAY', 'desc': '中秋節'},
    {'date': '2026-10-05', 'type': 'HOLIDAY', 'desc': '中秋節補假'},
    {'date': '2026-10-10', 'type': 'HOLIDAY', 'desc': '國慶日'},
]
