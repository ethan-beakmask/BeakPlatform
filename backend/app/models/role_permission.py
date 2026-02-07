"""
BeakPlatform RolePermission Model
角色權限關聯 Model

RBAC + ABAC 權限系統 - 將角色與權限關聯，並支持 ABAC 條件
"""
import json
from typing import Dict, Any, List, Optional

from sqlalchemy import Column, String, Boolean, Text
from sqlalchemy.orm import relationship

from .base import BaseModel
from .. import db


class RolePermission(BaseModel):
    """
    角色權限關聯 Model

    關聯角色和權限，並可附加 ABAC 條件。

    ABAC 條件範例：
    {
        "conditions": [
            {"type": "OWNERSHIP", "code": "OWNER"},
            {"type": "ORG", "code": "SAME_DEPT"}
        ],
        "logic": "OR"  # OR = 任一條件滿足, AND = 全部條件滿足
    }

    權限是全局定義的，角色權限關聯也是全局的 (使用 BaseModel)。
    企業自訂角色的權限存在另一個表 (未來擴展)。
    """
    __tablename__ = 'role_permissions'

    # 角色
    role_secure_code = Column(
        String(32),
        db.ForeignKey('roles.secure_code'),
        nullable=False,
        index=True
    )

    # 權限
    permission_secure_code = Column(
        String(32),
        db.ForeignKey('permissions.secure_code'),
        nullable=False,
        index=True
    )

    # ABAC 條件 (JSON)
    condition_json = Column(Text, nullable=True)

    # 是否啟用
    is_active = Column(Boolean, default=True, nullable=False)

    # 關聯
    role = relationship('Role', foreign_keys=[role_secure_code])
    permission = relationship(
        'Permission',
        foreign_keys=[permission_secure_code],
        back_populates='role_permissions'
    )

    @property
    def conditions(self) -> Optional[Dict[str, Any]]:
        """取得 ABAC 條件"""
        if not self.condition_json:
            return None
        try:
            return json.loads(self.condition_json)
        except (json.JSONDecodeError, TypeError):
            return None

    @conditions.setter
    def conditions(self, value: Optional[Dict[str, Any]]) -> None:
        """設定 ABAC 條件"""
        if value is None:
            self.condition_json = None
        else:
            self.condition_json = json.dumps(value, ensure_ascii=False)

    @property
    def has_conditions(self) -> bool:
        """是否有 ABAC 條件"""
        return self.condition_json is not None and self.condition_json.strip() != ''

    @property
    def condition_logic(self) -> str:
        """取得條件邏輯 (OR/AND)，預設 OR"""
        conditions = self.conditions
        if conditions and 'logic' in conditions:
            return conditions['logic']
        return 'OR'

    @property
    def condition_list(self) -> List[Dict[str, str]]:
        """取得條件清單"""
        conditions = self.conditions
        if conditions and 'conditions' in conditions:
            return conditions['conditions']
        return []

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'role_id': self.role_secure_code,
            'permission_id': self.permission_secure_code,
            'conditions': self.conditions,
            'has_conditions': self.has_conditions,
            'is_active': self.is_active,
        })

        if self.role:
            base['role'] = {
                'id': self.role.secure_code,
                'code': self.role.code,
                'name': self.role.name,
            }

        if self.permission:
            base['permission'] = {
                'id': self.permission.secure_code,
                'code': self.permission.code,
                'name': self.permission.name,
            }

        return base

    def __repr__(self):
        return f'<RolePermission {self.role_secure_code} -> {self.permission_secure_code}>'
