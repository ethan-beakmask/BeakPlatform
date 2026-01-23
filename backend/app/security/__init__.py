"""
BeakMask Security Module
核心安全機制：認證攔截、租戶隔離、權限檢查
"""
from .decorators import public_route, login_required, admin_required, system_admin_required
from .auth_interceptor import register_auth_interceptor
from .tenant_isolation import TenantContext, get_current_tenant
from .resource_gateway import ResourceGateway

__all__ = [
    'public_route',
    'login_required',
    'admin_required',
    'system_admin_required',
    'register_auth_interceptor',
    'TenantContext',
    'get_current_tenant',
    'ResourceGateway',
]
