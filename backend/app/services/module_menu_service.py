"""
BeakPlatform - Module Menu Service
模組選單註冊服務

負責：
1. 將模組定義的選單同步到 MenuItem 資料表
2. 管理模組選單的生命週期（新增、更新、停用）
3. 設定模組選單的權限（MenuPermission）
"""
import logging
from typing import Dict, List, Any, Optional, Set

from .. import db
from ..models import MenuItem, MenuPermission
from ..models.user import UserType
from ..constants import SYSTEM_ORG_CODE
from ..services.menu_service import MenuService

logger = logging.getLogger(__name__)


class ModuleMenuService:
    """模組選單服務"""

    # 預設所有用戶類型都可見
    DEFAULT_USER_TYPES = [
        UserType.SYSTEM_ADMIN,
        UserType.ORG_ADMIN,
        UserType.EMPLOYEE,
        UserType.EXTERNAL,
    ]

    @classmethod
    def register_module_menus(
        cls,
        module_name: str,
        menu_items: List[Dict[str, Any]],
        force: bool = False
    ) -> Dict[str, int]:
        """
        註冊模組的選單定義到資料庫

        預設只建立缺少的選單，不覆蓋已存在的（保護管理員手動修改）。
        使用 force=True 可強制覆蓋回模組定義。

        Args:
            module_name: 模組名稱
            menu_items: 選單定義列表
            force: 是否強制覆蓋已存在的選單

        Returns:
            {'created': n, 'updated': n, 'unchanged': n}
        """
        result = {'created': 0, 'updated': 0, 'unchanged': 0}

        if not menu_items:
            return result

        # 遞迴處理所有選單項目
        for menu_def in menu_items:
            sub_result = cls._register_menu_item(
                module_name=module_name,
                menu_def=menu_def,
                parent_secure_code=None,
                force=force
            )
            result['created'] += sub_result['created']
            result['updated'] += sub_result['updated']
            result['unchanged'] += sub_result['unchanged']

        try:
            db.session.commit()
            logger.info(
                f"Module {module_name}: Registered {result['created']} new, "
                f"{result['updated']} updated, {result['unchanged']} unchanged menus"
            )
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to register menus for {module_name}: {e}")
            raise

        return result

    @classmethod
    def _register_menu_item(
        cls,
        module_name: str,
        menu_def: Dict[str, Any],
        parent_secure_code: Optional[str],
        force: bool = False,
        parent_user_types: Optional[List] = None
    ) -> Dict[str, int]:
        """
        註冊單一選單項目（遞迴處理子選單）

        Args:
            module_name: 模組名稱
            menu_def: 選單定義
            parent_secure_code: 父選單 secure_code
            force: 是否強制覆蓋已存在的選單
            parent_user_types: 父選單的 user_types（子選單未指定時繼承）

        Returns:
            {'created': n, 'updated': n, 'unchanged': n}
        """
        result = {'created': 0, 'updated': 0, 'unchanged': 0}

        code = menu_def.get('code')
        name = menu_def.get('name')

        if not code or not name:
            logger.warning(
                f"Module {module_name}: Invalid menu definition "
                f"(missing code or name): {menu_def}"
            )
            return result

        # 查找現有選單（以 code 為準，含已刪除的）
        # 如果管理員手動刪除了模組選單，不應該被同步重建
        existing = MenuItem.query.filter_by(
            code=code,
            org_secure_code=SYSTEM_ORG_CODE,
        ).first()

        # 已被管理員刪除的選單，跳過不重建
        if existing and existing.is_deleted:
            result['unchanged'] += 1
            return result

        # 解析選單屬性
        icon = menu_def.get('icon')
        url = menu_def.get('url')
        sort_order = menu_def.get('sort_order', 0)
        is_expanded = menu_def.get('is_expanded', False)
        required_permission = menu_def.get('required_permission')
        # 子選單未指定 user_types 時，繼承父選單；頂層未指定則使用預設
        fallback_types = parent_user_types if parent_user_types else cls.DEFAULT_USER_TYPES
        user_types = menu_def.get('user_types', fallback_types)

        # 決定連結類型和目標
        link_type = 'route'
        link_target = url
        if not url:
            link_type = 'header'  # 無連結的選單作為標題
            link_target = None

        if existing:
            if not force:
                # 非強制模式：保留管理員手動修改，跳過更新
                result['unchanged'] += 1
                menu_secure_code = existing.secure_code
            else:
                # 強制模式：覆蓋回模組定義
                changed = False

                if existing.title != name:
                    existing.title = name
                    changed = True
                # 模組定義未提供 title_i18n 時保留 DB 現值（翻譯可能只回填在 DB）
                new_title_i18n = menu_def.get('title_i18n') or {}
                if new_title_i18n and (existing.title_i18n or {}) != new_title_i18n:
                    existing.title_i18n = new_title_i18n
                    changed = True
                if existing.icon != icon:
                    existing.icon = icon
                    changed = True
                if existing.link_type != link_type:
                    existing.link_type = link_type
                    changed = True
                if existing.link_target != link_target:
                    existing.link_target = link_target
                    changed = True
                if existing.display_order != sort_order:
                    existing.display_order = sort_order
                    changed = True
                if existing.is_expanded != is_expanded:
                    existing.is_expanded = is_expanded
                    changed = True
                if existing.required_permission != required_permission:
                    existing.required_permission = required_permission
                    changed = True
                if existing.parent_secure_code != parent_secure_code:
                    existing.parent_secure_code = parent_secure_code
                    existing.depth = cls._calculate_depth(parent_secure_code)
                    changed = True
                if not existing.is_active:
                    existing.is_active = True
                    changed = True

                # 更新權限
                current_perms = set(MenuService.get_menu_permissions(existing.secure_code))
                new_perms = set(user_types)
                if current_perms != new_perms:
                    MenuService.set_menu_permissions(existing.secure_code, list(user_types))
                    changed = True

                if changed:
                    result['updated'] += 1
                    logger.debug(f"Force updated menu: {code}")
                else:
                    result['unchanged'] += 1

                menu_secure_code = existing.secure_code

        else:
            # 建立新選單
            depth = cls._calculate_depth(parent_secure_code)

            new_menu = MenuItem(
                org_secure_code=SYSTEM_ORG_CODE,
                code=code,
                title=name,
                title_i18n=menu_def.get('title_i18n') or {},
                icon=icon,
                link_type=link_type,
                link_target=link_target,
                parent_secure_code=parent_secure_code,
                display_order=sort_order,
                depth=depth,
                is_expanded=is_expanded,
                is_active=True,
                is_shared=len(user_types) > 1,
                required_permission=required_permission,
            )
            db.session.add(new_menu)
            db.session.flush()  # 取得 secure_code

            # 設定權限
            MenuService.set_menu_permissions(new_menu.secure_code, list(user_types))

            result['created'] += 1
            logger.debug(f"Created menu: {code}")

            menu_secure_code = new_menu.secure_code

        # 遞迴處理子選單（繼承當前選單的 user_types）
        children = menu_def.get('children', [])
        for child_def in children:
            sub_result = cls._register_menu_item(
                module_name=module_name,
                menu_def=child_def,
                parent_secure_code=menu_secure_code,
                force=force,
                parent_user_types=list(user_types)
            )
            result['created'] += sub_result['created']
            result['updated'] += sub_result['updated']
            result['unchanged'] += sub_result['unchanged']

        return result

    @classmethod
    def _calculate_depth(cls, parent_secure_code: Optional[str]) -> int:
        """計算選單深度"""
        if not parent_secure_code:
            return 0

        parent = MenuItem.query.filter_by(
            secure_code=parent_secure_code
        ).first()

        if parent:
            return parent.depth + 1
        return 0

    @classmethod
    def sync_all_module_menus(
        cls,
        module_loader,
        force: bool = False
    ) -> Dict[str, Dict[str, int]]:
        """
        同步所有模組的選單

        Args:
            module_loader: ModuleLoader 實例
            force: 是否強制覆蓋已存在的選單

        Returns:
            {module_name: {'created': n, 'updated': n, 'unchanged': n}}
        """
        results = {}

        for module in module_loader.get_loaded_modules():
            if module.menu_items:
                try:
                    result = cls.register_module_menus(
                        module.name,
                        module.menu_items,
                        force=force
                    )
                    results[module.name] = result
                except Exception as e:
                    logger.error(f"Failed to sync menus for {module.name}: {e}")
                    results[module.name] = {'error': str(e)}

        return results

    @classmethod
    def deactivate_module_menus(cls, module_name: str) -> int:
        """
        停用模組的所有選單

        當模組被停用或移除時呼叫

        Args:
            module_name: 模組名稱

        Returns:
            停用的選單數量
        """
        # 停用模組選單 (精確匹配 code 或 code 以 'module_name.' 開頭)
        from sqlalchemy import or_
        count = MenuItem.query.filter(
            or_(
                MenuItem.code == module_name,
                MenuItem.code.like(f"{module_name}.%"),
            ),
            MenuItem.org_secure_code == SYSTEM_ORG_CODE,
            MenuItem.is_deleted == False,
            MenuItem.is_active == True
        ).update(
            {'is_active': False},
            synchronize_session=False
        )

        try:
            db.session.commit()
            logger.info(f"Deactivated {count} menus for module {module_name}")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to deactivate menus for {module_name}: {e}")
            raise

        return count

    @classmethod
    def get_module_menus(cls, module_name: str) -> List[MenuItem]:
        """
        取得模組的所有選單

        Args:
            module_name: 模組名稱

        Returns:
            MenuItem 列表
        """
        from sqlalchemy import or_
        return MenuItem.query.filter(
            or_(
                MenuItem.code == module_name,
                MenuItem.code.like(f"{module_name}.%"),
            ),
            MenuItem.org_secure_code == SYSTEM_ORG_CODE,
            MenuItem.is_deleted == False
        ).order_by(MenuItem.depth, MenuItem.display_order).all()

    @classmethod
    def ensure_system_org_exists(cls) -> bool:
        """
        確保系統企業 (SYSTEM_ORG_CODE) 組織存在

        Returns:
            是否成功
        """
        from ..models import Organization

        org = Organization.query.filter_by(
            secure_code=SYSTEM_ORG_CODE,
            is_deleted=False
        ).first()

        if not org:
            logger.warning(
                f"System organization '{SYSTEM_ORG_CODE}' not found. "
                "Module menus may not work correctly."
            )
            return False

        return True
