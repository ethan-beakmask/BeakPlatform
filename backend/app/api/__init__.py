"""
BeakPlatform API Blueprints Registration
"""
from flask import Flask


def register_blueprints(app: Flask) -> None:
    """
    註冊所有 API Blueprints。
    按照優先順序註冊：認證 > 用戶 > 企業管理 > 業務功能
    """
    from .auth import auth_bp
    from .users import users_bp
    from .organizations import organizations_bp
    from .contracts import contracts_bp
    from .organizational_units import units_bp
    from .roles import roles_bp
    from .menu import menu_bp
    from .modules import modules_bp
    from .pages import pages_bp
    from .system_settings import api_system_settings
    from .pageir_meta import pageir_meta_bp

    # Authentication routes
    app.register_blueprint(auth_bp, url_prefix='/auth')

    # User management
    app.register_blueprint(users_bp, url_prefix='/api/users')

    # Organization management
    app.register_blueprint(organizations_bp, url_prefix='/api/organizations')

    # Conglomerate management (system admin only)
    from .conglomerates import conglomerate_bp
    app.register_blueprint(conglomerate_bp, url_prefix='/api/conglomerates')

    # Contract management
    app.register_blueprint(contracts_bp)  # already has url_prefix

    # Organizational units (departments/groups)
    app.register_blueprint(units_bp)  # already has url_prefix

    # Roles and positions
    app.register_blueprint(roles_bp)  # already has url_prefix

    # Menu management
    app.register_blueprint(menu_bp, url_prefix='/api/menu')

    # Module management (No-Code Builder)
    app.register_blueprint(modules_bp, url_prefix='/api/modules')

    # Page management
    app.register_blueprint(pages_bp, url_prefix='/api/pages')

    # Page IR designer meta
    app.register_blueprint(pageir_meta_bp)

    # System settings (system admin only)
    app.register_blueprint(api_system_settings)  # already has url_prefix

    # Duty management (department responsibility labels)
    from .duties import duties_bp
    app.register_blueprint(duties_bp)  # already has url_prefix

    # Enterprise settings (SMTP, Telegram, etc.)
    from .enterprise_settings import api_enterprise_settings
    app.register_blueprint(api_enterprise_settings)

    # Enterprise data queries (available configs for workflow designer, etc.)
    from .enterprise_data import api_enterprise_data
    app.register_blueprint(api_enterprise_data)

    # User numbering rules
    from .user_numbering import api_numbering_bp
    app.register_blueprint(api_numbering_bp, url_prefix='/api')

    # Time management (work schedules)
    from .work_schedules import api_work_schedules
    app.register_blueprint(api_work_schedules)
    from .holiday_calendars import api_holiday_calendars
    app.register_blueprint(api_holiday_calendars)

    # Calendar projection API
    from .calendar import api_calendar
    app.register_blueprint(api_calendar)

    # Transliteration (CJK to romanized)
    from .transliteration import api_transliteration
    app.register_blueprint(api_transliteration, url_prefix='/api/transliterate')

    # Code generation/validation (universal)
    from .code_service import code_bp
    app.register_blueprint(code_bp)

    # Module access control (模組使用權)
    from .module_access import module_access_bp
    app.register_blueprint(module_access_bp)

    # Lookup table management (通用選項清單)
    from .lookup import lookup_bp
    app.register_blueprint(lookup_bp)

    # Permission central management (權限中央管理)
    from .permission_central import permission_central_bp
    app.register_blueprint(permission_central_bp)

    # Access center (權限管理中心)
    from .access_center import access_center_api_bp
    app.register_blueprint(access_center_api_bp)

    # Node Grants API (流程節點企業授權)
    from .node_grants import node_grants_api_bp
    app.register_blueprint(node_grants_api_bp)  # already has url_prefix

    # Security center (本機安全)
    from .security_center import security_center_bp
    app.register_blueprint(security_center_bp)

    # API Key management (平台級 API Key 管理)
    from .api_keys import api_keys_bp
    app.register_blueprint(api_keys_bp)

    # Personal API Key management (本人 API Key 領取/重產)
    from .my_api_keys import my_api_keys_bp
    app.register_blueprint(my_api_keys_bp)

    # Personal delegation management (本人代理授權清單/建立/撤銷)
    from .my_delegations import my_delegations_bp
    app.register_blueprint(my_delegations_bp)

    # Broadcasts (廣播系統)
    from .broadcasts import broadcasts_bp
    app.register_blueprint(broadcasts_bp)

    # 資料出口政策（遮罩揭示 + 政策管理）
    from .egress import egress_bp
    app.register_blueprint(egress_bp)

    # 統一檔案管理
    from .files import files_bp
    app.register_blueprint(files_bp)

    # 內部商場
    from .store import store_bp
    app.register_blueprint(store_bp)
