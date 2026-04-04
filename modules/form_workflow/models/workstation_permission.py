"""
FormWorkflow Module - Workstation Permission Model
工作站存取權限控制
"""
import secrets
from sqlalchemy import Column, String, Boolean, CheckConstraint, event

from .base import ModuleBaseModel


class FwWorkstationPermission(ModuleBaseModel):
    """
    工作站存取權限

    控制哪些部門/群組/個人可以進入特定工作站。
    結構與 FwMappingPermission 相同。

    grant_type:
        department - 部門（include_children 控制是否含子部門）
        group      - 群組（include_children 控制是否含子群組）
        user       - 個人
    """
    __tablename__ = 'fw_workstation_permissions'

    # 對應的工作站
    workstation_secure_code = Column(String(32), nullable=False, index=True)

    # 授權類型與目標
    grant_type = Column(String(20), nullable=False)
    grant_target = Column(String(100), nullable=False)
    grant_target_name = Column(String(200), nullable=False, default='')
    include_children = Column(Boolean, nullable=False, default=False)

    # 設定者
    created_by_name = Column(String(100), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "grant_type IN ('department', 'group', 'user')",
            name='fw_wsp_valid_grant_type'
        ),
    )

    def __repr__(self):
        return f'<FwWorkstationPermission {self.grant_type}:{self.grant_target} -> ws:{self.workstation_secure_code}>'

    def to_dict(self):
        return {
            'secure_code': self.secure_code,
            'workstation_secure_code': self.workstation_secure_code,
            'grant_type': self.grant_type,
            'grant_target': self.grant_target,
            'grant_target_name': self.grant_target_name,
            'include_children': self.include_children,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'created_by_name': self.created_by_name,
        }


@event.listens_for(FwWorkstationPermission, 'before_insert')
def generate_wsp_secure_code(mapper, connection, target):
    if not target.secure_code:
        target.secure_code = secrets.token_urlsafe(16)
