"""
BeakPlatform - Lookup Item Model
通用選項清單 - 選項資料

org_secure_code nullable:
  - NULL = 系統級選項 (全平台共用)
  - 有值 = 企業級選項 (企業自訂)

繼承 BaseModel 而非 TenantBaseModel，因為 org_secure_code 可為 NULL。
"""
from decimal import Decimal as PyDecimal

from sqlalchemy import Column, String, Integer, BigInteger, Boolean, Date, Time, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import Numeric

from .base import BaseModel
from .. import db


class LookupItem(BaseModel):
    __tablename__ = 'lookup_items'

    org_secure_code = Column(
        String(32),
        db.ForeignKey('organizations.secure_code'),
        nullable=True,
        index=True
    )
    category_code = Column(String(100), nullable=False, index=True)
    code = Column(String(100), nullable=False)
    label = Column(String(200), nullable=False)
    label_i18n = Column(JSONB, nullable=True, default=dict)
    value = Column(JSONB, nullable=True)
    value_str = Column(String(500), nullable=True)
    value_int = Column(BigInteger, nullable=True)
    value_decimal = Column(Numeric(20, 2), nullable=True)
    value_date = Column(Date, nullable=True)
    value_time = Column(Time, nullable=True)
    value_datetime = Column(DateTime, nullable=True)
    parent_code = Column(String(100), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)

    def to_dict(self):
        base = super().to_dict()
        dec = self.value_decimal
        base.update({
            'category_code': self.category_code,
            'code': self.code,
            'label': self.label,
            'label_i18n': self.label_i18n or {},
            'value': self.value,
            'value_str': self.value_str,
            'value_int': self.value_int,
            'value_decimal': float(dec) if dec is not None else None,
            'value_date': self.value_date.isoformat() if self.value_date else None,
            'value_time': self.value_time.strftime('%H:%M') if self.value_time else None,
            'value_datetime': self.value_datetime.isoformat() if self.value_datetime else None,
            'parent_code': self.parent_code,
            'sort_order': self.sort_order,
            'is_active': self.is_active,
        })
        return base
