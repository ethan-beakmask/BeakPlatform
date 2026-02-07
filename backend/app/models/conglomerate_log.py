"""
BeakMask Conglomerate Log Model
集團操作日誌 Model
"""
from typing import Dict, Any

from sqlalchemy import Column, String, Text, ForeignKey

from .base import BaseModel


class ConglomerateLog(BaseModel):
    """
    集團操作日誌

    記錄企業加入/退出集團的歷史
    """
    __tablename__ = 'conglomerate_logs'

    # 集團識別碼
    conglomerate_secure_code = Column(
        String(32),
        ForeignKey('conglomerates.secure_code'),
        nullable=False,
        index=True
    )

    # 企業識別碼
    org_secure_code = Column(
        String(32),
        ForeignKey('organizations.secure_code'),
        nullable=False,
        index=True
    )

    # 操作類型: JOIN, LEAVE
    action = Column(String(20), nullable=False)

    # 操作者信箱
    operator_email = Column(String(255), nullable=False)

    # 操作描述
    description = Column(Text, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        base = super().to_dict()
        base.update({
            'conglomerate_secure_code': self.conglomerate_secure_code,
            'org_secure_code': self.org_secure_code,
            'action': self.action,
            'operator_email': self.operator_email,
            'description': self.description,
        })
        return base

    def __repr__(self):
        return f'<ConglomerateLog {self.action} org={self.org_secure_code}>'
