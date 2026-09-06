"""PF-251 第 3b 期：delegations 退役遷移。

有效 delegation 只在本遷移中讀取，轉成 user_role_assignments 的 proxy 列。
不修改 delegations 原表資料；冪等靠 source_ref 去重。
"""
from datetime import datetime

from app import db
from app.models.associations import AssignmentKind, UserRoleAssignment
from app.models.menu_item import MenuItem
from app.models.permission_condition import PermissionCondition
from app.models.role import Role
from app.models.user import User
from app.services import proxy_assignment_service
from app.services.role_assignment_service import ensure_role_layer_compatible

MIGRATION_ACTOR = 'migration:pf251'
MIGRATION_REASON = '自代理授權遷移'


def _empty_counts() -> dict:
    return {
        'delegation_migrated': 0,
        'delegation_skipped_empty_scope': 0,
        'delegation_skipped_approval_limit': 0,
        'delegation_skipped_type': 0,
        'delegation_skipped_delegate_inactive': 0,
        'delegation_skipped_no_roles': 0,
        'proxy_rows_layer_skipped': 0,
        'proxy_created': 0,
        'proxy_revived': 0,
        'proxy_skipped': 0,
    }


def migrate_org_delegations(org, ctx=None) -> dict:
    """將單一企業未到期且未撤銷的 delegation 轉成 proxy 指派列；不 commit。"""
    from app.models.delegation import Delegation, DelegationStatus, DelegationType

    counts = _empty_counts()
    today = org.local_today()
    rows = Delegation.query.filter(
        Delegation.org_secure_code == org.secure_code,
        Delegation.is_deleted == False,  # noqa: E712
        Delegation.status != DelegationStatus.REVOKED,
        Delegation.effective_until >= today,
    ).order_by(Delegation.effective_from.asc(), Delegation.id.asc()).all()

    for row in rows:
        scope = None
        if row.delegation_type == DelegationType.SPECIFIC:
            allowed = row.get_allowed_form_templates()
            if not allowed:
                counts['delegation_skipped_empty_scope'] += 1
                continue
            scope = sorted(allowed)
        elif row.delegation_type == DelegationType.APPROVAL:
            if row.approval_limit is not None:
                counts['delegation_skipped_approval_limit'] += 1
                continue
        elif row.delegation_type != DelegationType.FULL:
            counts['delegation_skipped_type'] += 1
            continue

        delegate = User.query.filter(
            User.org_secure_code == org.secure_code,
            User.secure_code == row.delegate_secure_code,
            User.is_deleted == False,  # noqa: E712
            User.is_active == True,  # noqa: E712
        ).first()
        if not delegate:
            counts['delegation_skipped_delegate_inactive'] += 1
            continue

        sources = proxy_assignment_service.proxyable_regular_assignments(
            org.secure_code, row.delegator_secure_code, today)
        if not sources:
            counts['delegation_skipped_no_roles'] += 1
            continue

        touched = False
        for source in sources:
            role = Role.query.filter(
                Role.org_secure_code == org.secure_code,
                Role.secure_code == source.role_secure_code,
                Role.is_deleted == False,  # noqa: E712
            ).first()
            if not role:
                counts['proxy_rows_layer_skipped'] += 1
                continue
            try:
                ensure_role_layer_compatible(delegate, role)
            except ValueError:
                counts['proxy_rows_layer_skipped'] += 1
                continue

            outcome = _ensure_proxy(org.secure_code, row, source, scope)
            if outcome != 'skipped':
                counts[f'proxy_{outcome}'] += 1
                touched = True

        if touched:
            counts['delegation_migrated'] += 1

    return counts


def _ensure_proxy(org_sc, delegation, source, allowed_form_templates) -> str:
    source_ref = f'{MIGRATION_ACTOR}:{delegation.secure_code}'
    query = UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org_sc,
        UserRoleAssignment.user_secure_code == delegation.delegate_secure_code,
        UserRoleAssignment.role_secure_code == source.role_secure_code,
        UserRoleAssignment.assignment_kind == AssignmentKind.PROXY,
        UserRoleAssignment.acting_for_user_secure_code == delegation.delegator_secure_code,
        UserRoleAssignment.source_ref == source_ref,
    )
    if source.unit_secure_code:
        query = query.filter(UserRoleAssignment.unit_secure_code == source.unit_secure_code)
    else:
        query = query.filter(UserRoleAssignment.unit_secure_code.is_(None))
    existing = query.order_by(
        UserRoleAssignment.is_deleted.asc(),
        UserRoleAssignment.id.asc(),
    ).first()

    reason = (delegation.reason or '').strip() or MIGRATION_REASON
    if existing and not existing.is_deleted:
        return 'skipped'
    if existing:
        existing.is_deleted = False
        existing.deleted_at = None
        existing.valid_from = delegation.effective_from
        existing.valid_until = delegation.effective_until
        existing.allowed_form_templates = allowed_form_templates
        existing.grant_reason = reason
        existing.assigned_by = MIGRATION_ACTOR
        return 'revived'

    db.session.add(UserRoleAssignment(
        org_secure_code=org_sc,
        user_secure_code=delegation.delegate_secure_code,
        role_secure_code=source.role_secure_code,
        unit_secure_code=source.unit_secure_code,
        assignment_kind=AssignmentKind.PROXY,
        acting_for_user_secure_code=delegation.delegator_secure_code,
        valid_from=delegation.effective_from,
        valid_until=delegation.effective_until,
        allowed_form_templates=allowed_form_templates,
        grant_reason=reason,
        assigned_by=MIGRATION_ACTOR,
        source_ref=source_ref,
    ))
    return 'created'


def retire_delegation_globals(ctx=None) -> dict:
    """全域退役 delegation 選單與 DELEGATED 權限條件；不 commit。"""
    counts = {'menu_retired': 0, 'condition_retired': 0}
    now = datetime.utcnow()

    menus = MenuItem.query.filter(
        MenuItem.code == 'delegations',
        MenuItem.is_deleted == False,  # noqa: E712
    ).all()
    for menu in menus:
        menu.is_deleted = True
        menu.deleted_at = now
        counts['menu_retired'] += 1

    conditions = PermissionCondition.query.filter(
        PermissionCondition.code == 'DELEGATED',
        PermissionCondition.is_deleted == False,  # noqa: E712
    ).all()
    for condition in conditions:
        condition.is_deleted = True
        condition.deleted_at = now
        counts['condition_retired'] += 1

    return counts
