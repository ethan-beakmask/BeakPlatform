"""
Data CRUD Module - SiteMapPermission Model
網站地圖節點准入權限

准入模式（grant-based）：
  - 節點無任何 permission 記錄 → 開放給所有社群成員
  - 節點有 permission 記錄 → 白名單匹配（部門/社群/個人）

grant_type:
  department - 部門（include_children 控制是否含子部門）
  group      - 社群（include_children 控制是否含下層群組）
  user       - 個人

相容舊 target_type 欄位（ROLE/DEPARTMENT/GROUP/ACCOUNT），
新記錄統一使用 grant_type (department/group/user)。
"""
from typing import Dict, Any

from sqlalchemy import Column, String, Boolean

from .base import ModuleBaseModel


class DcSiteMapPermission(ModuleBaseModel):
    """網站地圖節點准入權限"""
    __tablename__ = 'dc_site_map_permissions'

    node_secure_code = Column(String(32), nullable=False, index=True)

    # 舊欄位（保留相容）
    target_type = Column(String(20), nullable=True)
    target_secure_code = Column(String(100), nullable=True)

    # 新欄位（grant-based 准入模式）
    grant_type = Column(String(20), nullable=True)
    grant_target = Column(String(100), nullable=True)
    grant_target_name = Column(String(200), nullable=True, default='')
    include_children = Column(Boolean, nullable=False, default=False)

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            'node_secure_code': self.node_secure_code,
            'target_type': self.target_type,
            'target_secure_code': self.target_secure_code,
            'grant_type': self.grant_type,
            'grant_target': self.grant_target,
            'grant_target_name': self.grant_target_name or '',
            'include_children': self.include_children,
        })
        return data
