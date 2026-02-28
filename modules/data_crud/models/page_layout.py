"""
Data CRUD Module - PageLayout Model
頁面佈局配置（Web Builder）
"""
from typing import Dict, Any

from sqlalchemy import Column, String, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB

from .base import ModuleBaseModel


class DcPageLayout(ModuleBaseModel):
    """頁面佈局配置"""
    __tablename__ = 'dc_page_layouts'

    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    layout_json = Column(JSONB, nullable=False, default=dict)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            'name': self.name,
            'description': self.description,
            'layout_json': self.layout_json or {'version': 2, 'widgets': []},
            'is_active': self.is_active,
        })
        return data
