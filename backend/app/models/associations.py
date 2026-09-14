"""
BeakMask Association Tables
關聯表 Model (多對多關係)
"""
from datetime import date, datetime
from typing import Dict, Any, Optional

from sqlalchemy import Column, String, Boolean, DateTime, Date, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB

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


class AssignmentKind:
    """角色指派性質。"""
    REGULAR = 'regular'
    PROXY = 'proxy'
    STANDBY = 'standby'
    ALL = (REGULAR, PROXY, STANDBY)
    HOLDING = (REGULAR, PROXY)


class UserRoleAssignment(TenantBaseModel):
    """
    用戶-角色關聯表

    一個用戶可以有多個角色/職務
    一個角色/職務可以被多個用戶擁有

    可以指定在哪個組織單位擔任此角色
    例如：用戶 A 在「業務部」擔任「部門主管」角色

    assignment_kind:
    - regular：正式持有；acting_for_user_secure_code 與 allowed_form_templates 一律 NULL。
    - proxy：代理持有；acting_for_user_secure_code 必填。
    - standby：候補持有；acting_for_user_secure_code 可空，僅在簽核授權判定且無可用持有者時生效。
    本期不在 model 層強制驗證，寫入路徑於後續期別收斂。
    """
    __tablename__ = 'user_role_assignments'
    __table_args__ = (
        Index(
            'ix_user_role_assignments_role_unit_kind',
            'org_secure_code',
            'role_secure_code',
            'unit_secure_code',
            'assignment_kind',
            postgresql_where=text("is_deleted = false"),
        ),
    )

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

    # 指派性質與代理資訊
    assignment_kind = Column(
        String(10),
        nullable=False,
        default=AssignmentKind.REGULAR,
        server_default=AssignmentKind.REGULAR,
    )
    acting_for_user_secure_code = Column(
        String(32),
        db.ForeignKey('users.secure_code'),
        nullable=True,
    )
    allowed_form_templates = Column(JSONB, nullable=True)
    source_ref = Column(String(100), nullable=True)
    grant_reason = Column(Text, nullable=True)

    # 關聯
    user = db.relationship('User', foreign_keys=[user_secure_code],
                          backref=db.backref('role_assignments', lazy='dynamic'))
    acting_for_user = db.relationship('User', foreign_keys=[acting_for_user_secure_code])
    role = db.relationship('Role', foreign_keys=[role_secure_code],
                          backref=db.backref('user_assignments', lazy='dynamic'))
    unit = db.relationship('OrganizationalUnit', foreign_keys=[unit_secure_code])

    @property
    def is_valid(self) -> bool:
        """檢查角色指派是否在有效期內"""
        return self.is_valid_on(self._org_today())

    def is_valid_on(self, today: date) -> bool:
        """指定企業當地日期是否在有效期內。"""
        if self.valid_from and today < self.valid_from:
            return False
        if self.valid_until and today > self.valid_until:
            return False
        return True

    def _org_today(self) -> date:
        """企業當地日曆日。"""
        org = getattr(self, 'organization', None)
        if org is None and self.org_secure_code:
            from .organization import Organization
            org = Organization.query.filter_by(secure_code=self.org_secure_code).first()
        if org is not None:
            return org.local_today()
        from app.utils.timezone import local_today
        return local_today('Asia/Taipei')

    def get_allowed_form_templates(self) -> set[str] | None:
        """取得限定表單模板集合；NULL 表示不限，其他非 list 形狀 fail-closed。"""
        value = self.allowed_form_templates
        if value is None:
            return None
        if isinstance(value, list):
            return {str(item) for item in value}
        return set()

    @classmethod
    def get_active_assignments(
        cls,
        user_secure_code: str,
        kinds=AssignmentKind.HOLDING,
    ) -> list:
        """
        取得用戶當前有效的角色指派（未刪除 + 在有效期內）。

        全站取用戶有效角色的唯一標準實作，
        供 permission_service / page_role_guard / menu_service 共用。

        預設只採計 regular/proxy，排除 standby；候補是否生效取決於他人當下
        是否可用，只能在簽核授權判定即時計算，不可讓選單與一般權限隨請假翻動。
        kinds=None 表示三種性質全部採計。
        """
        query = cls.query.filter(
            cls.user_secure_code == user_secure_code,
            cls.is_deleted == False,
        )
        if kinds is not None:
            query = query.filter(cls.assignment_kind.in_(tuple(kinds)))
        assignments = query.all()
        if not assignments:
            return []

        today = None
        user = assignments[0].user
        if user and user.organization:
            today = user.organization.local_today()
        if today is None:
            today = assignments[0]._org_today()
        return [a for a in assignments if a.is_valid_on(today)]

    @classmethod
    def get_active_role_secure_codes(
        cls,
        user_secure_code: str,
        kinds=AssignmentKind.HOLDING,
    ) -> set:
        """取得用戶當前有效角色的 secure_code 集合"""
        return {
            a.role_secure_code
            for a in cls.get_active_assignments(user_secure_code, kinds=kinds)
        }

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
            'assignment_kind': self.assignment_kind,
            'acting_for_user_id': self.acting_for_user_secure_code,
            'allowed_form_templates': self.allowed_form_templates,
            'source_ref': self.source_ref,
            'grant_reason': self.grant_reason,
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
