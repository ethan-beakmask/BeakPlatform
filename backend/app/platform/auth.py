"""
BeakPlatform - Authentication API for Modules
模組認證接口

提供模組存取當前用戶資訊和權限檢查的標準接口。
模組不應自行實作認證，而應使用這些接口。
"""
from functools import wraps
from typing import List, Optional, Set

from flask import abort, g
from flask_login import current_user as flask_current_user, login_required as flask_login_required


# Re-export current_user for convenience
current_user = flask_current_user


def get_user_permissions(user=None) -> Set[str]:
    """
    取得用戶的所有權限代碼

    Args:
        user: 用戶物件，預設為當前登入用戶

    Returns:
        權限代碼集合，如 {'form_workflow.form.create', 'form_workflow.form.view'}
    """
    if user is None:
        user = current_user

    if not user or not user.is_authenticated:
        return set()

    # 系統管理員擁有所有權限
    if user.is_system_admin:
        return {'*'}

    # 企業管理員擁有企業內所有權限
    if user.is_org_admin:
        return {'org.*'}

    # 從用戶角色取得權限
    permissions = set()

    # 透過 RolePermission 取得
    from ..models import RolePermission, UserRoleAssignment

    # 取得用戶的所有角色
    role_assignments = UserRoleAssignment.query.filter_by(
        user_secure_code=user.secure_code,
        is_deleted=False
    ).all()

    role_codes = [ra.role_secure_code for ra in role_assignments]

    if role_codes:
        role_permissions = RolePermission.query.filter(
            RolePermission.role_secure_code.in_(role_codes),
            RolePermission.is_deleted == False
        ).all()

        for rp in role_permissions:
            if rp.permission:
                permissions.add(rp.permission.code)

    return permissions


def has_permission(permission_code: str, user=None) -> bool:
    """
    檢查用戶是否有特定權限

    Args:
        permission_code: 權限代碼，如 'form_workflow.form.create'
        user: 用戶物件，預設為當前登入用戶

    Returns:
        是否有權限
    """
    permissions = get_user_permissions(user)

    # 超級權限
    if '*' in permissions:
        return True

    # 企業管理員權限（模組權限）
    if 'org.*' in permissions:
        # 企業管理員可以存取所有非系統級權限
        if not permission_code.startswith('system.'):
            return True

    # 精確匹配
    if permission_code in permissions:
        return True

    # 萬用字元匹配（如 form_workflow.* 匹配 form_workflow.form.create）
    parts = permission_code.split('.')
    for i in range(len(parts)):
        wildcard = '.'.join(parts[:i+1]) + '.*'
        if wildcard in permissions:
            return True

    return False


def require_login(f):
    """
    裝飾器：需要登入

    用法：
        @require_login
        def my_view():
            pass
    """
    return flask_login_required(f)


def require_permission(permission_code: str):
    """
    裝飾器：需要特定權限

    用法：
        @require_permission('form_workflow.form.create')
        def create_form():
            pass
    """
    def decorator(f):
        @wraps(f)
        @flask_login_required
        def decorated_function(*args, **kwargs):
            if not has_permission(permission_code):
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_any_permission(*permission_codes: str):
    """
    裝飾器：需要任一權限

    用法：
        @require_any_permission('form.view', 'form.edit')
        def view_or_edit_form():
            pass
    """
    def decorator(f):
        @wraps(f)
        @flask_login_required
        def decorated_function(*args, **kwargs):
            for code in permission_codes:
                if has_permission(code):
                    return f(*args, **kwargs)
            abort(403)
        return decorated_function
    return decorator


def require_all_permissions(*permission_codes: str):
    """
    裝飾器：需要所有權限

    用法：
        @require_all_permissions('form.view', 'form.approve')
        def approve_form():
            pass
    """
    def decorator(f):
        @wraps(f)
        @flask_login_required
        def decorated_function(*args, **kwargs):
            for code in permission_codes:
                if not has_permission(code):
                    abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_admin(f):
    """
    裝飾器：需要系統管理員

    用法：
        @require_admin
        def system_config():
            pass
    """
    @wraps(f)
    @flask_login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_system_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def require_org_admin(f):
    """
    裝飾器：需要企業管理員（或更高）

    用法：
        @require_org_admin
        def org_settings():
            pass
    """
    @wraps(f)
    @flask_login_required
    def decorated_function(*args, **kwargs):
        if not (current_user.is_system_admin or current_user.is_org_admin):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function
