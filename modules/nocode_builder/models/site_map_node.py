"""
Data CRUD Module - SiteMapNode Model
網站地圖節點

樹狀結構：透過 parent_secure_code 自引用。
node_type: folder(資料夾) / page(頁面)。
page 類型連結到 DcPageLayout。

准入模型 (access_roles):
  [] (空)     → NONE: 預設安全防呆，任何人都無法到此頁面
  ["GUEST"]   → 任何人都能到此頁面（含非成員）
  ["MANAGER", "MEMBER", ...] → 只有符合角色的成員才能到此頁面
不符合准入的用戶一律轉向 redirect_to (預設 /dashboard)。

Portal 准入 (access_matrix):
  {"read":{"groups":null|[codes],"min_level":code}}
  NULL = 尚未設定，沿用舊制行為（runtime 由 N3 定義）。
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

    # 准入控制: [] = NONE, ["GUEST"] = 任何人, ["MANAGER",...] = 角色清單
    access_roles = Column(JSONB, default=list)
    access_matrix = Column(JSONB, nullable=True)
    redirect_to = Column(String(200), default='/dashboard')

    # 權限模式: 'inherit'(向上繼承), 'policy'(政策組), 'custom'(自訂), NULL(禁止)
    permission_mode = Column(String(20), nullable=True, default='inherit')
    # 套用的權限政策組 secure_code (permission_mode='policy' 時使用)
    permission_policy_secure_code = Column(String(32), nullable=True)

    # 保留供過渡期（Phase 3 移至 widget 層級）
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
            'access_roles': self.access_roles or [],
            'access_matrix': self.access_matrix,
            'redirect_to': self.redirect_to or '/dashboard',
            'permission_mode': self.permission_mode,
            'permission_policy_secure_code': self.permission_policy_secure_code,
            'crud_overrides': self.crud_overrides or {},
            'data_filters': self.data_filters or {},
            'is_active': self.is_active,
        })
        return data
