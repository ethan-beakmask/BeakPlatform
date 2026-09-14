"""
BeakMask Module Access Control Model
模組使用權控制 - 控制企業內誰能使用哪個模組

target_type 支援:
- ROLE: 指派到角色
- DEPARTMENT: 指派到部門
- GROUP: 指派到群組
- ACCOUNT: 指派到個人帳號

向下相容: 某模組在某企業沒有任何 ACL 記錄 = 不限制（所有人可用）
"""
from sqlalchemy import Column, String

from .base import TenantBaseModel


class TargetType:
    """ACL 目標類型"""
    ROLE = 'ROLE'
    DEPARTMENT = 'DEPARTMENT'
    GROUP = 'GROUP'
    ACCOUNT = 'ACCOUNT'

    ALL = [ROLE, DEPARTMENT, GROUP, ACCOUNT]


class ModuleAccessControl(TenantBaseModel):
    """模組使用權控制"""
    __tablename__ = 'module_access_control'

    module_code = Column(String(100), nullable=False, index=True)
    target_type = Column(String(20), nullable=False)
    target_secure_code = Column(String(32), nullable=False)

    def to_dict(self):
        data = super().to_dict()
        data.update({
            'module_code': self.module_code,
            'target_type': self.target_type,
            'target_secure_code': self.target_secure_code,
        })
        return data
