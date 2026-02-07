"""
BeakPlatform Audit Log Model
稽核日誌 Model
"""
from sqlalchemy import Column, String, Text, ForeignKey

from .base import TenantBaseModel


class AuditLog(TenantBaseModel):
    """
    稽核日誌 Model

    記錄系統中的重要操作，包括：
    - 用戶新增/修改/刪除
    - 權限變更
    - 狀態切換
    """
    __tablename__ = 'audit_logs'

    # 操作者
    user_secure_code = Column(
        String(32),
        ForeignKey('users.secure_code'),
        nullable=True,
        comment='操作者'
    )

    # 操作類型
    action = Column(
        String(50),
        nullable=False,
        comment='操作類型 (CREATE, UPDATE, DELETE, TOGGLE_STATUS, etc.)'
    )

    # 資源類型
    resource_type = Column(
        String(50),
        nullable=False,
        comment='資源類型 (EXTERNAL_USER, USER, ROLE, etc.)'
    )

    # 資源識別碼
    resource_id = Column(
        String(100),
        nullable=True,
        comment='資源識別碼'
    )

    # 詳細描述
    details = Column(
        Text,
        nullable=True,
        comment='詳細描述'
    )

    # 來源 IP
    ip_address = Column(
        String(45),
        nullable=True,
        comment='來源 IP'
    )

    # 瀏覽器 User-Agent
    user_agent = Column(
        String(500),
        nullable=True,
        comment='瀏覽器 User-Agent'
    )

    def __repr__(self):
        return f'<AuditLog {self.action} {self.resource_type}/{self.resource_id}>'
