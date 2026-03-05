"""
Data CRUD Module - SubSystem Model
子系統配置

子系統綁定一個社群 (OrganizationalUnit type=GROUP)，
社群成員才能進入此子系統。
"""
from typing import Dict, Any

from sqlalchemy import Column, String, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB

from .base import ModuleBaseModel


class DcSubSystem(ModuleBaseModel):
    """子系統配置"""
    __tablename__ = 'dc_sub_systems'

    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(50), nullable=True)
    group_unit_secure_code = Column(String(32), nullable=False, index=True)
    menu_item_secure_code = Column(String(32), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Phase 1: 狀態機 + 開發者名單 + 佈局模式
    status = Column(String(20), default='draft', nullable=False)
    developers = Column(JSONB, default=list)
    layout_mode = Column(String(20), default='grid', nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            'name': self.name,
            'description': self.description,
            'icon': self.icon,
            'group_unit_secure_code': self.group_unit_secure_code,
            'menu_item_secure_code': self.menu_item_secure_code,
            'is_active': self.is_active,
            'status': self.status,
            'developers': self.developers or [],
            'layout_mode': self.layout_mode,
        })
        return data
