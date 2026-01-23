"""
BeakMask PersonalSchedule Model
個人排班 - 覆蓋共用班表的個人排班設定

參考：docs/knowledge/time-management-spec.md
"""
from typing import Dict, Any, List, Optional
from datetime import date

from sqlalchemy import Column, String, Date, Text, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import TenantBaseModel


class PersonalSchedule(TenantBaseModel):
    """
    個人排班 Model

    覆蓋共用班表的個人排班設定：
    - 指定班次（shift_type_secure_code）
    - 或自訂時段（custom_periods）
    - 兩者皆無表示排休

    優先級：個人排班 > 共用班表
    """
    __tablename__ = 'personal_schedules'

    # 用戶
    user_secure_code = Column(
        String(32),
        ForeignKey('users.secure_code'),
        nullable=False,
        index=True
    )

    # 排班日期
    schedule_date = Column(Date, nullable=False, index=True)

    # 班次（可選）
    shift_type_secure_code = Column(
        String(32),
        ForeignKey('shift_types.secure_code'),
        nullable=True
    )

    # 自訂時段（不使用班次定義時）
    custom_periods = Column(JSONB, nullable=True)

    # 來源：MANUAL=手動, TEMPLATE=範本, SWAP=調班
    source = Column(String(20), default='MANUAL', nullable=False)

    # 備註
    note = Column(Text, nullable=True)

    # 關聯：用戶
    user = relationship('User', back_populates='personal_schedules')

    # 關聯：班次
    shift_type = relationship('ShiftType', back_populates='personal_schedules')

    def get_work_periods(self) -> List[str]:
        """
        取得工作時段

        Returns:
            工作時段列表，如 ["09:00-12:00", "13:00-18:00"]
            排休返回空列表
        """
        # 優先使用班次
        if self.shift_type_secure_code and self.shift_type:
            return self.shift_type.work_periods or []

        # 其次使用自訂時段
        if self.custom_periods:
            return self.custom_periods

        # 兩者皆無表示排休
        return []

    def is_day_off(self) -> bool:
        """是否為排休日"""
        return len(self.get_work_periods()) == 0

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'user_secure_code': self.user_secure_code,
            'schedule_date': self.schedule_date.isoformat() if self.schedule_date else None,
            'shift_type_secure_code': self.shift_type_secure_code,
            'shift_type': self.shift_type.to_dict() if self.shift_type else None,
            'custom_periods': self.custom_periods,
            'work_periods': self.get_work_periods(),
            'source': self.source,
            'note': self.note,
            'is_day_off': self.is_day_off(),
        })
        return base

    def __repr__(self):
        return f'<PersonalSchedule {self.user_secure_code} @ {self.schedule_date}>'
