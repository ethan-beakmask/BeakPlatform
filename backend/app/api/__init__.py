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

    # Transliteration (CJK to romanized)
    from .transliteration import api_transliteration
    app.register_blueprint(api_transliteration, url_prefix='/api/transliterate')

    # Code generation/validation (universal)
    from .code_service import code_bp
    app.register_blueprint(code_bp)
