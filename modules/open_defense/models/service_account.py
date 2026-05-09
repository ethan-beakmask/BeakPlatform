"""
OpenDefense Module - Service Account Model

外部執行端登入帳號。secret 採 bcrypt 單向雜湊(不可還原),
登入時比對,通過後簽發短期 JWT。
"""
from sqlalchemy import Column, String, Boolean, DateTime, Integer
from sqlalchemy.dialects.postgresql import JSONB, INET

from .base import OdBaseModel


class OdServiceAccount(OdBaseModel):
    """執行端 Service Account"""
    __tablename__ = 'od_service_accounts'

    sa_id = Column(String(60), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)

    secret_hash = Column(String(255), nullable=False)

    allowed_enforcement_points = Column(JSONB, nullable=False, default=list)

    is_active = Column(Boolean, nullable=False, default=True)

    last_login_at = Column(DateTime, nullable=True)
    last_login_ip = Column(INET, nullable=True)

    failed_login_count = Column(Integer, nullable=False, default=0)
    lock_until = Column(DateTime, nullable=True)

    created_by_secure_code = Column(String(32), nullable=True)

    def to_dict(self):
        base = super().to_dict()
        base.update({
            'sa_id': self.sa_id,
            'name': self.name,
            'allowed_enforcement_points': self.allowed_enforcement_points or [],
            'is_active': self.is_active,
            'last_login_at': self.last_login_at.isoformat() if self.last_login_at else None,
            'last_login_ip': str(self.last_login_ip) if self.last_login_ip else None,
            'lock_until': self.lock_until.isoformat() if self.lock_until else None,
        })
        return base
