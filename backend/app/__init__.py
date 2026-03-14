"""
BeakMask - Security-First Multi-tenant SaaS Platform
"""
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_session import Session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_babel import Babel

from .security.auth_interceptor import register_auth_interceptor
from .security.security_headers import register_security_headers
from .security.url_access_control import register_page_access_interceptor, register_url_access_logger

# Extensions
db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
session = Session()
limiter = Limiter(key_func=get_remote_address)
babel = Babel()


def create_app(config_name: str = None) -> Flask:
    """Application factory pattern."""
    app = Flask(__name__)

    # Load configuration
    config_name = config_name or os.getenv('FLASK_ENV', 'production')
    app.config.from_object(f'app.config.{config_name.capitalize()}Config')

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    session.init_app(app)
    limiter.init_app(app)

    # Initialize Babel for i18n
    from .i18n import get_locale
    babel.init_app(app, locale_selector=get_locale)

    # Security: Configure login manager
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.session_protection = 'strong'

    # Register security interceptors (MUST be before blueprints)
    register_auth_interceptor(app)
    register_security_headers(app)

    # Register API blueprints
    from .api import register_blueprints
    register_blueprints(app)

    # Register Web blueprints (HTML pages)
    from .web import register_web_blueprints
    register_web_blueprints(app)

    # Register page access interceptor (after blueprints)
    register_page_access_interceptor(app)

    # Register URL access logger (for audit)
    register_url_access_logger(app)

    # Register audit logger (after_request hook for DB audit logs)
    from .security.audit_logger import register_audit_logger
    register_audit_logger(app)

    # Register error handlers
    register_error_handlers(app)

    # Register context processors
    register_context_processors(app)

    # Load modules (after blueprints and before returning)
    from .module_loader import init_module_loader
    init_module_loader(app)

    # Register CLI commands
    from .cli import register_cli
    register_cli(app)

    # Health check endpoint (public)
    from .security.decorators import public_route

    @app.route('/health')
    @public_route
    def health_check():
        return {'status': 'healthy', 'service': 'beakplatform'}, 200

    return app


def register_context_processors(app: Flask) -> None:
    """註冊模板 context processors"""
    from flask import g
    from flask_login import current_user

    @app.context_processor
    def inject_menu():
        """將選單資料注入到所有模板"""
        if current_user and current_user.is_authenticated:
            from .services.menu_service import MenuService
            try:
                menu_tree = MenuService.get_user_menu_tree(current_user, layout='navbar')
                return {'nav_menu': menu_tree}
            except Exception:
                return {'nav_menu': []}
        return {'nav_menu': []}

    @app.context_processor
    def inject_menu_helpers():
        """注入選單顏色 helper 函式"""
        def _menu_color_class(item):
            """根據 bg_level + is_cross_level 產生 CSS class (依 CSV 權限顏色表)"""
            level = item.get('bg_level', '') if isinstance(item, dict) else ''
            cross = item.get('is_cross_level', False) if isinstance(item, dict) else False
            if level == 'common':
                return 'menu-common'
            elif level == 'system':
                return 'menu-sys-cross' if cross else 'menu-sys-only'
            elif level == 'admin':
                return 'menu-org-cross' if cross else 'menu-org-only'
            elif level == 'user':
                return 'menu-user-cross' if cross else 'menu-user-only'
            elif level == 'external':
                return 'menu-ext-only'
            return ''
        return {'_menu_color_class': _menu_color_class}

    @app.context_processor
    def inject_menu_colors():
        """注入選單配色 CSS 變數覆蓋"""
        if current_user and current_user.is_authenticated:
            from .models.system_setting import SystemSetting
            try:
                saved = SystemSetting.get('menu_colors', default=None)
                if saved and isinstance(saved, dict):
                    return {'menu_color_overrides': saved}
            except Exception:
                pass
        return {'menu_color_overrides': None}

    @app.context_processor
    def inject_i18n():
        """將 i18n 相關資料注入到所有模板"""
        from .i18n import SUPPORTED_LANGUAGES
        return {
            'current_locale': getattr(g, 'locale', 'zh-TW'),
            'supported_languages': SUPPORTED_LANGUAGES,
        }


def register_error_handlers(app: Flask) -> None:
    """註冊錯誤處理器"""
    from flask import render_template, request, jsonify
    from flask_wtf.csrf import CSRFError
    from app.exceptions import ResourceNotFoundError

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': f'CSRF 驗證失敗: {error.description}'}), 400
        return render_template('errors/400.html'), 400

    @app.errorhandler(400)
    def bad_request(error):
        if request.is_json or request.path.startswith('/api/'):
            desc = getattr(error, 'description', 'Bad request')
            return jsonify({'success': False, 'error': str(desc)}), 400
        return render_template('errors/400.html'), 400

    @app.errorhandler(ResourceNotFoundError)
    def handle_resource_not_found(error):
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'error': str(error)}), 404
        return render_template('errors/404.html'), 404

    @app.errorhandler(401)
    def unauthorized(error):
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'error': 'Unauthorized'}), 401
        return render_template('errors/401.html'), 401

    @app.errorhandler(403)
    def forbidden(error):
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'error': 'Forbidden'}), 403
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found(error):
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'error': 'Not found'}), 404
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'error': 'Internal server error'}), 500
        return render_template('errors/500.html'), 500
