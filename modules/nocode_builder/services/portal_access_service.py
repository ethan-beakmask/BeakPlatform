"""Portal page access checks for public NoCode runtime."""
import logging

from ..models.site_map_node import DcSiteMapNode
from . import portal_permission_service

logger = logging.getLogger(__name__)


def check_page_access(sub_system_sc, page_layout_sc, portal_user) -> tuple[bool, str]:
    """
    Check portal page access_matrix at runtime.

    Returns:
        (allowed, reason). Reason is an English audit code, not user-facing text.
    """
    if portal_user is None:
        return False, 'no_session'

    try:
        node = DcSiteMapNode.query.filter_by(
            sub_system_secure_code=sub_system_sc,
            page_layout_secure_code=page_layout_sc,
            is_deleted=False,
            is_active=True,
        ).first()

        if not node or node.access_matrix is None:
            return True, 'no_matrix'

        matrix = node.access_matrix
        if not isinstance(matrix, dict):
            return False, 'bad_matrix'

        return _evaluate_rule(sub_system_sc, matrix.get('read'), portal_user)
    except Exception:
        logger.exception(
            'Portal page access check failed: page=%s sub_system=%s',
            page_layout_sc,
            sub_system_sc,
        )
        return False, 'error'


def check_widget_access(access_matrix, action, ctx) -> bool:
    """Check portal widget access_matrix for one action."""
    try:
        if not isinstance(ctx, dict):
            return False
        sub_system_sc = ctx.get('sub_system_sc')
        portal_user = ctx.get('portal_user')
        if not sub_system_sc or portal_user is None:
            return False
        if not isinstance(access_matrix, dict):
            return False
        if action not in access_matrix:
            return True

        allowed, _reason = _evaluate_rule(sub_system_sc, access_matrix.get(action), portal_user)
        return allowed
    except Exception:
        logger.exception(
            'Portal widget access check failed: action=%s sub_system=%s',
            action,
            ctx.get('sub_system_sc') if isinstance(ctx, dict) else None,
        )
        return False


def check_widget_write_access(access_matrix, action, ctx) -> bool:
    """Check portal widget write access_matrix with explicit opt-in semantics."""
    try:
        if action not in {'create', 'update', 'delete'}:
            return False
        if not isinstance(ctx, dict):
            return False
        sub_system_sc = ctx.get('sub_system_sc')
        portal_user = ctx.get('portal_user')
        if not sub_system_sc or portal_user is None:
            return False
        if not isinstance(access_matrix, dict):
            return False
        if action not in access_matrix:
            return False

        allowed, _reason = _evaluate_rule(sub_system_sc, access_matrix.get(action), portal_user)
        return allowed
    except Exception:
        logger.exception(
            'Portal widget write access check failed: action=%s sub_system=%s',
            action,
            ctx.get('sub_system_sc') if isinstance(ctx, dict) else None,
        )
        return False


def _evaluate_rule(sub_system_sc, rule, portal_user) -> tuple[bool, str]:
    """Evaluate one portal access rule against normalized portal user data."""
    if not isinstance(rule, dict):
        return False, 'bad_matrix'

    if not set(rule.keys()).issubset({'required_permissions', 'match_mode'}):
        return False, 'bad_matrix'

    if 'required_permissions' not in rule:
        return False, 'bad_matrix'

    perms = rule.get('required_permissions')
    if (
        not isinstance(perms, list)
        or not perms
        or any(not isinstance(code, str) for code in perms)
    ):
        return False, 'bad_matrix'
    mode = rule.get('match_mode', 'any')
    if mode not in {'any', 'all'}:
        return False, 'bad_matrix'
    if not portal_permission_service.has_permissions(sub_system_sc, portal_user, perms, mode):
        return False, 'permission_denied'

    return True, 'ok'
