"""
BeakMask Security Decorators
統一認證裝飾器 - 所有路由必須使用

[標準 AUTH-02] 統一認證 Decorator
所有路由必須使用以下裝飾器之一：
- @public_route: 公開路由，不需登入
- @login_required: 需要登入
- @admin_required: 需要企業管理員權限
- @system_admin_required: 需要系統管理員權限
"""
from functools import wraps
from flask import abort, g, request
from flask_login import current_user


def public_route(f):
    """
    標記為公開路由，不需要登入。
    此路由會被加入白名單，跳過全域認證檢查。
    """
    f._public_route = True

    @wraps(f)
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)

    return decorated_function


def login_required(f):
    """
    需要登入的路由。
    檢查：
    1. 用戶已登入
    2. 用戶帳號未被停用
    """
    f._login_required = True

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401, description="Authentication required")

        if not current_user.is_active:
            abort(403, description="Account is disabled")

        # Set tenant context
        g.current_org_secure_code = current_user.org_secure_code

        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    """
    需要企業管理員權限的路由。
    檢查：
    1. 用戶已登入
    2. 用戶帳號未被停用
    3. 用戶具有企業管理員角色
    """
    f._admin_required = True

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401, description="Authentication required")

        if not current_user.is_active:
            abort(403, description="Account is disabled")

        if not current_user.is_org_admin:
            abort(403, description="Admin privileges required")

        # Set tenant context
        g.current_org_secure_code = current_user.org_secure_code

        return f(*args, **kwargs)

    return decorated_function


def system_admin_required(f):
    """
    需要系統管理員權限的路由。
    檢查：
    1. 用戶已登入
    2. 用戶帳號未被停用
    3. 用戶具有系統管理員角色
    """
    f._system_admin_required = True

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401, description="Authentication required")

        if not current_user.is_active:
            abort(403, description="Account is disabled")

        if not current_user.is_system_admin:
            abort(403, description="System admin privileges required")

        # System admin can access all tenants
        # But still set context for audit logging
        g.current_org_secure_code = getattr(current_user, 'org_secure_code', None)

        return f(*args, **kwargs)

    return decorated_function


def module_access_required(module_code: str, check_acl: bool = True):
    """
    模組使用權路由檢查裝飾器。

    檢查順序：
    1. 登入 + 帳號啟用
    2. 合約驗證 → 企業須有該模組的有效合約
    3. 企業管理員 → 放行（通過合約驗證後）
    4. 模組 ACL 檢查（check_acl=True 時）

    注意：SYSTEM_ADMIN 不享有特權，與其他用戶相同流程。

    Args:
        module_code: 模組代碼 (如 'form_workflow', 'nocode_builder')
        check_acl: 是否檢查模組 ACL（終端用戶頁面可設 False，僅驗合約）

    Usage:
        @module_access_required('nocode_builder')           # 合約 + ACL
        @module_access_required('form_workflow', False)      # 僅合約
    """
    def decorator(f):
        f._module_access_required = module_code

        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401, description="Authentication required")

            if not current_user.is_active:
                abort(403, description="Account is disabled")

            # [SEC-02] SYSTEM_ADMIN 不享有特權，與其他用戶相同流程
            # 已移除: 系統管理員自動放行

            # 合約驗證（所有用戶皆須通過）
            from ..services.module_access_service import ModuleAccessService
            if not ModuleAccessService.check_module_contract(current_user, module_code):
                abort(403, description=f"No contract for module: {module_code}")

            # 企業管理員放行（已通過合約驗證）
            if getattr(current_user, 'is_org_admin', False):
                g.current_org_secure_code = current_user.org_secure_code
                return f(*args, **kwargs)

            # 一般用戶: 檢查模組 ACL（若啟用）
            if check_acl:
                if not ModuleAccessService.check_user_access(current_user, module_code):
                    abort(403, description=f"No access to module: {module_code}")

            g.current_org_secure_code = current_user.org_secure_code
            return f(*args, **kwargs)

        return decorated_function

    return decorator


def permission_required(resource_type: str, action: str):
    """
    資源級權限檢查裝飾器。

    Usage:
        @permission_required('form', 'edit')
        def edit_form(form_id):
            ...

    Args:
        resource_type: 資源類型 (form, workflow, user, etc.)
        action: 操作類型 (view, create, edit, delete)
    """
    def decorator(f):
        f._permission_required = (resource_type, action)

        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401, description="Authentication required")

            if not current_user.is_active:
                abort(403, description="Account is disabled")

            # Check permission via PermissionService
            from ..services.permission_service import PermissionService

            # Get resource_id from kwargs or request
            resource_id = kwargs.get(f'{resource_type}_id') or kwargs.get('id')

            if not PermissionService.check_permission(
                user=current_user,
                resource_type=resource_type,
                action=action,
                resource_id=resource_id
            ):
                abort(403, description=f"Permission denied: {action} on {resource_type}")

            g.current_org_secure_code = current_user.org_secure_code

            return f(*args, **kwargs)

        return decorated_function

    return decorator
