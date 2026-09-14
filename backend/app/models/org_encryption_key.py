"""
OrgEncryptionKey Model
企業加密金鑰 - 每個企業一把 active Org Key，用 Master Key 包裝後儲存
"""
from sqlalchemy import Column, String, Boolean, Text

from .base import TenantBaseModel


class OrgEncryptionKey(TenantBaseModel):
    """
    企業加密金鑰

    wrapped_key: Org Key 用 Master Key (AES-256-GCM) 包裝後的 base64 值
    key_nonce: 包裝時使用的 nonce (base64)
    algorithm: 加密演算法 (目前固定 AES-256-GCM)
    is_active: 是否為該企業目前使用的金鑰
    """
    __tablename__ = 'org_encryption_keys'

    wrapped_key = Column(Text, nullable=False)
    key_nonce = Column(String(64), nullable=False)
    algorithm = Column(String(32), nullable=False, default='AES-256-GCM')
    is_active = Column(Boolean, nullable=False, default=True)
