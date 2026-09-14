"""
OpenDefense Module - Intake Event Model

收到的 OCSF 事件原始記錄,作為 webhook 冪等鍵 + 稽核線索。
"""
from sqlalchemy import Column, String, Boolean, DateTime, SmallInteger, Index
from sqlalchemy.dialects.postgresql import JSONB

from .base import OdBaseModel


class OdIntakeEvent(OdBaseModel):
    """Webhook 收到的 OCSF 事件原始記錄"""
    __tablename__ = 'od_intake_events'

    correlation_id = Column(String(64), nullable=False, unique=True, index=True)

    intake_key_secure_code = Column(String(32), nullable=False, index=True)

    source_system = Column(String(50), nullable=False)
    event_class = Column(String(30), nullable=False)
    severity_id = Column(SmallInteger, nullable=True)

    raw_body = Column(JSONB, nullable=False)
    signature_verified = Column(Boolean, nullable=False, default=False)

    case_secure_code = Column(String(32), nullable=True, index=True)

    received_at = Column(DateTime, nullable=False, index=True)

    __table_args__ = (
        Index('idx_od_intake_events_org_received', 'org_secure_code', 'received_at'),
    )

    def to_dict(self):
        base = super().to_dict()
        base.update({
            'correlation_id': self.correlation_id,
            'source_system': self.source_system,
            'event_class': self.event_class,
            'severity_id': self.severity_id,
            'signature_verified': self.signature_verified,
            'case_secure_code': self.case_secure_code,
            'received_at': self.received_at.isoformat() if self.received_at else None,
        })
        return base
