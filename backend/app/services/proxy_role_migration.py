"""PF-251 第 3a 期：DEPT_PROXY1／DEPT_PROXY2 退役遷移（決策點 K2）。

每筆未刪除的 DEPT_PROXY1／DEPT_PROXY2 指派 → 對 DEPT_HEAD／DEPT_MANAGER／DEPT_DEPUTY@同單位各確保一列 standby，
原列軟刪；該企業兩個 PROXY 角色軟刪。冪等：第二次執行時 PROXY 角色已刪、查不到指派，全部計 0。
只由 scripts/migrate_proxy_assignments.py 第五段呼叫；不 commit。
"""
from datetime import datetime

from app import db
from app.models.associations import AssignmentKind, UserRoleAssignment
from app.models.role import Role

PROXY_ROLE_CODES = ('DEPT_PROXY1', 'DEPT_PROXY2')
STANDBY_TARGET_CODES = ('DEPT_HEAD', 'DEPT_MANAGER', 'DEPT_DEPUTY')
MIGRATION_TAG = 'migration:pf251'
MIGRATION_REASON = '自代理人(一)／(二)遷移'


def _empty_counts() -> dict:
    return {
        'proxy_rows_migrated': 0,
        'proxy_rows_dropped_no_unit': 0,
        'standby_created': 0,
        'standby_revived': 0,
        'standby_skipped': 0,
        'proxy_roles_deleted': 0,
    }


def _ensure_standby(org_sc: str, user_sc: str, role_sc: str, unit_sc: str, source) -> str:
    """確保一列 standby 存在；回 created／revived／skipped。"""
    existing = UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org_sc,
        UserRoleAssignment.user_secure_code == user_sc,
        UserRoleAssignment.role_secure_code == role_sc,
        UserRoleAssignment.unit_secure_code == unit_sc,
        UserRoleAssignment.assignment_kind == AssignmentKind.STANDBY,
    ).order_by(
        UserRoleAssignment.is_deleted.asc(),
        UserRoleAssignment.id.asc(),
    ).first()
    if existing and not existing.is_deleted:
        return 'skipped'
    if existing:
        existing.is_deleted = False
        existing.deleted_at = None
        existing.valid_from = source.valid_from
        existing.valid_until = source.valid_until
        existing.source_ref = MIGRATION_TAG
        existing.grant_reason = MIGRATION_REASON
        return 'revived'
    db.session.add(UserRoleAssignment(
        org_secure_code=org_sc,
        user_secure_code=user_sc,
        role_secure_code=role_sc,
        unit_secure_code=unit_sc,
        assignment_kind=AssignmentKind.STANDBY,
        acting_for_user_secure_code=None,
        valid_from=source.valid_from,
        valid_until=source.valid_until,
        assigned_by=MIGRATION_TAG,
        source_ref=MIGRATION_TAG,
        grant_reason=MIGRATION_REASON,
    ))
    return 'created'


def migrate_org_proxy_roles(org, ctx=None) -> dict:
    """對一個企業執行 PROXY 退役遷移；回傳計數 dict。ctx 只為與腳本其他段簽名一致，未使用。"""
    org_sc = org.secure_code
    counts = _empty_counts()

    proxy_roles = Role.query.filter(
        Role.org_secure_code == org_sc,
        Role.code.in_(PROXY_ROLE_CODES),
        Role.is_deleted == False,  # noqa: E712
    ).all()
    if not proxy_roles:
        return counts

    targets = {
        role.code: role
        for role in Role.query.filter(
            Role.org_secure_code == org_sc,
            Role.code.in_(STANDBY_TARGET_CODES),
            Role.is_deleted == False,  # noqa: E712
        ).all()
    }
    missing = [code for code in STANDBY_TARGET_CODES if code not in targets]
    if missing:
        raise RuntimeError(f'企業 {org.code} 缺主管類角色 {missing}，PROXY 指派無法遷移（先跑補種段）')

    now = datetime.utcnow()
    rows = UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org_sc,
        UserRoleAssignment.role_secure_code.in_([role.secure_code for role in proxy_roles]),
        UserRoleAssignment.is_deleted == False,  # noqa: E712
    ).order_by(
        UserRoleAssignment.assigned_at.asc(),
        UserRoleAssignment.id.asc(),
    ).all()

    for row in rows:
        row.is_deleted = True
        row.deleted_at = now
        if not row.unit_secure_code:
            counts['proxy_rows_dropped_no_unit'] += 1
            continue
        for code in STANDBY_TARGET_CODES:
            outcome = _ensure_standby(
                org_sc, row.user_secure_code, targets[code].secure_code, row.unit_secure_code, row,
            )
            counts[f'standby_{outcome}'] += 1
        counts['proxy_rows_migrated'] += 1

    for role in proxy_roles:
        role.is_deleted = True
        role.deleted_at = now
        counts['proxy_roles_deleted'] += 1

    return counts
