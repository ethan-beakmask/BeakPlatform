"""
Data CRUD Module - CrudView Model
視圖配置
"""
from typing import Dict, Any

from sqlalchemy import Column, String, Text, Boolean, Integer
from sqlalchemy.dialects.postgresql import JSONB

from .base import ModuleBaseModel


class DcCrudView(ModuleBaseModel):
    """CRUD 視圖配置"""
    __tablename__ = 'dc_crud_views'

    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    table_name = Column(String(128), nullable=False)
    columns_config = Column(JSONB, nullable=False, default=list)
    allow_create = Column(Boolean, default=True, nullable=False)
    allow_edit = Column(Boolean, default=True, nullable=False)
    allow_delete = Column(Boolean, default=True, nullable=False)
    soft_delete_column = Column(String(128), nullable=True)
    default_sort_column = Column(String(128), nullable=True)
    default_sort_dir = Column(String(4), default='ASC', nullable=False)
    page_size = Column(Integer, default=20, nullable=False)
    fixed_filters = Column(JSONB, default=dict, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    # 資料來源: 'org' = 企業 DB (預設), 'conglomerate' = 集團共享 DB
    data_source = Column(String(20), default='org', nullable=False, server_default='org')
    # 列級擁有權範圍: 'own' = 只能存取自己建的列（預設）, 'all' = 表級授權
    row_owner_scope = Column(String(8), default='own', nullable=False, server_default='own')

    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        data = super().to_dict()
        data.update({
            'name': self.name,
            'description': self.description,
            'table_name': self.table_name,
            'columns_config': self.columns_config or [],
            'allow_create': self.allow_create,
            'allow_edit': self.allow_edit,
            'allow_delete': self.allow_delete,
            'soft_delete_column': self.soft_delete_column,
            'default_sort_column': self.default_sort_column,
            'default_sort_dir': self.default_sort_dir,
            'page_size': self.page_size,
            'fixed_filters': self.fixed_filters or {},
            'is_active': self.is_active,
            'data_source': self.data_source or 'org',
            'row_owner_scope': self.row_owner_scope or 'own',
        })
        return data
