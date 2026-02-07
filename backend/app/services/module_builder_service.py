"""
BeakPlatform Module Builder Service
模組建置服務 - No-Code Builder 核心
"""
from typing import Dict, List, Optional, Any
import json

from ..models.module import Module
from ..models.page import Page
from ..models.menu_item import MenuItem
from ..security.resource_gateway import ResourceGateway
from .. import db


class ModuleBuilderService:
    """
    模組建置服務

    No-Code Builder 的核心，用於自動生成模組結構：
    - 建立模組
    - 生成頁面結構
    - 生成對應選單
    """

    # 預設頁面模板
    DEFAULT_PAGE_TEMPLATES = {
        'list': {
            'title_suffix': '列表',
            'url_suffix': '',
            'page_type': 'list',
        },
        'create': {
            'title_suffix': '新增',
            'url_suffix': '/create',
            'page_type': 'form',
        },
        'view': {
            'title_suffix': '詳情',
            'url_suffix': '/{id}',
            'page_type': 'detail',
        },
        'edit': {
            'title_suffix': '編輯',
            'url_suffix': '/{id}/edit',
            'page_type': 'form',
        },
    }

    @classmethod
    def create_module(
        cls,
        org_secure_code: str,
        code: str,
        name: str,
        description: Optional[str] = None,
        icon: Optional[str] = None,
        page_structure: Optional[Dict[str, Any]] = None,
        create_menu: bool = True,
        required_level: int = 2,
    ) -> Module:
        """
        建立新模組

        Args:
            org_secure_code: 企業識別碼
            code: 模組代碼 (如 'members')
            name: 模組名稱 (如 '會員系統')
            description: 模組描述
            icon: 模組圖標
            page_structure: 自訂頁面結構
            create_menu: 是否自動建立選單
            required_level: 選單權限等級

        Returns:
            建立的 Module

        page_structure 範例:
        {
            'main': {
                'title': '會員總覽',
                'type': 'dashboard',
                'children': ['list', 'stats', 'settings']
            },
            'list': {
                'title': '會員列表',
                'type': 'list',
                'children': ['create', 'import']
            },
            ...
        }
        """
        # 1. 建立模組
        module = Module(
            org_secure_code=org_secure_code,
            code=code,
            name=name,
            description=description,
            icon=icon,
            is_system_module=False,
            is_active=True,
        )
        db.session.add(module)
        db.session.flush()  # 取得 secure_code

        # 2. 建立頁面
        pages = {}
        if page_structure:
            pages = cls._create_pages_from_structure(
                module, page_structure
            )
        else:
            # 使用預設頁面結構
            pages = cls._create_default_pages(module)

        # 3. 建立選單結構
        if create_menu:
            cls._create_menu_structure(
                module, pages, page_structure, required_level
            )

        return module

    @classmethod
    def _create_default_pages(cls, module: Module) -> Dict[str, Page]:
        """
        建立預設頁面 (list, create, view, edit)

        Args:
            module: 模組

        Returns:
            {page_code: Page} 字典
        """
        pages = {}

        for page_code, template in cls.DEFAULT_PAGE_TEMPLATES.items():
            page = Page(
                org_secure_code=module.org_secure_code,
                module_secure_code=module.secure_code,
                code=f"{module.code}_{page_code}",
                title=f"{module.name}{template['title_suffix']}",
                url_path=f"/{module.code}{template['url_suffix']}",
                page_type=template['page_type'],
                required_access='authenticated',
                is_active=True,
            )
            db.session.add(page)
            pages[page_code] = page

        return pages

    @classmethod
    def _create_pages_from_structure(
        cls,
        module: Module,
        structure: Dict[str, Any]
    ) -> Dict[str, Page]:
        """
        根據自訂結構建立頁面

        Args:
            module: 模組
            structure: 頁面結構定義

        Returns:
            {page_code: Page} 字典
        """
        pages = {}

        for page_code, config in structure.items():
            title = config.get('title', page_code)
            page_type = config.get('type', 'custom')
            url_suffix = config.get('url', f'/{page_code}')
            required_access = config.get('access', 'authenticated')

            page = Page(
                org_secure_code=module.org_secure_code,
                module_secure_code=module.secure_code,
                code=f"{module.code}_{page_code}",
                title=title,
                url_path=f"/{module.code}{url_suffix}",
                page_type=page_type,
                required_access=required_access,
                is_active=True,
                settings=json.dumps(config.get('settings', {})) if config.get('settings') else None,
            )
            db.session.add(page)
            pages[page_code] = page

        return pages

    @classmethod
    def _create_menu_structure(
        cls,
        module: Module,
        pages: Dict[str, Page],
        structure: Optional[Dict[str, Any]],
        required_level: int
    ) -> MenuItem:
        """
        為模組建立選單結構

        Args:
            module: 模組
            pages: 已建立的頁面字典
            structure: 頁面結構定義
            required_level: 權限等級

        Returns:
            根選單項目
        """
        # 建立模組根選單
        first_page = next(iter(pages.values())) if pages else None

        root_menu = MenuItem(
            org_secure_code=module.org_secure_code,
            module_secure_code=module.secure_code,
            code=f"menu_{module.code}",
            title=module.name,
            icon=module.icon,
            link_type='route' if not first_page else 'page',
            link_target=first_page.secure_code if first_page else None,
            display_order=100,
            depth=0,
            required_level=required_level,
            is_expanded=False,
        )
        db.session.add(root_menu)
        db.session.flush()

        # 根據結構建立子選單
        if structure:
            cls._create_child_menus(
                module, pages, structure, root_menu, required_level
            )
        elif len(pages) > 1:
            # 預設結構：為每個頁面建立子選單
            for i, (page_code, page) in enumerate(pages.items()):
                child_menu = MenuItem(
                    org_secure_code=module.org_secure_code,
                    module_secure_code=module.secure_code,
                    parent_secure_code=root_menu.secure_code,
                    code=f"menu_{page.code}",
                    title=page.title.replace(module.name, '').strip() or page_code,
                    link_type='page',
                    link_target=page.secure_code,
                    display_order=i,
                    depth=1,
                    required_level=required_level,
                )
                db.session.add(child_menu)

        return root_menu

    @classmethod
    def _create_child_menus(
        cls,
        module: Module,
        pages: Dict[str, Page],
        structure: Dict[str, Any],
        parent_menu: MenuItem,
        required_level: int,
        processed: Optional[set] = None
    ) -> None:
        """
        遞迴建立子選單

        Args:
            module: 模組
            pages: 頁面字典
            structure: 結構定義
            parent_menu: 父選單
            required_level: 權限等級
            processed: 已處理的頁面代碼集合
        """
        if processed is None:
            processed = set()

        # 取得父選單對應的頁面配置
        parent_code = parent_menu.code.replace(f"menu_{module.code}_", '').replace(f"menu_{module.code}", 'main')

        if parent_code in structure:
            config = structure[parent_code]
            children = config.get('children', [])

            for i, child_code in enumerate(children):
                if child_code in processed:
                    continue

                processed.add(child_code)

                # 取得子頁面
                page = pages.get(child_code)

                # 取得子配置
                child_config = structure.get(child_code, {})
                child_title = child_config.get('title', child_code)

                # 建立子選單
                child_menu = MenuItem(
                    org_secure_code=module.org_secure_code,
                    module_secure_code=module.secure_code,
                    parent_secure_code=parent_menu.secure_code,
                    code=f"menu_{module.code}_{child_code}",
                    title=child_title,
                    link_type='page' if page else 'header',
                    link_target=page.secure_code if page else None,
                    display_order=i,
                    depth=parent_menu.depth + 1,
                    required_level=required_level,
                )
                db.session.add(child_menu)
                db.session.flush()

                # 遞迴處理子選單的子選單
                if child_config.get('children'):
                    cls._create_child_menus(
                        module, pages, structure,
                        child_menu, required_level, processed
                    )

    @classmethod
    def delete_module(
        cls,
        module_secure_code: str,
        hard_delete: bool = False
    ) -> bool:
        """
        刪除模組及其所有相關資源

        Args:
            module_secure_code: 模組識別碼
            hard_delete: 是否硬刪除

        Returns:
            是否成功
        """
        module = ResourceGateway.get(
            Module,
            module_secure_code,
            check_permission=False
        )

        if not module:
            return False

        # 檢查是否為系統模組
        if module.is_system_module:
            return False

        from datetime import datetime
        now = datetime.utcnow()

        if hard_delete:
            # 硬刪除相關選單
            MenuItem.query.filter_by(
                module_secure_code=module_secure_code
            ).delete()

            # 硬刪除相關頁面
            Page.query.filter_by(
                module_secure_code=module_secure_code
            ).delete()

            # 硬刪除模組
            db.session.delete(module)
        else:
            # 軟刪除相關選單
            MenuItem.query.filter_by(
                module_secure_code=module_secure_code
            ).update({
                'is_deleted': True,
                'deleted_at': now
            })

            # 軟刪除相關頁面
            Page.query.filter_by(
                module_secure_code=module_secure_code
            ).update({
                'is_deleted': True,
                'deleted_at': now
            })

            # 軟刪除模組
            module.is_deleted = True
            module.deleted_at = now

        return True

    @classmethod
    def get_module_structure(cls, module_secure_code: str) -> Dict[str, Any]:
        """
        取得模組的完整結構 (含頁面和選單)

        Args:
            module_secure_code: 模組識別碼

        Returns:
            模組結構字典
        """
        module = ResourceGateway.get(
            Module,
            module_secure_code,
            check_permission=False
        )

        if not module:
            return {}

        # 取得頁面
        pages = Page.query.filter(
            Page.module_secure_code == module_secure_code,
            Page.is_deleted == False
        ).all()

        # 取得選單
        menu_items = MenuItem.query.filter(
            MenuItem.module_secure_code == module_secure_code,
            MenuItem.is_deleted == False
        ).order_by(MenuItem.depth, MenuItem.display_order).all()

        return {
            'module': module.to_dict(),
            'pages': [p.to_dict() for p in pages],
            'menu_items': [m.to_dict() for m in menu_items],
        }
