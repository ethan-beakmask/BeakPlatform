"""
NoCode Builder - PageTemplate Model
頁面模板：儲存可重複利用的頁面設計
"""
from sqlalchemy import Column, String, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB

from .base import ModuleBaseModel


class DcPageTemplate(ModuleBaseModel):
    """頁面模板"""
    __tablename__ = 'dc_page_templates'

    # scope='system' 的內建樣板不屬任何企業，故此表的 org_secure_code 允許 NULL。
    org_secure_code = Column(String(32), nullable=True, index=True)
    scope = Column(String(20), nullable=False, default='org', server_default='org', index=True)
    sub_system_secure_code = Column(String(32), nullable=True, index=True)
    source_sub_system_sc = Column(String(32), nullable=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=False, default='常用', server_default='常用')
    layout_json = Column(JSONB, nullable=False, default=dict)
    style_config = Column(JSONB, default=dict)
    thumbnail_svg = Column(Text, nullable=True)
    created_by_sc = Column(String(32), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    def to_dict(self):
        data = super().to_dict()
        data.update({
            'scope': self.scope or 'org',
            'sub_system_secure_code': self.sub_system_secure_code,
            'source_sub_system_sc': self.source_sub_system_sc,
            'name': self.name,
            'description': self.description,
            'category': self.category or '常用',
            'layout_json': self.layout_json or {},
            'style_config': self.style_config or {},
            'thumbnail_svg': self.thumbnail_svg or '',
            'created_by_sc': self.created_by_sc,
            'is_active': self.is_active,
        })
        return data
