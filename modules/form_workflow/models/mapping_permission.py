"""
FormWorkflow Module - Mapping Permission Model
配對填寫權限控制
"""
import secrets
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, BigInteger, CheckConstraint, event


from .base import ModuleBaseModel


class FwMappingPermission(ModuleBaseModel):
    """
    配對填寫權限

    控制哪些部門/群組/個人/角色可以在表單中心填寫特定已發行表單。
    若某配對無任何記錄，預設由 EMPLOYEE（企業成員）角色可填；
    FLOW_DESIGNER / FORM_DESIGNER 角色不受規則限制，永遠可填（供試行）。

    grant_type:
        department - 部門（include_children 控制是否含子部門）
        group      - 群組（唯一授權外部廠商的管道）
        user       - 個人（排除 EXTERNAL 用戶）
        role       - 角色（比對 roles.code，排除 EXTERNAL 用戶）
    """
    __tablename__ = 'fw_mapping_permissions'

    # PK 為 bigint（與既有資料一致，PF-168 對齊）
    id = Column(BigInteger, primary_key=True)

    # 對應的配對
    mapping_secure_code = Column(String(32), nullable=False, index=True)

    # 授權類型與目標
    grant_type = Column(String(20), nullable=False)
    grant_target = Column(String(100), nullable=False)
    grant_target_name = Column(String(200), nullable=False, default='')
    include_children = Column(Boolean, nullable=False, default=False)

    # 設定者
    created_by_name = Column(String(100), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "grant_type IN ('department', 'group', 'user', 'role')",
            name='fw_mp_valid_grant_type'
        ),
    )

    def __repr__(self):
        return f'<FwMappingPermission {self.grant_type}:{self.grant_target} -> mapping:{self.mapping_secure_code}>'

    def to_dict(self):
        return {
            'secure_code': self.secure_code,
            'mapping_secure_code': self.mapping_secure_code,
            'grant_type': self.grant_type,
            'grant_target': self.grant_target,
            'grant_target_name': self.grant_target_name,
            'include_children': self.include_children,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'created_by_name': self.created_by_name,
        }


@event.listens_for(FwMappingPermission, 'before_insert')
def generate_mp_secure_code(mapper, connection, target):
    if not target.secure_code:
        target.secure_code = secrets.token_urlsafe(16)
