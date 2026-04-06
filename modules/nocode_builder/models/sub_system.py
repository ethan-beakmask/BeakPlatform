"""
Data CRUD Module - SubSystem Model
子系統配置

子系統可選綁定社群/部門；開發者透過 developers JSONB 管理。
名稱 (name) 為 Single Source of Truth，選單標題跟隨同步。
"""
from typing import Dict, Any

from sqlalchemy import Column, String, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB

from .base import ModuleBaseModel


class DcSubSystem(ModuleBaseModel):
    """子系統配置"""
    __tablename__ = 'dc_sub_systems'

    code = Column(String(60), nullable=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(50), nullable=True)
    group_unit_secure_code = Column(String(32), nullable=True, index=True)
    menu_item_secure_code = Column(String(32), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # 狀態機 + 開發者名單 + 佈局模式
    status = Column(String(20), default='draft', nullable=False)
    developers = Column(JSONB, default=list)
    layout_mode = Column(String(20), default='grid', nullable=False)

    # 來源申請單號（由 SubSystemProvision 節點自動填入）
    provision_serial_number = Column(String(100), nullable=True, index=True)

    # 子系統預設樣式
    style_config = Column(JSONB, default=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            'code': self.code,
            'name': self.name,
            'description': self.description,
            'icon': self.icon,
            'group_unit_secure_code': self.group_unit_secure_code,
            'menu_item_secure_code': self.menu_item_secure_code,
            'is_active': self.is_active,
            'status': self.status,
            'developers': self.developers or [],
            'layout_mode': self.layout_mode,
            'provision_serial_number': self.provision_serial_number,
            'style_config': self.style_config or {},
        })
        return data
