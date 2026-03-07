"""
BeakMask Audit Log Model
稽核日誌 Model
"""
from sqlalchemy import Column, String, Text, Integer, ForeignKey

from .base import TenantBaseModel


class AuditLog(TenantBaseModel):
    """
    稽核日誌 Model

    記錄系統中的重要操作，包括：
    - 認證事件 (LOGIN, LOGOUT, LOGIN_FAILED)
    - 寫入操作 (CREATE, UPDATE, DELETE)
    - 讀取操作 (READ, VERBOSE 模式)
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
        comment='操作類型 (LOGIN, LOGOUT, CREATE, UPDATE, DELETE, READ, etc.)'
    )

    # 資源類型
    resource_type = Column(
        String(50),
        nullable=False,
        comment='資源類型 (AUTH, USER, ROLE, FORM, etc.)'
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

    # HTTP 請求資訊
    request_method = Column(
        String(10),
        nullable=True,
        comment='HTTP method (GET, POST, PUT, DELETE, etc.)'
    )

    request_path = Column(
        String(500),
        nullable=True,
        comment='URL path'
    )

    status_code = Column(
        Integer,
        nullable=True,
        comment='HTTP response status code'
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

    def to_dict(self):
        base = super().to_dict()
        base.update({
            'user_secure_code': self.user_secure_code,
            'action': self.action,
            'resource_type': self.resource_type,
            'resource_id': self.resource_id,
            'details': self.details,
            'request_method': self.request_method,
            'request_path': self.request_path,
            'status_code': self.status_code,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
        })
        return base
