"""
部門成員關係與部門主管角色的共用服務。

API 與 seed 腳本都從這裡維護 SOLID membership 與 DEPT_* 角色指派。
reconcile_dept_manager() 是 seed 腳本使用的冪等同步入口。
"""
from datetime import datetime

from app import db
from app.models import Role
from app.models.associations import UserRoleAssignment
from app.models.user_unit_membership import (
    MembershipRole,
    MembershipType,
    UserUnitMembership,
)


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
    2. 軟刪除該部門下的所有部門系統角色指派 (DEPT_MEMBER, DEPT_EMPLOYEE, DEPT_MANAGER)
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

    for role_code in ('DEPT_MEMBER', 'DEPT_EMPLOYEE', 'DEPT_MANAGER'):
        role = get_system_role(org_sc, role_code)
        if role:
            revoke_role_assignment(org_sc, user_sc, role.secure_code, unit_sc)


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

    dept_employee_role = get_system_role(org_sc, 'DEPT_EMPLOYEE')

    user.primary_unit_secure_code = unit_sc
    ensure_dept_membership(user, unit, operator)

    existing_manager_assignments = UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org_sc,
        UserRoleAssignment.role_secure_code == dept_manager_role.secure_code,
        UserRoleAssignment.unit_secure_code == unit_sc,
        UserRoleAssignment.is_deleted == False,  # noqa: E712
    ).all()

    for assignment in existing_manager_assignments:
        assignment.is_deleted = True
        assignment.deleted_at = datetime.utcnow()
        if dept_employee_role:
            ensure_role_assignment(
                org_sc, assignment.user_secure_code,
                dept_employee_role.secure_code, unit_sc,
                operator
            )

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
        return False

    set_dept_manager(manager, unit, operator)
    return True
