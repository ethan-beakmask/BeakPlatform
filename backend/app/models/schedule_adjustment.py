"""
BeakMask ScheduleAdjustment Model
排班調整 - 請假、加班、調班、取消班次

參考：docs/knowledge/time-management-spec.md

此 Model 預留給第三階段的請假單/加班單整合使用
"""
from typing import Dict, Any, List, Optional
from datetime import date, datetime

from sqlalchemy import Column, String, Date, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import TenantBaseModel


class ScheduleAdjustment(TenantBaseModel):
    """
    排班調整 Model

    用於記錄對排班的調整：
    - LEAVE: 請假（原時段不工作）
    - OVERTIME: 加班（額外工作時段）
    - SWAP: 調班（與他人交換）
    - CANCEL: 取消班次

    優先級：排班調整 > 個人排班 > 共用班表
    """
    __tablename__ = 'schedule_adjustments'

    # 用戶
    user_secure_code = Column(
        String(32),
        ForeignKey('users.secure_code'),
        nullable=False,
        index=True
    )

    # 調整日期
    adjust_date = Column(Date, nullable=False, index=True)

    # 調整類型
    adjust_type = Column(String(20), nullable=False)

    # 原本時段
    original_periods = Column(JSONB, nullable=True)

    # 調整後時段（加班用）
    adjusted_periods = Column(JSONB, nullable=True)

    # 關聯表單（第三階段用）
    form_instance_secure_code = Column(String(32), nullable=True)

    # 代班人
    substitute_user_secure_code = Column(
        String(32),
        ForeignKey('users.secure_code'),
        nullable=True
    )

    # 狀態
    status = Column(String(20), default='PENDING', nullable=False, index=True)

    # 審核資訊
    approved_at = Column(DateTime, nullable=True)
    approved_by = Column(String(32), nullable=True)

    # 備註
    note = Column(Text, nullable=True)

    # 關聯：用戶
    user = relationship(
        'User',
        foreign_keys=[user_secure_code],
        back_populates='schedule_adjustments'
    )

    # 關聯：代班人
    substitute_user = relationship(
        'User',
        foreign_keys=[substitute_user_secure_code]
    )

    def get_effective_periods(self) -> List[str]:
        """
        取得調整後的有效工作時段

        Returns:
            工作時段列表
        """
        if self.adjust_type == 'LEAVE':
            return []  # 請假無工時
        elif self.adjust_type == 'CANCEL':
            return []  # 取消班次無工時
        elif self.adjust_type in ('OVERTIME', 'SWAP'):
            return self.adjusted_periods or []
        return []

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'user_secure_code': self.user_secure_code,
            'adjust_date': self.adjust_date.isoformat() if self.adjust_date else None,
            'adjust_type': self.adjust_type,
            'original_periods': self.original_periods,
            'adjusted_periods': self.adjusted_periods,
            'form_instance_secure_code': self.form_instance_secure_code,
            'substitute_user_secure_code': self.substitute_user_secure_code,
            'status': self.status,
            'approved_at': self.approved_at.isoformat() if self.approved_at else None,
            'approved_by': self.approved_by,
            'note': self.note,
        })
        return base

    def __repr__(self):
        return f'<ScheduleAdjustment {self.user_secure_code} @ {self.adjust_date}: {self.adjust_type}>'
