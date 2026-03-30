"""
BeakMask ApprovalCategory Model
核決權限類別 - 定義各種費用類別及其核決金額上限

用途：
- 管理員可建立各種費用類別（零用金、辦公室設備、耗材、教育訓練等）
- 每個職等可針對不同類別設定不同的核決上限
"""
from typing import Dict, Any, Optional, List
from decimal import Decimal

from sqlalchemy import Column, String, Integer, Boolean, Text, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import TenantBaseModel
from .mixins import I18nMixin


class ApprovalCategory(TenantBaseModel, I18nMixin):
    """
    核決權限類別

    企業可自訂各種費用類別，例如：
    - 零用金
    - 辦公室設備
    - 耗材
    - 教育訓練
    - 差旅費
    - 廣告行銷
    """
    __tablename__ = 'approval_categories'

    # 類別代碼 (如: PETTY_CASH, EQUIPMENT)
    code = Column(String(50), nullable=False, index=True)

    # 類別名稱 (中文)
    name = Column(String(100), nullable=False)

    # 多語系名稱 (JSONB: {"en": "...", "zh-CN": "...", "ja": "..."})
    name_i18n = Column(JSONB, nullable=True, default=dict)

    # [向下相容] 舊欄位 — 新程式碼請用 name_i18n
    name_en = Column(String(100), nullable=True)

    # I18nMixin 向下相容映射
    _I18N_LEGACY_FIELD_MAP = {'en': 'name_en'}

    # 類別描述
    description = Column(Text, nullable=True)

    # 幣別 (預設 TWD)
    currency = Column(String(3), default='TWD', nullable=False)

    # 排序順序
    sort_order = Column(Integer, default=0, nullable=False)

    # 是否為系統預設 (不可刪除)
    is_system_default = Column(Boolean, default=False, nullable=False)

    # 是否啟用
    is_active = Column(Boolean, default=True, nullable=False)

    # 關聯：此類別的所有職等核決上限
    approval_limits = relationship(
        'JobLevelApprovalLimit',
        back_populates='category',
        cascade='all, delete-orphan'
    )

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'code': self.code,
            'name': self.name,
            'name_i18n': self.name_i18n or {},
            'name_en': self.name_en,
            'description': self.description,
            'currency': self.currency,
            'sort_order': self.sort_order,
            'is_system_default': self.is_system_default,
            'is_active': self.is_active,
        })
        return base

    def __repr__(self):
        return f'<ApprovalCategory {self.code}: {self.name}>'


class JobLevelApprovalLimit(TenantBaseModel):
    """
    職等核決上限

    關聯表：職等 + 類別 = 核決金額上限
    """
    __tablename__ = 'job_level_approval_limits'

    # 職等 secure_code (外鍵)
    job_level_secure_code = Column(
        String(32),
        ForeignKey('job_levels.secure_code'),
        nullable=False,
        index=True
    )

    # 類別 secure_code (外鍵)
    category_secure_code = Column(
        String(32),
        ForeignKey('approval_categories.secure_code'),
        nullable=False,
        index=True
    )

    # 核決金額上限 (NULL = 無上限)
    approval_limit = Column(Numeric(15, 2), nullable=True)

    # 關聯
    job_level = relationship('JobLevel', back_populates='approval_limits')
    category = relationship('ApprovalCategory', back_populates='approval_limits')

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'job_level_secure_code': self.job_level_secure_code,
            'category_secure_code': self.category_secure_code,
            'approval_limit': float(self.approval_limit) if self.approval_limit is not None else None,
            'category_name': self.category.name if self.category else None,
            'category_code': self.category.code if self.category else None,
        })
        return base

    def __repr__(self):
        return f'<JobLevelApprovalLimit {self.job_level_secure_code}/{self.category_secure_code}: {self.approval_limit}>'


# 預設費用類別 (供 seed 使用)
DEFAULT_APPROVAL_CATEGORIES = [
    {
        'code': 'PETTY_CASH',
        'name': '零用金',
        'name_en': 'Petty Cash',
        'description': '日常零星費用',
        'sort_order': 10,
    },
    {
        'code': 'EQUIPMENT',
        'name': '辦公室設備',
        'name_en': 'Office Equipment',
        'description': '辦公設備採購',
        'sort_order': 20,
    },
    {
        'code': 'CONSUMABLES',
        'name': '耗材',
        'name_en': 'Consumables',
        'description': '消耗性物品',
        'sort_order': 30,
    },
    {
        'code': 'TRAINING',
        'name': '教育訓練',
        'name_en': 'Training',
        'description': '企業成員訓練課程',
        'sort_order': 40,
    },
    {
        'code': 'TRAVEL',
        'name': '差旅費',
        'name_en': 'Travel',
        'description': '出差相關費用',
        'sort_order': 50,
    },
    {
        'code': 'MARKETING',
        'name': '廣告行銷',
        'name_en': 'Marketing',
        'description': '廣告及行銷費用',
        'sort_order': 60,
    },
]
