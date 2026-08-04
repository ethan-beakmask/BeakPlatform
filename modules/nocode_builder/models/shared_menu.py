"""
NoCode Builder - Shared Menu Model
子系統層級共用選單
"""
from sqlalchemy import Boolean, Column, String
from sqlalchemy.dialects.postgresql import JSONB

from .base import ModuleBaseModel


class DcSharedMenu(ModuleBaseModel):
    """子系統共用選單"""
    __tablename__ = 'dc_shared_menus'

    sub_system_secure_code = Column(String(32), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    items = Column(JSONB, nullable=False, default=list)
    config = Column(JSONB, nullable=False, default=dict)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    def to_dict(self):
        data = super().to_dict()
        data.update({
            'sub_system_secure_code': self.sub_system_secure_code,
            'name': self.name,
            'items': self.items or [],
            'config': self.config or {},
            'is_active': self.is_active,
        })
        return data
