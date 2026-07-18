"""Capability helpers for UI and API permission checks."""
from functools import wraps

from flask import g, has_request_context, jsonify
from flask_babel import gettext as _
from flask_login import current_user

from .permission_service import PermissionService


def _resolve_user(user=None):
    if user is not None:
        return user
    if not has_request_context():
        return None
    return current_user


def user_can(permission_code: str, user=None) -> bool:
    """Return whether the user has the given permission code."""
    resolved_user = _resolve_user(user)
    if not resolved_user or not getattr(resolved_user, 'is_authenticated', False):
        return False

    if not has_request_context():
        return PermissionService.check(resolved_user, permission_code).allowed

    cache = getattr(g, '_capability_cache', None)
    if cache is None:
        cache = {}
        g._capability_cache = cache

    key = (resolved_user.secure_code, permission_code)
    if key not in cache:
        cache[key] = PermissionService.check(
            resolved_user, permission_code).allowed
    return cache[key]


def build_caps(permission_codes: list, user=None) -> dict:
    """Build a permission-code to allowed map for the current page."""
    return {code: user_can(code, user=user) for code in permission_codes}


def permission_required(permission_code: str):
    """Require a permission code for an API endpoint."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not user_can(permission_code):
                return jsonify({
                    'success': False,
                    'error': 'permission_denied',
                    'message': _('缺少權限：%(code)s', code=permission_code),
                }), 403
            return f(*args, **kwargs)

        return decorated_function
    return decorator
