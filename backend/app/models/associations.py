"""
BeakMask Association Tables
關聯表 Model (多對多關係)
"""
from datetime import datetime
from typing import Dict, Any, Optional

from sqlalchemy import Column, String, Boolean, DateTime, Date

from .base import TenantBaseModel
from .. import db


class UserUnitAssignment(TenantBaseModel):
    """
    用戶-組織單位關聯表

    一個用戶可以屬於多個部門/群組
    一個部門/群組可以有多個用戶
    """
    __tablename__ = 'user_unit_assignments'

    # 用戶
    user_secure_code = Column(
        String(32),
        db.ForeignKey('users.secure_code'),
        nullable=False,
        index=True
    )

    # 組織單位
    unit_secure_code = Column(
        String(32),
        db.ForeignKey('organizational_units.secure_code'),
        nullable=False,
        index=True
    )

    # 是否為主要單位
    is_primary = Column(Boolean, default=False, nullable=False)

    # 指派時間
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 指派者
    assigned_by = Column(String(100), nullable=True)

    # 關聯
    user = db.relationship('User', foreign_keys=[user_secure_code],
                          backref=db.backref('unit_assignments', lazy='dynamic'))
    unit = db.relationship('OrganizationalUnit', foreign_keys=[unit_secure_code],
                          backref=db.backref('member_assignments', lazy='dynamic'))

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'user_id': self.user_secure_code,
            'unit_id': self.unit_secure_code,
            'is_primary': self.is_primary,
            'assigned_at': self.assigned_at.isoformat() if self.assigned_at else None,
        })
        return base

    def __repr__(self):
        return f'<UserUnitAssignment {self.user_secure_code} -> {self.unit_secure_code}>'


class UserRoleAssignment(TenantBaseModel):
    """
    用戶-角色關聯表

    一個用戶可以有多個角色/職務
    一個角色/職務可以被多個用戶擁有

    可以指定在哪個組織單位擔任此角色
    例如：用戶 A 在「業務部」擔任「部門主管」角色
    """
    __tablename__ = 'user_role_assignments'

    # 用戶
    user_secure_code = Column(
        String(32),
        db.ForeignKey('users.secure_code'),
        nullable=False,
        index=True
    )

    # 角色
    role_secure_code = Column(
        String(32),
        db.ForeignKey('roles.secure_code'),
        nullable=False,
        index=True
    )

    # 在哪個組織單位擔任此角色 (NULL = 全企業)
    unit_secure_code = Column(
        String(32),
        db.ForeignKey('organizational_units.secure_code'),
        nullable=True,
        index=True
    )

    # 有效期限
    valid_from = Column(Date, nullable=True)
    valid_until = Column(Date, nullable=True)

    # 指派時間
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 指派者
    assigned_by = Column(String(100), nullable=True)

    # 關聯
    user = db.relationship('User', foreign_keys=[user_secure_code],
                          backref=db.backref('role_assignments', lazy='dynamic'))
    role = db.relationship('Role', foreign_keys=[role_secure_code],
                          backref=db.backref('user_assignments', lazy='dynamic'))
    unit = db.relationship('OrganizationalUnit', foreign_keys=[unit_secure_code])

    @property
    def is_valid(self) -> bool:
        """檢查角色指派是否在有效期內"""
        from datetime import date
        today = date.today()

        if self.valid_from and today < self.valid_from:
            return False
        if self.valid_until and today > self.valid_until:
            return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'user_id': self.user_secure_code,
            'role_id': self.role_secure_code,
            'unit_id': self.unit_secure_code,
            'valid_from': self.valid_from.isoformat() if self.valid_from else None,
            'valid_until': self.valid_until.isoformat() if self.valid_until else None,
            'is_valid': self.is_valid,
            'assigned_at': self.assigned_at.isoformat() if self.assigned_at else None,
        })

        if self.role:
            base['role'] = {
                'id': self.role.secure_code,
                'code': self.role.code,
                'name': self.role.name,
            }

        if self.unit:
            base['unit'] = {
                'id': self.unit.secure_code,
                'name': self.unit.name,
            }

        return base

    def __repr__(self):
        return f'<UserRoleAssignment {self.user_secure_code} -> {self.role_secure_code}>'
