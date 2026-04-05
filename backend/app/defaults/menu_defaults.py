"""
BeakPlatform - Menu Default Definitions
選單預設值定義 (Single Source of Truth)

平台核心選單的預設值，供初始化腳本和重置功能共用。
模組選單的預設值由各模組 MODULE_INFO['menu_items'] 定義。

display_order 使用連續序號 (0, 1, 2...)，與拖曳排序儲存格式一致。
"""

# 用戶類型列表
ALL_USER_TYPES = ['SYSTEM_ADMIN', 'ORG_ADMIN', 'EMPLOYEE', 'EXTERNAL']


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
        return list(ALL_USER_TYPES)
    else:
        if required_level == 0 or required_level == 1:
            return ['SYSTEM_ADMIN']
        elif required_level == 30:
            return ['ORG_ADMIN']
        elif required_level == 20:
            return ['SYSTEM_ADMIN', 'ORG_ADMIN']
        else:
            return ['SYSTEM_ADMIN', 'ORG_ADMIN']


# ============================================================================
# 核心平台選單定義
# 只包含平台級選單，模組選單由各模組 MODULE_INFO['menu_items'] 定義
# display_order 為同層連續序號，2026-03-30 從 DB 匯出校正
# ============================================================================
CORE_MENUS = [
    # ===== 深度 0 根選單 (order 0-18) =====
    {
        'code': 'dashboard',
        'title': '儀表板',
        'icon': None,
        'link_type': 'route',
        'link_target': 'main.dashboard',
        'display_order': 0,
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
        'display_order': 1,
        'depth': 0,
        'required_level': 2,
        'is_shared': True,
    },
    {
        'code': 'form_workflow.center',
        'title': '表單中心',
        'icon': None,
        'link_type': 'route',
        'link_target': 'form_workflow_web.center',
        'display_order': 2,
        'depth': 0,
        'required_level': 2,
        'is_shared': True,
    },
    # order 3: form_workflow (模組，由 MODULE_INFO 定義)
    # order 4: spec_formulate (模組，由 MODULE_INFO 定義)
    # order 5: nocode_builder (模組，由 MODULE_INFO 定義)
    {
        'code': 'security_localsystem',
        'title': '本機安全',
        'icon': None,
        'link_type': 'header',
        'link_target': None,
        'display_order': 6,
        'depth': 0,
        'required_level': 0,
        'is_shared': False,
    },
    {
        'code': 'org_management',
        'title': '企業管理',
        'icon': None,
        'link_type': 'header',
        'link_target': None,
        'display_order': 7,
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
        'display_order': 8,
        'depth': 0,
        'required_level': 0,
        'is_shared': False,
    },
    {
        'code': 'servsr_manage',
        'title': '主機管理',
        'icon': None,
        'link_type': 'header',
        'link_target': None,
        'display_order': 9,
        'depth': 0,
        'required_level': 0,
        'is_shared': False,
    },
    {
        'code': 'perm_mgmt',
        'title': '權限管理',
        'icon': None,
        'link_type': 'header',
        'link_target': None,
        'display_order': 10,
        'depth': 0,
        'required_level': 0,
        'is_shared': False,
        'is_expanded': True,
    },
    {
        'code': 'org_config_mgr',
        'title': '系統管理',
        'icon': None,
        'link_type': 'header',
        'link_target': None,
        'display_order': 11,
        'depth': 0,
        'required_level': 30,
        'is_shared': False,
        'is_expanded': True,
    },
    {
        'code': 'org_account',
        'title': '帳號管理',
        'icon': None,
        'link_type': 'header',
        'link_target': None,
        'display_order': 12,
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
        'display_order': 13,
        'depth': 0,
        'required_level': 30,
        'is_shared': False,
    },
    {
        'code': 'departments',
        'title': '部門設定',
        'icon': None,
        'link_type': 'route',
        'link_target': 'departments.department_settings',
        'display_order': 14,
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
        'display_order': 15,
        'depth': 0,
        'required_level': 30,
        'is_shared': False,
    },
    {
        'code': 'roles_control',
        'title': '角色管控',
        'icon': 'ri-user-star-line',
        'link_type': 'header',
        'link_target': None,
        'display_order': 16,
        'depth': 0,
        'required_level': 30,
        'is_shared': False,
    },
    {
        'code': 'org_security',
        'title': '系統安全',
        'icon': None,
        'link_type': 'header',
        'link_target': None,
        'display_order': 17,
        'depth': 0,
        'required_level': 30,
        'is_shared': False,
    },
    {
        'code': 'platform_help',
        'title': '說明',
        'icon': None,
        'link_type': 'header',
        'link_target': None,
        'display_order': 18,
        'depth': 0,
        'required_level': 2,
        'is_shared': True,
    },

    # ===== 深度 1 子選單 =====

    # -- 本機安全 (security_localsystem) --
    {
        'code': 'login_fail_monitor',
        'title': '登入錯誤監看',
        'parent_code': 'security_localsystem',
        'link_type': 'url',
        'link_target': '/security/login-failures/',
        'display_order': 0,
        'depth': 1,
        'required_level': 0,
        'is_shared': False,
    },

    # -- 企業管理 (org_management) --
    {
        'code': 'organizations_contracts',
        'title': '企業與合約管理',
        'parent_code': 'org_management',
        'link_type': 'route',
        'link_target': 'organizations.list_orgs',
        'display_order': 0,
        'depth': 1,
        'required_level': 0,
        'is_shared': False,
    },
    {
        'code': 'org_databases_system',
        'title': '企業獨立資料庫管理',
        'parent_code': 'org_management',
        'link_type': 'route',
        'link_target': 'org_databases.system_view',
        'display_order': 1,
        'depth': 1,
        'required_level': 0,
        'is_shared': False,
    },
    {
        'code': 'cg_databases_overview',
        'title': '集團資料庫總覽',
        'parent_code': 'org_management',
        'link_type': 'route',
        'link_target': 'cg_databases.overview',
        'display_order': 3,
        'depth': 1,
        'required_level': 0,
        'is_shared': False,
    },

    # -- 主機管理 (servsr_manage) --
    {
        'code': 'redis_monitor',
        'title': 'Redis 監看',
        'parent_code': 'servsr_manage',
        'icon': 'ri-database-2-line',
        'link_type': 'url',
        'link_target': '/server-manage/redis-monitor',
        'display_order': 0,
        'depth': 1,
        'required_level': 0,
        'is_shared': False,
    },
    {
        'code': 'data_maintenance',
        'title': '資料維護',
        'parent_code': 'servsr_manage',
        'link_type': 'route',
        'link_target': 'hostconfig.data_maintenance',
        'display_order': 1,
        'depth': 1,
        'required_level': 0,
        'is_shared': False,
    },
    # -- 權限管理 (perm_mgmt) --
    {
        'code': 'menu_manage',
        'title': '選單管理',
        'parent_code': 'perm_mgmt',
        'link_type': 'route',
        'link_target': 'menu.list_menu',
        'display_order': 0,
        'depth': 1,
        'required_level': 0,
        'is_shared': False,
    },
    {
        'code': 'sys_accounts',
        'title': '系統管理員帳號',
        'parent_code': 'perm_mgmt',
        'link_type': 'route',
        'link_target': 'sys_accounts.list_accounts',
        'display_order': 1,
        'depth': 1,
        'required_level': 0,
        'is_shared': False,
    },
    {
        'code': 'permission_central',
        'title': '權限中央管理',
        'parent_code': 'perm_mgmt',
        'link_type': 'url',
        'link_target': '/permissions/',
        'display_order': 2,
        'depth': 1,
        'required_level': 0,
        'is_shared': False,
    },
    {
        'code': 'modules',
        'title': '模組管理',
        'parent_code': 'perm_mgmt',
        'link_type': 'route',
        'link_target': 'modules.list_modules',
        'display_order': 3,
        'depth': 1,
        'required_level': 0,
        'is_shared': False,
    },

    # -- 系統管理 (org_config_mgr) --
    {
        'code': 'system_settings',
        'title': '系統設定',
        'parent_code': 'org_config_mgr',
        'link_type': 'route',
        'link_target': 'admin.settings',
        'display_order': 0,
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
        'display_order': 1,
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
        'display_order': 2,
        'depth': 1,
        'required_level': 30,
        'is_shared': False,
    },

    # -- 帳號管理 (org_account) --
    {
        'code': 'numbering',
        'title': '編號設定',
        'parent_code': 'org_account',
        'link_type': 'route',
        'link_target': 'numbering.list_rules',
        'display_order': 0,
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
        'display_order': 1,
        'depth': 1,
        'required_level': 30,
        'is_shared': False,
    },
    {
        'code': 'users',
        'title': '企業成員帳號',
        'parent_code': 'org_account',
        'link_type': 'route',
        'link_target': 'users.list_users',
        'display_order': 2,
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
        'display_order': 3,
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
        'display_order': 4,
        'depth': 1,
        'required_level': 30,
        'is_shared': False,
    },

    # -- 職級職稱 (jobs_config) --
    {
        'code': 'job_matrix',
        'title': '職級職稱矩陣',
        'parent_code': 'jobs_config',
        'link_type': 'route',
        'link_target': 'job_levels.job_matrix',
        'display_order': 0,
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
        'display_order': 1,
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
        'display_order': 2,
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
        'display_order': 3,
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
        'display_order': 4,
        'depth': 1,
        'required_level': 30,
        'is_shared': False,
    },

    # -- 角色管控 (roles_control) --
    {
        'code': 'permission_central_org',
        'title': '權限中央管理',
        'parent_code': 'roles_control',
        'link_type': 'url',
        'link_target': '/permissions/',
        'display_order': 0,
        'depth': 1,
        'required_level': 30,
        'is_shared': False,
    },
    {
        'code': 'module_perm_mgmt',
        'title': '模組權限管理',
        'parent_code': 'roles_control',
        'link_type': 'route',
        'link_target': 'admin.module_permissions',
        'display_order': 1,
        'depth': 1,
        'required_level': 30,
        'is_shared': False,
        'required_permission': 'module:manage',
    },
    {
        'code': 'account_roles',
        'title': '帳號角色權限表',
        'parent_code': 'roles_control',
        'link_type': 'route',
        'link_target': 'account_roles.index',
        'display_order': 3,
        'depth': 1,
        'required_level': 30,
        'is_shared': False,
    },

    # -- 系統安全 (org_security) --
    {
        'code': 'login_fail_monitor_org',
        'title': '登入錯誤監看',
        'parent_code': 'org_security',
        'link_type': 'url',
        'link_target': '/security/login-failures/',
        'display_order': 0,
        'depth': 1,
        'required_level': 30,
        'is_shared': False,
    },
    {
        'code': 'org_rate_limits',
        'title': '速率限制',
        'parent_code': 'org_security',
        'link_type': 'url',
        'link_target': '/security/rate-limits/',
        'display_order': 1,
        'depth': 1,
        'required_level': 30,
        'is_shared': False,
    },
    {
        'code': 'alert_broadcasts_org',
        'title': '緊急廣播管理',
        'parent_code': 'org_security',
        'link_type': 'url',
        'link_target': '/security/alert-broadcasts/',
        'display_order': 2,
        'depth': 1,
        'required_level': 30,
        'is_shared': False,
    },

    # -- 說明 (platform_help) --
    {
        'code': 'platform_help.system_admin',
        'title': '系統管理員說明',
        'parent_code': 'platform_help',
        'link_type': 'route',
        'link_target': 'platform_help.index',
        'display_order': 0,
        'depth': 1,
        'required_level': 0,
        'is_shared': False,
        '_user_types_override': ['SYSTEM_ADMIN'],
    },
    {
        'code': 'platform_help.org_admin',
        'title': '企業管理員說明',
        'parent_code': 'platform_help',
        'link_type': 'route',
        'link_target': 'platform_help.index',
        'display_order': 1,
        'depth': 1,
        'required_level': 30,
        'is_shared': False,
        '_user_types_override': ['ORG_ADMIN'],
    },
    {
        'code': 'platform_help.employee',
        'title': '企業成員說明',
        'parent_code': 'platform_help',
        'link_type': 'route',
        'link_target': 'platform_help.index',
        'display_order': 2,
        'depth': 1,
        'required_level': 2,
        'is_shared': False,
        '_user_types_override': ['EMPLOYEE'],
    },
    {
        'code': 'platform_help.external',
        'title': '外部廠商說明',
        'parent_code': 'platform_help',
        'link_type': 'route',
        'link_target': 'platform_help.index',
        'display_order': 3,
        'depth': 1,
        'required_level': 2,
        'is_shared': False,
        '_user_types_override': ['EXTERNAL'],
    },
]


# ============================================================================
# 選單角色需求預設值 (雙鑰匙 Key2)
# menu_code → [role_codes]
#
# 從 system.local 的 menu_role_requirements 匯出 (2026-03-30)
# SYSTEM_ADMIN 專用選單不需要角色（程式 bypass），故不在此列
# ============================================================================
MENU_ROLE_DEFAULTS = {
    # 共用選單（ALL user types）
    'dashboard': ['ORG_ADMIN', 'EMPLOYEE', 'EXTERNAL_USERS'],
    'personal_settings': ['ORG_ADMIN', 'EMPLOYEE', 'EXTERNAL_USERS'],
    'form_workflow.center': ['ORG_ADMIN', 'EMPLOYEE'],
    'platform_help': ['ORG_ADMIN', 'EMPLOYEE', 'EXTERNAL_USERS'],

    # 說明子選單（各 user_type 專屬）
    'platform_help.org_admin': ['ORG_ADMIN'],
    'platform_help.employee': ['EMPLOYEE'],
    'platform_help.external': ['EXTERNAL_USERS'],

    # 表單流程模組（ORG_ADMIN + FORM_DESIGNER + FLOW_DESIGNER）
    'form_workflow': ['ORG_ADMIN', 'FORM_DESIGNER', 'FLOW_DESIGNER'],
    'form_workflow.categories': ['ORG_ADMIN', 'FORM_DESIGNER', 'FLOW_DESIGNER'],
    'form_workflow.form_themes': ['ORG_ADMIN', 'FORM_DESIGNER', 'FLOW_DESIGNER'],
    'form_workflow.mappings': ['ORG_ADMIN', 'FORM_DESIGNER', 'FLOW_DESIGNER'],
    'form_workflow.templates': ['ORG_ADMIN', 'FORM_DESIGNER'],
    'form_workflow.workflows': ['ORG_ADMIN', 'FLOW_DESIGNER'],

    # 系統管理區（ORG_ADMIN only）
    'org_config_mgr': ['ORG_ADMIN'],
    'system_settings': ['ORG_ADMIN'],
    'org_admins': ['ORG_ADMIN'],
    'org_databases_org': ['ORG_ADMIN'],

    # 帳號管理區（ORG_ADMIN only）
    'org_account': ['ORG_ADMIN'],
    'numbering': ['ORG_ADMIN'],
    'roles': ['ORG_ADMIN'],
    'users': ['ORG_ADMIN'],
    'work_schedules': ['ORG_ADMIN'],
    'external_users': ['ORG_ADMIN'],

    # 職級職稱區（ORG_ADMIN only）
    'jobs_config': ['ORG_ADMIN'],
    'job_matrix': ['ORG_ADMIN'],
    'job_levels': ['ORG_ADMIN'],
    'job_families': ['ORG_ADMIN'],
    'job_titles': ['ORG_ADMIN'],
    'job_approval_categories': ['ORG_ADMIN'],

    # 部門/社群（ORG_ADMIN only）
    'departments': ['ORG_ADMIN'],
    'groups': ['ORG_ADMIN'],

    # 角色管控區（ORG_ADMIN only）
    'roles_control': ['ORG_ADMIN'],
    'account_roles': ['ORG_ADMIN'],
    'module_perm_mgmt': ['ORG_ADMIN'],
    'permission_central_org': ['ORG_ADMIN'],

    # 系統安全區（ORG_ADMIN only）
    'org_security': ['ORG_ADMIN'],
    'login_fail_monitor_org': ['ORG_ADMIN'],
    'org_rate_limits': ['ORG_ADMIN'],
    'alert_broadcasts_org': ['ORG_ADMIN'],

    # 規格制定模組（ORG_ADMIN + SPEC_DESIGNER）
    'spec_formulate': ['ORG_ADMIN', 'SPEC_DESIGNER'],
    'spec_formulate.spec_multifaceted': ['ORG_ADMIN', 'SPEC_DESIGNER'],

    # 無程式碼建構模組（ORG_ADMIN + SUBSYS_DESIGNER）
    'nocode_builder': ['ORG_ADMIN', 'SUBSYS_DESIGNER'],
    'nocode_builder.sub_systems': ['ORG_ADMIN', 'SUBSYS_DESIGNER'],
    'nocode_builder.lookup': ['ORG_ADMIN', 'SUBSYS_DESIGNER'],
}


def build_defaults_map(module_loader=None):
    """
    建構完整的選單預設值 map

    合併平台核心選單 (CORE_MENUS) 和模組選單定義。
    key 為 menu code，value 為該選單的所有預設屬性。

    Args:
        module_loader: ModuleLoader 實例（可選，用於載入模組選單定義）

    Returns:
        {code: {display_order, parent_code, depth, title, icon, ...}, ...}
    """
    defaults = {}

    # 平台核心選單
    for menu_def in CORE_MENUS:
        code = menu_def['code']
        # _user_types_override 允許部分選單直接指定 user_types（不走 required_level 邏輯）
        if '_user_types_override' in menu_def:
            user_types = menu_def['_user_types_override']
        else:
            user_types = get_allowed_user_types(
                menu_def['required_level'],
                menu_def.get('is_shared', False)
            )
        defaults[code] = {
            'display_order': menu_def['display_order'],
            'parent_code': menu_def.get('parent_code'),
            'depth': menu_def.get('depth', 0),
            'title': menu_def['title'],
            'icon': menu_def.get('icon'),
            'link_type': menu_def['link_type'],
            'link_target': menu_def.get('link_target'),
            'is_expanded': menu_def.get('is_expanded', False),
            'is_shared': menu_def.get('is_shared', False),
            'required_permission': menu_def.get('required_permission'),
            'user_types': user_types,
        }

    # 模組選單
    if module_loader:
        for module in module_loader.get_loaded_modules():
            if not module.menu_items:
                continue
            _flatten_module_menus(
                defaults,
                module.menu_items,
                parent_code=None,
                parent_user_types=None
            )

    return defaults


def _flatten_module_menus(defaults, menu_items, parent_code, parent_user_types):
    """遞迴展開模組選單定義到 defaults map"""
    fallback_types = parent_user_types or list(ALL_USER_TYPES)

    for menu_def in menu_items:
        code = menu_def.get('code')
        if not code:
            continue

        url = menu_def.get('url')
        link_type = 'route' if url else 'header'
        link_target = url if url else None
        user_types = menu_def.get('user_types', fallback_types)
        depth = 0 if parent_code is None else 1

        defaults[code] = {
            'display_order': menu_def.get('sort_order', 0),
            'parent_code': parent_code,
            'depth': depth,
            'title': menu_def.get('name', ''),
            'icon': menu_def.get('icon'),
            'link_type': link_type,
            'link_target': link_target,
            'is_expanded': menu_def.get('is_expanded', False),
            'is_shared': len(user_types) > 1,
            'required_permission': menu_def.get('required_permission'),
            'user_types': list(user_types),
        }

        # 遞迴處理子選單
        children = menu_def.get('children', [])
        if children:
            _flatten_module_menus(
                defaults, children,
                parent_code=code,
                parent_user_types=list(user_types)
            )
