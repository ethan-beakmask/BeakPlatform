"""
BeakPlatform Web Routes (HTML Pages)
網頁路由 - 用於渲染 HTML 頁面

與 API 路由分離：
- /api/* -> JSON API (backend/app/api/)
- /*     -> HTML Pages (backend/app/web/)

路由層級：
- /public/*  -> 對外公開區 (無需登入)
- /portal/*  -> 系統管理員專區 (SYSTEM_ORG_CODE)
- /admin/*   -> 企業管理員專區 (各企業)
- /*         -> 一般用戶功能
"""
from flask import Flask


def register_web_blueprints(app: Flask) -> None:
    """
    註冊所有網頁路由 Blueprints。
    """
    from .main import main_bp
    from .users import users_bp
    from .roles import roles_bp
    from .organizations import organizations_bp
    from .profile import profile_bp
    from .menu import menu_web_bp
    from .modules import modules_web_bp
    from .units import units_bp
    from .public import public_bp
    from .admin import admin_bp
    from .hostconfig import hostconfig_bp
    from .job_levels import job_levels_bp
    from .job_families import job_families_bp
    from .job_titles import job_titles_bp
    from .positions import positions_bp
    from .delegations import delegations_bp
    from .sys_accounts import sys_accounts_bp
    from .departments import departments_bp
    from .groups import groups_bp, my_groups_bp
    from .numbering import numbering_bp
    from .approval_categories import approval_categories_bp
    from .org_admins import org_admins_bp
    from .org_admin_rescue import org_admin_rescue_bp
    from .external_users import external_users_bp
    from .account_roles import account_roles_bp
    from .access_center import access_center_bp
    # Main routes (dashboard, etc.)
    app.register_blueprint(main_bp)

    # Dev tools - 開發工具 (僅限內網，生產環境不包含此檔案)
    try:
        from .dev import dev_bp
        app.register_blueprint(dev_bp, url_prefix='/dev')
    except ImportError:
        pass

    # Public - 對外公開區 (無需登入)
    app.register_blueprint(public_bp, url_prefix='/public')

    # System Accounts - 系統級帳號管理 (SYSTEM_ORG_CODE)
    app.register_blueprint(sys_accounts_bp, url_prefix='/sys-accounts')

    # Admin - 企業管理員專區 (各企業)
    app.register_blueprint(admin_bp, url_prefix='/admin')

    # Org Admins - 企業管理員帳號管理
    app.register_blueprint(org_admins_bp)

    # Org Admin Rescue - 系統管理員管理企業管理員（救援）
    app.register_blueprint(org_admin_rescue_bp)

    # External Users - 外部廠商帳號管理
    app.register_blueprint(external_users_bp)

    # Account Roles Overview - 帳號角色權限表 (企業管理員)
    app.register_blueprint(account_roles_bp, url_prefix='/admin/account-roles')

    # Department settings - 部門設定 (企業管理員)
    app.register_blueprint(departments_bp, url_prefix='/admin/departments')

    # Group settings - 群組設定 (企業管理員 + 團長)
    app.register_blueprint(groups_bp, url_prefix='/admin/groups')

    # My Groups - 我的社群 (團長入口)
    app.register_blueprint(my_groups_bp, url_prefix='/my-groups')

    # Host Config - 主機設定區 (系統管理員)
    app.register_blueprint(hostconfig_bp, url_prefix='/hostconfig')

    # User management pages
    app.register_blueprint(users_bp, url_prefix='/users')

    # Role management pages
    app.register_blueprint(roles_bp, url_prefix='/roles')

    # Organization management pages
    app.register_blueprint(organizations_bp, url_prefix='/organizations')

    # Profile pages
    app.register_blueprint(profile_bp, url_prefix='/profile')

    # Menu management pages (protected by @system_admin_required)
    app.register_blueprint(menu_web_bp, url_prefix='/menu')

    # Module management pages (No-Code Builder)
    app.register_blueprint(modules_web_bp, url_prefix='/modules')

    # Organizational units pages (Departments/Groups)
    app.register_blueprint(units_bp, url_prefix='/units')

    # Job level management pages (HR Structure)
    app.register_blueprint(job_levels_bp, url_prefix='/job-levels')

    # Job family management pages (HR Structure)
    app.register_blueprint(job_families_bp, url_prefix='/job-families')

    # Job title management pages (HR Structure)
    app.register_blueprint(job_titles_bp, url_prefix='/job-titles')

    # Employee position management pages (HR Structure)
    app.register_blueprint(positions_bp, url_prefix='/positions')

    # Delegation management pages (代理授權)
    app.register_blueprint(delegations_bp, url_prefix='/delegations')

    # User numbering rules (用戶編號規則)
    app.register_blueprint(numbering_bp)

    # Approval categories (核決權限類別)
    app.register_blueprint(approval_categories_bp, url_prefix='/job-approval-categories')

    # Work schedules (時間管理 - 班表設定)
    from .work_schedules import work_schedules_bp
    app.register_blueprint(work_schedules_bp)

    # Org Database Monitor (企業獨立資料庫監視)
    from .org_databases import org_databases_bp
    app.register_blueprint(org_databases_bp)

    # Conglomerate Database Overview (集團資料庫總覽)
    from .cg_databases import cg_databases_bp
    app.register_blueprint(cg_databases_bp)

    # Permission Central Management (權限中央管理)
    from .permission_central import permission_central_bp
    app.register_blueprint(permission_central_bp, url_prefix='/permissions')

    # Access Center (權限管理中心)
    app.register_blueprint(access_center_bp, url_prefix='/access')

    # Security Center (本機安全)
    from .security_center import security_center_bp
    app.register_blueprint(security_center_bp, url_prefix='/security')

    # Platform Help (平台說明)
    from .platform_help import platform_help_bp
    app.register_blueprint(platform_help_bp, url_prefix='/help')

    # Server Manage - 主機管理 (系統管理員)
    from .server_manage import server_manage_bp
    app.register_blueprint(server_manage_bp, url_prefix='/server-manage')

    # Store - 內部商場
    from .store import store_web_bp
    app.register_blueprint(store_web_bp, url_prefix='/store')
