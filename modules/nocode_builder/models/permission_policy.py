"""
Data CRUD Module - PermissionPolicyGroup / PermissionPolicyRule Models
權限政策組

每個子系統可建立多個權限政策組，每組包含多條 grant-based 准入規則。
網站地圖節點可選擇套用某個政策組，或向上繼承，或自訂權限。

permission_mode (on DcSiteMapNode):
  'inherit' - 向上繼承父節點的權限（新增節點的預設值）
  'policy'  - 套用指定的權限政策組
  'custom'  - 自訂 grant-based 權限（沿用 DcSiteMapPermission）
  NULL/空   - 禁止所有人（僅設計者預覽）
"""
from typing import Dict, Any

from sqlalchemy import Column, String, Text, Boolean

from .base import ModuleBaseModel


class DcPermissionPolicyGroup(ModuleBaseModel):
    """權限政策組"""
    __tablename__ = 'dc_permission_policy_groups'

    sub_system_secure_code = Column(String(32), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            'sub_system_secure_code': self.sub_system_secure_code,
            'name': self.name,
            'description': self.description or '',
        })
        return data


class DcPermissionPolicyRule(ModuleBaseModel):
    """權限政策組規則"""
    __tablename__ = 'dc_permission_policy_rules'

    policy_group_secure_code = Column(String(32), nullable=False, index=True)
    grant_type = Column(String(20), nullable=False)
    grant_target = Column(String(100), nullable=False)
    grant_target_name = Column(String(200), nullable=True, default='')
    include_children = Column(Boolean, nullable=False, default=False)

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            'policy_group_secure_code': self.policy_group_secure_code,
            'grant_type': self.grant_type,
            'grant_target': self.grant_target,
            'grant_target_name': self.grant_target_name or '',
            'include_children': self.include_children,
        })
        return data
