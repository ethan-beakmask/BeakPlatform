"""
BeakMask Menu Service
選單服務 - 負責建構用戶可見的選單樹

權限設計：
- MenuPermission 交叉表決定選單對 user_type 的可見性
- org_secure_code 用於管理權限（誰能編輯選單），不影響可見性
- required_permission 設定的選單需要通過 RBAC 權限檢查
- 模組選單需要企業擁有有效合約授權才可見
"""
import json
import logging
from datetime import date
from typing import List, Dict, Any, Optional, Set
from flask import g, url_for

from ..models.menu_item import MenuItem
from ..models.menu_permission import MenuPermission
from ..models.user import UserType
from ..constants import SYSTEM_ORG_CODE
from .. import db

logger = logging.getLogger(__name__)


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
        # 1. 取得用戶 user_type 有權限的選單 secure_codes (MenuPermission 治理)
        perm_governed_codes = cls._get_allowed_menu_codes(user)

        # 1.5 模組選單注入 (模組治理)
        module_injected_codes = set()
        user_type_str = str(user.user_type)
        if user_type_str == 'SYSTEM_ADMIN':
            module_injected_codes = set()  # 系統管理員不看模組選單
        elif user_type_str == 'ORG_ADMIN':
            module_injected_codes = cls._get_all_module_menu_codes()
        else:
            module_injected_codes = cls._get_module_access_menu_codes(user)

        # 合併兩個來源
        allowed_menu_codes = perm_governed_codes | module_injected_codes

        # 標記：純模組注入的選單 (不在 MenuPermission 中)
        # 只有這些選單才受 Steps 6~6.7 的模組過濾
        # MenuPermission 治理的選單 = 管理員勾選即生效，不受合約/ACL/社群過濾
        module_only_codes = module_injected_codes - perm_governed_codes

        # 2. 取得用戶的 RBAC 權限列表 (用於 required_permission 檢查)
        user_permissions = cls._get_user_permission_codes(user)

        # 3. 建立查詢
        # 選單可見性由 MenuPermission + module_access_control 共同決定
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
        filtered_items = cls._filter_by_rbac_permission(
            items, user_permissions
        )

        # 6~6.7 模組治理過濾
        # 6. 合約過濾：對所有模組選單生效（含 MenuPermission 治理的）
        #    合約是商業層級控制，優先於 MenuPermission，不可繞過
        # 6.5~6.7 ACL/社群過濾：只對 module_only_codes 執行（MenuPermission 可繞過）
        if str(user.user_type) != 'SYSTEM_ADMIN':
            authorized_modules = cls._get_authorized_modules(user)
            filtered_items = cls._filter_by_contract(
                filtered_items, authorized_modules
            )

        if str(user.user_type) not in ('SYSTEM_ADMIN', 'ORG_ADMIN'):
            filtered_items = cls._filter_with_bypass(
                filtered_items, module_only_codes,
                cls._filter_by_module_access, user
            )

        if str(user.user_type) not in ('SYSTEM_ADMIN', 'ORG_ADMIN'):
            filtered_items = cls._filter_with_bypass(
                filtered_items, module_only_codes,
                cls._filter_by_sub_system_membership, user
            )

        # 7. 預先載入所有選單的權限資訊 (用於顯示權限等級標記)
        menu_permissions_map = cls._get_menu_permissions_map(
            [item.secure_code for item in filtered_items]
        )

        # 8. 取得語系 (優先用 g.locale，由 auth_interceptor 設定)
        locale = getattr(g, 'locale', None)
        if not locale:
            locale = 'zh-TW'
            if hasattr(user, 'organization') and user.organization:
                locale = user.organization.get_setting('locale', 'zh-TW')

        # 9. 建構樹狀結構
        return cls._build_tree(
            filtered_items,
            menu_permissions_map=menu_permissions_map,
            locale=locale,
        )

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
            if not item.required_permission:
                filtered.append(item)
                continue

            if item.required_permission in user_permissions:
                filtered.append(item)

        return filtered

    @staticmethod
    def _filter_with_bypass(items, subject_codes, filter_fn, *args):
        """
        治理分流：只對 subject_codes 內的選單執行 filter_fn，其餘直接保留。

        用途：MenuPermission 治理的選單不受模組過濾 (合約/ACL/社群) 影響，
        只有純模組注入的選單 (subject_codes) 才進入 filter_fn。

        Args:
            items: 完整選單列表
            subject_codes: 需要過濾的選單 secure_code 集合
            filter_fn: 過濾函式，簽名為 fn(items, *args)
            *args: 傳給 filter_fn 的額外參數

        Returns:
            過濾後的選單列表 (保持原始順序)
        """
        if not subject_codes:
            return items

        subject = [i for i in items if i.secure_code in subject_codes]
        if not subject:
            return items

        filtered_subject = filter_fn(subject, *args)
        filtered_sc = {i.secure_code for i in filtered_subject}

        return [i for i in items
                if i.secure_code not in subject_codes or i.secure_code in filtered_sc]

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
        locale: str = 'zh-TW',
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

    # [已棄用] 固定底色選單標題 - 改為統一使用權限等級著色
    FIXED_BLACK_TITLES = set()

    @classmethod
    def _item_to_dict(
        cls,
        item: MenuItem,
        allowed_types: Optional[Set[str]] = None,
        locale: str = 'zh-TW',
    ) -> Dict[str, Any]:
        """
        將選單項目轉換為前端需要的格式

        顏色規則 (與 /menu/ 管理頁面一致，viewer-independent):
        - 固定標題 → bg_level='fixed' (黑底白字)
        - has_sys AND has_org → bg_level='system', is_cross_level=True (紅底黃字)
        - has_sys only → bg_level='system', is_cross_level=False (紅底白字)
        - has_org only → bg_level='admin', is_cross_level=False (藍底白字)
        - else → 無特殊顏色

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

        # 計算權限等級標記 (viewer-independent，依 CSV 權限顏色表)
        # 底色 = 最高權限等級，cross = 還有更低等級也能存取
        bg_level = ''
        is_cross_level = False

        if allowed_types:
            has_system_admin = UserType.SYSTEM_ADMIN in allowed_types
            has_org_admin = UserType.ORG_ADMIN in allowed_types
            has_employee = UserType.EMPLOYEE in allowed_types
            has_external = UserType.EXTERNAL in allowed_types

            type_count = sum([has_system_admin, has_org_admin, has_employee, has_external])

            # 3+ types = 跨階層基本選單
            if type_count >= 3:
                bg_level = 'common'
            elif has_system_admin:
                bg_level = 'system'
                is_cross_level = has_org_admin or has_employee or has_external
            elif has_org_admin:
                bg_level = 'admin'
                is_cross_level = has_employee or has_external
            elif has_employee:
                bg_level = 'user'
                is_cross_level = has_external
            elif has_external:
                bg_level = 'external'

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
            permission = MenuPermission(
                menu_secure_code=menu_secure_code,
                user_type=user_type
            )
            db.session.add(permission)

        # 自動更新 is_shared 欄位
        menu_item = MenuItem.query.filter_by(secure_code=menu_secure_code).first()
        if menu_item:
            menu_item.is_shared = len(user_types) > 1

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
        'EMPLOYEE': '員工',
        'EXTERNAL': '外部廠商',
    }

    # decorator 中文名稱 (用於錯誤訊息)
    _DECORATOR_LABELS = {
        'system_admin_required': '僅限系統管理員',
        'admin_required': '僅限管理員（系統+企業）',
        'login_required': '所有已登入用戶',
    }

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

        from flask import current_app
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
            from datetime import datetime
            menu_item.is_deleted = True
            menu_item.deleted_at = datetime.utcnow()
        else:
            db.session.delete(menu_item)

        return True

    # ========================================
    # 子系統選單過濾 (社群成員身份)
    # ========================================

    # 子系統父選單 code
    _SUB_SYSTEM_PARENT_CODE = 'sub_system'

    @classmethod
    def _filter_by_sub_system_membership(
        cls,
        items: List[MenuItem],
        user
    ) -> List[MenuItem]:
        """
        過濾子系統選單: 只有對應社群成員能看到

        透過 DcSubSystem.menu_item_secure_code 反查選單歸屬的子系統，
        再查社群成員身份決定可見性。admin 不經此過濾 (在呼叫端已判斷)。
        """
        try:
            # 找出「子系統」父選單
            sub_system_parent_sc = None
            for item in items:
                if item.code == cls._SUB_SYSTEM_PARENT_CODE:
                    sub_system_parent_sc = item.secure_code
                    break

            if not sub_system_parent_sc:
                return items

            # 收集「子系統」header 下的子選單
            sub_menu_scs = set()
            for item in items:
                if item.parent_secure_code == sub_system_parent_sc:
                    sub_menu_scs.add(item.secure_code)

            if not sub_menu_scs:
                return items

            # 透過 DB 關聯查詢：哪些子系統綁定了這些選單
            from modules.nocode_builder.models.sub_system import DcSubSystem
            sub_systems = DcSubSystem.query.filter(
                DcSubSystem.menu_item_secure_code.in_(sub_menu_scs),
                DcSubSystem.is_deleted == False,
            ).all()

            # menu_sc -> group_unit_sc 映射
            menu_group_map = {
                ss.menu_item_secure_code: ss.group_unit_secure_code
                for ss in sub_systems
                if ss.group_unit_secure_code
            }

            if not menu_group_map:
                # 無任何子系統綁定選單，移除所有子系統子選單
                return [i for i in items if i.secure_code not in sub_menu_scs]

            # 批量查詢用戶的社群成員身份
            from ..models.user_unit_membership import UserUnitMembership
            group_scs = set(menu_group_map.values())

            memberships = UserUnitMembership.query.filter(
                UserUnitMembership.user_secure_code == user.secure_code,
                UserUnitMembership.unit_secure_code.in_(group_scs),
                UserUnitMembership.is_deleted == False,
                UserUnitMembership.is_active == True,
            ).all()
            user_group_scs = {m.unit_secure_code for m in memberships}

            # 過濾
            result = []
            for item in items:
                if item.secure_code not in sub_menu_scs:
                    result.append(item)
                    continue
                # 子系統子選單：檢查社群成員身份
                group_sc = menu_group_map.get(item.secure_code)
                if not group_sc:
                    # 無 DB 關聯的子選單 (手動建立的)，保留
                    result.append(item)
                elif group_sc in user_group_scs:
                    result.append(item)
                # else: 非成員，移除

            return result

        except Exception as e:
            logger.warning('Sub system membership filter failed, skipping: %s', e)
            return items

    # ========================================
    # 合約驅動模組選單過濾
    # ========================================

    @classmethod
    def _get_authorized_modules(cls, user) -> Set[str]:
        """
        取得用戶企業的已授權模組代碼集合

        根據企業所有 ACTIVE 且在有效期限內的合約，
        聯集所有 modules_config 中的模組代碼。

        Args:
            user: 當前用戶

        Returns:
            已授權的模組代碼集合 (如 {'form_workflow', 'nocode_builder'})
        """
        from ..models.contract import Contract, ContractStatus

        org_sc = getattr(user, 'org_secure_code', None)
        if not org_sc:
            return set()

        # 系統企業不受合約限制，授權所有已安裝模組
        if org_sc == SYSTEM_ORG_CODE:
            from .lookup_service import LookupService
            installed_items = LookupService.get_items('INSTALLED_MODULES')
            return {item['code'] for item in installed_items}

        today = date.today()

        contracts = Contract.query.filter(
            Contract.org_secure_code == org_sc,
            Contract.status == ContractStatus.ACTIVE,
            Contract.start_date <= today,
            Contract.end_date >= today,
            Contract.is_deleted == False
        ).all()

        authorized = set()
        for contract in contracts:
            if contract.modules_config:
                try:
                    modules = json.loads(contract.modules_config)
                    if isinstance(modules, list):
                        authorized.update(modules)
                except (json.JSONDecodeError, TypeError):
                    logger.warning(
                        f"Invalid modules_config in contract {contract.contract_number}"
                    )

        return authorized

    @classmethod
    def _filter_by_contract(
        cls,
        items: List[MenuItem],
        authorized_modules: Set[str]
    ) -> List[MenuItem]:
        """
        根據合約授權過濾模組選單

        模組選單的判定方式：code 前綴匹配已安裝模組名稱。
        非模組選單（平台核心選單）不受影響。

        Args:
            items: 選單項目列表
            authorized_modules: 已授權的模組代碼集合

        Returns:
            過濾後的選單項目列表
        """
        from ..services.lookup_service import LookupService

        # 取得所有已安裝模組的代碼 (get_items 回傳 List[dict])
        installed_items = LookupService.get_items('INSTALLED_MODULES')
        installed_module_codes = {item['code'] for item in installed_items}

        if not installed_module_codes:
            return items

        filtered = []
        for item in items:
            # 判斷此選單是否屬於某個模組 (code 前綴匹配)
            module_code = cls._get_module_code_for_menu(item.code, installed_module_codes)

            if module_code is None:
                # 不是模組選單，直接保留
                filtered.append(item)
            elif module_code in authorized_modules:
                # 是模組選單且已授權
                filtered.append(item)
            # else: 模組選單但未授權，過濾掉

        return filtered

    @classmethod
    def _get_all_module_menu_codes(cls) -> Set[str]:
        """
        取得所有已安裝模組的選單 secure_codes

        供 SYSTEM_ADMIN / ORG_ADMIN 使用，讓管理員看到所有模組選單。
        合約過濾在後續 Step 6 處理。

        Returns:
            所有模組選單的 secure_code 集合
        """
        try:
            from .lookup_service import LookupService
            from sqlalchemy import or_

            installed_items = LookupService.get_items('INSTALLED_MODULES')
            installed_module_codes = {item['code'] for item in installed_items}

            if not installed_module_codes:
                return set()

            conditions = []
            for mc in installed_module_codes:
                conditions.append(MenuItem.code == mc)
                conditions.append(MenuItem.code.like(f'{mc}.%'))

            menus = MenuItem.query.filter(
                or_(*conditions),
                MenuItem.is_deleted == False,
                MenuItem.is_active == True
            ).all()

            return {m.secure_code for m in menus}

        except Exception as e:
            logger.warning('_get_all_module_menu_codes failed: %s', e)
            return set()

    @classmethod
    def _get_module_access_menu_codes(cls, user) -> Set[str]:
        """
        根據 module_access_control 取得用戶可見的模組選單 secure_codes

        當用戶透過 /admin/module-permissions 被指派模組使用權時，
        該模組的選單自動加入用戶的可見範圍，不需要 MenuPermission 預先設定。

        Args:
            user: 當前用戶

        Returns:
            模組選單的 secure_code 集合
        """
        try:
            from .module_access_service import ModuleAccessService
            from .lookup_service import LookupService
            from sqlalchemy import or_

            accessible, _controlled = ModuleAccessService.get_accessible_modules(user)
            if not accessible:
                return set()

            # 取得已安裝模組代碼
            installed_items = LookupService.get_items('INSTALLED_MODULES')
            installed_module_codes = {item['code'] for item in installed_items}

            # 交集：用戶可存取 且 已安裝的模組
            target_modules = accessible & installed_module_codes
            if not target_modules:
                return set()

            # 查詢這些模組的選單項目 (code == module_code 或 code LIKE 'module_code.%')
            conditions = []
            for mc in target_modules:
                conditions.append(MenuItem.code == mc)
                conditions.append(MenuItem.code.like(f'{mc}.%'))

            menus = MenuItem.query.filter(
                or_(*conditions),
                MenuItem.is_deleted == False,
                MenuItem.is_active == True
            ).all()

            return {m.secure_code for m in menus}

        except Exception as e:
            logger.warning('_get_module_access_menu_codes failed: %s', e)
            return set()

    @classmethod
    def _filter_by_module_access(
        cls,
        items: List[MenuItem],
        user
    ) -> List[MenuItem]:
        """
        根據模組使用權過濾選單

        有 ACL 記錄的模組才檢查；無 ACL 記錄的模組保留（向下相容）。
        非模組選單不受影響。

        Args:
            items: 選單項目列表
            user: 當前用戶

        Returns:
            過濾後的選單項目列表
        """
        try:
            from .module_access_service import ModuleAccessService
            from .lookup_service import LookupService

            # 取得使用者可存取的模組 + 有 ACL 設定的模組
            accessible, controlled = ModuleAccessService.get_accessible_modules(user)

            if not controlled:
                return items  # 沒有任何 ACL 記錄，全部保留

            # 取得已安裝模組代碼
            installed_items = LookupService.get_items('INSTALLED_MODULES')
            installed_module_codes = {item['code'] for item in installed_items}

            if not installed_module_codes:
                return items

            filtered = []
            for item in items:
                module_code = cls._get_module_code_for_menu(item.code, installed_module_codes)

                if module_code is None:
                    filtered.append(item)
                elif module_code not in controlled:
                    filtered.append(item)
                elif module_code in accessible:
                    filtered.append(item)

            return filtered

        except Exception as e:
            logger.warning('Module access filter failed, skipping: %s', e)
            return items

    @staticmethod
    def _get_module_code_for_menu(menu_code: str, installed_modules: Set[str]) -> Optional[str]:
        """
        判斷選單 code 屬於哪個模組

        規則：menu_code 等於模組代碼，或以 '模組代碼.' 開頭。

        Args:
            menu_code: 選單的 code
            installed_modules: 已安裝模組代碼集合

        Returns:
            模組代碼，或 None（不屬於任何模組）
        """
        for module_code in installed_modules:
            if menu_code == module_code or menu_code.startswith(f'{module_code}.'):
                return module_code
        return None
