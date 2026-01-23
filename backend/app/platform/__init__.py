"""
BeakPlatform - Platform API for Modules
模組使用的平台接口

這個套件提供模組與平台互動的標準接口，
模組不應直接存取 app.models 或 app.services，
而應透過這些接口取得所需資料。

使用方式：
    from app.platform.auth import current_user, require_login, require_permission
    from app.platform.data import get_current_org, get_users, get_departments
"""

from .auth import (
    current_user,
    get_user_permissions,
    require_login,
    require_permission,
    require_admin,
    require_org_admin,
)

from .data import (
    get_current_org,
    get_users,
    get_user_by_code,
    get_departments,
    get_department_by_code,
    get_roles,
)

__all__ = [
    # Auth
    'current_user',
    'get_user_permissions',
    'require_login',
    'require_permission',
    'require_admin',
    'require_org_admin',
    # Data
    'get_current_org',
    'get_users',
    'get_user_by_code',
    'get_departments',
    'get_department_by_code',
    'get_roles',
]
