"""
Data CRUD Module - SubSystemPage Model
子系統頁面配置

每個子系統可掛載多個 DcPageLayout，
透過 visible_roles / crud_overrides / data_filters 控制不同角色的存取。
"""
from typing import Dict, Any

from sqlalchemy import Column, String, Boolean, Integer
from sqlalchemy.dialects.postgresql import JSONB

from .base import ModuleBaseModel


class DcSubSystemPage(ModuleBaseModel):
    """子系統頁面配置"""
    __tablename__ = 'dc_sub_system_pages'

    sub_system_secure_code = Column(String(32), nullable=False, index=True)
    page_layout_secure_code = Column(String(32), nullable=False, index=True)
    display_name = Column(String(200), nullable=True)
    display_order = Column(Integer, default=0, nullable=False)

    # 可見性: ["*"] = 全部, ["MANAGER","DEPUTY"] = 僅管理層
    visible_roles = Column(JSONB, nullable=False, default=lambda: ['*'])

    # 按角色覆蓋 CRUD: {"MANAGER":{"create":true,"edit":true,"delete":true},...}
    crud_overrides = Column(JSONB, default=dict)

    # 按角色注入資料篩選: {"MEMBER":{"created_by":"$CURRENT_USER"},...}
    data_filters = Column(JSONB, default=dict)

    is_active = Column(Boolean, default=True, nullable=False, index=True)

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            'sub_system_secure_code': self.sub_system_secure_code,
            'page_layout_secure_code': self.page_layout_secure_code,
            'display_name': self.display_name,
            'display_order': self.display_order,
            'visible_roles': self.visible_roles or ['*'],
            'crud_overrides': self.crud_overrides or {},
            'data_filters': self.data_filters or {},
            'is_active': self.is_active,
        })
        return data
