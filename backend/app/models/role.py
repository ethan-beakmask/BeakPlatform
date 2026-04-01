"""
BeakMask Role Model
角色/職務 Model

RBAC + ABAC 權限系統核心模型
"""
from typing import Dict, Any, List, Optional

from sqlalchemy import Column, String, Boolean, Text, Integer
from sqlalchemy.orm import relationship

from .base import TenantBaseModel
from .. import db


class RoleType:
    """角色類型"""
    POSITION = 'POSITION'  # 職務 (用於部門，如: 主管、企業成員)
    ROLE = 'ROLE'          # 角色 (通用，可用於部門和群組)


class ScopeType:
    """適用範圍"""
    GLOBAL = 'GLOBAL'          # 全企業
    DEPARTMENT = 'DEPARTMENT'  # 部門
    GROUP = 'GROUP'            # 群組


class RoleLevel:
    """
    角色層級

    用於區分角色的權限範圍，不同層級的角色有不同的可見性和管理權限。
    """
    SYSTEM = 'SYSTEM'    # 系統級 (系統管理員)
    ORG = 'ORG'          # 企業級 (企業管理員、表單流程管理者)
    MODULE = 'MODULE'    # 模組級 (模組管理員、模組作者、模組讀者)
    MEMBER = 'MEMBER'    # 成員級 (部門成員、群組成員、企業成員...)


class ExclusiveGroup:
    """
    互斥群組

    同一互斥群組的角色不能同時指派給同一用戶。
    例如：EMPLOYEE、ORG_ADMIN、EXTERNAL 三者互斥，
    一個人只能擁有其中一種身份角色。
    """
    NONE = None                        # 無互斥限制
    IDENTITY_TYPE = 'IDENTITY_TYPE'    # 身份類型互斥 (企業成員/企業管理員/外部廠商)


class Role(TenantBaseModel):
    """
    角色/職務 Model

    樹狀結構：
    - parent_secure_code: 父層角色 (NULL = 根層級)
    - full_path: 完整路徑

    職務與角色的差異：
    - 職務 (POSITION): 用於部門，如主管、副主管、企業成員
    - 角色 (ROLE): 通用，可同時用於部門和群組

    適用範圍：
    - GLOBAL: 全企業通用
    - DEPARTMENT: 僅限部門
    - GROUP: 僅限群組

    多對多關係：
    - 一個用戶可以有多個角色/職務
    - 一個角色/職務可以被多個用戶擁有
    """
    __tablename__ = 'roles'

    # 角色類型
    role_type = Column(
        String(20),
        default=RoleType.ROLE,
        nullable=False,
        index=True
    )

    # 適用範圍
    scope_type = Column(
        String(20),
        default=ScopeType.GLOBAL,
        nullable=False,
        index=True
    )

    # 角色層級 (SYSTEM/ORG/MODULE/MEMBER)
    role_level = Column(
        String(20),
        default=RoleLevel.MEMBER,
        nullable=False,
        index=True
    )

    # 互斥群組 (同群組角色不能同時指派)
    exclusive_group = Column(
        String(20),
        nullable=True,
        index=True
    )

    # 繼承自哪個角色 (權限繼承，非樹狀結構)
    inherits_from_secure_code = Column(
        String(32),
        db.ForeignKey('roles.secure_code', use_alter=True, name='fk_role_inherits'),
        nullable=True,
        index=True
    )

    # 角色代碼 (組織內唯一)
    code = Column(String(50), nullable=False, index=True)

    # 角色名稱
    name = Column(String(255), nullable=False)

    # 描述
    description = Column(Text, nullable=True)

    # 父層角色 (樹狀結構)
    parent_secure_code = Column(
        String(32),
        db.ForeignKey('roles.secure_code', use_alter=True, name='fk_role_parent'),
        nullable=True,
        index=True
    )

    # 完整路徑
    full_path = Column(String(1000), nullable=True)

    # 層級深度
    level = Column(Integer, default=1, nullable=False)

    # 排序順序
    sort_order = Column(Integer, default=0, nullable=False)

    # 是否為管理者角色
    is_manager = Column(Boolean, default=False, nullable=False)

    # 是否為系統預設角色 (不可刪除)
    is_system_role = Column(Boolean, default=False, nullable=False)

    # 是否啟用
    is_active = Column(Boolean, default=True, nullable=False)

    # 權限設定 (JSON)
    permissions = Column(Text, nullable=True)

    # 關聯: 樹狀結構的父角色
    parent = relationship(
        'Role',
        remote_side='Role.secure_code',
        backref='children',
        foreign_keys=[parent_secure_code]
    )

    # 關聯: 權限繼承的父角色
    inherits_from = relationship(
        'Role',
        remote_side='Role.secure_code',
        foreign_keys=[inherits_from_secure_code],
        backref='inherited_by'
    )

    # 綁定的組織單位 (如果角色是為特定單位建立的)
    bound_unit_secure_code = Column(
        String(32),
        db.ForeignKey('organizational_units.secure_code'),
        nullable=True
    )
    bound_unit = relationship('OrganizationalUnit', foreign_keys=[bound_unit_secure_code])

    @property
    def is_position(self) -> bool:
        """是否為職務"""
        return self.role_type == RoleType.POSITION

    @property
    def is_role(self) -> bool:
        """是否為角色"""
        return self.role_type == RoleType.ROLE

    @property
    def is_global(self) -> bool:
        """是否為全企業通用"""
        return self.scope_type == ScopeType.GLOBAL

    @property
    def is_root(self) -> bool:
        """是否為根層級"""
        return self.parent_secure_code is None

    @property
    def is_system_level(self) -> bool:
        """是否為系統級角色"""
        return self.role_level == RoleLevel.SYSTEM

    @property
    def is_org_level(self) -> bool:
        """是否為企業級角色"""
        return self.role_level == RoleLevel.ORG

    @property
    def is_module_level(self) -> bool:
        """是否為模組級角色"""
        return self.role_level == RoleLevel.MODULE

    @property
    def is_member_level(self) -> bool:
        """是否為成員級角色"""
        return self.role_level == RoleLevel.MEMBER

    def get_inherited_roles(self) -> List['Role']:
        """
        取得所有繼承的角色鏈 (從自己往上)

        例如：模組作者 繼承 模組讀者
        呼叫 模組作者.get_inherited_roles() 返回 [模組作者, 模組讀者]
        """
        roles = [self]
        current = self.inherits_from
        visited = {self.secure_code}  # 防止循環

        while current and current.secure_code not in visited:
            roles.append(current)
            visited.add(current.secure_code)
            current = current.inherits_from

        return roles

    def update_full_path(self) -> None:
        """更新完整路徑和層級"""
        if self.parent:
            self.full_path = f'{self.parent.full_path}/{self.name}'
            self.level = self.parent.level + 1
        else:
            self.full_path = f'/{self.name}'
            self.level = 1

    def update_children_paths(self) -> None:
        """遞迴更新所有子角色的路徑"""
        for child in self.children:
            if not child.is_deleted:
                child.update_full_path()
                child.update_children_paths()

    def get_ancestors(self) -> List['Role']:
        """取得所有祖先角色"""
        ancestors = []
        current = self.parent
        while current:
            ancestors.insert(0, current)
            current = current.parent
        return ancestors

    def get_descendants(self, include_self: bool = False) -> List['Role']:
        """取得所有後代角色"""
        result = [self] if include_self else []
        for child in self.children:
            if not child.is_deleted:
                result.extend(child.get_descendants(include_self=True))
        return result

    def to_dict(self, include_children: bool = False) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'role_type': self.role_type,
            'scope_type': self.scope_type,
            'role_level': self.role_level,
            'exclusive_group': self.exclusive_group,
            'code': self.code,
            'name': self.name,
            'description': self.description,
            'full_path': self.full_path,
            'level': self.level,
            'sort_order': self.sort_order,
            'is_manager': self.is_manager,
            'is_system_role': self.is_system_role,
            'is_active': self.is_active,
            'parent_id': self.parent_secure_code,
            'inherits_from_id': self.inherits_from_secure_code,
        })

        if self.bound_unit:
            base['bound_unit'] = {
                'id': self.bound_unit.secure_code,
                'name': self.bound_unit.name,
                'unit_type': self.bound_unit.unit_type,
            }

        if include_children:
            base['children'] = [
                child.to_dict(include_children=True)
                for child in self.children
                if not child.is_deleted
            ]

        return base

    def __repr__(self):
        return f'<Role {self.role_type}:{self.code}>'
