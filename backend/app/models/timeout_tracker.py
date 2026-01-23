"""
BeakMask TimeoutTracker Model
逾時追蹤 - 追蹤表單流程的簽核逾時

參考：docs/knowledge/time-management-spec.md
"""
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from .base import TenantBaseModel


class TimeoutTracker(TenantBaseModel):
    """
    逾時追蹤 Model

    追蹤表單流程的簽核逾時：
    - ABSOLUTE: 絕對時間（24/7 倒數）
    - WORKING: 工作時間（僅在班表內倒數）
    - BOTH: 雙軌制（任一觸發即逾時）
    """
    __tablename__ = 'timeout_trackers'

    # 關聯表單流程
    form_instance_secure_code = Column(String(32), nullable=False, index=True)
    node_instance_secure_code = Column(String(32), nullable=False, index=True)

    # 簽核者
    assignee_secure_code = Column(
        String(32),
        ForeignKey('users.secure_code'),
        nullable=False,
        index=True
    )

    # 逾時模式
    timeout_mode = Column(String(20), nullable=False)

    # 規則1：絕對時間設定
    timeout_absolute_seconds = Column(Integer, nullable=True)
    timeout_absolute_at = Column(DateTime, nullable=True)

    # 規則2：工作時間設定
    timeout_working_seconds = Column(Integer, nullable=True)
    remaining_working_seconds = Column(Integer, nullable=True)

    # 請假標記（由請假流程寫入）
    on_leave = Column(Boolean, default=False, nullable=False)
    on_leave_until = Column(DateTime, nullable=True)

    # 狀態
    status = Column(String(20), default='PENDING', nullable=False, index=True)
    timeout_triggered_at = Column(DateTime, nullable=True)

    # 最後檢查時間
    last_check_at = Column(DateTime, nullable=True)

    # 關聯：簽核者
    assignee = relationship('User', back_populates='timeout_trackers')

    def is_timeout(self) -> bool:
        """檢查是否已逾時"""
        now = datetime.utcnow()

        # 規則1 檢查
        if self.timeout_absolute_at and now >= self.timeout_absolute_at:
            return True

        # 規則2 檢查
        if self.remaining_working_seconds is not None:
            if self.remaining_working_seconds <= 0:
                return True

        return False

    def mark_timeout(self) -> None:
        """標記為已逾時"""
        self.status = 'TIMEOUT'
        self.timeout_triggered_at = datetime.utcnow()

    def mark_completed(self) -> None:
        """標記為已完成（簽核完成）"""
        self.status = 'COMPLETED'

    def mark_transferred(self) -> None:
        """標記為已轉移（轉代理人）"""
        self.status = 'TRANSFERRED'

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'form_instance_secure_code': self.form_instance_secure_code,
            'node_instance_secure_code': self.node_instance_secure_code,
            'assignee_secure_code': self.assignee_secure_code,
            'timeout_mode': self.timeout_mode,
            'timeout_absolute_seconds': self.timeout_absolute_seconds,
            'timeout_absolute_at': self.timeout_absolute_at.isoformat() if self.timeout_absolute_at else None,
            'timeout_working_seconds': self.timeout_working_seconds,
            'remaining_working_seconds': self.remaining_working_seconds,
            'on_leave': self.on_leave,
            'on_leave_until': self.on_leave_until.isoformat() if self.on_leave_until else None,
            'status': self.status,
            'timeout_triggered_at': self.timeout_triggered_at.isoformat() if self.timeout_triggered_at else None,
            'last_check_at': self.last_check_at.isoformat() if self.last_check_at else None,
        })
        return base

    def __repr__(self):
        return f'<TimeoutTracker {self.node_instance_secure_code}: {self.status}>'
