"""Portal page access checks for public NoCode runtime."""
import logging

from flask import g, has_request_context
from sqlalchemy import text

from ..models.site_map_node import DcSiteMapNode
from .data_source_manager import DataSourceManager, ensure_portal_schema

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


def _evaluate_rule(sub_system_sc, rule, portal_user) -> tuple[bool, str]:
    """Evaluate one portal access rule against normalized portal user data."""
    if not isinstance(rule, dict):
        return False, 'bad_matrix'

    if 'groups' not in rule:
        return False, 'bad_matrix'

    groups = rule.get('groups')
    if groups is not None:
        if not isinstance(groups, list) or not groups:
            return False, 'bad_matrix'
        group_code = portal_user.get('group_code')
        if not group_code or group_code not in groups:
            return False, 'group_denied'

    min_level = rule.get('min_level')
    if not isinstance(min_level, str):
        return False, 'bad_matrix'

    min_rank = _get_level_rank(sub_system_sc, min_level)
    if min_rank is None:
        return False, 'level_missing'

    user_rank = portal_user.get('level_rank')
    if not isinstance(user_rank, int) or isinstance(user_rank, bool):
        user_rank = 0
    if user_rank < min_rank:
        return False, 'level_denied'

    return True, 'ok'


def _get_level_rank(sub_system_sc, code):
    """Return active portal level rank by code, with per-request subsystem cache."""
    if has_request_context():
        cache = getattr(g, '_portal_level_rank_cache', None)
        if cache is None:
            cache = {}
            g._portal_level_rank_cache = cache
        levels = cache.get(sub_system_sc)
        if levels is None:
            levels = _load_level_ranks(sub_system_sc)
            cache[sub_system_sc] = levels
        return levels.get(code)

    return _load_level_ranks(sub_system_sc).get(code)


def _load_level_ranks(sub_system_sc):
    ensure_portal_schema(sub_system_sc)
    mgr = DataSourceManager()
    with mgr.get_session(sub_system_sc, 'portal') as sess:
        rows = sess.execute(
            text(
                'SELECT code, rank FROM portal_levels '
                'WHERE is_active = :is_active'
            ),
            {'is_active': 1},
        ).mappings().all()
        return {row['code']: int(row['rank']) for row in rows}
