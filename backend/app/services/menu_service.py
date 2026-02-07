"""
BeakPlatform Menu Service
選單服務 - 負責建構用戶可見的選單樹

權限設計：
- MenuPermission 交叉表決定選單對 user_type 的可見性
- org_secure_code 用於管理權限（誰能編輯選單），不影響可見性
- required_permission 設定的選單需要通過 RBAC 權限檢查
"""
from typing import List, Dict, Any, Optional, Set
from flask import g, url_for

from ..models.menu_item import MenuItem
from ..models.menu_permission import MenuPermission
from ..models.user import UserType
from .. import db

# system.local 企業識別碼
SYSTEM_ORG_CODE = 'system.local'


class MenuService:
    """
    選單服務

    負責：
    1. 建構用戶可見的選單樹
    2. 選單 CRUD 操作
    3. 選單權限過濾

    權限設計：
    - MenuPermission 交叉表決定選單對 user_type 的可見性
    - org_secure_code 用於管理權限（誰能編輯/刪除選單），不影響可見性
    - required_permission 設定的選單需要通過 RBAC 權限檢查
    """

    # 用戶類型列表 (用於權限交叉表)
    USER_TYPES = [
        UserType.SYSTEM_ADMIN,
        UserType.ORG_ADMIN,
        UserType.EMPLOYEE,
        UserType.EXTERNAL,
    ]

    @classmethod
    def get_user_menu_tree(
        cls,
        user,
        layout: str = 'sidebar',
        include_inactive: bool = False
    ) -> List[Dict[str, Any]]:
        """
        取得用戶可見的選單樹

        可見性邏輯：
        1. 根據 user.user_type 查詢 MenuPermission 取得有權限的選單
        2. 過濾需要 RBAC 權限的選單 (required_permission)
        3. 不受 org_secure_code 限制

        Args:
            user: 當前用戶
            layout: 'sidebar' 或 'navbar' (目前未區分)
            include_inactive: 是否包含未啟用的選單 (管理用)

        Returns:
            選單樹結構 (巢狀字典列表)
        """
        # 1. 取得用戶 user_type 有權限的選單 secure_codes
        allowed_menu_codes = cls._get_allowed_menu_codes(user)

        # 2. 取得用戶的 RBAC 權限列表 (用於 required_permission 檢查)
        user_permissions = cls._get_user_permission_codes(user)

        # 3. 建立查詢
        # 選單可見性由 MenuPermission 交叉表決定，不受 org_secure_code 限制
        # org_secure_code 只用於管理權限（誰能編輯選單）
        query = MenuItem.query.filter(
            MenuItem.is_deleted == False,
            MenuItem.secure_code.in_(allowed_menu_codes) if allowed_menu_codes else False
        )

        if not include_inactive:
            query = query.filter(MenuItem.is_active == True)

        # 4. 取得所有選單項目
        items = query.order_by(
            MenuItem.is_shared.desc(),  # 共用選單排前面
            MenuItem.depth,
            MenuItem.display_order
        ).all()

        # 5. 過濾需要 RBAC 權限的選單
        filtered_items = cls._filter_by_rbac_permission(items, user_permissions)

        # 6. 預先載入所有選單的權限資訊 (用於顯示權限等級標記)
        menu_permissions_map = cls._get_menu_permissions_map(
            [item.secure_code for item in filtered_items]
        )

        # 7. 取得語系 (優先用 g.locale，由 auth_interceptor 設定)
        locale = getattr(g, 'locale', None)
        if not locale:
            locale = 'zh-TW'
            if hasattr(user, 'organization') and user.organization:
                locale = user.organization.get_setting('locale', 'zh-TW')

        # 8. 建構樹狀結構
        return cls._build_tree(filtered_items, menu_permissions_map=menu_permissions_map, locale=locale)

    @classmethod
    def _get_allowed_menu_codes(cls, user) -> Set[str]:
        """
        取得用戶有權限的選單 secure_codes (基於 user_type)

        Args:
            user: 當前用戶

        Returns:
            有權限的選單 secure_code 集合
        """
        # 查詢該用戶類型可見的選單
        permissions = MenuPermission.query.filter(
            MenuPermission.user_type == user.user_type,
            MenuPermission.is_deleted == False
        ).all()

        return {p.menu_secure_code for p in permissions}

    @classmethod
    def _get_user_permission_codes(cls, user) -> Set[str]:
        """
        取得用戶的 RBAC 權限代碼列表

        Args:
            user: 當前用戶

        Returns:
            權限代碼集合 (如 {'user:read', 'form_instance:create', ...})
        """
        from .permission_service import PermissionService
        return PermissionService.get_all_permission_codes(user)

    @classmethod
    def _filter_by_rbac_permission(
        cls,
        items: List[MenuItem],
        user_permissions: Set[str]
    ) -> List[MenuItem]:
        """
        過濾需要 RBAC 權限的選單

        Args:
            items: 選單項目列表
            user_permissions: 用戶擁有的權限代碼集合

        Returns:
            過濾後的選單項目列表
        """
        filtered = []
        for item in items:
            # 沒有設定 required_permission 的選單，直接通過
            if not item.required_permission:
                filtered.append(item)
                continue

            # 檢查用戶是否有所需權限
            if item.required_permission in user_permissions:
                filtered.append(item)

        return filtered

    @classmethod
    def _get_menu_permissions_map(
        cls,
        menu_secure_codes: List[str]
    ) -> Dict[str, Set[str]]:
        """
        批量取得選單的權限映射

        Args:
            menu_secure_codes: 選單 secure_code 列表

        Returns:
            {menu_secure_code: {user_type1, user_type2, ...}, ...}
        """
        if not menu_secure_codes:
            return {}

        permissions = MenuPermission.query.filter(
            MenuPermission.menu_secure_code.in_(menu_secure_codes),
            MenuPermission.is_deleted == False
        ).all()

        result: Dict[str, Set[str]] = {}
        for p in permissions:
            if p.menu_secure_code not in result:
                result[p.menu_secure_code] = set()
            result[p.menu_secure_code].add(p.user_type)

        return result

    @classmethod
    def _build_tree(
        cls,
        items: List[MenuItem],
        parent_code: Optional[str] = None,
        menu_permissions_map: Optional[Dict[str, Set[str]]] = None,
        locale: str = 'zh-TW'
    ) -> List[Dict[str, Any]]:
        """
        建構選單樹

        Args:
            items: 所有選單項目
            parent_code: 父選單的 secure_code (None = 根層級)
            menu_permissions_map: 選單權限映射 {menu_secure_code: {user_types}}
            locale: 語系代碼

        Returns:
            樹狀結構的字典列表
        """
        result = []

        for item in items:
            if item.parent_secure_code == parent_code:
                allowed_types = menu_permissions_map.get(item.secure_code, set()) if menu_permissions_map else set()
                node = cls._item_to_dict(item, allowed_types, locale=locale)
                node['children'] = cls._build_tree(items, item.secure_code, menu_permissions_map, locale=locale)
                result.append(node)

        return result

    @classmethod
    def _item_to_dict(
        cls,
        item: MenuItem,
        allowed_types: Optional[Set[str]] = None,
        locale: str = 'zh-TW'
    ) -> Dict[str, Any]:
        """
        將選單項目轉換為前端需要的格式

        Args:
            item: MenuItem 物件
            allowed_types: 該選單允許的用戶類型集合
            locale: 語系代碼

        Returns:
            字典格式的選單項目
        """
        from ..models.user import UserType

        # 解析連結
        href = cls._resolve_link(item)

        # 判斷是否為系統級選單 (屬於 system.local)
        is_system_menu = item.org_secure_code == SYSTEM_ORG_CODE

        # 計算權限等級標記 (用於前端顯示不同顏色)
        # 底色根據最高權限等級：
        # - 'fixed': 固定黑底白字（所有權限通用的選單）
        # - 'system': 包含 SYSTEM_ADMIN → 紅底
        # - 'admin': 包含 ORG_ADMIN (無 SYSTEM_ADMIN) → 藍底
        # - 'user': 只有 EMPLOYEE/EXTERNAL → 無特殊底色
        # 跨權限時字體用黃色提示

        # 這 4 個選單對所有權限開放，強制使用黑底白字
        FIXED_BLACK_TITLES = {'模組區', '個人設定', '儀表板', '表單中心'}

        if item.title in FIXED_BLACK_TITLES:
            bg_level = 'fixed'
            is_cross_level = False
        else:
            bg_level = 'user'  # 底色等級
            is_cross_level = False  # 是否跨權限

            if allowed_types:
                has_employee = UserType.EMPLOYEE in allowed_types
                has_external = UserType.EXTERNAL in allowed_types
                has_org_admin = UserType.ORG_ADMIN in allowed_types
                has_system_admin = UserType.SYSTEM_ADMIN in allowed_types

                # 計算底色等級 (取最高)
                if has_system_admin:
                    bg_level = 'system'
                elif has_org_admin:
                    bg_level = 'admin'
                else:
                    bg_level = 'user'

                # 判斷是否跨權限 (被多個層級共用)
                level_count = sum([
                    has_system_admin,
                    has_org_admin,
                    has_employee or has_external  # EMPLOYEE 和 EXTERNAL 算同一層級
                ])
                is_cross_level = level_count > 1

        return {
            'id': item.secure_code,
            'code': item.code,
            'title': item.get_localized_title(locale),
            'icon': item.icon,
            'link_type': item.link_type,
            'link_target': item.link_target,
            'href': href,
            'open_in_new_tab': item.open_in_new_tab,
            'is_expanded': item.is_expanded,
            'depth': item.depth,
            'is_active': item.is_active,
            'is_system_menu': is_system_menu,
            'bg_level': bg_level,
            'is_cross_level': is_cross_level,
            'children': [],
        }

    @classmethod
    def _resolve_link(cls, item: MenuItem) -> Optional[str]:
        """
        解析選單連結

        Args:
            item: MenuItem 物件

        Returns:
            解析後的 URL 或 None
        """
        if item.link_type == 'url':
            return item.link_target

        if item.link_type == 'route' and item.link_target:
            # 如果以 / 開頭，視為直接 URL 路徑
            if item.link_target.startswith('/'):
                return item.link_target
            # 否則視為 Flask 端點名稱
            try:
                return url_for(item.link_target)
            except Exception:
                # Route 不存在時返回 #
                return '#'

        if item.link_type == 'page' and item.link_target:
            # 連結到動態頁面
            return f'/p/{item.link_target}'

        if item.link_type in ('divider', 'header'):
            return None

        return '#'

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

        同時自動更新 is_shared 欄位：
        - 權限只給 1 種用戶類型 → is_shared = False
        - 權限給 2+ 種用戶類型 → is_shared = True

        Args:
            menu_secure_code: 選單識別碼
            user_types: 允許的用戶類型列表
        """
        # 刪除現有權限
        MenuPermission.query.filter(
            MenuPermission.menu_secure_code == menu_secure_code
        ).delete()

        # 建立新權限
        for user_type in user_types:
            permission = MenuPermission(
                menu_secure_code=menu_secure_code,
                user_type=user_type
            )
            db.session.add(permission)

        # 自動更新 is_shared 欄位
        menu_item = MenuItem.query.filter_by(secure_code=menu_secure_code).first()
        if menu_item:
            menu_item.is_shared = len(user_types) > 1

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
            if new_parent != menu_item.parent_secure_code:
                menu_item.parent_secure_code = new_parent

                # 重新計算深度
                if new_parent:
                    parent = MenuItem.query.filter_by(
                        secure_code=new_parent
                    ).first()
                    menu_item.depth = parent.depth + 1 if parent else 0
                else:
                    menu_item.depth = 0

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
            from datetime import datetime
            menu_item.is_deleted = True
            menu_item.deleted_at = datetime.utcnow()
        else:
            db.session.delete(menu_item)

        return True
