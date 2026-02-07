"""
BeakPlatform MenuItem Model
選單項目 - 樹狀結構的動態選單
"""
from typing import Dict, Any, List, Optional

from sqlalchemy import Column, String, Boolean, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import TenantBaseModel


class MenuItem(TenantBaseModel):
    """
    選單項目 Model (樹狀結構)

    使用 Adjacency List Pattern 實現樹狀結構。
    可無限層級，建議控制在 3-4 層。

    link_type 說明:
    - 'page': 連結到 Page (link_target = page.secure_code)
    - 'url': 外部 URL (link_target = https://...)
    - 'route': Flask route name (link_target = blueprint.function_name)
    - 'divider': 分隔線 (link_target = None)
    - 'header': 區塊標題，不可點擊 (link_target = None)

    required_level 說明:
    - 0: system_admin (系統管理員)
    - 1: org_admin (企業管理員)
    - 2: authenticated (已登入用戶)
    數字越小權限越高，選單只對權限 <= required_level 的用戶顯示
    """
    __tablename__ = 'menu_items'

    # 所屬模組 (可選)
    module_secure_code = Column(
        String(32),
        ForeignKey('modules.secure_code'),
        nullable=True,
        index=True
    )

    # 父選單項目 (NULL = 根層級)
    parent_secure_code = Column(
        String(32),
        ForeignKey('menu_items.secure_code', use_alter=True, name='fk_menu_parent'),
        nullable=True,
        index=True
    )

    # 選單代碼 (企業內唯一)
    code = Column(String(50), nullable=False)

    # 選單標題
    title = Column(String(100), nullable=False)

    # 多語系標題 (JSONB: {"en": "...", "zh-CN": "...", "ja": "..."})
    title_i18n = Column(JSONB, nullable=True, default=dict)

    # [向下相容] 舊欄位 — 新程式碼請用 title_i18n
    title_en = Column(String(100), nullable=True)
    title_zh_cn = Column(String(100), nullable=True)

    # 選單圖標 (文字符號)
    icon = Column(String(10), nullable=True)

    # 連結類型
    link_type = Column(String(20), default='route', nullable=False)

    # 連結目標
    link_target = Column(String(255), nullable=True)

    # 是否在新視窗開啟
    open_in_new_tab = Column(Boolean, default=False, nullable=False)

    # 顯示順序 (同層級內)
    display_order = Column(Integer, default=0, nullable=False)

    # 層級深度 (由程式自動計算，用於優化查詢)
    depth = Column(Integer, default=0, nullable=False)

    # 是否預設展開
    is_expanded = Column(Boolean, default=False, nullable=False)

    # 是否啟用
    is_active = Column(Boolean, default=True, nullable=False)

    # [已棄用] Phase 1 簡化權限 - 改用 MenuPermission 交叉表
    # 保留欄位用於向下相容，新程式碼應使用 permissions 關聯
    required_level = Column(Integer, default=2, nullable=False)

    # === Phase 2 系統級擴展 ===
    # 是否為系統共用選單 (只有 system.local 的選單可設為 True)
    # is_shared=True 的選單會出現在所有企業用戶的選單中
    is_shared = Column(Boolean, default=False, nullable=False, index=True)

    # 關聯的權限代碼 (如 "user:manage")
    # 若設定，只有擁有該權限的用戶才能看到此選單
    required_permission = Column(String(50), nullable=True, index=True)

    # Relationships
    module = relationship('Module', back_populates='menu_items')
    parent = relationship(
        'MenuItem',
        remote_side='MenuItem.secure_code',
        back_populates='children',
        foreign_keys=[parent_secure_code]
    )
    children = relationship(
        'MenuItem',
        back_populates='parent',
        foreign_keys=[parent_secure_code],
        order_by='MenuItem.display_order'
    )
    permissions = relationship(
        'MenuPermission',
        back_populates='menu_item',
        cascade='all, delete-orphan'
    )

    # [向下相容] 語系代碼 → 舊欄位名映射
    _LOCALE_FIELD_MAP = {
        'zh-TW': 'title',
        'zh-CN': 'title_zh_cn',
        'en': 'title_en',
    }

    def get_localized_title(self, locale: str = 'zh-TW') -> str:
        """
        取得本地化標題

        查找順序：
        1. title_i18n[locale]  (JSONB 新格式)
        2. 舊欄位 title_en / title_zh_cn  (向下相容)
        3. title (zh-TW 原文)

        Args:
            locale: 語系代碼 (zh-TW, zh-CN, en, ja)

        Returns:
            本地化標題
        """
        # zh-TW 直接返回 title
        if locale == 'zh-TW':
            return self.title

        # 1. 優先查 JSONB
        if self.title_i18n and isinstance(self.title_i18n, dict):
            value = self.title_i18n.get(locale)
            if value:
                return value

        # 2. Fallback 到舊欄位
        field = self._LOCALE_FIELD_MAP.get(locale)
        if field and field != 'title':
            value = getattr(self, field, None)
            if value:
                return value

        # 3. Fallback 到 title
        return self.title

    def to_dict(self, include_children: bool = False) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'code': self.code,
            'title': self.title,
            'title_i18n': self.title_i18n or {},
            'title_en': self.title_en,
            'title_zh_cn': self.title_zh_cn,
            'icon': self.icon,
            'link_type': self.link_type,
            'link_target': self.link_target,
            'open_in_new_tab': self.open_in_new_tab,
            'display_order': self.display_order,
            'depth': self.depth,
            'is_expanded': self.is_expanded,
            'is_active': self.is_active,
            'required_level': self.required_level,
            'parent_id': self.parent_secure_code,
            'module_id': self.module_secure_code,
            'is_shared': self.is_shared,
            'required_permission': self.required_permission,
        })

        if include_children:
            base['children'] = [
                child.to_dict(include_children=True)
                for child in self.children
                if not child.is_deleted
            ]

        return base

    def get_ancestors(self) -> List['MenuItem']:
        """取得所有祖先節點（從根到父）"""
        ancestors = []
        current = self.parent
        while current:
            ancestors.insert(0, current)
            current = current.parent
        return ancestors

    def get_descendants(self) -> List['MenuItem']:
        """取得所有子孫節點（深度優先）"""
        descendants = []
        for child in self.children:
            if not child.is_deleted:
                descendants.append(child)
                descendants.extend(child.get_descendants())
        return descendants

    def calculate_depth(self) -> int:
        """計算節點深度"""
        if not self.parent_secure_code:
            return 0
        return len(self.get_ancestors())

    def __repr__(self):
        return f'<MenuItem {self.code}: {self.title}>'
