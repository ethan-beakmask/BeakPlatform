"""
BeakMask MenuPermission Model
選單權限交叉表 - 定義哪種用戶類型可以看到哪些選單

設計理念：
- 系統管理員、企業管理員、一般用戶是「平行」的，不是繼承的
- 系統管理員不能看到其他企業的選單（ISO27001/27701 隱私要求）
- 選單可見性 = 系統功能 + 模組授權
"""
from datetime import datetime
from typing import Dict, Any

from sqlalchemy import Column, String, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from .base import BaseModel
from .. import db


class MenuPermission(BaseModel):
    """
    選單權限交叉表

    定義哪種 user_type 可以看到哪個選單項目。

    user_type 說明:
    - SYSTEM_ADMIN: 系統管理員專屬功能
    - ORG_ADMIN: 企業管理員可見
    - EMPLOYEE: 員工可見
    - EXTERNAL: 外部廠商可見

    注意：這裡的權限是「平行」的，不是繼承的。
    例如：SYSTEM_ADMIN 只能看到 user_type='SYSTEM_ADMIN' 的選單，
    除非該選單也對 SYSTEM_ADMIN 開放。
    """
    __tablename__ = 'menu_permissions'

    # 唯一約束：同一選單+同一用戶類型只能有一筆
    __table_args__ = (
        UniqueConstraint('menu_secure_code', 'user_type', name='unique_menu_user_type'),
    )

    # 選單項目
    menu_secure_code = Column(
        String(32),
        ForeignKey('menu_items.secure_code', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # 用戶類型
    user_type = Column(
        String(20),
        nullable=False,
        index=True,
        comment='用戶類型: SYSTEM_ADMIN, ORG_ADMIN, EMPLOYEE, EXTERNAL'
    )

    # 額外條件 (JSON，預留未來擴充)
    # 例如: {"require_module": "module_xxx"} 表示需要特定模組授權
    conditions = Column(Text, nullable=True)

    # 關聯
    menu_item = relationship('MenuItem', back_populates='permissions')

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'menu_secure_code': self.menu_secure_code,
            'user_type': self.user_type,
            'conditions': self.conditions,
        })
        return base

    def __repr__(self):
        return f'<MenuPermission menu={self.menu_secure_code} user_type={self.user_type}>'
