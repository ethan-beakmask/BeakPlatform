"""
BeakMask Contract Model
合約 Model
"""
import json
from datetime import date, datetime
from typing import Dict, Any, Optional

from sqlalchemy import Column, String, Date, Text, Numeric, Sequence, ForeignKey, DateTime
from sqlalchemy.orm import relationship

from .base import TenantBaseModel
from .. import db


class ContractStatus:
    """合約狀態"""
    ACTIVE = 'ACTIVE'      # 有效
    DISABLED = 'DISABLED'  # 停用


# 合約編號序列
contract_number_seq = Sequence('contract_number_seq', start=1)


class Contract(TenantBaseModel):
    """
    合約 Model

    企業可有多張合約同時進行。
    登入權限根據所有 ACTIVE 合約計算：
    - 開始時間：取所有合約的最早開始日期
    - 結束時間：取所有合約的最晚結束日期（當天 23:59:59）
    """
    __tablename__ = 'contracts'

    # 合約編號 (唯一，格式: CTR-YYYYMMDD-XXXX)
    contract_number = Column(String(50), unique=True, nullable=False, index=True)

    # 合約名稱/描述
    name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)

    # 合約期間
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)

    # 合約金額
    amount = Column(Numeric(12, 2), nullable=True)

    # 合約狀態
    status = Column(
        String(20),
        default=ContractStatus.ACTIVE,
        nullable=False
    )

    # 模組配置 (JSON，預留欄位)
    modules_config = Column(Text, nullable=True)

    # 備註
    notes = Column(Text, nullable=True)

    # 稽核欄位
    created_by_secure_code = Column(
        String(32),
        ForeignKey('users.secure_code'),
        nullable=True,
        comment='建立者'
    )
    modified_by_secure_code = Column(
        String(32),
        ForeignKey('users.secure_code'),
        nullable=True,
        comment='最後修改者'
    )
    modified_at = Column(DateTime, nullable=True, comment='最後修改時間')

    # 關聯
    organization = relationship('Organization', back_populates='contracts')
    created_by = relationship('User', foreign_keys=[created_by_secure_code])
    modified_by = relationship('User', foreign_keys=[modified_by_secure_code])

    @staticmethod
    def generate_contract_number() -> str:
        """
        產生合約編號

        格式: CTR-YYYYMMDD-XXXX
        XXXX 為當天的序號
        """
        today = date.today()
        date_str = today.strftime('%Y%m%d')
        prefix = f'CTR-{date_str}-'

        # 查詢今天已有的合約數量
        count = Contract.query.filter(
            Contract.contract_number.like(f'{prefix}%')
        ).count()

        return f'{prefix}{(count + 1):04d}'

    def _org_today(self) -> date:
        if self.organization:
            return self.organization.local_today()

        from app.utils.timezone import local_today
        return local_today('Asia/Taipei')

    @property
    def is_active(self) -> bool:
        """合約是否有效（狀態為 ACTIVE 且在期限內）"""
        if self.status != ContractStatus.ACTIVE:
            return False
        today = self._org_today()
        return self.start_date <= today <= self.end_date

    @property
    def is_expired(self) -> bool:
        """合約是否已過期"""
        return self._org_today() > self.end_date

    @property
    def is_not_started(self) -> bool:
        """合約是否尚未開始"""
        return self._org_today() < self.start_date

    @property
    def days_remaining(self) -> Optional[int]:
        """
        剩餘天數

        Returns:
            int: 正數表示剩餘天數，負數表示已過期天數
            None: 如果合約狀態為 DISABLED
        """
        if self.status == ContractStatus.DISABLED:
            return None
        today = self._org_today()
        return (self.end_date - today).days

    def to_dict(self, include_org: bool = False) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'contract_number': self.contract_number,
            'name': self.name,
            'description': self.description,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'amount': float(self.amount) if self.amount else None,
            'status': self.status,
            'is_active': self.is_active,
            'is_expired': self.is_expired,
            'days_remaining': self.days_remaining,
            'modules_config': json.loads(self.modules_config) if self.modules_config else [],
            'modified_at': self.modified_at.isoformat() if self.modified_at else None,
        })

        # 稽核資訊
        if self.created_by:
            base['created_by'] = {
                'id': self.created_by.secure_code,
                'display_name': self.created_by.display_name,
            }
        if self.modified_by:
            base['modified_by'] = {
                'id': self.modified_by.secure_code,
                'display_name': self.modified_by.display_name,
            }

        if include_org and self.organization:
            base['organization'] = {
                'id': self.organization.secure_code,
                'code': self.organization.code,
                'name': self.organization.name,
            }

        return base

    def __repr__(self):
        return f'<Contract {self.contract_number}>'
