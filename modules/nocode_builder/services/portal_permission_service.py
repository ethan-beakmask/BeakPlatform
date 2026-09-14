"""PF-7 portal 權限碼有效權限計算服務。

本模組只讀取子系統 portal.db，依 PF-7 規則合併階級、管理角色、個人 allow，
最後以個人 deny 優先扣除，提供 access_matrix 權限碼判定核心。
"""
import logging

from flask import g, has_request_context
from sqlalchemy import text

from .data_source_manager import DataSourceManager, ensure_portal_schema

logger = logging.getLogger(__name__)


def resolve_effective_permissions(sub_system_sc: str, portal_user: dict) -> frozenset[str]:
    """Return effective permission codes for one normalized portal user."""
    if not isinstance(portal_user, dict):
        return frozenset()

    level_rank = portal_user.get('level_rank')
    if not isinstance(level_rank, int) or isinstance(level_rank, bool):
        level_rank = 0
    user_id = portal_user.get('user_id')

    cache_key = (sub_system_sc, user_id, level_rank)
    if has_request_context():
        cache = getattr(g, '_portal_effective_perms_cache', None)
        if cache is None:
            cache = {}
            g._portal_effective_perms_cache = cache
        if cache_key not in cache:
            cache[cache_key] = _load_effective_permissions(sub_system_sc, user_id, level_rank)
        return cache[cache_key]

    return _load_effective_permissions(sub_system_sc, user_id, level_rank)


def has_permission(sub_system_sc: str, portal_user: dict, code: str) -> bool:
    """Return whether the portal user has one permission code."""
    if not isinstance(code, str):
        return False
    return code in resolve_effective_permissions(sub_system_sc, portal_user)


def has_permissions(sub_system_sc: str, portal_user: dict, codes, match_mode: str = 'any') -> bool:
    """Return whether the portal user has any/all requested permission codes."""
    if (
        not isinstance(codes, (list, tuple, set))
        or not codes
        or match_mode not in {'any', 'all'}
    ):
        return False

    required = set(codes)
    perms = resolve_effective_permissions(sub_system_sc, portal_user)
    if match_mode == 'any':
        return bool(perms.intersection(required))
    return required.issubset(perms)


def _load_effective_permissions(sub_system_sc: str, user_id, level_rank: int) -> frozenset[str]:
    try:
        ensure_portal_schema(sub_system_sc)
        mgr = DataSourceManager()
        with mgr.get_session(sub_system_sc, 'portal') as sess:
            perms = set(_load_level_permissions(sess, level_rank))

            if user_id is None:
                return frozenset(perms)

            if not _is_active_user(sess, user_id):
                return frozenset()

            perms.update(_load_role_permissions(sess, user_id))
            perms.update(_load_user_allow_permissions(sess, user_id))
            perms.difference_update(_load_user_deny_permissions(sess, user_id))
            return frozenset(perms)
    except Exception:
        logger.exception(
            'Portal effective permission resolution failed: sub_system=%s user_id=%s',
            sub_system_sc,
            user_id,
        )
        return frozenset()


def _load_level_permissions(sess, level_rank: int) -> set[str]:
    rows = sess.execute(
        text(
            'SELECT DISTINCT p.code '
            'FROM portal_levels AS l '
            'JOIN portal_level_permissions AS lp ON lp.level_id = l.id '
            'JOIN portal_permissions AS p ON p.id = lp.permission_id '
            'WHERE l.is_active = :is_active '
            'AND l.rank <= :level_rank '
            'AND p.enabled = :enabled'
        ),
        {'is_active': 1, 'level_rank': level_rank, 'enabled': 1},
    ).mappings().all()
    return {row['code'] for row in rows}


def _is_active_user(sess, user_id) -> bool:
    return bool(
        sess.execute(
            text(
                'SELECT 1 FROM portal_users '
                'WHERE id = :user_id AND is_active = :is_active'
            ),
            {'user_id': user_id, 'is_active': 1},
        ).scalar()
    )


def _load_role_permissions(sess, user_id) -> set[str]:
    rows = sess.execute(
        text(
            'SELECT DISTINCT p.code '
            'FROM portal_user_roles AS ur '
            'JOIN portal_admin_roles AS r ON r.id = ur.role_id '
            'JOIN portal_role_permissions AS rp ON rp.role_id = r.id '
            'JOIN portal_permissions AS p ON p.id = rp.permission_id '
            'WHERE ur.user_id = :user_id '
            'AND r.enabled = :role_enabled '
            'AND p.enabled = :permission_enabled '
            "AND (ur.valid_from IS NULL OR ur.valid_from <= datetime('now')) "
            "AND (ur.valid_until IS NULL OR ur.valid_until > datetime('now'))"
        ),
        {'user_id': user_id, 'role_enabled': 1, 'permission_enabled': 1},
    ).mappings().all()
    return {row['code'] for row in rows}


def _load_user_allow_permissions(sess, user_id) -> set[str]:
    rows = sess.execute(
        text(
            'SELECT DISTINCT p.code '
            'FROM portal_user_permissions AS up '
            'JOIN portal_permissions AS p ON p.id = up.permission_id '
            'WHERE up.user_id = :user_id '
            'AND up.effect = :effect '
            'AND p.enabled = :enabled '
            "AND (up.valid_from IS NULL OR up.valid_from <= datetime('now')) "
            "AND (up.valid_until IS NULL OR up.valid_until > datetime('now'))"
        ),
        {'user_id': user_id, 'effect': 'allow', 'enabled': 1},
    ).mappings().all()
    return {row['code'] for row in rows}


def _load_user_deny_permissions(sess, user_id) -> set[str]:
    rows = sess.execute(
        text(
            'SELECT DISTINCT p.code '
            'FROM portal_user_permissions AS up '
            'JOIN portal_permissions AS p ON p.id = up.permission_id '
            'WHERE up.user_id = :user_id '
            'AND up.effect = :effect '
            "AND (up.valid_from IS NULL OR up.valid_from <= datetime('now')) "
            "AND (up.valid_until IS NULL OR up.valid_until > datetime('now'))"
        ),
        {'user_id': user_id, 'effect': 'deny'},
    ).mappings().all()
    return {row['code'] for row in rows}
