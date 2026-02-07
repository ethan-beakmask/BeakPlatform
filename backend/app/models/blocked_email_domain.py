"""
BeakPlatform Blocked Email Domain Model
禁止註冊的公共信箱 Domain
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Integer, String, DateTime

from .. import db


class BlockedEmailDomain(db.Model):
    """
    禁止註冊的公共信箱 Domain

    用於阻止使用 Gmail, Yahoo, Hotmail 等公共信箱 Domain 註冊企業。
    這些 Domain 不能作為企業的 domain_name。
    """
    __tablename__ = 'blocked_email_domains'

    id = Column(Integer, primary_key=True)
    domain = Column(String(255), unique=True, nullable=False, index=True, comment='Email Domain（小寫）')
    reason = Column(String(255), nullable=True, comment='封鎖原因')
    created_at = Column(DateTime, default=datetime.utcnow, comment='建立時間')

    @staticmethod
    def is_blocked(domain: str) -> bool:
        """
        檢查 domain 是否在黑名單

        Args:
            domain: 要檢查的 domain（會自動轉小寫）

        Returns:
            bool: True 表示在黑名單中
        """
        if not domain:
            return False
        return BlockedEmailDomain.query.filter_by(
            domain=domain.lower().strip()
        ).first() is not None

    @staticmethod
    def get_blocked_reason(domain: str) -> Optional[str]:
        """
        取得封鎖原因

        Args:
            domain: 要檢查的 domain

        Returns:
            str: 封鎖原因，如果不在黑名單則返回 None
        """
        if not domain:
            return None
        record = BlockedEmailDomain.query.filter_by(
            domain=domain.lower().strip()
        ).first()
        return record.reason if record else None

    @staticmethod
    def add_domain(domain: str, reason: str = None) -> 'BlockedEmailDomain':
        """
        新增封鎖的 domain

        Args:
            domain: 要封鎖的 domain
            reason: 封鎖原因

        Returns:
            BlockedEmailDomain: 新增的記錄

        Raises:
            ValueError: 如果 domain 已存在
        """
        domain = domain.lower().strip()
        if BlockedEmailDomain.is_blocked(domain):
            raise ValueError(f'Domain {domain} 已在黑名單中')

        record = BlockedEmailDomain(domain=domain, reason=reason)
        db.session.add(record)
        return record

    @staticmethod
    def remove_domain(domain: str) -> bool:
        """
        從黑名單移除 domain

        Args:
            domain: 要移除的 domain

        Returns:
            bool: True 表示成功移除，False 表示不存在
        """
        record = BlockedEmailDomain.query.filter_by(
            domain=domain.lower().strip()
        ).first()
        if record:
            db.session.delete(record)
            return True
        return False

    @staticmethod
    def list_all():
        """列出所有封鎖的 domain"""
        return BlockedEmailDomain.query.order_by(BlockedEmailDomain.domain).all()

    def to_dict(self):
        """轉換為字典"""
        return {
            'id': self.id,
            'domain': self.domain,
            'reason': self.reason,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    def __repr__(self):
        return f'<BlockedEmailDomain {self.domain}>'
