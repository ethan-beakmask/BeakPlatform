"""
部門成員關係與部門主管角色的共用服務。

API 與 seed 腳本都從這裡維護 SOLID membership 與 DEPT_* 角色指派。
reconcile_dept_manager() 是 seed 腳本使用的冪等同步入口。
purge_unit_memberships() 是刪除單位時的唯一清理入口（PF-249）：單位一旦軟刪除，
指向它的成員關係與帶 unit_secure_code 的角色指派全部一起軟刪除，不留「角色@已刪單位」。
"""
from datetime import datetime

from app import db
from app.models import Role
from app.models.associations import AssignmentKind, UserRoleAssignment
from app.models.user import User
from app.models.user_unit_membership import (
    MembershipRole,
    MembershipType,
    UserUnitMembership,
)

# 部門系統角色：兩個成員類（ROLE）＋三個職位類（POSITION）。
# 移除成員或刪除單位時五個都要收，只收前三個會留下副主管殘留。
DEPT_MEMBER_ROLE_CODES = ('DEPT_MEMBER', 'DEPT_EMPLOYEE')
DEPT_POSITION_ROLE_CODES = ('DEPT_HEAD', 'DEPT_MANAGER', 'DEPT_DEPUTY')
DEPT_ROLE_CODES = DEPT_MEMBER_ROLE_CODES + DEPT_POSITION_ROLE_CODES


def get_system_role(org_sc: str, role_code: str) -> Role | None:
    """取得企業的系統角色 (by code)。"""
    return Role.query.filter(
        Role.org_secure_code == org_sc,
        Role.code == role_code,
        Role.is_deleted == False,  # noqa: E712
    ).first()


def ensure_role_assignment(org_sc: str, user_sc: str, role_sc: str,
                           unit_sc: str, operator: str) -> None:
    """確保角色指派存在（建立或恢復軟刪除的記錄）。"""
    existing = UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org_sc,
        UserRoleAssignment.user_secure_code == user_sc,
        UserRoleAssignment.role_secure_code == role_sc,
        UserRoleAssignment.unit_secure_code == unit_sc,
        UserRoleAssignment.assignment_kind == AssignmentKind.REGULAR,
    ).first()

    if existing:
        if existing.is_deleted:
            existing.is_deleted = False
            existing.deleted_at = None
        return

    assignment = UserRoleAssignment(
        org_secure_code=org_sc,
        user_secure_code=user_sc,
        role_secure_code=role_sc,
        unit_secure_code=unit_sc,
        assigned_by=operator,
    )
    db.session.add(assignment)


def revoke_role_assignment(org_sc: str, user_sc: str, role_sc: str,
                           unit_sc: str) -> None:
    """軟刪除指定角色指派。"""
    assignment = UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org_sc,
        UserRoleAssignment.user_secure_code == user_sc,
        UserRoleAssignment.role_secure_code == role_sc,
        UserRoleAssignment.unit_secure_code == unit_sc,
        UserRoleAssignment.assignment_kind == AssignmentKind.REGULAR,
        UserRoleAssignment.is_deleted == False,  # noqa: E712
    ).first()

    if assignment:
        assignment.is_deleted = True
        assignment.deleted_at = datetime.utcnow()


def ensure_solid_membership(user, unit) -> None:
    """確保 SOLID 部門成員關係存在（建立或恢復軟刪除的記錄）。"""
    org_sc = unit.org_secure_code
    user_sc = user.secure_code
    unit_sc = unit.secure_code

    existing = UserUnitMembership.query.filter(
        UserUnitMembership.org_secure_code == org_sc,
        UserUnitMembership.user_secure_code == user_sc,
        UserUnitMembership.unit_secure_code == unit_sc,
        UserUnitMembership.membership_type == MembershipType.SOLID,
    ).first()

    if existing:
        if existing.is_deleted:
            existing.is_deleted = False
            existing.deleted_at = None
        return

    membership = UserUnitMembership(
        org_secure_code=org_sc,
        user_secure_code=user_sc,
        unit_secure_code=unit_sc,
        membership_type=MembershipType.SOLID,
        role_type=MembershipRole.MEMBER,
    )
    db.session.add(membership)


def ensure_dept_membership(user, unit, operator: str) -> None:
    """
    確保部門成員關係與系統角色存在。

    1. 建立或恢復 UserUnitMembership(SOLID)
    2. 指派 DEPT_MEMBER (部門成員基底角色)
    3. 指派 DEPT_EMPLOYEE (部門員工，預設非管理職)
    """
    org_sc = unit.org_secure_code
    user_sc = user.secure_code
    unit_sc = unit.secure_code

    ensure_solid_membership(user, unit)

    dept_member = get_system_role(org_sc, 'DEPT_MEMBER')
    if dept_member:
        ensure_role_assignment(
            org_sc, user_sc, dept_member.secure_code, unit_sc, operator
        )

    dept_employee = get_system_role(org_sc, 'DEPT_EMPLOYEE')
    if dept_employee:
        ensure_role_assignment(
            org_sc, user_sc, dept_employee.secure_code, unit_sc, operator
        )


def remove_dept_membership(user, unit) -> None:
    """
    移除部門成員關係與所有部門角色。

    1. 軟刪除 UserUnitMembership(SOLID)
    2. 軟刪除該人在該單位下的所有角色指派（任何角色、任何性質）
    """
    org_sc = unit.org_secure_code
    user_sc = user.secure_code
    unit_sc = unit.secure_code

    membership = UserUnitMembership.query.filter(
        UserUnitMembership.org_secure_code == org_sc,
        UserUnitMembership.user_secure_code == user_sc,
        UserUnitMembership.unit_secure_code == unit_sc,
        UserUnitMembership.membership_type == MembershipType.SOLID,
        UserUnitMembership.is_deleted == False,  # noqa: E712
    ).first()

    if membership:
        membership.is_deleted = True
        membership.deleted_at = datetime.utcnow()

    now = datetime.utcnow()
    assignments = UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org_sc,
        UserRoleAssignment.user_secure_code == user_sc,
        UserRoleAssignment.unit_secure_code == unit_sc,
        UserRoleAssignment.is_deleted == False,  # noqa: E712
    ).all()
    for assignment in assignments:
        assignment.is_deleted = True
        assignment.deleted_at = now


def _unit_member_secure_codes(unit) -> set[str]:
    """單位的成員集合＝有效 SOLID membership 的人 ∪ primary_unit 指向此單位的人（未刪帳號）。"""
    org_sc = unit.org_secure_code
    unit_sc = unit.secure_code
    from_memberships = {
        row.user_secure_code
        for row in db.session.query(UserUnitMembership.user_secure_code).join(
            User, User.secure_code == UserUnitMembership.user_secure_code
        ).filter(
            UserUnitMembership.org_secure_code == org_sc,
            UserUnitMembership.unit_secure_code == unit_sc,
            UserUnitMembership.membership_type == MembershipType.SOLID,
            UserUnitMembership.is_deleted == False,  # noqa: E712
            User.is_deleted == False,  # noqa: E712
        ).all()
    }
    from_primary = {
        row.secure_code
        for row in db.session.query(User.secure_code).filter(
            User.org_secure_code == org_sc,
            User.primary_unit_secure_code == unit_sc,
            User.is_deleted == False,  # noqa: E712
        ).all()
    }
    return from_memberships | from_primary


def count_unit_members(unit) -> int:
    """單位成員數（不含子單位）。刪除單位前的「此單位有 N 個成員」守門用這個，不要只數 primary_unit。"""
    return len(_unit_member_secure_codes(unit))


def purge_unit_memberships(unit) -> dict:
    """
    刪除單位時的清理（PF-249）。不 commit，不動 unit 本身的 is_deleted。

    1. primary_unit 指向此單位的帳號改為未分配（NULL）
    2. 軟刪除指向此單位的**所有** UserUnitMembership（SOLID／DOTTED／MEMBER 都收）
    3. 軟刪除帶此 unit_secure_code 的**所有** UserRoleAssignment（不限 DEPT_*，
       GROUP_* 或任何以此單位為範圍的指派一律作廢——單位沒了，角色@它就沒有意義）

    回傳 {'members': 受影響帳號數, 'memberships': 軟刪列數, 'assignments': 軟刪列數}。
    只針對「這一個單位」；cascade 刪子單位時呼叫端逐一呼叫。
    """
    org_sc = unit.org_secure_code
    unit_sc = unit.secure_code
    now = datetime.utcnow()
    member_codes = _unit_member_secure_codes(unit)

    primary_users = User.query.filter(
        User.org_secure_code == org_sc,
        User.primary_unit_secure_code == unit_sc,
        User.is_deleted == False,  # noqa: E712
    ).all()
    for user in primary_users:
        user.primary_unit_secure_code = None

    memberships = UserUnitMembership.query.filter(
        UserUnitMembership.org_secure_code == org_sc,
        UserUnitMembership.unit_secure_code == unit_sc,
        UserUnitMembership.is_deleted == False,  # noqa: E712
    ).all()
    for membership in memberships:
        membership.is_deleted = True
        membership.deleted_at = now

    assignments = UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org_sc,
        UserRoleAssignment.unit_secure_code == unit_sc,
        UserRoleAssignment.is_deleted == False,  # noqa: E712
    ).all()
    for assignment in assignments:
        assignment.is_deleted = True
        assignment.deleted_at = now

    return {
        'members': len(member_codes),
        'memberships': len(memberships),
        'assignments': len(assignments),
    }


def _has_regular_role(org_sc: str, user_sc: str, role_code: str, unit_sc: str) -> bool:
    role = get_system_role(org_sc, role_code)
    if not role:
        return False
    return UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org_sc,
        UserRoleAssignment.user_secure_code == user_sc,
        UserRoleAssignment.role_secure_code == role.secure_code,
        UserRoleAssignment.unit_secure_code == unit_sc,
        UserRoleAssignment.assignment_kind == AssignmentKind.REGULAR,
        UserRoleAssignment.is_deleted == False,  # noqa: E712
    ).first() is not None


def _holds_manager_or_deputy(org_sc: str, user_sc: str, unit_sc: str) -> bool:
    return (
        _has_regular_role(org_sc, user_sc, 'DEPT_MANAGER', unit_sc)
        or _has_regular_role(org_sc, user_sc, 'DEPT_DEPUTY', unit_sc)
    )


def _restore_employee_if_not_leadership(org_sc: str, user_sc: str, unit_sc: str, operator: str) -> None:
    if _holds_manager_or_deputy(org_sc, user_sc, unit_sc):
        return
    dept_employee_role = get_system_role(org_sc, 'DEPT_EMPLOYEE')
    if dept_employee_role:
        ensure_role_assignment(org_sc, user_sc, dept_employee_role.secure_code, unit_sc, operator)


def _sync_head(org_sc: str, user_sc: str, unit_sc: str, operator: str) -> None:
    head_role = get_system_role(org_sc, 'DEPT_HEAD')
    if not head_role:
        return
    if _holds_manager_or_deputy(org_sc, user_sc, unit_sc):
        ensure_role_assignment(org_sc, user_sc, head_role.secure_code, unit_sc, operator)
    else:
        revoke_role_assignment(org_sc, user_sc, head_role.secure_code, unit_sc)


def set_dept_manager(user, unit, operator: str) -> None:
    """
    把 user 設為 unit 的部門主管。

    primary_unit ← unit；確保 SOLID 成員關係＋DEPT_MEMBER；既有 DEPT_MANAGER@unit
    持有者全部軟刪並改回 DEPT_EMPLOYEE@unit；新主管撤 DEPT_EMPLOYEE@unit、加
    DEPT_MANAGER@unit。不 commit。呼叫端自行負責 user_type 層界檢查。
    """
    org_sc = unit.org_secure_code
    unit_sc = unit.secure_code
    dept_manager_role = get_system_role(org_sc, 'DEPT_MANAGER')
    if not dept_manager_role:
        raise LookupError('DEPT_MANAGER')

    user.primary_unit_secure_code = unit_sc
    ensure_dept_membership(user, unit, operator)

    existing_manager_assignments = UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org_sc,
        UserRoleAssignment.role_secure_code == dept_manager_role.secure_code,
        UserRoleAssignment.unit_secure_code == unit_sc,
        UserRoleAssignment.assignment_kind == AssignmentKind.REGULAR,
        UserRoleAssignment.is_deleted == False,  # noqa: E712
    ).all()

    for assignment in existing_manager_assignments:
        assignment.is_deleted = True
        assignment.deleted_at = datetime.utcnow()
        _sync_head(org_sc, assignment.user_secure_code, unit_sc, operator)
        _restore_employee_if_not_leadership(org_sc, assignment.user_secure_code, unit_sc, operator)

    dept_employee_role = get_system_role(org_sc, 'DEPT_EMPLOYEE')
    if dept_employee_role:
        revoke_role_assignment(
            org_sc, user.secure_code,
            dept_employee_role.secure_code, unit_sc
        )

    new_assignment = UserRoleAssignment(
        org_secure_code=org_sc,
        user_secure_code=user.secure_code,
        role_secure_code=dept_manager_role.secure_code,
        unit_secure_code=unit_sc,
        assigned_by=operator,
    )
    db.session.add(new_assignment)
    _sync_head(org_sc, user.secure_code, unit_sc, operator)


def set_dept_deputy(user, unit, operator: str) -> None:
    """把 user 設為 unit 的部門副主管。"""
    org_sc = unit.org_secure_code
    unit_sc = unit.secure_code
    dept_deputy_role = get_system_role(org_sc, 'DEPT_DEPUTY')
    if not dept_deputy_role:
        raise LookupError('DEPT_DEPUTY')

    user.primary_unit_secure_code = user.primary_unit_secure_code or unit_sc
    ensure_dept_membership(user, unit, operator)

    existing_deputy_assignments = UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org_sc,
        UserRoleAssignment.role_secure_code == dept_deputy_role.secure_code,
        UserRoleAssignment.unit_secure_code == unit_sc,
        UserRoleAssignment.assignment_kind == AssignmentKind.REGULAR,
        UserRoleAssignment.is_deleted == False,  # noqa: E712
    ).all()

    for assignment in existing_deputy_assignments:
        assignment.is_deleted = True
        assignment.deleted_at = datetime.utcnow()
        _sync_head(org_sc, assignment.user_secure_code, unit_sc, operator)
        _restore_employee_if_not_leadership(org_sc, assignment.user_secure_code, unit_sc, operator)

    dept_employee_role = get_system_role(org_sc, 'DEPT_EMPLOYEE')
    if dept_employee_role:
        revoke_role_assignment(org_sc, user.secure_code, dept_employee_role.secure_code, unit_sc)

    db.session.add(UserRoleAssignment(
        org_secure_code=org_sc,
        user_secure_code=user.secure_code,
        role_secure_code=dept_deputy_role.secure_code,
        unit_secure_code=unit_sc,
        assigned_by=operator,
    ))
    _sync_head(org_sc, user.secure_code, unit_sc, operator)


def remove_dept_manager(user, unit, operator: str) -> None:
    """移除 user 在 unit 的正主管職位，不移出部門。"""
    org_sc = unit.org_secure_code
    unit_sc = unit.secure_code
    dept_manager_role = get_system_role(org_sc, 'DEPT_MANAGER')
    if not dept_manager_role:
        raise LookupError('DEPT_MANAGER')
    revoke_role_assignment(org_sc, user.secure_code, dept_manager_role.secure_code, unit_sc)
    _sync_head(org_sc, user.secure_code, unit_sc, operator)
    _restore_employee_if_not_leadership(org_sc, user.secure_code, unit_sc, operator)


def remove_dept_deputy(user, unit, operator: str) -> None:
    """移除 user 在 unit 的副主管職位，不移出部門。"""
    org_sc = unit.org_secure_code
    unit_sc = unit.secure_code
    dept_deputy_role = get_system_role(org_sc, 'DEPT_DEPUTY')
    if not dept_deputy_role:
        raise LookupError('DEPT_DEPUTY')
    revoke_role_assignment(org_sc, user.secure_code, dept_deputy_role.secure_code, unit_sc)
    _sync_head(org_sc, user.secure_code, unit_sc, operator)
    _restore_employee_if_not_leadership(org_sc, user.secure_code, unit_sc, operator)


def reconcile_dept_manager(manager, unit, operator: str) -> bool:
    """同步單位主管；已正確時只修必要狀態且回傳 False。"""
    org_sc = unit.org_secure_code
    unit_sc = unit.secure_code
    dept_manager_role = get_system_role(org_sc, 'DEPT_MANAGER')
    if not dept_manager_role:
        raise LookupError('DEPT_MANAGER')

    active_holders = {
        assignment.user_secure_code
        for assignment in UserRoleAssignment.query.filter(
            UserRoleAssignment.org_secure_code == org_sc,
            UserRoleAssignment.role_secure_code == dept_manager_role.secure_code,
            UserRoleAssignment.unit_secure_code == unit_sc,
            UserRoleAssignment.assignment_kind == AssignmentKind.REGULAR,
            UserRoleAssignment.is_deleted == False,  # noqa: E712
        ).all()
    }
    if active_holders == {manager.secure_code}:
        ensure_solid_membership(manager, unit)

        dept_member_role = get_system_role(org_sc, 'DEPT_MEMBER')
        if dept_member_role:
            ensure_role_assignment(
                org_sc,
                manager.secure_code,
                dept_member_role.secure_code,
                unit_sc,
                operator,
            )

        dept_employee_role = get_system_role(org_sc, 'DEPT_EMPLOYEE')
        if dept_employee_role:
            revoke_role_assignment(
                org_sc,
                manager.secure_code,
                dept_employee_role.secure_code,
                unit_sc,
            )
        _sync_head(org_sc, manager.secure_code, unit_sc, operator)
        return False

    set_dept_manager(manager, unit, operator)
    return True


# ==================== 部門管理層讀取／候補（PF-251 3a-1：API 檔不直接查 model） ====================

# 決策點 K2：部門頁登記的候補代理人對三個主管類角色各寫一列 standby
LEADERSHIP_STANDBY_ROLE_CODES = ('DEPT_HEAD', 'DEPT_MANAGER', 'DEPT_DEPUTY')


def user_brief(user) -> dict:
    return {
        'id': user.secure_code,
        'display_name': user.display_name,
        'native_name': user.native_name,
        'english_name': user.english_name,
        'employee_id': user.employee_id,
        'email': user.email,
    }


def load_active_user(org_sc: str, user_sc: str):
    """同企業、未刪除、啟用的帳號（DATA-01）；找不到回 None。"""
    return User.query.filter(
        User.secure_code == user_sc,
        User.org_secure_code == org_sc,
        User.is_deleted == False,  # noqa: E712
        User.is_active == True,  # noqa: E712
    ).first()


def regular_position_holder(org_sc: str, role_code: str, unit_sc: str):
    """該單位某職位角色的第一位 regular 持有者（只看單位指派，不含全企業）；回 User 或 None。"""
    from app.services.unit_resolver import resolve_role_holders

    role = get_system_role(org_sc, role_code)
    if not role:
        return None
    for user_sc in resolve_role_holders(role.secure_code, org_sc, unit_sc, unit_only=True):
        user = load_active_user(org_sc, user_sc)
        if user:
            return user
    return None


def standby_rows(org_sc: str, unit_sc: str, user_sc: str | None = None):
    """該單位三個主管角色的未刪除 standby 列（可限定某人）；回 (rows, {role_sc: code})。"""
    roles = {
        role.code: role.secure_code
        for role in Role.query.filter(
            Role.org_secure_code == org_sc,
            Role.code.in_(LEADERSHIP_STANDBY_ROLE_CODES),
            Role.is_deleted == False,  # noqa: E712
        ).all()
    }
    if not roles:
        return [], {}
    query = UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org_sc,
        UserRoleAssignment.unit_secure_code == unit_sc,
        UserRoleAssignment.role_secure_code.in_(list(roles.values())),
        UserRoleAssignment.assignment_kind == AssignmentKind.STANDBY,
        UserRoleAssignment.is_deleted == False,  # noqa: E712
    )
    if user_sc:
        query = query.filter(UserRoleAssignment.user_secure_code == user_sc)
    rows = query.order_by(UserRoleAssignment.assigned_at.asc(), UserRoleAssignment.id.asc()).all()
    return rows, {sc: code for code, sc in roles.items()}


def standby_role_codes_held(org_sc: str, unit_sc: str, user_sc: str) -> set[str]:
    """某人在該單位已持有哪些主管角色的 standby 列（部門頁登記時只補缺的那幾列，不比對錯誤訊息）。"""
    rows, code_by_sc = standby_rows(org_sc, unit_sc, user_sc)
    return {code_by_sc[row.role_secure_code] for row in rows if row.role_secure_code in code_by_sc}


def list_unit_leadership(org_sc: str, unit_sc: str) -> dict:
    """部門管理層：{'manager': brief|None, 'deputy': brief|None, 'standby': [brief + standby_roles, ...]}。"""
    manager = regular_position_holder(org_sc, 'DEPT_MANAGER', unit_sc)
    deputy = regular_position_holder(org_sc, 'DEPT_DEPUTY', unit_sc)

    rows, code_by_sc = standby_rows(org_sc, unit_sc)
    ordered = []
    by_user = {}
    for row in rows:
        entry = by_user.get(row.user_secure_code)
        if entry is None:
            user = load_active_user(org_sc, row.user_secure_code)
            if not user:
                continue
            entry = user_brief(user)
            entry['standby_roles'] = []
            by_user[row.user_secure_code] = entry
            ordered.append(entry)
        code = code_by_sc.get(row.role_secure_code)
        if code and code not in entry['standby_roles']:
            entry['standby_roles'].append(code)

    return {
        'manager': user_brief(manager) if manager else None,
        'deputy': user_brief(deputy) if deputy else None,
        'standby': ordered,
    }


def remove_unit_standby(org_sc: str, unit_sc: str, user_sc: str):
    """軟刪某人在該單位三個主管角色的 standby 列（有幾列刪幾列）。不 commit。

    回 (user, removed_count)；帳號不在本企業或已刪除時回 (None, 0)。
    """
    user = User.query.filter(
        User.secure_code == user_sc,
        User.org_secure_code == org_sc,
        User.is_deleted == False,  # noqa: E712
    ).first()
    if not user:
        return None, 0
    rows, _codes = standby_rows(org_sc, unit_sc, user_sc)
    now = datetime.utcnow()
    for row in rows:
        row.is_deleted = True
        row.deleted_at = now
    return user, len(rows)
