"""
BeakPlatform - Lookup Category Model
通用選項清單 - 類別定義

org_secure_code nullable:
  - NULL = 系統級類別 (全平台共用)
  - 有值 = 企業級類別 (企業自訂)

繼承 BaseModel 而非 TenantBaseModel，因為 org_secure_code 可為 NULL。
"""
from sqlalchemy import Column, String, Boolean, Text
from sqlalchemy.dialects.postgresql import JSONB

from .base import BaseModel
from .. import db


class LookupCategory(BaseModel):
    __tablename__ = 'lookup_categories'

    org_secure_code = Column(
        String(32),
        db.ForeignKey('organizations.secure_code'),
        nullable=True,
        index=True
    )
    code = Column(String(100), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    name_i18n = Column(JSONB, nullable=True, default=dict)
    description = Column(Text, nullable=True)
    is_system = Column(Boolean, nullable=False, default=False)
    is_hierarchical = Column(Boolean, nullable=False, default=False)

    def to_dict(self):
        base = super().to_dict()
        base.update({
            'code': self.code,
            'name': self.name,
            'name_i18n': self.name_i18n or {},
            'description': self.description,
            'is_system': self.is_system,
            'is_hierarchical': self.is_hierarchical,
        })
        return base
