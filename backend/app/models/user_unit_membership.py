"""
BeakMask UserUnitMembership Model
用戶-組織單位成員關係 Model

用於記錄：
1. 部門：實線(SOLID)/虛線(DOTTED) 匯報關係
2. 社群：成員(MEMBER) 關係
"""
from typing import Dict, Any, Optional
from datetime import date

from sqlalchemy import Column, String, Date, Text, ForeignKey
from sqlalchemy.orm import relationship

from .base import TenantBaseModel


class MembershipType:
    """成員類型"""
    SOLID = 'SOLID'      # 實線匯報（正式歸屬部門）
    DOTTED = 'DOTTED'    # 虛線匯報（跨部門支援）
    MEMBER = 'MEMBER'    # 社群成員


class MembershipRole:
    """角色類型"""
    MANAGER = 'MANAGER'  # 主管/團長
    DEPUTY = 'DEPUTY'    # 副主管/副團長
    PROXY1 = 'PROXY1'    # 代理人(一)
    PROXY2 = 'PROXY2'    # 代理人(二)
    MEMBER = 'MEMBER'    # 一般成員/團員


class UserUnitMembership(TenantBaseModel):
    """
    用戶-組織單位成員關係 Model

    記錄用戶與組織單位（部門/社群）的歸屬關係。

    部門關係：
    - SOLID：實線匯報，正式歸屬的主要部門（每人只能有一個）
    - DOTTED：虛線匯報，跨部門支援關係（可以有多個）

    社群關係：
    - MEMBER：社群成員（可以加入多個社群）
    """
    __tablename__ = 'user_unit_memberships'

    # 關係雙方
    user_secure_code = Column(
        String(32),
        ForeignKey('users.secure_code'),
        nullable=False,
        index=True
    )
    unit_secure_code = Column(
        String(32),
        ForeignKey('organizational_units.secure_code'),
        nullable=False,
        index=True
    )

    # 成員類型
    membership_type = Column(
        String(20),
        nullable=False,
        default=MembershipType.MEMBER,
        index=True
    )

    # 角色類型（可選）
    role_type = Column(String(20), nullable=True)

    # 生效期間
    start_date = Column(Date, default=date.today, nullable=True)
    end_date = Column(Date, nullable=True)

    # 備註
    notes = Column(Text, nullable=True)

    # Relationships
    user = relationship('User', back_populates='unit_memberships')
    unit = relationship('OrganizationalUnit', back_populates='user_memberships')

    @property
    def is_active(self) -> bool:
        """檢查此關係是否在有效期內"""
        today = date.today()
        if self.start_date and self.start_date > today:
            return False
        if self.end_date and self.end_date < today:
            return False
        return not self.is_deleted

    @property
    def is_cross_department(self) -> bool:
        """是否為跨部門關係"""
        return self.membership_type == MembershipType.DOTTED

    @property
    def is_primary(self) -> bool:
        """是否為主要歸屬（實線）"""
        return self.membership_type == MembershipType.SOLID

    @property
    def is_group_member(self) -> bool:
        """是否為社群成員"""
        return self.membership_type == MembershipType.MEMBER

    @property
    def is_leader(self) -> bool:
        """是否為管理層（主管/副主管/代理）"""
        return self.role_type in (
            MembershipRole.MANAGER,
            MembershipRole.DEPUTY,
            MembershipRole.PROXY1,
            MembershipRole.PROXY2
        )

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'user_secure_code': self.user_secure_code,
            'unit_secure_code': self.unit_secure_code,
            'membership_type': self.membership_type,
            'role_type': self.role_type,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'notes': self.notes,
            'is_active': self.is_active,
            'is_cross_department': self.is_cross_department,
            'is_primary': self.is_primary,
            'is_leader': self.is_leader,
        })

        # 包含用戶資訊（如果已載入）
        if self.user:
            base['user'] = {
                'id': self.user.secure_code,
                'display_name': self.user.display_name,
                'native_name': self.user.native_name,
                'english_name': self.user.english_name,
                'employee_id': self.user.employee_id,
                'user_type': self.user.user_type,
            }

        # 包含單位資訊（如果已載入）
        if self.unit:
            base['unit'] = {
                'id': self.unit.secure_code,
                'code': self.unit.code,
                'name': self.unit.name,
                'unit_type': self.unit.unit_type,
            }

        return base

    def __repr__(self):
        return f'<UserUnitMembership {self.user_secure_code} -> {self.unit_secure_code} ({self.membership_type})>'
