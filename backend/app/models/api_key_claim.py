"""
Platform API Key one-time claim model.

Stores who may claim an API key secret and whether it has been claimed.
The secret itself is never stored here; it is decrypted from api_keys at claim time.
"""
from sqlalchemy import Column, String, DateTime

from .base import BaseModel


class ApiKeyClaim(BaseModel):
    """One-time API Key secret claim ticket."""
    __tablename__ = 'api_key_claims'

    org_secure_code = Column(String(32), nullable=False, index=True)
    api_key_secure_code = Column(String(32), nullable=False, index=True)
    beneficiary_user_secure_code = Column(String(32), nullable=False, index=True)
    form_instance_secure_code = Column(String(32), nullable=True)
    expires_at = Column(DateTime, nullable=False)
    claimed_at = Column(DateTime, nullable=True)
    claimed_ip = Column(String(45), nullable=True)

    def to_dict(self):
        base = super().to_dict()
        base.update({
            'api_key_secure_code': self.api_key_secure_code,
            'beneficiary_user_secure_code': self.beneficiary_user_secure_code,
            'form_instance_secure_code': self.form_instance_secure_code,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'claimed_at': self.claimed_at.isoformat() if self.claimed_at else None,
            'claimed_ip': self.claimed_ip,
        })
        return base
