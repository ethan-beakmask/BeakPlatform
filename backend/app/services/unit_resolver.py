"""
使用者所屬單位與單位祖先鏈的唯一實作。

簽核授權（task_authorizer）、FormAdapter 的申請人單位解析（第 2 期）
與 OpHrLookup（第 4 期）都應使用本模組，避免各自重建不同規則。
"""
from datetime import date

from app.models.employee_position import EmployeePosition, PositionType
from app.models.organization import Organization
from app.models.organizational_unit import OrganizationalUnit
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
