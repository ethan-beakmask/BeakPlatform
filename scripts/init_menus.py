#!/usr/bin/env python3
"""
BeakPlatform 選單初始化腳本
用於在新安裝的環境中建立核心平台選單

注意：
- 只包含平台級選單，不包含模組選單（form_workflow, nocode_builder, spec_formulate 等）
- 模組選單由 ModuleMenuService.sync_all_module_menus() 在 Flask 啟動時自動建立
- 使用 --force 可強制重建所有平台選單
"""

import sys
import os

# 跳過模組同步：init_menus 只負責平台選單，模組選單由 Flask 啟動時同步
os.environ['SKIP_MODULE_SYNC'] = '1'

# 加入 backend 路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app import create_app, db
from app.models import MenuItem, Organization, MenuPermission
from app.models.user import UserType
from app.defaults.menu_defaults import CORE_MENUS, get_allowed_user_types
from app.constants import SYSTEM_ORG_CODE
import secrets


def generate_secure_code(length=22):
    """產生安全的隨機碼"""
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-'
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def set_menu_permissions(menu_secure_code, user_types):
    """設定選單的用戶類型權限"""
    for user_type in user_types:
        permission = MenuPermission(
            menu_secure_code=menu_secure_code,
            user_type=user_type
        )
        db.session.add(permission)


# CORE_MENUS 從 app.defaults.menu_defaults 統一管理（Single Source of Truth）


def init_menus(force=False):
    """初始化核心平台選單

    Args:
        force: 若為 True，會先清除現有選單再建立
    """
    app = create_app()

    with app.app_context():
        # 確認系統企業存在
        org = Organization.query.filter_by(secure_code=SYSTEM_ORG_CODE).first()
        if not org:
            print(f"錯誤: {SYSTEM_ORG_CODE} 企業不存在，請先執行 init_database.sh")
            return False

        # 統計現有平台選單（排除模組選單）
        # 模組選單以模組名開頭 (如 form_workflow.*, nocode_builder.*, spec_formulate.*)
        existing_count = MenuItem.query.filter_by(
            org_secure_code=SYSTEM_ORG_CODE,
            is_deleted=False
        ).count()

        if existing_count > 0:
            if force or '--force' in sys.argv:
                print(f"清除現有的 {existing_count} 個選單項目...")
                # 取得所有選單的 secure_code
                menu_codes = [m.secure_code for m in MenuItem.query.filter(
                    MenuItem.org_secure_code == SYSTEM_ORG_CODE
                ).all()]
                # 先刪除權限
                if menu_codes:
                    MenuPermission.query.filter(
                        MenuPermission.menu_secure_code.in_(menu_codes)
                    ).delete(synchronize_session=False)
                # 再刪除子選單（有 parent_secure_code 的）
                MenuItem.query.filter(
                    MenuItem.org_secure_code == SYSTEM_ORG_CODE,
                    MenuItem.parent_secure_code.isnot(None)
                ).delete(synchronize_session=False)
                # 最後刪除父選單
                MenuItem.query.filter(
                    MenuItem.org_secure_code == SYSTEM_ORG_CODE
                ).delete(synchronize_session=False)
                db.session.commit()
                print("選單已清除")
            else:
                print(f"已存在 {existing_count} 個選單項目")
                print("使用 --force 參數可強制重建選單")
                return True

        # 建立選單，分兩輪：先建 depth=0，再建 depth=1
        code_to_secure_code = {}
        created_count = 0

        # 第一輪: depth=0 的選單
        print("建立根選單...")
        for menu_def in CORE_MENUS:
            if menu_def.get('depth', 0) != 0:
                continue

            secure_code = generate_secure_code()
            menu = MenuItem(
                secure_code=secure_code,
                org_secure_code=SYSTEM_ORG_CODE,
                code=menu_def['code'],
                title=menu_def['title'],
                title_i18n=menu_def.get('title_i18n') or {},
                icon=menu_def.get('icon'),
                link_type=menu_def['link_type'],
                link_target=menu_def.get('link_target'),
                open_in_new_tab=menu_def.get('open_in_new_tab', False),
                display_order=menu_def['display_order'],
                depth=0,
                is_expanded=menu_def.get('is_expanded', False),
                is_active=True,
                required_level=menu_def['required_level'],
                is_shared=menu_def.get('is_shared', False),
                required_permission=menu_def.get('required_permission'),
            )
            db.session.add(menu)
            code_to_secure_code[menu_def['code']] = secure_code

            # 設定選單權限（_user_types_override 優先）
            if '_user_types_override' in menu_def:
                user_types = menu_def['_user_types_override']
            else:
                user_types = get_allowed_user_types(
                    menu_def['required_level'],
                    menu_def.get('is_shared', False)
                )
            set_menu_permissions(secure_code, user_types)
            created_count += 1

        db.session.flush()  # 讓 FK 可以參照

        # 第二輪: depth=1 的選單
        print("建立子選單...")
        for menu_def in CORE_MENUS:
            if menu_def.get('depth', 0) != 1:
                continue

            parent_code = menu_def.get('parent_code')
            parent_secure_code = code_to_secure_code.get(parent_code)

            if not parent_secure_code:
                print(f"  警告: 找不到父選單 {parent_code}，跳過 {menu_def['code']}")
                continue

            secure_code = generate_secure_code()
            menu = MenuItem(
                secure_code=secure_code,
                org_secure_code=SYSTEM_ORG_CODE,
                parent_secure_code=parent_secure_code,
                code=menu_def['code'],
                title=menu_def['title'],
                title_i18n=menu_def.get('title_i18n') or {},
                icon=menu_def.get('icon'),
                link_type=menu_def['link_type'],
                link_target=menu_def.get('link_target'),
                open_in_new_tab=menu_def.get('open_in_new_tab', False),
                display_order=menu_def['display_order'],
                depth=1,
                is_expanded=menu_def.get('is_expanded', False),
                is_active=True,
                required_level=menu_def['required_level'],
                is_shared=menu_def.get('is_shared', False),
                required_permission=menu_def.get('required_permission'),
            )
            db.session.add(menu)
            code_to_secure_code[menu_def['code']] = secure_code

            # 設定選單權限（_user_types_override 優先）
            if '_user_types_override' in menu_def:
                user_types = menu_def['_user_types_override']
            else:
                user_types = get_allowed_user_types(
                    menu_def['required_level'],
                    menu_def.get('is_shared', False)
                )
            set_menu_permissions(secure_code, user_types)
            created_count += 1

        db.session.commit()
        print(f"成功建立 {created_count} 個選單項目")

        # 建立預設選單角色需求（雙鑰匙 Key2）
        print("建立選單角色需求...")
        from app.services.menu_service import MenuService
        items = MenuItem.query.filter_by(is_deleted=False).all()
        code_to_item = {item.code: item for item in items}
        mrr_count = MenuService.seed_all_orgs_role_requirements(code_to_item)
        db.session.commit()
        print(f"建立 {mrr_count} 筆選單角色需求")

        print("模組選單（表單流程、資料表工具等）將在 Flask 啟動時自動同步")
        return True


if __name__ == '__main__':
    success = init_menus()
    sys.exit(0 if success else 1)
