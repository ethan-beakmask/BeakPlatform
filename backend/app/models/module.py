"""
BeakMask Module Model
功能模組 - No-Code Builder 的基礎單位
"""
from typing import Dict, Any

from sqlalchemy import Column, String, Boolean, Integer, Text, CheckConstraint
from sqlalchemy.orm import relationship

from .base import TenantBaseModel


class Module(TenantBaseModel):
    """
    模組 Model

    代表一個功能模組 (如: 會員系統、報名系統)。
    No-Code Builder 可自動生成模組及其關聯的頁面和選單。
    """
    __tablename__ = 'modules'
    __table_args__ = (
        CheckConstraint("scope IN ('tenant', 'platform')", name='ck_modules_scope'),
    )

    # 模組代碼 (企業內唯一)
    code = Column(String(50), nullable=False)

    # 模組名稱
    name = Column(String(100), nullable=False)

    # 模組描述
    description = Column(Text, nullable=True)

    # 模組圖標 (文字符號，如 "👤")
    icon = Column(String(10), nullable=True)

    # 模組用途範圍: tenant=一般業務模組, platform=基礎設施模組(僅系統企業)
    scope = Column(String(20), nullable=False, default='tenant')

    # 是否系統內建模組 (不可刪除)
    is_system_module = Column(Boolean, default=False, nullable=False)

    # 是否啟用
    is_active = Column(Boolean, default=True, nullable=False)

    # 顯示順序
    display_order = Column(Integer, default=0, nullable=False)

    # 模組設定 (JSON)
    settings = Column(Text, nullable=True)

    # Relationships
    menu_items = relationship('MenuItem', back_populates='module', lazy='dynamic')
    pages = relationship('Page', back_populates='module', lazy='dynamic')

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'code': self.code,
            'name': self.name,
            'description': self.description,
            'icon': self.icon,
            'scope': self.scope,
            'is_system_module': self.is_system_module,
            'is_active': self.is_active,
            'display_order': self.display_order,
        })
        return base

    def __repr__(self):
        return f'<Module {self.code}>'
