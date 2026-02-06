"""
BeakMask Global Authentication Interceptor
全域認證攔截器 - Deny by Default

[標準 AUTH-01] 全域認證攔截
所有請求必須經過認證檢查，除非明確列入白名單
"""
import logging
from flask import Flask, request, abort, g
from flask_login import current_user

logger = logging.getLogger(__name__)

# 公開路由白名單 - 只有這些路由不需要登入
PUBLIC_ROUTES_WHITELIST = {
    # 健康檢查
    '/health',

    # 認證相關
    '/auth/login',
    '/auth/logout',
    '/auth/forgot-password',
    '/auth/reset-password',

    # 靜態資源
    '/static/',
    '/favicon.ico',

    # 公開表單 (透過 secure_code 存取)
    '/public/form/',
}

# 公開路由前綴 - 以這些開頭的路由不需要登入
# 注意: /portal/ 已移除，改用 @public_route decorator 精確控制
PUBLIC_ROUTE_PREFIXES = (
    '/static/',
    '/public/',
    '/dev/',  # 開發工具 - 僅內網 IP 可存取 (由 internal_network_only 控制)
)


def is_public_route(endpoint: str, path: str, view_func) -> bool:
    """
    檢查路由是否為公開路由。

    判斷順序：
    1. 檢查 view function 是否有 @public_route 裝飾器
    2. 檢查路徑是否在白名單中
    3. 檢查路徑是否以公開前綴開頭
    """
    # 1. Check decorator
    if view_func and getattr(view_func, '_public_route', False):
        return True

    # 2. Check exact match in whitelist
    if path in PUBLIC_ROUTES_WHITELIST:
        return True

    # 3. Check prefix match
    if path.startswith(PUBLIC_ROUTE_PREFIXES):
        return True

    return False


def register_auth_interceptor(app: Flask) -> None:
    """
    註冊全域認證攔截器。
    必須在所有 blueprints 之前呼叫。
    """

    @app.before_request
    def global_auth_interceptor():
        """
        全域認證攔截 - Deny by Default

        每個請求都會經過這裡，除非是白名單路由，
        否則必須通過認證才能繼續。
        """
        # Get view function for this request
        view_func = app.view_functions.get(request.endpoint)

        # Check if this is a public route
        if is_public_route(request.endpoint, request.path, view_func):
            # Public route - allow without auth
            g.is_public_route = True
            return None

        # Not a public route - require authentication
        g.is_public_route = False

        if not current_user.is_authenticated:
            logger.warning(
                f"Unauthenticated access attempt: {request.method} {request.path} "
                f"from {request.remote_addr}"
            )
            abort(401, description="Authentication required")

        if not current_user.is_active:
            logger.warning(
                f"Disabled account access attempt: user_id={current_user.id} "
                f"path={request.path}"
            )
            abort(403, description="Account is disabled")

        # Set tenant context for all authenticated requests
        g.current_org_secure_code = current_user.org_secure_code
        g.current_user_id = current_user.id

        # Set locale: user preference > org setting > platform default
        g.locale = current_user.interface_language or \
            (current_user.organization.get_setting('locale', 'zh-TW')
             if current_user.organization else 'zh-TW')

        return None


def add_public_route(path: str) -> None:
    """動態添加公開路由到白名單。"""
    PUBLIC_ROUTES_WHITELIST.add(path)


def remove_public_route(path: str) -> None:
    """從白名單移除公開路由。"""
    PUBLIC_ROUTES_WHITELIST.discard(path)
