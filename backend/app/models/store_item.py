"""
BeakPlatform Store Item Model
內部商場商品
"""
from sqlalchemy import Column, String, Text, Boolean, DateTime, BigInteger
from sqlalchemy.dialects.postgresql import JSONB

from .base import BaseModel


class StoreItem(BaseModel):
    """
    商場商品

    儲存官方範本、軟體包等可供企業安裝的商品。
    item_type:
      - workflow_bundle: 表單+流程範本包 (payload 含 form_template + workflow_template + mapping)
      - form_template: 單獨表單範本
      - software: 軟體包 (未來)
    source:
      - official: BeakMask 官方提供
      - enterprise: 企業自建 (未來)
    scope:
      - tenant: 一般企業可安裝
      - platform: 僅系統企業可用
    """
    __tablename__ = 'store_items'

    # PK 為 bigint（與既有資料一致，PF-168 對齊）
    id = Column(BigInteger, primary_key=True)

    # org_secure_code: NULL=官方, 有值=企業自建
    org_secure_code = Column(String(100), nullable=True, index=True)

    code = Column(String(100), nullable=False, unique=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(50), nullable=True)

    item_type = Column(String(30), nullable=False, default='workflow_bundle')
    category = Column(String(100), nullable=True)
    version = Column(String(20), nullable=False, default='1.0')

    # 商品內容 (JSON)
    # workflow_bundle: {"form_template": {...}, "workflow_template": {...}, "mapping": {...}}
    payload = Column(JSONB, nullable=True)

    source = Column(String(20), nullable=False, default='official')
    scope = Column(String(20), nullable=False, default='tenant')

    is_active = Column(Boolean, nullable=False, default=True)

    def to_dict(self, include_payload=False):
        base = super().to_dict()
        base.update({
            'code': self.code,
            'name': self.name,
            'description': self.description,
            'icon': self.icon,
            'item_type': self.item_type,
            'category': self.category,
            'version': self.version,
            'source': self.source,
            'scope': self.scope,
            'is_active': self.is_active,
        })
        if include_payload:
            base['payload'] = self.payload
        return base

    def __repr__(self):
        return f'<StoreItem {self.code} v{self.version}>'
