"""
BeakMask Global Authentication Interceptor
全域認證攔截器 - Deny by Default

[標準 AUTH-01] 全域認證攔截
所有請求必須經過認證檢查，除非明確列入白名單

[標準 AUTH-03] 原始管理員強制初始設定
is_original_admin 帳號登入後，若該企業尚未建立綁定管理員，
強制導向初始設定頁面，完成後停用原始管理員。

[標準 AUTH-04] 強制變更密碼
must_change_password 帳號只能開改密頁與登出；
頁面請求導向改密頁，API 請求回 password_change_required。
"""
import logging
from flask import Flask, request, abort, g, redirect, url_for, jsonify
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

# [AUTH-03] 原始管理員強制初始設定期間允許通過的路徑。
ORIGINAL_ADMIN_SETUP_PREFIXES = (
    '/admin/initial-setup',
    '/auth/change-password',
    '/auth/logout',
    '/auth/password-policy',
    '/users/check-username',
    '/api/numbering/',
    '/api/transliterate/',
)

# [AUTH-04] 強制變更密碼期間仍可通行的路徑（PF-243）。
# 改密頁本身、登出、密碼政策查詢；靜態檔與 @public_route 在更前面已放行。
PASSWORD_CHANGE_ALLOWED_PREFIXES = (
    '/auth/change-password',
    '/auth/logout',
    '/auth/password-policy',
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

        # Set timezone: user preference > org setting > platform default
        g.timezone = current_user.timezone or \
            (current_user.organization.get_setting('timezone', 'Asia/Taipei')
             if current_user.organization else 'Asia/Taipei')

        # [AUTH-03] 原始管理員強制初始設定
        # 原始管理員登入後，若企業尚未建立綁定管理員，強制導向初始設定頁面
        # 必須在 PageRoleGuard 之前執行，否則新企業無角色設定時
        # PageRoleGuard 會因「無角色 = 擋下」而強制登出原始管理員
        if current_user.is_original_admin and current_user.is_active:
            # 允許通過的路徑: 初始設定頁面本身、變更密碼、登出、靜態資源、API
            allowed_prefixes = ORIGINAL_ADMIN_SETUP_PREFIXES
            if not request.path.startswith(allowed_prefixes):
                from ..models.user import User, UserType
                has_bound_admin = User.query.filter(
                    User.org_secure_code == current_user.org_secure_code,
                    User.user_type == UserType.ORG_ADMIN,
                    User.bound_employee_secure_code.isnot(None),
                    User.is_active == True,
                    User.is_deleted == False
                ).first() is not None

                if not has_bound_admin:
                    return redirect(url_for('org_admins.initial_setup'))

        # [AUTH-04] 強制變更密碼（PF-243）：持暫時密碼的帳號只能開改密頁與登出，
        # 頁面請求 302 到改密頁、API 請求 403 password_change_required。
        # 原始管理員走初始設定精靈時另外放行精靈所需路徑（精靈結束會停用該帳號，強迫先改密沒有意義）。
        if getattr(current_user, 'must_change_password', False):
            allowed = PASSWORD_CHANGE_ALLOWED_PREFIXES
            if getattr(current_user, 'is_original_admin', False):
                allowed = allowed + ORIGINAL_ADMIN_SETUP_PREFIXES
            if not request.path.startswith(allowed):
                change_url = url_for('auth.change_password')
                if request.is_json or request.path.startswith('/api/'):
                    return jsonify({'error': 'password_change_required', 'redirect': change_url}), 403
                return redirect(change_url)

        # [SEC-01] 網頁角色守衛 (Page Role Guard)
        # 檢查用戶是否持有存取該頁面所需的角色
        # 失敗時強制登出 + 寫稽核日誌
        from ..services.page_role_guard import PageRoleGuard
        denial = PageRoleGuard.enforce(current_user)
        if denial is not None:
            redirect_url, status_code = denial
            return redirect(redirect_url)

        return None


def add_public_route(path: str) -> None:
    """動態添加公開路由到白名單。"""
    PUBLIC_ROUTES_WHITELIST.add(path)


def remove_public_route(path: str) -> None:
    """從白名單移除公開路由。"""
    PUBLIC_ROUTES_WHITELIST.discard(path)
