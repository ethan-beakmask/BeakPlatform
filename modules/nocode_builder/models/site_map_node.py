"""
Data CRUD Module - SiteMapNode Model
網站地圖節點

樹狀結構：透過 parent_secure_code 自引用。
node_type: folder(資料夾) / page(頁面)。
page 類型連結到 DcPageLayout。
"""
from typing import Dict, Any

from sqlalchemy import Column, String, Boolean, Integer
from sqlalchemy.dialects.postgresql import JSONB

from .base import ModuleBaseModel


class DcSiteMapNode(ModuleBaseModel):
    """網站地圖節點"""
    __tablename__ = 'dc_site_map_nodes'

    sub_system_secure_code = Column(String(32), nullable=False, index=True)
    parent_secure_code = Column(String(32), nullable=True, index=True)
    name = Column(String(200), nullable=False)
    icon = Column(String(50), nullable=True)
    node_type = Column(String(20), nullable=False, default='page')
    page_layout_secure_code = Column(String(32), nullable=True)
    display_order = Column(Integer, default=0, nullable=False)
    crud_overrides = Column(JSONB, default=dict)
    data_filters = Column(JSONB, default=dict)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            'sub_system_secure_code': self.sub_system_secure_code,
            'parent_secure_code': self.parent_secure_code,
            'name': self.name,
            'icon': self.icon,
            'node_type': self.node_type,
            'page_layout_secure_code': self.page_layout_secure_code,
            'display_order': self.display_order,
            'crud_overrides': self.crud_overrides or {},
            'data_filters': self.data_filters or {},
            'is_active': self.is_active,
        })
        return data
