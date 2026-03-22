"""
BeakPlatform - Broadcast Acknowledgment Model
緊急廣播已讀確認記錄
"""
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Index

from .base import BaseModel
from .. import db


class BroadcastAcknowledgment(BaseModel):
    """
    廣播已讀確認

    記錄 AlertBroadcast 的用戶確認行為。
    broadcast_secure_code 對應 lookup_items 中 category_code='broadcast' 的記錄。
    """
    __tablename__ = 'broadcast_acknowledgments'

    broadcast_secure_code = Column(String(32), nullable=False, index=True)
    user_secure_code = Column(
        String(32),
        db.ForeignKey('users.secure_code'),
        nullable=False,
        index=True
    )
    org_secure_code = Column(
        String(32),
        db.ForeignKey('organizations.secure_code'),
        nullable=False,
        index=True
    )
    acknowledged_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index(
            'ix_broadcast_ack_unique',
            'broadcast_secure_code', 'user_secure_code',
            unique=True
        ),
    )

    def to_dict(self):
        base = super().to_dict()
        base.update({
            'broadcast_secure_code': self.broadcast_secure_code,
            'user_secure_code': self.user_secure_code,
            'acknowledged_at': self.acknowledged_at.isoformat() if self.acknowledged_at else None,
        })
        return base
