"""
NoCode Builder - Shared Component Model
子系統層級共用元件
"""
from sqlalchemy import Boolean, Column, String
from sqlalchemy.dialects.postgresql import JSONB

from .base import ModuleBaseModel


class DcSharedComponent(ModuleBaseModel):
    """子系統共用元件"""
    __tablename__ = 'dc_shared_components'

    sub_system_secure_code = Column(String(32), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    widget_type = Column(String(32), nullable=False)
    widget_json = Column(JSONB, nullable=False, default=dict)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    def to_dict(self):
        data = super().to_dict()
        data.update({
            'sub_system_secure_code': self.sub_system_secure_code,
            'name': self.name,
            'widget_type': self.widget_type,
            'widget_json': self.widget_json or {},
            'is_active': self.is_active,
        })
        return data
