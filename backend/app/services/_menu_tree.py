"""
選單樹建構 Mixin - 負責建構用戶可見的選單樹與可見性過濾

方法：
- get_user_menu_tree: 主入口，組合所有過濾步驟
- _get_allowed_menu_codes: MenuPermission 查詢
- _get_user_permission_codes: RBAC 權限代碼
- _filter_by_rbac_permission: RBAC 過濾
- _filter_by_role_requirements: 雙鑰匙角色過濾
- _prune_empty_parents: 裁剪空 header/divider
- _filter_with_bypass: 治理分流
- _get_menu_permissions_map: 批量權限映射
- _build_tree: 樹狀結構建構
- _item_to_dict: 選單項目序列化
- _resolve_link: 連結解析
"""
import logging
from typing import List, Dict, Any, Optional, Set

from flask import g, url_for

from ..models.menu_item import MenuItem
from ..models.menu_permission import MenuPermission
from ..models.user import UserType
from ..constants import SYSTEM_ORG_CODE

logger = logging.getLogger(__name__)


class MenuTreeMixin:
    """選單樹建構與可見性過濾"""

    # [已棄用] 固定底色選單標題 - 改為統一使用權限等級著色
    FIXED_BLACK_TITLES = set()

    @classmethod
    def get_user_menu_tree(
        cls,
        user,
        layout: str = 'sidebar',
        include_inactive: bool = False
    ) -> List[Dict[str, Any]]:
        """
        取得用戶可見的選單樹

        可見性邏輯（雙鑰匙安全模型）：
        1. MenuPermission (user_type) 取得有權限的選單
        2. 模組注入（非 SYSTEM_ADMIN，依 ACL）
        3. RBAC 權限過濾 (required_permission)
        4. 合約/ACL/社群過濾
        5. 角色過濾（非 SYSTEM_ADMIN，MenuRoleRequirement 雙鑰匙）
        6. 空 header 裁剪

        SYSTEM_ADMIN 走程式控制（decorator），不受角色過濾。

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
        # ORG_ADMIN 不再無條件注入所有模組選單，改由 MenuPermission 統一治理
        # 模組安裝時 module_menu_service 已為 ORG_ADMIN 建立 MenuPermission 記錄
        module_injected_codes = set()
        user_type_str = str(user.user_type)
        if user_type_str == 'SYSTEM_ADMIN':
            module_injected_codes = set()  # 系統管理員不看模組選單
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

        # 7. 雙鑰匙角色過濾 (SYSTEM_ADMIN / ORG_ADMIN bypass)
        # ORG_ADMIN 負責設定角色與權限，已由 MenuPermission 管控可見範圍
        # 僅 EMPLOYEE / EXTERNAL 須通過 user_type + 角色兩把鑰匙
        if user_type_str not in ('SYSTEM_ADMIN', 'ORG_ADMIN'):
            filtered_items = cls._filter_by_role_requirements(
                filtered_items, user
            )
            # 裁剪空 header/divider（子項被角色過濾後變空的結構元素）
            filtered_items = cls._prune_empty_parents(filtered_items)

        # 9. 預先載入所有選單的權限資訊 (用於顯示權限等級標記)
        menu_permissions_map = cls._get_menu_permissions_map(
            [item.secure_code for item in filtered_items]
        )

        # 10. 取得語系 (優先用 g.locale，由 auth_interceptor 設定)
        locale = getattr(g, 'locale', None)
        if not locale:
            locale = 'zh-TW'
            if hasattr(user, 'organization') and user.organization:
                locale = user.organization.get_setting('locale', 'zh-TW')

        # 11. 建構樹狀結構
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

    @classmethod
    def _filter_by_role_requirements(
        cls,
        items: List[MenuItem],
        user
    ) -> List[MenuItem]:
        """
        雙鑰匙角色過濾：選單必須有角色設定且用戶持有所需角色。

        規則：
        - header/divider → 通過（結構元素，無 URL，後續由 _prune_empty_parents 裁剪）
        - 有角色設定且用戶持有所需角色 → 通過
        - 有角色設定但用戶未持有 → 過濾
        - 無角色設定 → 過濾（雙鑰匙：必須配置角色才能存取）

        Args:
            items: 選單項目列表
            user: 當前用戶

        Returns:
            過濾後的選單項目列表
        """
        from ..models.menu_role_requirement import MenuRoleRequirement
        from ..models.associations import UserRoleAssignment

        org_sc = user.org_secure_code
        item_scs = [i.secure_code for i in items]

        if not item_scs:
            return []

        # 批量查詢該企業的角色需求
        requirements = MenuRoleRequirement.query.filter(
            MenuRoleRequirement.menu_secure_code.in_(item_scs),
            MenuRoleRequirement.org_secure_code == org_sc,
            MenuRoleRequirement.is_deleted == False,
        ).all()

        # 建立映射: menu_sc -> {required_role_sc, ...}
        role_map = {}
        for req in requirements:
            role_map.setdefault(req.menu_secure_code, set()).add(
                req.role_secure_code
            )

        # 取得用戶當前有效角色（全站標準實作）
        user_role_scs = UserRoleAssignment.get_active_role_secure_codes(
            user.secure_code
        )

        filtered = []
        for item in items:
            # 結構元素（header/divider）直接通過，後續由 _prune_empty_parents 裁剪
            if item.link_type in ('header', 'divider'):
                filtered.append(item)
                continue

            required = role_map.get(item.secure_code)
            if required is None:
                # 無角色設定 → 雙鑰匙擋下（不顯示在 sidebar）
                continue

            if user_role_scs & required:
                filtered.append(item)
            # else: 有角色設定但用戶未持有 → 過濾

        return filtered

    @classmethod
    def _prune_empty_parents(cls, items: List[MenuItem]) -> List[MenuItem]:
        """
        遞迴移除沒有可見子項目的 header/divider。

        當子項目被角色過濾移除後，空的父結構元素也應移除，
        避免 sidebar 出現空的分類標題。
        """
        while True:
            item_scs = {i.secure_code for i in items}
            # 收集有子項目的 parent_secure_code
            has_children = set()
            for item in items:
                if item.parent_secure_code and item.parent_secure_code in item_scs:
                    has_children.add(item.parent_secure_code)

            pruned = [
                i for i in items
                if i.link_type not in ('header', 'divider')
                or i.secure_code in has_children
            ]

            if len(pruned) == len(items):
                break  # 無更多可裁剪
            items = pruned

        return items

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
        # 解析連結
        href = cls._resolve_link(item)

        # 判斷是否為系統級選單 (屬於 SYSTEM_ORG_CODE)
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
            if item.link_target and item.link_target.startswith('/'):
                from flask import request as _req
                return f'{_req.script_root}{item.link_target}'
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
            from flask import request as _req
            return f'{_req.script_root}/p/{item.link_target}'

        if item.link_type in ('divider', 'header'):
            return None

        return '#'
