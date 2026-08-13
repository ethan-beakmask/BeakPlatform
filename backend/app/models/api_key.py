"""
Platform API Key Model

企業級外部系統 API Key(HMAC 簽章認證用)。
secret 用 Org Key 加密(沿用 crypto.key_manager.encrypt_file/decrypt_file),
驗章時還原原始 32-byte secret 進行 HMAC-SHA256 比對。

scopes 為 JSONB,平台層不解釋語意,由各消費端解釋自己的 scope type:
    {"form_category": ["<FwCategory SC>", ...], "form": ["<published SC>", ...]}

規格: dev-notes/API_KEY_TRIGGER_SPEC.md
"""
from sqlalchemy import Column, String, DateTime, LargeBinary
from sqlalchemy.dialects.postgresql import JSONB

from .base import BaseModel

STATUS_ACTIVE = 'active'
STATUS_SUSPENDED = 'suspended'
STATUS_REVOKED = 'revoked'


class ApiKey(BaseModel):
    """平台級 API Key(per 外部系統/裝置)"""
    __tablename__ = 'api_keys'

    org_secure_code = Column(String(32), nullable=False, index=True)

    key_id = Column(String(40), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    consumer_label = Column(String(200), nullable=True)
    description = Column(String(500), nullable=True)

    secret_ciphertext = Column(LargeBinary, nullable=False)
    secret_file_nonce = Column(LargeBinary, nullable=False)
    secret_wrapped_dek = Column(String(255), nullable=False)
    secret_dek_nonce = Column(String(64), nullable=False)
    secret_encryption_key_sc = Column(String(32), nullable=False)

    status = Column(String(20), nullable=False, default=STATUS_ACTIVE, index=True)
    suspended_reason = Column(String(500), nullable=True)
    suspended_at = Column(DateTime, nullable=True)

    # 來源 IP 白名單(支援 CIDR);NULL = 不鎖 IP(動態 IP 場景)
    allowed_ips = Column(JSONB, nullable=True)

    # 授權範圍(消費端自行解釋)
    scopes = Column(JSONB, nullable=False, default=dict)

    # 綁定的專用系統帳號(發動表單時的申請人);NULL 則僅記 consumer_label
    applicant_user_secure_code = Column(String(32), nullable=True)

    expires_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)

    created_by_secure_code = Column(String(32), nullable=True)

    def to_dict(self):
        base = super().to_dict()
        base.update({
            'key_id': self.key_id,
            'name': self.name,
            'consumer_label': self.consumer_label,
            'description': self.description,
            'status': self.status,
            'suspended_reason': self.suspended_reason,
            'suspended_at': self.suspended_at.isoformat() if self.suspended_at else None,
            'allowed_ips': self.allowed_ips,
            'scopes': self.scopes or {},
            'applicant_user_secure_code': self.applicant_user_secure_code,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None,
            'created_by_secure_code': self.created_by_secure_code,
        })
        return base
