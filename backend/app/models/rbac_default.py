"""
BeakPlatform RbacDefault Model
RBAC 出廠預設值 - 系統管理員儲存的角色權限快照

設計理念：
- 正規化儲存，一行一個 role_code + permission_code 對
- 與 menu_defaults 表設計一致，皆為 DB-based 出廠值
- 不繫結 org_secure_code（系統級，供所有企業恢復用）
"""
from datetime import datetime
from typing import Dict, Any

from sqlalchemy import Column, String, Integer, DateTime, UniqueConstraint

from .. import db


class RbacDefault(db.Model):
    """
    RBAC 出廠預設值

    系統管理員透過「設定目前組態成出廠值」按鈕，
    將指定企業的系統角色 RBAC 權限快照到此表。

    restore_defaults 讀取此表覆蓋企業角色權限。
    若此表為空，fallback 到 rbac_defaults.json（若存在）。
    """
    __tablename__ = 'rbac_defaults'

    __table_args__ = (
        UniqueConstraint('role_code', 'permission_code',
                         name='unique_rbac_default_role_perm'),
    )

    id = Column(Integer, primary_key=True)

    # 角色代碼 (對應 roles.code)
    role_code = Column(String(50), nullable=False, index=True)

    # 權限代碼 (對應 permissions.code)
    permission_code = Column(String(50), nullable=False, index=True)

    # 快照紀錄
    saved_by = Column(String(100), nullable=False)
    saved_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'role_code': self.role_code,
            'permission_code': self.permission_code,
            'saved_by': self.saved_by,
            'saved_at': self.saved_at.isoformat() if self.saved_at else None,
        }

    def __repr__(self):
        return f'<RbacDefault {self.role_code}:{self.permission_code}>'
