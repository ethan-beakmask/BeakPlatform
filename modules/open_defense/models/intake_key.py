"""
OpenDefense Module - Intake Key Model

事件來源端的 HMAC 共用密鑰。
secret 用 Org Key 加密(沿用 crypto.key_manager.encrypt_file/decrypt_file),
驗章時還原原始 32-byte secret 進行 HMAC-SHA256 比對。
"""
from sqlalchemy import Column, String, Boolean, DateTime, LargeBinary
from sqlalchemy.dialects.postgresql import JSONB

from .base import OdBaseModel


class OdIntakeKey(OdBaseModel):
    """事件接收金鑰(per intake source)"""
    __tablename__ = 'od_intake_keys'

    key_id = Column(String(40), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)

    hmac_secret_ciphertext = Column(LargeBinary, nullable=False)
    hmac_secret_file_nonce = Column(LargeBinary, nullable=False)
    hmac_secret_wrapped_dek = Column(String(255), nullable=False)
    hmac_secret_dek_nonce = Column(String(64), nullable=False)
    hmac_secret_encryption_key_sc = Column(String(32), nullable=False)

    allowed_source_systems = Column(JSONB, nullable=False, default=list)

    is_active = Column(Boolean, nullable=False, default=True)
    expires_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)

    created_by_secure_code = Column(String(32), nullable=True)

    def to_dict(self):
        base = super().to_dict()
        base.update({
            'key_id': self.key_id,
            'name': self.name,
            'allowed_source_systems': self.allowed_source_systems or [],
            'is_active': self.is_active,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None,
        })
        return base
