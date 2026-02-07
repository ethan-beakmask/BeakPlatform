"""
BeakPlatform Delegation Model
代理授權 Model - 職務代理機制

當主管出差、請假時，可授權代理人：
1. 全權代理 - 代理人可執行所有權限
2. 限定代理 - 只能簽核特定金額或特定流程

代理授權的重要性：
- 避免流程卡住（主管不在時）
- 符合稽核要求（有明確的授權紀錄）
- 彈性的權限控制（可限定範圍）
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, Any, Optional

from sqlalchemy import Column, String, Boolean, Date, DateTime, Text, Numeric, ForeignKey
from sqlalchemy.orm import relationship

from .base import TenantBaseModel
from .. import db


class DelegationType:
    """代理類型"""
    FULL = 'FULL'                # 全權代理
    APPROVAL = 'APPROVAL'        # 僅簽核代理
    SPECIFIC = 'SPECIFIC'        # 特定流程代理


class DelegationStatus:
    """代理狀態"""
    PENDING = 'PENDING'          # 待生效
    ACTIVE = 'ACTIVE'            # 生效中
    EXPIRED = 'EXPIRED'          # 已過期
    REVOKED = 'REVOKED'          # 已撤銷


class Delegation(TenantBaseModel):
    """
    代理授權 Model

    支援：
    - 全權代理：代理人可執行授權人的所有權限
    - 限定代理：只能簽核特定金額以下，或特定流程類型
    - 時間限定：指定生效期間

    範例：
    - 王經理出差 12/20-12/31，授權李副理全權代理
    - 張處長授權陳經理代理簽核 100 萬以下的請購單
    """
    __tablename__ = 'delegations'

    # 授權人（誰授權）
    delegator_secure_code = Column(
        String(32),
        ForeignKey('users.secure_code'),
        nullable=False,
        index=True
    )

    # 被授權人（誰被授權）
    delegate_secure_code = Column(
        String(32),
        ForeignKey('users.secure_code'),
        nullable=False,
        index=True
    )

    # 代理類型
    delegation_type = Column(
        String(20),
        default=DelegationType.FULL,
        nullable=False,
        index=True
    )

    # 狀態
    status = Column(
        String(20),
        default=DelegationStatus.PENDING,
        nullable=False,
        index=True
    )

    # 生效期間
    effective_from = Column(Date, nullable=False)
    effective_until = Column(Date, nullable=False)

    # 金額上限（NULL = 無上限，使用授權人原有權限）
    approval_limit = Column(Numeric(15, 2), nullable=True)
    approval_currency = Column(String(3), default='TWD', nullable=False)

    # 特定流程類型（JSON 陣列，如 ["請購單", "費用報銷"]）
    # NULL = 所有流程
    allowed_process_types = Column(Text, nullable=True)

    # 授權原因
    reason = Column(Text, nullable=True)

    # 授權時間
    created_by = Column(String(100), nullable=True)

    # 撤銷資訊
    revoked_at = Column(DateTime, nullable=True)
    revoked_by = Column(String(100), nullable=True)
    revoke_reason = Column(Text, nullable=True)

    # 關聯
    delegator = relationship('User', foreign_keys=[delegator_secure_code],
                            backref=db.backref('delegations_given', lazy='dynamic'))
    delegate = relationship('User', foreign_keys=[delegate_secure_code],
                           backref=db.backref('delegations_received', lazy='dynamic'))

    @property
    def is_active(self) -> bool:
        """檢查代理授權是否生效中"""
        if self.status != DelegationStatus.ACTIVE:
            return False
        today = date.today()
        return self.effective_from <= today <= self.effective_until

    @property
    def is_expired(self) -> bool:
        """檢查是否已過期"""
        return date.today() > self.effective_until

    @property
    def days_remaining(self) -> int:
        """剩餘天數"""
        if self.is_expired:
            return 0
        return (self.effective_until - date.today()).days

    def can_approve_amount(self, amount: Decimal, currency: str = 'TWD') -> bool:
        """
        檢查代理人是否可簽核指定金額

        Args:
            amount: 金額
            currency: 幣別

        Returns:
            是否可簽核
        """
        if not self.is_active:
            return False

        if self.approval_limit is None:
            return True  # 無上限

        if currency != self.approval_currency:
            # TODO: 匯率轉換
            pass

        return amount <= self.approval_limit

    def can_handle_process(self, process_type: str) -> bool:
        """
        檢查代理人是否可處理指定流程類型

        Args:
            process_type: 流程類型

        Returns:
            是否可處理
        """
        if not self.is_active:
            return False

        if self.allowed_process_types is None:
            return True  # 所有流程

        import json
        try:
            allowed = json.loads(self.allowed_process_types)
            return process_type in allowed
        except:
            return True

    def activate(self) -> None:
        """啟動代理授權"""
        self.status = DelegationStatus.ACTIVE

    def revoke(self, revoked_by: str, reason: str = None) -> None:
        """撤銷代理授權"""
        self.status = DelegationStatus.REVOKED
        self.revoked_at = datetime.utcnow()
        self.revoked_by = revoked_by
        self.revoke_reason = reason

    def check_and_update_status(self) -> None:
        """檢查並更新狀態"""
        today = date.today()

        if self.status == DelegationStatus.REVOKED:
            return  # 已撤銷不變更

        if today < self.effective_from:
            self.status = DelegationStatus.PENDING
        elif today > self.effective_until:
            self.status = DelegationStatus.EXPIRED
        else:
            self.status = DelegationStatus.ACTIVE

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'delegator_id': self.delegator_secure_code,
            'delegate_id': self.delegate_secure_code,
            'delegation_type': self.delegation_type,
            'status': self.status,
            'is_active': self.is_active,
            'effective_from': self.effective_from.isoformat() if self.effective_from else None,
            'effective_until': self.effective_until.isoformat() if self.effective_until else None,
            'days_remaining': self.days_remaining,
            'approval_limit': float(self.approval_limit) if self.approval_limit else None,
            'approval_currency': self.approval_currency,
            'allowed_process_types': self.allowed_process_types,
            'reason': self.reason,
        })

        if self.delegator:
            base['delegator'] = {
                'id': self.delegator.secure_code,
                'name': self.delegator.display_name,
            }

        if self.delegate:
            base['delegate'] = {
                'id': self.delegate.secure_code,
                'name': self.delegate.display_name,
            }

        return base

    def __repr__(self):
        return f'<Delegation {self.delegator_secure_code} -> {self.delegate_secure_code}>'
