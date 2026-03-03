"""
Data CRUD Module - SiteMapPermission Model
網站地圖節點權限

白名單模式：節點無任何權限記錄 = 所有人可見；有記錄 = 白名單匹配。
target_type: ROLE / DEPARTMENT / GROUP / ACCOUNT
"""
from typing import Dict, Any

from sqlalchemy import Column, String

from .base import ModuleBaseModel


class DcSiteMapPermission(ModuleBaseModel):
    """網站地圖節點權限"""
    __tablename__ = 'dc_site_map_permissions'

    node_secure_code = Column(String(32), nullable=False, index=True)
    target_type = Column(String(20), nullable=False)
    target_secure_code = Column(String(32), nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            'node_secure_code': self.node_secure_code,
            'target_type': self.target_type,
            'target_secure_code': self.target_secure_code,
        })
        return data
