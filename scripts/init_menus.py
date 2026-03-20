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
import secrets

# 用戶類型列表
ALL_USER_TYPES = ['SYSTEM_ADMIN', 'ORG_ADMIN', 'EMPLOYEE', 'EXTERNAL']


def generate_secure_code(length=22):
    """產生安全的隨機碼"""
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-'
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def get_allowed_user_types(required_level, is_shared):
    """
    根據 required_level 和 is_shared 決定允許的用戶類型

    required_level:
        0 = 系統管理員專用
        1 = 系統管理員專用
        2 = 一般用戶（若 is_shared=True 則所有人，否則企業管理員以上）
        20 = 企業管理員 + 系統管理員
        30 = 企業管理員專用（不含系統管理員）
    """
    if is_shared:
        # 共享選單：所有用戶類型都可見
        return ALL_USER_TYPES
    else:
        # 非共享選單
        if required_level == 0 or required_level == 1:
            # 系統管理員專用
            return ['SYSTEM_ADMIN']
        elif required_level == 30:
            # 企業管理員專用（系統管理員不可見）
            return ['ORG_ADMIN']
        elif required_level == 20:
            # 企業管理員以上（含系統管理員）
            return ['SYSTEM_ADMIN', 'ORG_ADMIN']
        else:
            # 預設企業管理員以上
            return ['SYSTEM_ADMIN', 'ORG_ADMIN']


def set_menu_permissions(menu_secure_code, user_types):
    """設定選單的用戶類型權限"""
    for user_type in user_types:
        permission = MenuPermission(
            menu_secure_code=menu_secure_code,
            user_type=user_type
        )
        db.session.add(permission)


# ============================================================================
# 核心平台選單定義
# 只包含平台級選單，模組選單（form_workflow, nocode_builder, spec_formulate 等）由模組自行註冊
# ============================================================================
CORE_MENUS = [
    # ===== 深度 0 的選單 =====
    {
        'code': 'form_workflow.center',
        'title': '表單中心',
        'icon': None,
        'link_type': 'route',
        'link_target': 'form_workflow_web.center',
        'display_order': 20,
        'depth': 0,
        'required_level': 2,
        'is_shared': True,
    },
    {
        'code': 'dashboard',
        'title': '儀表板',
        'icon': None,
        'link_type': 'route',
        'link_target': 'main.dashboard',
        'display_order': 100,
        'depth': 0,
        'required_level': 2,
        'is_shared': True,
    },
    {
        'code': 'personal_settings',
        'title': '個人設定',
        'icon': None,
        'link_type': 'route',
        'link_target': 'main.personal_settings',
        'display_order': 110,
        'depth': 0,
        'required_level': 0,
        'is_shared': True,
    },
    {
        'code': 'module_area',
        'title': '模組區',
        'icon': None,
        'link_type': 'header',
        'link_target': None,
        'display_order': 140,
        'depth': 0,
        'required_level': 30,
        'is_shared': False,
        'is_expanded': True,
    },
    {
        'code': 'org_management',
        'title': '企業管理',
        'icon': None,
        'link_type': 'header',
        'link_target': None,
        'display_order': 310,
        'depth': 0,
        'required_level': 0,
        'is_shared': False,
        'is_expanded': True,
    },
    {
        'code': 'server_settings',
        'title': '主機設定',
        'icon': None,
        'link_type': 'route',
        'link_target': 'hostconfig.server_settings',
        'display_order': 320,
        'depth': 0,
        'required_level': 1,
        'is_shared': False,
    },
    {
        'code': 'perm_mgmt',
        'title': '權限管理',
        'icon': None,
        'link_type': 'header',
        'link_target': None,
        'display_order': 330,
        'depth': 0,
        'required_level': 0,
        'is_shared': False,
        'is_expanded': True,
    },
    {
        'code': 'sys_accounts',
        'title': '系統級帳號管理',
        'icon': None,
        'link_type': 'route',
        'link_target': 'sys_accounts.list_accounts',
        'display_order': 340,
        'depth': 0,
        'required_level': 0,
        'is_shared': False,
    },
    {
        'code': 'org_config_mgr',
        'title': '系統管理',
        'icon': None,
        'link_type': 'header',
        'link_target': None,
        'display_order': 1000,
        'depth': 0,
        'required_level': 30,
        'is_shared': False,
        'is_expanded': True,
    },
    {
        'code': 'departments',
        'title': '部門設定',
        'icon': None,
        'link_type': 'route',
        'link_target': 'departments.department_settings',
        'display_order': 2000,
        'depth': 0,
        'required_level': 30,
        'is_shared': False,
    },
    {
        'code': 'org_account',
        'title': '帳號管理',
        'icon': None,
        'link_type': 'header',
        'link_target': None,
        'display_order': 3000,
        'depth': 0,
        'required_level': 30,
        'is_shared': False,
    },
    {
        'code': 'jobs_config',
        'title': '職級職稱',
        'icon': None,
        'link_type': 'header',
        'link_target': None,
        'display_order': 5000,
        'depth': 0,
        'required_level': 30,
        'is_shared': False,
    },
    {
        'code': 'groups',
        'title': '社群設定',
        'icon': None,
        'link_type': 'route',
        'link_target': 'groups.group_settings',
        'display_order': 22000,
        'depth': 0,
        'required_level': 30,
        'is_shared': False,
    },
    {
        'code': 'module_users',
        'title': '模組用戶設定',
        'icon': None,
        'link_type': 'route',
        'link_target': 'admin.module_users',
        'display_order': 25000,
        'depth': 0,
        'required_level': 30,
        'is_shared': False,
    },

    # ===== 深度 1 的選單 (有父選單) =====

    # -- 模組區 子選單 --
    {
        'code': 'module_perm_mgmt',
        'title': '模組權限管理',
        'parent_code': 'module_area',
        'link_type': 'route',
        'link_target': 'admin.module_permissions',
        'display_order': 50,
        'depth': 1,
        'required_level': 30,
        'is_shared': False,
        'required_permission': 'module:manage',
    },

    # -- 企業管理 子選單 --
    {
        'code': 'organizations_contracts',
        'title': '企業與合約管理',
        'parent_code': 'org_management',
        'link_type': 'route',
        'link_target': 'organizations.list_orgs',
        'display_order': 10,
        'depth': 1,
        'required_level': 1,
        'is_shared': False,
    },
    {
        'code': 'org_databases_system',
        'title': '企業獨立資料庫管理',
        'parent_code': 'org_management',
        'link_type': 'route',
        'link_target': 'org_databases.system_view',
        'display_order': 20,
        'depth': 1,
        'required_level': 0,
        'is_shared': False,
    },
    {
        'code': 'data_maintenance',
        'title': '資料維護',
        'parent_code': 'org_management',
        'link_type': 'route',
        'link_target': 'hostconfig.data_maintenance',
        'display_order': 30,
        'depth': 1,
        'required_level': 0,
        'is_shared': False,
    },

    # -- 權限管理 子選單 --
    {
        'code': 'menu_manage',
        'title': '選單管理',
        'parent_code': 'perm_mgmt',
        'link_type': 'route',
        'link_target': 'menu.list_menu',
        'display_order': 21,
        'depth': 1,
        'required_level': 1,
        'is_shared': False,
    },
    {
        'code': 'modules',
        'title': '模組管理',
        'parent_code': 'perm_mgmt',
        'link_type': 'route',
        'link_target': 'modules.list_modules',
        'display_order': 22,
        'depth': 1,
        'required_level': 1,
        'is_shared': False,
    },

    # -- 系統管理 子選單 --
    {
        'code': 'system_settings',
        'title': '系統設定',
        'parent_code': 'org_config_mgr',
        'link_type': 'route',
        'link_target': 'admin.settings',
        'display_order': 201,
        'depth': 1,
        'required_level': 30,
        'is_shared': False,
    },
    {
        'code': 'org_admins',
        'title': '企業管理員',
        'parent_code': 'org_config_mgr',
        'link_type': 'route',
        'link_target': 'org_admins.list_admins',
        'display_order': 590,
        'depth': 1,
        'required_level': 30,
        'is_shared': False,
    },
    {
        'code': 'org_databases_org',
        'title': '獨立資料庫',
        'parent_code': 'org_config_mgr',
        'link_type': 'route',
        'link_target': 'org_databases.org_view',
        'display_order': 600,
        'depth': 1,
        'required_level': 30,
        'is_shared': False,
    },

    # -- 帳號管理 子選單 --
    {
        'code': 'numbering',
        'title': '編號設定',
        'parent_code': 'org_account',
        'link_type': 'route',
        'link_target': 'numbering.list_rules',
        'display_order': 3100,
        'depth': 1,
        'required_level': 30,
        'is_shared': False,
    },
    {
        'code': 'roles',
        'title': '角色管理',
        'parent_code': 'org_account',
        'link_type': 'route',
        'link_target': 'roles.list_roles',
        'display_order': 3150,
        'depth': 1,
        'required_level': 30,
        'is_shared': False,
    },
    {
        'code': 'users',
        'title': '員工帳號',
        'parent_code': 'org_account',
        'link_type': 'route',
        'link_target': 'users.list_users',
        'display_order': 3200,
        'depth': 1,
        'required_level': 30,
        'is_shared': False,
    },
    {
        'code': 'work_schedules',
        'title': '基本班表',
        'parent_code': 'org_account',
        'link_type': 'route',
        'link_target': 'work_schedules.list_schedules',
        'display_order': 3300,
        'depth': 1,
        'required_level': 30,
        'is_shared': False,
    },
    {
        'code': 'external_users',
        'title': '外部廠商',
        'parent_code': 'org_account',
        'link_type': 'route',
        'link_target': 'external_users.list_external_users',
        'display_order': 3900,
        'depth': 1,
        'required_level': 30,
        'is_shared': False,
    },

    # -- 職級職稱 子選單 --
    {
        'code': 'job_matrix',
        'title': '職級職稱矩陣',
        'parent_code': 'jobs_config',
        'link_type': 'route',
        'link_target': 'job_levels.job_matrix',
        'display_order': 3100,
        'depth': 1,
        'required_level': 30,
        'is_shared': False,
    },
    {
        'code': 'job_levels',
        'title': '職等設定',
        'parent_code': 'jobs_config',
        'link_type': 'route',
        'link_target': 'job_levels.list_job_levels',
        'display_order': 3200,
        'depth': 1,
        'required_level': 30,
        'is_shared': False,
    },
    {
        'code': 'job_families',
        'title': '職系設定',
        'parent_code': 'jobs_config',
        'link_type': 'route',
        'link_target': 'job_families.list_job_families',
        'display_order': 3300,
        'depth': 1,
        'required_level': 30,
        'is_shared': False,
    },
    {
        'code': 'job_titles',
        'title': '職稱設定',
        'parent_code': 'jobs_config',
        'link_type': 'route',
        'link_target': 'job_titles.list_job_titles',
        'display_order': 3400,
        'depth': 1,
        'required_level': 30,
        'is_shared': False,
    },
    {
        'code': 'job_approval_categories',
        'title': '核決權限',
        'parent_code': 'jobs_config',
        'link_type': 'route',
        'link_target': 'approval_categories.list_categories',
        'display_order': 3500,
        'depth': 1,
        'required_level': 30,
        'is_shared': False,
    },
]


def init_menus(force=False):
    """初始化核心平台選單

    Args:
        force: 若為 True，會先清除現有選單再建立
    """
    app = create_app()

    with app.app_context():
        # 確認 system.local 企業存在
        org = Organization.query.filter_by(secure_code='system.local').first()
        if not org:
            print("錯誤: system.local 企業不存在，請先執行 init_database.sh")
            return False

        # 統計現有平台選單（排除模組選單）
        # 模組選單以模組名開頭 (如 form_workflow.*, nocode_builder.*, spec_formulate.*)
        existing_count = MenuItem.query.filter_by(
            org_secure_code='system.local',
            is_deleted=False
        ).count()

        if existing_count > 0:
            if force or '--force' in sys.argv:
                print(f"清除現有的 {existing_count} 個選單項目...")
                # 取得所有選單的 secure_code
                menu_codes = [m.secure_code for m in MenuItem.query.filter(
                    MenuItem.org_secure_code == 'system.local'
                ).all()]
                # 先刪除權限
                if menu_codes:
                    MenuPermission.query.filter(
                        MenuPermission.menu_secure_code.in_(menu_codes)
                    ).delete(synchronize_session=False)
                # 再刪除子選單（有 parent_secure_code 的）
                MenuItem.query.filter(
                    MenuItem.org_secure_code == 'system.local',
                    MenuItem.parent_secure_code.isnot(None)
                ).delete(synchronize_session=False)
                # 最後刪除父選單
                MenuItem.query.filter(
                    MenuItem.org_secure_code == 'system.local'
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
                org_secure_code='system.local',
                code=menu_def['code'],
                title=menu_def['title'],
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

            # 設定選單權限
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
                org_secure_code='system.local',
                parent_secure_code=parent_secure_code,
                code=menu_def['code'],
                title=menu_def['title'],
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

            # 設定選單權限
            user_types = get_allowed_user_types(
                menu_def['required_level'],
                menu_def.get('is_shared', False)
            )
            set_menu_permissions(secure_code, user_types)
            created_count += 1

        db.session.commit()
        print(f"成功建立 {created_count} 個選單項目")
        print("模組選單（表單流程、資料表工具等）將在 Flask 啟動時自動同步")
        return True


if __name__ == '__main__':
    success = init_menus()
    sys.exit(0 if success else 1)
