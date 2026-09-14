"""
選單 CRUD Mixin - 負責選單的新增、修改、刪除與權限設定

方法：
- get_all_menu_items: 取得企業所有選單
- create_menu_item: 建立選單項目
- set_menu_permissions: 設定選單權限
- _validate_permission_consistency: SEC-03 權限一致性驗證
- get_menu_permissions: 取得單一選單權限
- get_permission_matrix: 取得權限交叉矩陣
- update_menu_order: 批量更新順序
- delete_menu_item: 刪除選單項目
"""
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Set

from flask import current_app

from ..models.menu_item import MenuItem
from ..models.menu_permission import MenuPermission
from ..models.user import UserType
from .. import db

logger = logging.getLogger(__name__)


class MenuCrudMixin:
    """選單 CRUD 操作與權限設定"""

    # decorator flag → 允許的最寬 user_type 集合
    _DECORATOR_ALLOWED_TYPES = {
        'system_admin_required': {'SYSTEM_ADMIN'},
        'admin_required': {'SYSTEM_ADMIN', 'ORG_ADMIN'},
        'login_required': {'SYSTEM_ADMIN', 'ORG_ADMIN', 'EMPLOYEE', 'EXTERNAL'},
    }

    # user_type 中文名稱 (用於錯誤訊息)
    _USER_TYPE_LABELS = {
        'SYSTEM_ADMIN': '系統管理員',
        'ORG_ADMIN': '企業管理員',
        'EMPLOYEE': '企業成員',
        'EXTERNAL': '外部廠商',
    }

    # decorator 中文名稱 (用於錯誤訊息)
    _DECORATOR_LABELS = {
        'system_admin_required': '僅限系統管理員',
        'admin_required': '僅限管理員（系統+企業）',
        'login_required': '所有已登入用戶',
    }

    @classmethod
    def get_all_menu_items(
        cls,
        org_secure_code: str,
        include_deleted: bool = False
    ) -> List[MenuItem]:
        """
        取得企業內所有選單項目 (管理用)

        Args:
            org_secure_code: 企業識別碼
            include_deleted: 是否包含已刪除的

        Returns:
            選單項目列表
        """
        query = MenuItem.query.filter(
            MenuItem.org_secure_code == org_secure_code
        )

        if not include_deleted:
            query = query.filter(MenuItem.is_deleted == False)

        return query.order_by(
            MenuItem.depth,
            MenuItem.display_order
        ).all()

    @classmethod
    def create_menu_item(
        cls,
        org_secure_code: str,
        code: str,
        title: str,
        link_type: str = 'route',
        link_target: Optional[str] = None,
        parent_secure_code: Optional[str] = None,
        module_secure_code: Optional[str] = None,
        icon: Optional[str] = None,
        display_order: int = 0,
        allowed_user_types: Optional[List[str]] = None,
        is_expanded: bool = False,
        open_in_new_tab: bool = False,
    ) -> MenuItem:
        """
        建立選單項目

        Args:
            org_secure_code: 企業識別碼
            code: 選單代碼
            title: 選單標題
            link_type: 連結類型
            link_target: 連結目標
            parent_secure_code: 父選單識別碼
            module_secure_code: 模組識別碼
            icon: 圖標
            display_order: 顯示順序
            allowed_user_types: 允許的用戶類型列表，None 表示所有人可見
            is_expanded: 預設展開
            open_in_new_tab: 新視窗開啟

        Returns:
            建立的 MenuItem
        """
        # 計算深度
        depth = 0
        if parent_secure_code:
            parent = MenuItem.query.filter_by(
                secure_code=parent_secure_code
            ).first()
            if parent:
                depth = parent.depth + 1

        menu_item = MenuItem(
            org_secure_code=org_secure_code,
            code=code,
            title=title,
            link_type=link_type,
            link_target=link_target,
            parent_secure_code=parent_secure_code,
            module_secure_code=module_secure_code,
            icon=icon,
            display_order=display_order,
            depth=depth,
            is_expanded=is_expanded,
            open_in_new_tab=open_in_new_tab,
        )

        db.session.add(menu_item)
        db.session.flush()  # 取得 secure_code

        # 設定權限
        if allowed_user_types is None:
            # 預設所有用戶類型都可見
            allowed_user_types = cls.USER_TYPES
        cls.set_menu_permissions(menu_item.secure_code, allowed_user_types)

        return menu_item

    @classmethod
    def set_menu_permissions(
        cls,
        menu_secure_code: str,
        user_types: List[str]
    ) -> None:
        """
        設定選單的用戶類型權限

        [SEC-03] 儲存前即時驗證：
        - 比對目標路由的 decorator，確保 user_type 組合不會比 decorator 更寬鬆
        - 不一致時拒絕儲存並拋出 ValueError

        同時自動更新 is_shared 欄位：
        - 權限只給 1 種用戶類型 → is_shared = False
        - 權限給 2+ 種用戶類型 → is_shared = True

        Args:
            menu_secure_code: 選單識別碼
            user_types: 允許的用戶類型列表

        Raises:
            ValueError: user_type 組合與路由 decorator 不一致
        """
        # [SEC-03] 即時驗證: user_type 不能比路由 decorator 更寬鬆
        menu_item = MenuItem.query.filter_by(secure_code=menu_secure_code).first()
        if menu_item and menu_item.link_target and menu_item.link_type == 'route':
            cls._validate_permission_consistency(menu_item, user_types)

        # 刪除現有權限
        MenuPermission.query.filter(
            MenuPermission.menu_secure_code == menu_secure_code
        ).delete()

        # 建立新權限
        for user_type in user_types:
            perm = MenuPermission(
                menu_secure_code=menu_secure_code,
                user_type=user_type
            )
            db.session.add(perm)

        # 自動更新 is_shared 欄位
        menu_item = MenuItem.query.filter_by(secure_code=menu_secure_code).first()
        if menu_item:
            menu_item.is_shared = len(user_types) > 1

    @classmethod
    def _validate_permission_consistency(
        cls,
        menu_item: MenuItem,
        user_types: List[str],
    ) -> None:
        """
        [SEC-03] 即時驗證 user_type 與路由 decorator 一致性

        如果新的 user_type 包含路由 decorator 不允許的類型，拒絕並拋出 ValueError。

        Args:
            menu_item: 選單項目
            user_types: 欲設定的 user_type 列表

        Raises:
            ValueError: 權限與路由不一致
        """
        link_target = menu_item.link_target
        if not link_target or link_target.startswith('/'):
            return  # URL 路徑，非 Flask endpoint

        view_func = current_app.view_functions.get(link_target)
        if not view_func:
            return  # 端點不存在（另外處理）

        # 偵測 decorator
        if getattr(view_func, '_module_access_required', False):
            return  # 模組路由有獨立存取控制

        decorator_name = None
        for flag in ('system_admin_required', 'admin_required', 'login_required'):
            if getattr(view_func, f'_{flag}', False):
                decorator_name = flag
                break

        if not decorator_name:
            return  # 無法偵測，跳過

        allowed = cls._DECORATOR_ALLOWED_TYPES[decorator_name]
        proposed = {str(ut) for ut in user_types}
        overflow = proposed - allowed

        if overflow:
            overflow_labels = [cls._USER_TYPE_LABELS.get(t, t) for t in sorted(overflow)]
            route_label = cls._DECORATOR_LABELS[decorator_name]
            raise ValueError(
                f'權限衝突：此選單指向的路由 ({link_target}) '
                f'存取限制為「{route_label}」，'
                f'無法授權給 {", ".join(overflow_labels)}'
            )

    @classmethod
    def get_menu_permissions(cls, menu_secure_code: str) -> List[str]:
        """
        取得選單的用戶類型權限列表

        Args:
            menu_secure_code: 選單識別碼

        Returns:
            允許的用戶類型列表
        """
        permissions = MenuPermission.query.filter(
            MenuPermission.menu_secure_code == menu_secure_code,
            MenuPermission.is_deleted == False
        ).all()

        return [p.user_type for p in permissions]

    @classmethod
    def get_permission_matrix(cls, org_secure_code: str) -> Dict[str, Dict[str, bool]]:
        """
        取得選單權限交叉矩陣

        Args:
            org_secure_code: 企業識別碼

        Returns:
            {menu_secure_code: {user_type: True/False, ...}, ...}
        """
        # 取得該企業所有選單
        menu_items = MenuItem.query.filter(
            MenuItem.org_secure_code == org_secure_code,
            MenuItem.is_deleted == False
        ).all()

        # 取得所有權限記錄
        permissions = MenuPermission.query.filter(
            MenuPermission.menu_secure_code.in_([m.secure_code for m in menu_items]),
            MenuPermission.is_deleted == False
        ).all()

        # 建立權限集合
        perm_set = {(p.menu_secure_code, p.user_type) for p in permissions}

        # 建立交叉矩陣
        matrix = {}
        for menu in menu_items:
            matrix[menu.secure_code] = {
                user_type: (menu.secure_code, user_type) in perm_set
                for user_type in cls.USER_TYPES
            }

        return matrix

    @classmethod
    def update_menu_order(
        cls,
        items: List[Dict[str, Any]]
    ) -> None:
        """
        批量更新選單順序

        Args:
            items: [{secure_code, display_order, parent_secure_code}, ...]
        """
        for item_data in items:
            menu_item = MenuItem.query.filter_by(
                secure_code=item_data['secure_code']
            ).first()

            if not menu_item:
                continue

            # 更新順序
            menu_item.display_order = item_data.get('display_order', 0)

            # 更新父節點
            new_parent = item_data.get('parent_secure_code')
            if 'parent_secure_code' in item_data and new_parent != menu_item.parent_secure_code:
                menu_item.parent_secure_code = new_parent

                # 重新計算深度
                if new_parent:
                    parent = MenuItem.query.filter_by(
                        secure_code=new_parent
                    ).first()
                    menu_item.depth = parent.depth + 1 if parent else 0
                else:
                    menu_item.depth = 0

                # 遞迴更新子孫深度
                for descendant in menu_item.get_descendants():
                    descendant.depth = descendant.calculate_depth()

    @classmethod
    def delete_menu_item(
        cls,
        menu_item: MenuItem,
        soft: bool = True
    ) -> bool:
        """
        刪除選單項目

        Args:
            menu_item: 要刪除的選單項目
            soft: 是否軟刪除

        Returns:
            是否成功刪除
        """
        # 檢查是否有子項目
        children_count = MenuItem.query.filter(
            MenuItem.parent_secure_code == menu_item.secure_code,
            MenuItem.is_deleted == False
        ).count()

        if children_count > 0:
            return False

        if soft:
            menu_item.is_deleted = True
            menu_item.deleted_at = datetime.utcnow()
        else:
            db.session.delete(menu_item)

        return True
