"""
OpenDefense Module - Defense Decision Model

決策廣播表。由 workflow 節點(decision_writer)寫入,外部執行端拉取後落地實施。
"""
from sqlalchemy import Column, String, Boolean, DateTime, Integer, Text, Index
from sqlalchemy.dialects.postgresql import JSONB

from .base import OdBaseModel


VALID_ACTIONS = ('block', 'unblock', 'allow', 'escalate', 'observe')
VALID_TARGET_TYPES = (
    'ip', 'ipv6', 'cidr', 'domain', 'url', 'asn', 'country',
    'user_agent', 'jwt_sub',
)
VALID_DECIDED_VIA = ('human', 'auto', 'ai')
VALID_STATUSES = (
    'pending', 'picked_up', 'applied', 'partial',
    'failed', 'expired', 'revoked',
)
VALID_SEVERITIES = ('info', 'low', 'medium', 'high', 'critical')


class OdDefenseDecision(OdBaseModel):
    """防禦決策"""
    __tablename__ = 'od_defense_decisions'

    case_secure_code = Column(String(32), nullable=True, index=True)
    workflow_node_id = Column(String(40), nullable=True)

    intake_event_secure_code = Column(String(32), nullable=True, index=True)

    action = Column(String(20), nullable=False)
    target_type = Column(String(20), nullable=False)
    target_value = Column(String(500), nullable=False)
    enforcement_points = Column(JSONB, nullable=False, default=list)
    severity = Column(String(10), nullable=True)

    ttl_seconds = Column(Integer, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    reason = Column(Text, nullable=True)
    decided_via = Column(String(10), nullable=False)
    decided_by_secure_code = Column(String(32), nullable=True)
    decided_at = Column(DateTime, nullable=False)

    status = Column(String(20), nullable=False, default='pending', index=True)
    picked_up_at = Column(DateTime, nullable=True)
    applied_at = Column(DateTime, nullable=True)
    applied_by = Column(String(100), nullable=True)
    application_result = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)

    revoked_by_decision_secure_code = Column(String(32), nullable=True)

    related_finding_ids = Column(JSONB, nullable=True)
    decision_metadata = Column(JSONB, nullable=True)

    __table_args__ = (
        Index('idx_od_decisions_target', 'target_type', 'target_value'),
        Index('idx_od_decisions_org_time', 'org_secure_code', 'created_at'),
        Index('idx_od_decisions_pending_expiry', 'status', 'expires_at'),
    )

    def to_dict(self):
        base = super().to_dict()
        base.update({
            'case_secure_code': self.case_secure_code,
            'action': self.action,
            'target_type': self.target_type,
            'target_value': self.target_value,
            'enforcement_points': self.enforcement_points or [],
            'severity': self.severity,
            'ttl_seconds': self.ttl_seconds,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'reason': self.reason,
            'decided_via': self.decided_via,
            'decided_at': self.decided_at.isoformat() if self.decided_at else None,
            'status': self.status,
            'picked_up_at': self.picked_up_at.isoformat() if self.picked_up_at else None,
            'applied_at': self.applied_at.isoformat() if self.applied_at else None,
            'applied_by': self.applied_by,
            'application_result': self.application_result,
            'error_message': self.error_message,
        })
        return base
