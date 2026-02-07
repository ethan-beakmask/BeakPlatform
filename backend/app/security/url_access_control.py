"""
BeakPlatform URL Access Control
URL 層級存取控制

[標準 URL-01] URL 層級存取控制
1. 不能透過 URL 直接存取未授權頁面
2. URL 參數不可被猜測利用
3. 使用 secure_code 取代自增 ID

安全機制：
1. 全域認證攔截 (auth_interceptor.py)
2. 路由權限 decorator (decorators.py)
3. ResourceGateway 租戶過濾 (resource_gateway.py)
4. URL 參數驗證 (本模組)
"""
import re
import logging
from functools import wraps
from flask import abort, request, g
from flask_login import current_user

logger = logging.getLogger(__name__)


# secure_code 格式驗證
SECURE_CODE_PATTERN = re.compile(r'^[A-Za-z0-9_-]{10,32}$')


def validate_secure_code(secure_code: str) -> bool:
    """
    驗證 secure_code 格式。

    secure_code 必須是 10-32 個字元的 URL-safe 字串。
    這可以防止：
    1. SQL 注入 (只允許特定字元)
    2. 猜測攻擊 (需要足夠長度)

    Args:
        secure_code: 要驗證的識別碼

    Returns:
        True if valid, False otherwise
    """
    if not secure_code:
        return False
    return bool(SECURE_CODE_PATTERN.match(secure_code))


def require_valid_secure_code(param_name: str = 'secure_code'):
    """
    驗證 URL 中的 secure_code 參數。

    Usage:
        @app.route('/users/<secure_code>')
        @require_valid_secure_code('secure_code')
        def view_user(secure_code):
            ...

    Args:
        param_name: URL 參數名稱
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            secure_code = kwargs.get(param_name)

            if not validate_secure_code(secure_code):
                logger.warning(
                    f"Invalid secure_code format: {secure_code} "
                    f"path={request.path} user={getattr(current_user, 'id', 'anonymous')}"
                )
                abort(404)  # 返回 404 而非 400，避免洩漏資訊

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def log_access_attempt(resource_type: str, action: str):
    """
    記錄存取嘗試 (用於審計)。

    Usage:
        @app.route('/users/<secure_code>')
        @log_access_attempt('user', 'view')
        def view_user(secure_code):
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 記錄存取嘗試
            user_id = getattr(current_user, 'id', None)
            org_code = getattr(g, 'current_org_secure_code', None)

            logger.info(
                f"Access attempt: {action} {resource_type} "
                f"user_id={user_id} org={org_code} "
                f"path={request.path} method={request.method}"
            )

            return f(*args, **kwargs)

        return decorated_function

    return decorator


class URLAccessPolicy:
    """
    URL 存取政策定義。

    定義哪些 URL pattern 需要哪些權限。
    """

    # URL pattern -> required permission
    POLICIES = {
        # Admin only routes
        r'^/users/?': 'admin',
        r'^/users/.*': 'admin',
        r'^/roles/?': 'admin',
        r'^/roles/.*': 'admin',

        # System admin only routes
        r'^/organizations/?': 'system_admin',
        r'^/organizations/.*': 'system_admin',

        # Authenticated user routes
        r'^/dashboard': 'authenticated',
        r'^/profile/?': 'authenticated',
        r'^/profile/.*': 'authenticated',

        # Public routes (no restriction)
        r'^/auth/.*': 'public',
        r'^/health': 'public',
        r'^/static/.*': 'public',
    }

    @classmethod
    def get_required_permission(cls, path: str) -> str:
        """
        取得路徑所需的權限等級。

        Args:
            path: URL 路徑

        Returns:
            'public', 'authenticated', 'admin', 'system_admin'
        """
        for pattern, permission in cls.POLICIES.items():
            if re.match(pattern, path):
                return permission

        # Default: require authentication
        return 'authenticated'

    @classmethod
    def check_access(cls, path: str, user) -> bool:
        """
        檢查用戶是否有權存取該路徑。

        Args:
            path: URL 路徑
            user: 用戶物件 (current_user)

        Returns:
            True if has access, False otherwise
        """
        required = cls.get_required_permission(path)

        if required == 'public':
            return True

        if not user or not user.is_authenticated:
            return False

        if required == 'authenticated':
            return True

        if required == 'admin':
            return user.is_org_admin or user.is_system_admin

        if required == 'system_admin':
            return user.is_system_admin

        return False


def register_url_access_logger(app):
    """
    註冊 URL 存取日誌記錄器。

    在 after_request 記錄所有存取，用於安全審計。
    """

    @app.after_request
    def log_request(response):
        """記錄請求結果"""
        # 只記錄非靜態資源
        if not request.path.startswith('/static'):
            user_id = getattr(current_user, 'id', None) if current_user else None

            # 記錄失敗的存取嘗試
            if response.status_code in (401, 403, 404):
                logger.warning(
                    f"Access denied: {request.method} {request.path} "
                    f"status={response.status_code} "
                    f"user_id={user_id} ip={request.remote_addr}"
                )

        return response


def register_page_access_interceptor(app):
    """
    註冊頁面存取攔截器。

    在 before_request 中檢查動態頁面權限。
    對於未授權的訪問：
    - Web 頁面：重導向到儀表板
    - API：返回 403
    """
    from flask import redirect, url_for

    @app.before_request
    def check_page_access():
        """檢查頁面存取權限"""
        # 跳過 API 路由
        if request.path.startswith('/api/'):
            return None

        # 跳過靜態資源和認證路由
        skip_prefixes = ('/static/', '/auth/', '/health', '/favicon.ico')
        if any(request.path.startswith(p) for p in skip_prefixes):
            return None

        # 跳過未認證用戶 (會被 auth_interceptor 處理)
        if not current_user or not current_user.is_authenticated:
            return None

        # 延遲導入避免循環依賴
        from ..services.page_permission_service import PagePermissionService

        # 檢查頁面權限
        access = PagePermissionService.check_url_access(
            current_user, request.path
        )

        if access == 'denied':
            logger.warning(
                f"Page access denied: user={current_user.secure_code} "
                f"path={request.path} ip={request.remote_addr}"
            )

            # Web 頁面：重導向到儀表板
            if request.accept_mimetypes.accept_html:
                return redirect(url_for('main.dashboard'))

            # 非 HTML 請求：返回 403
            abort(403)

        # 將權限等級存入 g 供模板使用
        g.page_access = access

        return None
