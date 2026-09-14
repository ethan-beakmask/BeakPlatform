"""
BeakPlatform MenuDefault Model
選單出廠預設值 - 系統管理員儲存的選單快照

設計理念：
- 正規化儲存，一行一個選單項
- 與 menu_items 表欄位對齊，方便比對與回存
- user_types / role_codes 以 JSONB 儲存（Key1/Key2 預設值）
- 不繫結 org_secure_code（系統級，供所有企業重置用）
"""
from datetime import datetime
from typing import Dict, Any

from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB

from .. import db


class MenuDefault(db.Model):
    """
    選單出廠預設值

    系統管理員透過「設定目前組態成出廠值」按鈕，
    將當前 menu_items + menu_permissions + menu_role_requirements
    快照到此表。

    reset_menu_factory 讀取此表覆蓋回 menu_items。
    若此表為空，fallback 到 menu_defaults.py。
    """
    __tablename__ = 'menu_defaults'

    id = Column(Integer, primary_key=True)

    # 選單代碼 (unique，對應 menu_items.code)
    code = Column(String(50), unique=True, nullable=False, index=True)

    # 選單屬性（與 menu_items 對齊）
    title = Column(String(100), nullable=False)
    title_i18n = Column(JSONB, nullable=True, default=dict)
    icon = Column(String(50), nullable=True)
    link_type = Column(String(20), nullable=False, default='route')
    link_target = Column(String(255), nullable=True)
    display_order = Column(Integer, nullable=False, default=0)
    depth = Column(Integer, nullable=False, default=0)
    parent_code = Column(String(50), nullable=True)
    is_expanded = Column(Boolean, nullable=False, default=False)
    is_shared = Column(Boolean, nullable=False, default=False)
    required_permission = Column(String(50), nullable=True)

    # 雙鑰匙預設值
    # Key1: MenuPermission 的 user_type 列表
    # e.g. ["SYSTEM_ADMIN", "ORG_ADMIN"]
    user_types = Column(JSONB, nullable=False, default=list)

    # Key2: MenuRoleRequirement 的 role code 列表
    # e.g. ["ORG_ADMIN", "FORM_DESIGNER"]
    role_codes = Column(JSONB, nullable=False, default=list)

    # 快照紀錄
    saved_by = Column(String(100), nullable=False)
    saved_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'code': self.code,
            'title': self.title,
            'title_i18n': self.title_i18n or {},
            'icon': self.icon,
            'link_type': self.link_type,
            'link_target': self.link_target,
            'display_order': self.display_order,
            'depth': self.depth,
            'parent_code': self.parent_code,
            'is_expanded': self.is_expanded,
            'is_shared': self.is_shared,
            'required_permission': self.required_permission,
            'user_types': self.user_types or [],
            'role_codes': self.role_codes or [],
            'saved_by': self.saved_by,
            'saved_at': self.saved_at.isoformat() if self.saved_at else None,
        }

    def __repr__(self):
        return f'<MenuDefault {self.code}: {self.title}>'
