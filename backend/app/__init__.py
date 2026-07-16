"""
BeakMask - Security-First Multi-tenant SaaS Platform
Multi-tenant RBAC platform with dynamic module loading
"""
import os
from flask import Flask
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.wrappers import Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_session import Session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_babel import Babel

from .security.auth_interceptor import register_auth_interceptor
from .security.security_headers import register_security_headers
from .security.url_access_control import register_url_access_logger


def _rate_limit_key():
    """分層速率限制 key function。

    已認證用戶: 以 user secure_code 為限制單位 (解決 NAT 共用 IP 問題)
    未認證請求: 以來源 IP 為限制單位
    """
    from flask_login import current_user
    try:
        if current_user and current_user.is_authenticated:
            return f"user:{current_user.secure_code}"
    except Exception:
        pass
    return get_remote_address()


# Extensions
db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
session = Session()
limiter = Limiter(key_func=_rate_limit_key)
babel = Babel()


def create_app(config_name: str = None) -> Flask:
    """Application factory pattern."""
    app = Flask(__name__)

    # 關閉尾部斜線強制重導向
    # 避免 /api/users → 308 → /api/users/ 造成 CSP connect-src 'self' 阻擋
    app.url_map.strict_slashes = False

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

    # Register URL access logger (for audit)
    register_url_access_logger(app)

    # Register access logger (HTTP request log to file)
    from .security.access_logger import register_access_logger
    register_access_logger(app)

    # Register audit logger (after_request hook for DB audit logs)
    from .security.audit_logger import register_audit_logger
    register_audit_logger(app)

    # Register error handlers
    register_error_handlers(app)

    # Register template filters
    register_template_filters(app)

    # Register context processors
    register_context_processors(app)

    # Register static asset cache-busting
    register_static_cache_busting(app)

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
    @limiter.exempt
    def health_check():
        return {'status': 'healthy', 'service': 'beakplatform'}, 200

    # SEC-03: 選單權限與路由裝飾器一致性審計
    from .security.permission_audit import run_startup_audit
    run_startup_audit(app)

    # URL 前綴隔離：APP_PREFIX 環境變數控制，預設 /beakplatform
    # DispatcherMiddleware 自動設定 SCRIPT_NAME，url_for() / window.__BP / {{ app_prefix }} 自動帶前綴
    app_prefix = os.getenv('APP_PREFIX', '/beakplatform').rstrip('/')
    if app_prefix:
        def _root_fallback(environ, start_response):
            resp = Response('Not Found', status=404, content_type='text/plain')
            return resp(environ, start_response)

        app.wsgi_app = DispatcherMiddleware(_root_fallback, {app_prefix: app.wsgi_app})

    return app


def register_template_filters(app: Flask) -> None:
    """註冊 Jinja2 模板 filter"""
    from flask import g
    from datetime import datetime
    from zoneinfo import ZoneInfo

    @app.template_global('egress_visibility')
    def egress_visibility(resource, context, field):
        """單一欄位對當前用戶的能見度：clear/masked/hidden（規格見 EGRESS_POLICY_SPEC.md）"""
        from .services import egress_service
        return egress_service.field_visibility(resource, context, field)

    @app.template_global('egress_value')
    def egress_value(resource, context, record_sc, field, value):
        """
        伺服端渲染的出口欄位值。

        用法:
            {{ egress_value('user', 'detail', user.secure_code, 'mobile_phone_1', user.mobile_phone_1) }}

        masked -> 遮罩 span（真值不進 HTML，hover 由 egress-mask.js 揭示）
        hidden -> 空字串（整列隱藏請搭配 egress_visibility 判斷）
        clear  -> 逸出後的值；空值顯示「未設定」
        """
        from markupsafe import Markup, escape
        from flask_babel import gettext
        from .services import egress_service

        vis = egress_service.field_visibility(resource, context, field)
        if vis == 'hidden':
            return ''
        if vis == 'masked':
            return Markup(
                '<span class="bk-egress-mask"'
                f' data-egress-resource="{escape(resource)}"'
                f' data-egress-record="{escape(record_sc)}"'
                f' data-egress-field="{escape(field)}"'
                f' title="{escape(gettext("滑鼠停留以揭示"))}">'
                '●●●●●●</span>'
            )
        if value is None or value == '':
            return Markup(
                f'<span class="empty-value">{escape(gettext("未設定"))}</span>')
        return escape(value)

    @app.template_filter('tz_format')
    def tz_format_filter(dt, fmt='%Y-%m-%d %H:%M:%S'):
        """
        將 datetime 轉換為用戶時區後格式化。

        用法:
            {{ record.created_at|tz_format }}
            {{ record.created_at|tz_format('%Y-%m-%d') }}
        """
        if dt is None:
            return '-'
        if not isinstance(dt, datetime):
            return str(dt)
        tz_name = getattr(g, 'timezone', 'Asia/Taipei')
        try:
            target_tz = ZoneInfo(tz_name)
        except Exception:
            target_tz = ZoneInfo('Asia/Taipei')

        if dt.tzinfo is None:
            # naive datetime: DB 使用 datetime.utcnow() 儲存，視為 UTC
            dt = dt.replace(tzinfo=ZoneInfo('UTC'))
        return dt.astimezone(target_tz).strftime(fmt)


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

    # Jinja2 自訂 test：value 是否包含於序列（selectattr(..., 'contains', x) 用）
    app.jinja_env.tests['contains'] = lambda seq, value: value in (seq or ())

    @app.context_processor
    def inject_i18n():
        """將 i18n 相關資料注入到所有模板"""
        from .i18n import SUPPORTED_LANGUAGES
        return {
            'current_locale': getattr(g, 'locale', 'zh-TW'),
            'supported_languages': SUPPORTED_LANGUAGES,
        }

    @app.context_processor
    def inject_timezone():
        """將用戶時區注入到所有模板"""
        return {
            'current_timezone': getattr(g, 'timezone', 'Asia/Taipei'),
        }

    @app.context_processor
    def inject_app_prefix():
        """注入 URL 前綴（來自 SCRIPT_NAME），供模板和前端 JS 使用"""
        from flask import request as req
        return {'app_prefix': req.script_root}

    @app.context_processor
    def inject_system_org_code():
        """將系統企業識別碼注入到所有模板"""
        from .constants import SYSTEM_ORG_CODE
        return {'SYSTEM_ORG_CODE': SYSTEM_ORG_CODE}

    @app.context_processor
    def inject_broadcast_config():
        """將廣播輪詢間隔注入到所有模板"""
        from flask_login import current_user as ctx_user
        interval = 1
        if hasattr(ctx_user, 'is_authenticated') and ctx_user.is_authenticated:
            if hasattr(ctx_user, 'organization') and ctx_user.organization:
                interval = ctx_user.organization.get_setting(
                    'broadcast_poll_interval_minutes', 1
                )
        return {
            'broadcast_poll_interval_minutes': interval,
        }


def register_error_handlers(app: Flask) -> None:
    """註冊錯誤處理器"""
    from flask import render_template, request, jsonify
    from flask_wtf.csrf import CSRFError
    from app.exceptions import ResourceNotFoundError, PermissionDeniedError

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

    @app.errorhandler(PermissionDeniedError)
    def handle_permission_denied(error):
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'error': str(error)}), 403
        return render_template('errors/403.html'), 403

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

    @app.errorhandler(429)
    def ratelimit_handler(error):
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({
                'success': False,
                'error': '請求頻率過高，請稍後再試',
            }), 429
        return render_template('errors/429.html'), 429

    @app.errorhandler(500)
    def internal_error(error):
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'error': 'Internal server error'}), 500
        return render_template('errors/500.html'), 500


def register_static_cache_busting(app: Flask) -> None:
    """靜態資源 cache-busting：確保 JS/CSS 變更後瀏覽器立即載入新版。

    兩層機制：
    1. url_for('static', ...) 自動附加 ?v=<啟動時間戳> 參數
    2. 所有 /static/ 回應設定 Cache-Control: no-cache，強制條件請求（304/200）
    """
    import time
    from flask import request as req

    _boot_version = str(int(time.time()))

    @app.url_defaults
    def _static_cache_bust(endpoint, values):
        if endpoint == 'static' or (endpoint and endpoint.endswith('.static')):
            values['v'] = _boot_version

    @app.after_request
    def _static_no_cache(response):
        if req.path.startswith('/static/') and response.status_code == 200:
            ext = req.path.rsplit('.', 1)[-1].lower() if '.' in req.path else ''
            if ext in ('js', 'css'):
                response.headers['Cache-Control'] = 'no-cache, must-revalidate'
        return response
