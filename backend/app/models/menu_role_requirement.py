"""
BeakPlatform MenuRoleRequirement Model
選單角色需求 - 定義存取選單項目所需的角色

白名單制：
- 選單無任何角色需求記錄 → 沿用現有 user_type 裝飾器檢查
- 選單有角色需求記錄 → 用戶必須持有其中至少一個角色
- 各企業獨立設定
"""
from typing import Dict, Any

from sqlalchemy import Column, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from .base import TenantBaseModel


class MenuRoleRequirement(TenantBaseModel):
    """
    選單角色需求

    定義某個選單項目在某個企業中需要哪些角色才能存取。
    同一選單可設定多個角色（OR 關係：持有任一角色即可）。
    """
    __tablename__ = 'menu_role_requirements'

    __table_args__ = (
        UniqueConstraint(
            'menu_secure_code', 'role_secure_code', 'org_secure_code',
            name='unique_menu_role_org'
        ),
    )

    # 選單項目
    menu_secure_code = Column(
        String(32),
        ForeignKey('menu_items.secure_code', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # 角色
    role_secure_code = Column(
        String(32),
        ForeignKey('roles.secure_code', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Relationships
    menu_item = relationship('MenuItem', backref='role_requirements')
    role = relationship('Role')

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'menu_secure_code': self.menu_secure_code,
            'role_secure_code': self.role_secure_code,
        })
        if self.role:
            base['role'] = {
                'id': self.role.secure_code,
                'code': self.role.code,
                'name': self.role.name,
            }
        return base

    def __repr__(self):
        return f'<MenuRoleRequirement menu={self.menu_secure_code} role={self.role_secure_code}>'
