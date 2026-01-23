"""
BeakMask OrganizationalUnit Model
組織單位 Model (部門/群組)
"""
from typing import Dict, Any, List, Optional

from sqlalchemy import Column, String, Boolean, Text, Integer
from sqlalchemy.orm import relationship

from .base import TenantBaseModel
from .. import db


class UnitType:
    """組織單位類型"""
    DEPARTMENT = 'DEPARTMENT'  # 部門 (正式組織架構)
    GROUP = 'GROUP'            # 群組 (非正式群體，如社團、福委會)


class OrganizationalUnit(TenantBaseModel):
    """
    組織單位 Model (部門/群組)

    樹狀結構：
    - parent_secure_code: 父層單位 (NULL = 根層級)
    - full_path: 完整路徑 (如: /總公司/業務部)
    - level: 層級深度 (從 1 開始)

    部門與群組的差異只在定義：
    - 部門：正式組織架構，有明確的上下級關係
    - 群組：非正式群體，如自行車社、福委會，通常是平行的
    """
    __tablename__ = 'organizational_units'

    # 單位類型
    unit_type = Column(
        String(20),
        default=UnitType.DEPARTMENT,
        nullable=False,
        index=True
    )

    # 單位代碼 (組織內唯一)
    code = Column(String(50), nullable=False, index=True)

    # 單位名稱
    name = Column(String(255), nullable=False)

    # 描述
    description = Column(Text, nullable=True)

    # 父層單位 (樹狀結構，NULL = 根層級)
    parent_secure_code = Column(
        String(32),
        db.ForeignKey('organizational_units.secure_code', use_alter=True, name='fk_unit_parent'),
        nullable=True,
        index=True
    )

    # 完整路徑 (如: /總公司/業務部)
    full_path = Column(String(1000), nullable=True)

    # 層級深度 (從 1 開始)
    level = Column(Integer, default=1, nullable=False)

    # 排序順序
    sort_order = Column(Integer, default=0, nullable=False)

    # 是否啟用
    is_active = Column(Boolean, default=True, nullable=False)

    # 是否為系統保留單位 (不可刪除)
    is_system_unit = Column(Boolean, default=False, nullable=False)

    # 關聯
    parent = relationship(
        'OrganizationalUnit',
        remote_side='OrganizationalUnit.secure_code',
        backref='children',
        foreign_keys=[parent_secure_code]
    )

    # 成員角色 secure_code (自動建立)
    member_role_secure_code = Column(String(32), nullable=True)

    # 跨部門/社群成員關係
    user_memberships = relationship('UserUnitMembership', back_populates='unit')

    @property
    def is_department(self) -> bool:
        """是否為部門"""
        return self.unit_type == UnitType.DEPARTMENT

    @property
    def is_group(self) -> bool:
        """是否為群組"""
        return self.unit_type == UnitType.GROUP

    @property
    def is_root(self) -> bool:
        """是否為根層級"""
        return self.parent_secure_code is None

    def update_full_path(self) -> None:
        """
        更新完整路徑和層級

        應在建立或移動單位時呼叫
        """
        if self.parent:
            self.full_path = f'{self.parent.full_path}/{self.name}'
            self.level = self.parent.level + 1
        else:
            self.full_path = f'/{self.name}'
            self.level = 1

    def update_children_paths(self) -> None:
        """
        遞迴更新所有子單位的路徑

        當單位名稱或位置變更時呼叫
        """
        for child in self.children:
            if not child.is_deleted:
                child.update_full_path()
                child.update_children_paths()

    def get_ancestors(self) -> List['OrganizationalUnit']:
        """
        取得所有祖先單位 (從根到父)

        Returns:
            List[OrganizationalUnit]: 祖先列表，從根層級開始
        """
        ancestors = []
        current = self.parent
        while current:
            ancestors.insert(0, current)
            current = current.parent
        return ancestors

    def get_descendants(self, include_self: bool = False) -> List['OrganizationalUnit']:
        """
        取得所有後代單位

        Args:
            include_self: 是否包含自己

        Returns:
            List[OrganizationalUnit]: 後代列表
        """
        result = [self] if include_self else []
        for child in self.children:
            if not child.is_deleted:
                result.extend(child.get_descendants(include_self=True))
        return result

    def get_sibling_count(self) -> int:
        """取得同層級單位數量"""
        return OrganizationalUnit.query.filter(
            OrganizationalUnit.org_secure_code == self.org_secure_code,
            OrganizationalUnit.parent_secure_code == self.parent_secure_code,
            OrganizationalUnit.unit_type == self.unit_type,
            OrganizationalUnit.is_deleted == False,
            OrganizationalUnit.secure_code != self.secure_code
        ).count()

    def to_dict(self, include_children: bool = False, include_ancestors: bool = False) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'unit_type': self.unit_type,
            'code': self.code,
            'name': self.name,
            'description': self.description,
            'full_path': self.full_path,
            'level': self.level,
            'sort_order': self.sort_order,
            'is_active': self.is_active,
            'is_system_unit': self.is_system_unit,
            'is_root': self.is_root,
            'parent_id': self.parent_secure_code,
        })

        if include_ancestors:
            base['ancestors'] = [
                {'id': a.secure_code, 'name': a.name}
                for a in self.get_ancestors()
            ]

        if include_children:
            base['children'] = [
                child.to_dict(include_children=True)
                for child in self.children
                if not child.is_deleted
            ]

        return base

    def __repr__(self):
        return f'<OrganizationalUnit {self.unit_type}:{self.code}>'
