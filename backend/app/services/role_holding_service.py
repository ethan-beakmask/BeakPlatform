"""角色@單位持有判定。

本服務只處理 user_role_assignments 的 regular/proxy/standby 性質、可用性與
有效持有者解析；表單流程模型由呼叫端以 form_template_sc 值或 callable 傳入。
"""
from datetime import date, datetime

from app.models.associations import AssignmentKind, UserRoleAssignment
from app.models.role import Role, RoleType
from app.models.user import User
from app.services.unit_resolver import (
    get_unit_ancestor_codes,
    get_unit_descendant_codes,
    org_local_now,
    org_local_today,
)


_KIND_ORDER = {
    AssignmentKind.REGULAR: 0,
    AssignmentKind.PROXY: 1,
    AssignmentKind.STANDBY: 2,
}


def load_actor_assignments(user_secure_code: str, org_secure_code: str, today: date) -> list[dict]:
    """使用者在該企業今天有效的全部指派，三種性質都含。"""
    rows = UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org_secure_code,
        UserRoleAssignment.user_secure_code == user_secure_code,
        UserRoleAssignment.is_deleted == False,  # noqa: E712
    ).order_by(
        UserRoleAssignment.assigned_at.asc(),
        UserRoleAssignment.id.asc(),
    ).all()
    active = [row for row in rows if row.is_valid_on(today)]
    active.sort(key=lambda row: (
        _KIND_ORDER.get(row.assignment_kind, 99),
        row.assigned_at,
        row.id,
    ))
    return [
        {
            'role_sc': row.role_secure_code,
            'unit_sc': row.unit_secure_code or None,
            'kind': row.assignment_kind,
            'scope': row.get_allowed_form_templates(),
            'acting_for': row.acting_for_user_secure_code,
        }
        for row in active
    ]


def has_available_holder(
    role_secure_code: str,
    org_secure_code: str,
    unit_secure_code: str | None,
    *,
    today: date,
    local_now: datetime,
) -> bool:
    """R@U 此刻是否有至少一位可用的 regular/proxy 持有者。"""
    query = UserRoleAssignment.query.join(
        User,
        UserRoleAssignment.user_secure_code == User.secure_code,
    ).filter(
        UserRoleAssignment.org_secure_code == org_secure_code,
        UserRoleAssignment.role_secure_code == role_secure_code,
        UserRoleAssignment.assignment_kind.in_(AssignmentKind.HOLDING),
        UserRoleAssignment.is_deleted == False,  # noqa: E712
        User.org_secure_code == org_secure_code,
        User.is_active == True,  # noqa: E712
        User.is_deleted == False,  # noqa: E712
    )
    if unit_secure_code is not None:
        query = query.filter(
            (UserRoleAssignment.unit_secure_code == unit_secure_code)
            | (UserRoleAssignment.unit_secure_code == None)  # noqa: E711
        )

    from app.services.schedule_service import ScheduleService

    for assignment, user in query.with_entities(UserRoleAssignment, User).all():
        if assignment.is_valid_on(today) and not ScheduleService.is_on_leave(user, local_now):
            return True
    return False


def _role_type(role_secure_code: str, org_secure_code: str) -> str | None:
    role = Role.query.filter(
        Role.org_secure_code == org_secure_code,
        Role.secure_code == role_secure_code,
        Role.is_deleted == False,  # noqa: E712
    ).first()
    return role.role_type if role else None


def _assignment_matches_unit(
    assignment: UserRoleAssignment,
    target_unit_sc: str | None,
    org_secure_code: str,
    *,
    include_descendant_units: bool,
) -> bool:
    held_unit_sc = assignment.unit_secure_code or None
    if target_unit_sc is None:
        return True
    if held_unit_sc is None or held_unit_sc == target_unit_sc:
        return True
    if not include_descendant_units:
        return False
    return held_unit_sc in get_unit_descendant_codes(target_unit_sc, org_secure_code)


def effective_holders(
    role_secure_code: str,
    org_secure_code: str,
    unit_secure_code: str | None = None,
    *,
    include_descendant_units: bool = False,
    today: date | None = None,
    local_now: datetime | None = None,
) -> list[str]:
    """此刻能以 R@U 身分簽核的人。"""
    if today is None:
        today = org_local_today(org_secure_code)
    if local_now is None:
        local_now = org_local_now(org_secure_code)

    role_type = _role_type(role_secure_code, org_secure_code)
    use_descendants = include_descendant_units and role_type != RoleType.POSITION

    query = UserRoleAssignment.query.join(
        User,
        UserRoleAssignment.user_secure_code == User.secure_code,
    ).filter(
        UserRoleAssignment.org_secure_code == org_secure_code,
        UserRoleAssignment.role_secure_code == role_secure_code,
        UserRoleAssignment.is_deleted == False,  # noqa: E712
        User.org_secure_code == org_secure_code,
        User.is_active == True,  # noqa: E712
        User.is_deleted == False,  # noqa: E712
    ).order_by(
        UserRoleAssignment.assigned_at.asc(),
        UserRoleAssignment.id.asc(),
    )

    rows = [
        assignment
        for assignment in query.all()
        if assignment.is_valid_on(today)
    ]
    include_standby = not has_available_holder(
        role_secure_code,
        org_secure_code,
        unit_secure_code,
        today=today,
        local_now=local_now,
    )

    holders = []
    seen = set()
    for assignment in rows:
        kind = assignment.assignment_kind
        if kind in AssignmentKind.HOLDING:
            if not _assignment_matches_unit(
                assignment,
                unit_secure_code,
                org_secure_code,
                include_descendant_units=use_descendants,
            ):
                continue
        elif kind == AssignmentKind.STANDBY:
            if not include_standby:
                continue
            held_unit_sc = assignment.unit_secure_code or None
            if unit_secure_code is not None and held_unit_sc not in (unit_secure_code, None):
                continue
        else:
            continue

        user_sc = assignment.user_secure_code
        if user_sc in seen:
            continue
        seen.add(user_sc)
        holders.append(user_sc)
    return holders


def holds(
    assignments: list[dict],
    role_secure_code: str,
    unit_secure_code: str | None,
    *,
    is_position: bool,
    ancestors_of,
    is_available,
    form_template_sc_of,
) -> tuple[str, str | None] | None:
    """純函式，判定行為人是否持有指定 (role, unit)。"""
    for assignment in assignments:
        role_sc = assignment.get('role_sc')
        held_unit_sc = assignment.get('unit_sc')
        kind = assignment.get('kind')
        scope = assignment.get('scope')
        acting_for = assignment.get('acting_for')
        if role_sc != role_secure_code:
            continue
        if kind == AssignmentKind.STANDBY and is_available(role_secure_code, held_unit_sc):
            continue
        if scope is not None:
            form_template_sc = form_template_sc_of()
            if form_template_sc is None or form_template_sc not in scope:
                continue
        if held_unit_sc == unit_secure_code or held_unit_sc is None or unit_secure_code is None:
            return kind, acting_for
        if (
            kind != AssignmentKind.STANDBY
            and not is_position
            and unit_secure_code in ancestors_of(held_unit_sc)
        ):
            return kind, acting_for
    return None
