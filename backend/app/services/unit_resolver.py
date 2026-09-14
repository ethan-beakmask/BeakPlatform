"""
使用者所屬單位、單位祖先鏈與 (角色, 單位) 持有者的唯一實作。

簽核授權（task_authorizer）、FormAdapter 的申請人單位解析（第 2 期）
與 OpHrLookup（第 4 期）都應使用本模組，避免各自重建不同規則。
"""
from datetime import date, datetime

from app.models.employee_position import EmployeePosition, PositionType
from app.models.organization import Organization
from app.models.organizational_unit import OrganizationalUnit
from app.models.role import Role
from app.models.associations import AssignmentKind, UserRoleAssignment
from app.models.user import User
from app.models.user_unit_membership import MembershipType, UserUnitMembership


def org_local_today(org_secure_code: str) -> date:
    """回傳企業當地日；企業查不到時使用平台預設 Asia/Taipei。"""
    org = Organization.query.filter_by(
        secure_code=org_secure_code,
        is_deleted=False,
    ).first()
    if org:
        return org.local_today()

    from app.utils.timezone import local_today
    return local_today('Asia/Taipei')


def org_local_now(org_secure_code: str, ref_utc: datetime | None = None) -> datetime:
    """回傳企業當地現在時間（naive）；企業查不到時使用平台預設 Asia/Taipei。"""
    org = Organization.query.filter_by(
        secure_code=org_secure_code,
        is_deleted=False,
    ).first()
    tz_name = org.get_setting('timezone', 'Asia/Taipei') if org else 'Asia/Taipei'

    from app.utils.calendar_time import utc_to_local
    return utc_to_local(tz_name, ref_utc or datetime.utcnow()).replace(tzinfo=None)


def resolve_user_unit(
    user_secure_code: str,
    org_secure_code: str,
    today: date | None = None,
) -> str | None:
    """依 SOLID membership、primary 快照、主要任職卡解析使用者所屬單位。"""
    if today is None:
        today = org_local_today(org_secure_code)

    user = User.query.filter(
        User.org_secure_code == org_secure_code,
        User.secure_code == user_secure_code,
        User.is_deleted == False,  # noqa: E712
    ).first()
    primary_unit_sc = user.primary_unit_secure_code if user else None

    memberships = UserUnitMembership.query.join(
        OrganizationalUnit,
        UserUnitMembership.unit_secure_code == OrganizationalUnit.secure_code,
    ).filter(
        UserUnitMembership.org_secure_code == org_secure_code,
        UserUnitMembership.user_secure_code == user_secure_code,
        UserUnitMembership.membership_type == MembershipType.SOLID,
        UserUnitMembership.is_deleted == False,  # noqa: E712
        (UserUnitMembership.start_date == None) | (UserUnitMembership.start_date <= today),  # noqa: E711
        (UserUnitMembership.end_date == None) | (UserUnitMembership.end_date >= today),  # noqa: E711
        OrganizationalUnit.org_secure_code == org_secure_code,
        OrganizationalUnit.is_deleted == False,  # noqa: E712
    ).all()

    if memberships:
        if primary_unit_sc:
            primary_matches = [
                m for m in memberships if m.unit_secure_code == primary_unit_sc
            ]
            if primary_matches:
                memberships = primary_matches
        memberships.sort(key=lambda m: (m.start_date is None, m.start_date or date.max, m.id))
        return memberships[0].unit_secure_code

    position = EmployeePosition.query.filter(
        EmployeePosition.org_secure_code == org_secure_code,
        EmployeePosition.user_secure_code == user_secure_code,
        EmployeePosition.position_type == PositionType.PRIMARY,
        EmployeePosition.is_active == True,  # noqa: E712
        EmployeePosition.is_deleted == False,  # noqa: E712
        EmployeePosition.effective_from <= today,
        (EmployeePosition.effective_until == None) | (EmployeePosition.effective_until >= today),  # noqa: E711
    ).order_by(
        EmployeePosition.effective_from.asc(),
        EmployeePosition.id.asc(),
    ).first()
    return position.unit_secure_code if position else None


def get_unit_ancestor_codes(unit_secure_code: str, org_secure_code: str) -> list[str]:
    """回傳 [父, 祖父, ..., 根]，遇到不存在、已刪除或循環即停止。"""
    current = OrganizationalUnit.query.filter(
        OrganizationalUnit.org_secure_code == org_secure_code,
        OrganizationalUnit.secure_code == unit_secure_code,
        OrganizationalUnit.is_deleted == False,  # noqa: E712
    ).first()
    if not current:
        return []

    ancestors = []
    visited = {current.secure_code}
    parent_sc = current.parent_secure_code
    while parent_sc and parent_sc not in visited:
        parent = OrganizationalUnit.query.filter(
            OrganizationalUnit.org_secure_code == org_secure_code,
            OrganizationalUnit.secure_code == parent_sc,
            OrganizationalUnit.is_deleted == False,  # noqa: E712
        ).first()
        if not parent:
            break
        ancestors.append(parent.secure_code)
        visited.add(parent.secure_code)
        parent_sc = parent.parent_secure_code

    return ancestors


def get_unit(unit_secure_code: str, org_secure_code: str) -> OrganizationalUnit | None:
    """取得同企業、未刪除的單位；找不到時回 None。"""
    return OrganizationalUnit.query.filter(
        OrganizationalUnit.org_secure_code == org_secure_code,
        OrganizationalUnit.secure_code == unit_secure_code,
        OrganizationalUnit.is_deleted == False,  # noqa: E712
    ).first()


def get_unit_descendant_codes(unit_secure_code: str, org_secure_code: str) -> list[str]:
    """回傳所有未刪除後代單位 secure_code（不含自己），BFS 並防循環。"""
    root = get_unit(unit_secure_code, org_secure_code)
    if not root:
        return []

    descendants = []
    visited = {root.secure_code}
    frontier = [root.secure_code]
    while frontier:
        children = OrganizationalUnit.query.filter(
            OrganizationalUnit.org_secure_code == org_secure_code,
            OrganizationalUnit.parent_secure_code.in_(frontier),
            OrganizationalUnit.is_deleted == False,  # noqa: E712
        ).order_by(
            OrganizationalUnit.id.asc(),
        ).all()
        next_frontier = []
        for child in children:
            if child.secure_code in visited:
                continue
            visited.add(child.secure_code)
            descendants.append(child.secure_code)
            next_frontier.append(child.secure_code)
        frontier = next_frontier

    return descendants


def resolve_role_holders(
    role_secure_code: str,
    org_secure_code: str,
    unit_secure_code: str | None = None,
    include_descendant_units: bool = False,
    today: date | None = None,
    unit_only: bool = False,
    kinds: tuple[str, ...] | None = AssignmentKind.HOLDING[:1],
) -> list[str]:
    """回傳當下有效持有指定 (role, unit) 的啟用使用者 secure_code。

    unit_only=True 且有指定 unit 時，只取該單位範圍，不含全企業指派。
    kinds 預設只看 regular；None 表示三種指派性質全部採計。
    """
    if today is None:
        today = org_local_today(org_secure_code)

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
    )
    if kinds is not None:
        query = query.filter(UserRoleAssignment.assignment_kind.in_(kinds))
    if unit_secure_code is not None:
        units = [unit_secure_code]
        if include_descendant_units:
            units.extend(get_unit_descendant_codes(unit_secure_code, org_secure_code))
        if unit_only:
            query = query.filter(UserRoleAssignment.unit_secure_code.in_(units))
        else:
            query = query.filter(
                (UserRoleAssignment.unit_secure_code.in_(units))
                | (UserRoleAssignment.unit_secure_code == None)  # noqa: E711
            )

    assignments = query.order_by(
        UserRoleAssignment.assigned_at.asc(),
        UserRoleAssignment.id.asc(),
    ).all()

    holders = []
    seen = set()
    for assignment in assignments:
        user_sc = assignment.user_secure_code
        if not user_sc or user_sc in seen or not assignment.is_valid_on(today):
            continue
        seen.add(user_sc)
        holders.append(user_sc)
    return holders


# PF-251 決策點 J：每站的「主管」看三個主管類角色的 regular 持有者，代表人依此優先序。
# 正副主管都持有 DEPT_HEAD（dept_membership_service._sync_head 連帶授撤），三者取聯集是為了容忍
# 尚未連帶授予 HEAD 的舊資料（BeakPlatform-VM 遷移前、權限中心直接指派的 DEPT_MANAGER）；資料一致時聯集＝HEAD。
DEPT_HEAD_ROLE_PRIORITY = ('DEPT_MANAGER', 'DEPT_DEPUTY', 'DEPT_HEAD')


def _dept_head_role_secure_codes(org_secure_code: str) -> list[str]:
    """依 DEPT_HEAD_ROLE_PRIORITY 順序回傳該企業存在的主管類角色 secure_code。"""
    roles = Role.query.filter(
        Role.org_secure_code == org_secure_code,
        Role.code.in_(DEPT_HEAD_ROLE_PRIORITY),
        Role.is_deleted == False,  # noqa: E712
    ).all()
    by_code = {role.code: role.secure_code for role in roles}
    return [by_code[code] for code in DEPT_HEAD_ROLE_PRIORITY if code in by_code]


def _ordered_head_holders(role_secure_codes, org_secure_code, unit_secure_code, today, unit_only):
    """三個主管類角色的 regular 持有者，依角色優先序再依 assigned_at 去重保序。"""
    ordered = []
    seen = set()
    for role_sc in role_secure_codes:
        for user_sc in resolve_role_holders(
            role_sc,
            org_secure_code,
            unit_secure_code,
            include_descendant_units=False,
            today=today,
            unit_only=unit_only,
        ):
            if user_sc in seen:
                continue
            seen.add(user_sc)
            ordered.append(user_sc)
    return ordered


def iter_manager_chain(
    user_secure_code: str,
    org_secure_code: str,
    today: date | None = None,
):
    """由部門推導的主管鏈（PF-251 決策點 J）。

    每站的主管＝該單位 DEPT_MANAGER／DEPT_DEPUTY／DEPT_HEAD 的 regular 持有者（代理不進核決鏈），
    代表人正主管優先、再副主管、再只持 HEAD 者；每站先取單位指派，沒有可用人選才退回全企業指派。
    """
    if today is None:
        today = org_local_today(org_secure_code)

    role_secure_codes = _dept_head_role_secure_codes(org_secure_code)
    if not role_secure_codes:
        return

    start = resolve_user_unit(user_secure_code, org_secure_code, today)
    if not start:
        return

    units = [start] + get_unit_ancestor_codes(start, org_secure_code)
    visited = {user_secure_code}
    for level, unit_sc in enumerate(units):
        unit_holders = _ordered_head_holders(role_secure_codes, org_secure_code, unit_sc, today, True)
        holder = next((sc for sc in unit_holders if sc not in visited), None)
        if holder is None:
            all_holders = _ordered_head_holders(role_secure_codes, org_secure_code, unit_sc, today, False)
            unit_set = set(unit_holders)
            holder = next(
                (sc for sc in all_holders if sc not in visited and sc not in unit_set),
                None,
            )
        if not holder:
            continue
        visited.add(holder)
        unit = get_unit(unit_sc, org_secure_code)
        yield {
            'manager_secure_code': holder,
            'unit_secure_code': unit_sc,
            'unit_name': unit.name if unit else '',
            'levels_up': level,
        }


def resolve_direct_manager(
    user_secure_code: str,
    org_secure_code: str,
    today: date | None = None,
) -> dict | None:
    """直屬主管＝主管鏈第一站；沒有就 None。"""
    return next(iter_manager_chain(user_secure_code, org_secure_code, today), None)
