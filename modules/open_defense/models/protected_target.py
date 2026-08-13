"""
OpenDefense Module - Protected Target Model

封鎖保護清單。服務層會以此表搭配內建網段,阻止基礎設施被誤寫成封鎖決策。
"""
from sqlalchemy import Boolean, Column, Index, String

from .base import OdBaseModel


VALID_PROTECTED_ENTRY_TYPES = ('protect', 'exempt')


class OdProtectedTarget(OdBaseModel):
    """封鎖保護清單：禁止（或明確豁免）被寫成封鎖決策的目標。"""
    __tablename__ = 'od_protected_targets'

    entry_type = Column(String(10), nullable=False, default='protect')
    target_value = Column(String(64), nullable=False)
    name = Column(String(100), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    note = Column(String(500), nullable=True)
    created_by_secure_code = Column(String(32), nullable=True)

    __table_args__ = (
        Index('idx_od_protected_org_active', 'org_secure_code', 'entry_type', 'is_active'),
    )

    def to_dict(self):
        base = super().to_dict()
        base.update({
            'entry_type': self.entry_type,
            'target_value': self.target_value,
            'name': self.name,
            'is_active': self.is_active,
            'note': self.note,
            'created_by_secure_code': self.created_by_secure_code,
        })
        return base
