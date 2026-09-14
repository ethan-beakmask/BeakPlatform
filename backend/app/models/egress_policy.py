"""
Egress Policy Models
資料出口政策：欄位能見度、計量閾值、出口稽核

規格：dev-notes/EGRESS_POLICY_SPEC.md
"""
from sqlalchemy import Column, String, Integer, Boolean, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from .base import TenantBaseModel

# 能見度三值，嚴格度由低到高
VISIBILITY_CLEAR = 'clear'
VISIBILITY_MASKED = 'masked'
VISIBILITY_HIDDEN = 'hidden'
VISIBILITY_ORDER = {VISIBILITY_CLEAR: 0, VISIBILITY_MASKED: 1, VISIBILITY_HIDDEN: 2}

EGRESS_CONTEXTS = ('list', 'detail', 'form_node', 'export')
EGRESS_METERS = ('list_rows', 'reveal', 'export')


class EgressFieldPolicy(TenantBaseModel):
    """
    欄位出口政策

    政策鍵：(org, resource_code, field_name, context) + 適用對象。
    適用對象優先序：角色+部門 > 角色(全部門) > 資源預設(role NULL)。
    同級多筆命中取最嚴格 visibility。
    """
    __tablename__ = 'egress_field_policies'
    __table_args__ = (
        UniqueConstraint(
            'org_secure_code', 'resource_code', 'field_name', 'context',
            'role_secure_code', 'department_secure_code', 'node_key',
            name='uq_egress_policy_scope',
        ),
    )

    resource_code = Column(String(50), nullable=False, index=True)
    field_name = Column(String(100), nullable=False)
    context = Column(String(20), nullable=False)  # list/detail/form_node/export

    # 適用對象（NULL 見 docstring）
    role_secure_code = Column(String(32), nullable=True, index=True)
    department_secure_code = Column(String(32), nullable=True)
    node_key = Column(String(100), nullable=True)  # form_node 語境的流程節點綁定

    visibility = Column(String(10), nullable=False, default=VISIBILITY_CLEAR)
    tier = Column(String(20), nullable=False, default='normal')  # 敏感度分級
    is_active = Column(Boolean, nullable=False, default=True)

    def to_dict(self):
        base = super().to_dict()
        base.update({
            'resource_code': self.resource_code,
            'field_name': self.field_name,
            'context': self.context,
            'role_secure_code': self.role_secure_code,
            'department_secure_code': self.department_secure_code,
            'node_key': self.node_key,
            'visibility': self.visibility,
            'tier': self.tier,
            'is_active': self.is_active,
        })
        return base


class EgressTierThreshold(TenantBaseModel):
    """
    敏感度分級 × 水表 × 閾值

    meter: list_rows / reveal / export
    window_minutes 內累計達 threshold 即觸發警戒（同窗冷卻不重複告警）。
    """
    __tablename__ = 'egress_tier_thresholds'
    __table_args__ = (
        UniqueConstraint(
            'org_secure_code', 'tier', 'meter',
            name='uq_egress_threshold_scope',
        ),
    )

    tier = Column(String(20), nullable=False)
    meter = Column(String(20), nullable=False)
    threshold = Column(Integer, nullable=False)
    window_minutes = Column(Integer, nullable=False, default=60)
    is_active = Column(Boolean, nullable=False, default=True)

    def to_dict(self):
        base = super().to_dict()
        base.update({
            'tier': self.tier,
            'meter': self.meter,
            'threshold': self.threshold,
            'window_minutes': self.window_minutes,
            'is_active': self.is_active,
        })
        return base


class EgressAuditLog(TenantBaseModel):
    """
    出口稽核記錄

    action:
        - 'list' / 'detail' / 'export': 一次出口，record_scs 為本次下發的記錄清單
        - 'reveal': 單格揭示，field_name 記欄位
        - 'alert': 水表觸發警戒
    """
    __tablename__ = 'egress_audit_logs'

    user_secure_code = Column(String(32), nullable=False, index=True)
    resource_code = Column(String(50), nullable=False, index=True)
    context = Column(String(20), nullable=False)
    action = Column(String(20), nullable=False, index=True)

    record_scs = Column(JSONB, nullable=True)   # 本次出口的記錄 secure_code 清單
    field_name = Column(String(100), nullable=True)  # reveal 時
    row_count = Column(Integer, nullable=False, default=0)
    tier = Column(String(20), nullable=True)
    meter = Column(String(20), nullable=True)   # alert 時記觸發的水表
    ip_address = Column(String(45), nullable=True)

    def to_dict(self):
        base = super().to_dict()
        base.update({
            'user_secure_code': self.user_secure_code,
            'resource_code': self.resource_code,
            'context': self.context,
            'action': self.action,
            'record_scs': self.record_scs,
            'field_name': self.field_name,
            'row_count': self.row_count,
            'tier': self.tier,
            'meter': self.meter,
            'ip_address': self.ip_address,
        })
        return base
