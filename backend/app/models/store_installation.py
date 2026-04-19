"""
BeakPlatform Store Installation Model
內部商場安裝記錄
"""
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Boolean
from sqlalchemy.dialects.postgresql import JSONB

from .base import BaseModel


class StoreInstallation(BaseModel):
    """
    商品安裝記錄

    記錄哪個企業安裝了哪個商品、誰安裝的、安裝結果。
    """
    __tablename__ = 'store_installations'

    org_secure_code = Column(String(100), nullable=False, index=True)

    store_item_secure_code = Column(String(32), nullable=False, index=True)
    store_item_code = Column(String(100), nullable=False)
    installed_version = Column(String(20), nullable=False)

    installed_by_secure_code = Column(String(32), nullable=False)
    installed_by_name = Column(String(100), nullable=True)
    installed_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # 安裝結果摘要 (建立了哪些表單/流程)
    result_summary = Column(JSONB, nullable=True)

    def to_dict(self):
        base = super().to_dict()
        base.update({
            'store_item_secure_code': self.store_item_secure_code,
            'store_item_code': self.store_item_code,
            'installed_version': self.installed_version,
            'installed_by_name': self.installed_by_name,
            'installed_at': self.installed_at.isoformat() if self.installed_at else None,
            'result_summary': self.result_summary,
        })
        return base

    def __repr__(self):
        return f'<StoreInstallation {self.store_item_code}@{self.org_secure_code}>'
