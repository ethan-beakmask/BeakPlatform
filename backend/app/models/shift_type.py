"""
BeakPlatform ShiftType Model
班次定義 - 早班、中班、晚班等

參考：docs/knowledge/time-management-spec.md
"""
from typing import Dict, Any, List

from sqlalchemy import Column, String, Integer, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import TenantBaseModel


class ShiftType(TenantBaseModel):
    """
    班次定義 Model

    定義企業的班次類型：
    - 早班 (MORNING): 08:00-16:00
    - 中班 (AFTERNOON): 16:00-24:00
    - 晚班 (NIGHT): 00:00-08:00
    - 休息 (OFF): 無工作時段

    用於個人排班時選擇班次
    """
    __tablename__ = 'shift_types'

    # 班次代碼 (如: MORNING, NIGHT)
    shift_code = Column(String(20), nullable=False, index=True)

    # 班次名稱
    name = Column(String(50), nullable=False)

    # 工作時段
    work_periods = Column(JSONB, nullable=False)

    # 月曆顯示顏色 (如: #4CAF50)
    color = Column(String(7), nullable=True)

    # 排序順序
    sort_order = Column(Integer, default=0, nullable=False)

    # 是否啟用
    is_active = Column(Boolean, default=True, nullable=False)

    # 關聯：使用此班次的個人排班
    personal_schedules = relationship('PersonalSchedule', back_populates='shift_type')

    def get_total_hours(self) -> float:
        """計算班次總工時（小時）"""
        total_minutes = 0
        for period in (self.work_periods or []):
            try:
                start_str, end_str = period.split('-')
                start_h, start_m = map(int, start_str.split(':'))
                end_h, end_m = map(int, end_str.split(':'))

                start_minutes = start_h * 60 + start_m
                end_minutes = end_h * 60 + end_m

                # 處理跨日（如 22:00-06:00）
                if end_minutes < start_minutes:
                    end_minutes += 24 * 60

                total_minutes += end_minutes - start_minutes
            except (ValueError, AttributeError):
                continue

        return total_minutes / 60

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'shift_code': self.shift_code,
            'name': self.name,
            'work_periods': self.work_periods,
            'color': self.color,
            'sort_order': self.sort_order,
            'is_active': self.is_active,
            'total_hours': self.get_total_hours(),
        })
        return base

    def __repr__(self):
        return f'<ShiftType {self.shift_code}: {self.name}>'


# 預設班次資料 (供 seed 使用)
DEFAULT_SHIFT_TYPES = [
    {
        'shift_code': 'MORNING',
        'name': '早班',
        'work_periods': ['08:00-16:00'],
        'color': '#4CAF50',
        'sort_order': 1,
    },
    {
        'shift_code': 'AFTERNOON',
        'name': '中班',
        'work_periods': ['16:00-24:00'],
        'color': '#2196F3',
        'sort_order': 2,
    },
    {
        'shift_code': 'NIGHT',
        'name': '晚班',
        'work_periods': ['00:00-08:00'],
        'color': '#9C27B0',
        'sort_order': 3,
    },
    {
        'shift_code': 'DAY',
        'name': '日班',
        'work_periods': ['09:00-12:00', '13:00-18:00'],
        'color': '#FF9800',
        'sort_order': 4,
    },
    {
        'shift_code': 'OFF',
        'name': '休息',
        'work_periods': [],
        'color': '#9E9E9E',
        'sort_order': 99,
    },
]
