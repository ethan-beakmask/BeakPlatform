"""OIDC claims, recalculated from current tenant data for every token use."""
import logging

from app.models import (
    MembershipRole, OrganizationalUnit, Organization, Role, UserRoleAssignment,
    UserUnitMembership,
)
from app.models.associations import AssignmentKind
from app.models.organizational_unit import UnitType


logger = logging.getLogger(__name__)


def _scribe_admin(user, org):
    if user.user_type in ('ORG_ADMIN', 'SYSTEM_ADMIN'):
        return True
    role = Role.query.filter(
        Role.org_secure_code == org.secure_code,
        Role.code == 'SCRIBE_ADMIN',
        Role.is_deleted.is_(False),
        Role.is_active.is_(True),
    ).first()
    if role is None:
        return False
    return role.secure_code in UserRoleAssignment.get_active_role_secure_codes(
        user.secure_code, kinds=AssignmentKind.HOLDING)


def _project_groups(user, org):
    root = OrganizationalUnit.query.filter(
        OrganizationalUnit.org_secure_code == org.secure_code,
        OrganizationalUnit.code == 'PROJECTS_GROUPCLASS',
        OrganizationalUnit.is_deleted.is_(False),
        OrganizationalUnit.is_active.is_(True),
    ).first()
    if root is None:
        return []

    units = OrganizationalUnit.query.filter(
        OrganizationalUnit.org_secure_code == org.secure_code,
        OrganizationalUnit.unit_type == UnitType.GROUP,
        OrganizationalUnit.is_deleted.is_(False),
        OrganizationalUnit.is_active.is_(True),
    ).all()
    by_parent = {}
    for unit in units:
        by_parent.setdefault(unit.parent_secure_code, []).append(unit)
    descendants, stack = [], list(by_parent.get(root.secure_code, []))
    while stack:
        unit = stack.pop()
        descendants.append(unit)
        stack.extend(by_parent.get(unit.secure_code, []))
    if not descendants:
        return []

    today = org.local_today()
    unit_by_sc = {unit.secure_code: unit for unit in descendants}
    memberships = UserUnitMembership.query.filter(
        UserUnitMembership.org_secure_code == org.secure_code,
        UserUnitMembership.user_secure_code == user.secure_code,
        UserUnitMembership.unit_secure_code.in_(unit_by_sc),
        UserUnitMembership.is_deleted.is_(False),
    ).all()
    memberships = [m for m in memberships
                   if (m.start_date is None or m.start_date <= today)
                   and (m.end_date is None or m.end_date >= today)]
    # 同一群組可能有多筆成員關係（例：一般成員＋團長），每個群組只出一筆，任一筆是團長／副團長即為 manager
    roles = {}
    for m in memberships:
        is_manager = m.role_type in (MembershipRole.MANAGER, MembershipRole.DEPUTY)
        roles[m.unit_secure_code] = roles.get(m.unit_secure_code, False) or is_manager
    ordered = sorted(roles, key=lambda sc: (unit_by_sc[sc].name, sc))
    if len(ordered) > 200:
        logger.warning('OIDC project_groups truncated to 200 for user %s',
                       user.secure_code)
    return [{
        'key': sc,
        'name': unit_by_sc[sc].name,
        'role': 'manager' if roles[sc] else 'member',
    } for sc in ordered[:200]]


def build_claims(user, scopes, client):
    """Return the sole canonical OIDC user-claim representation."""
    scope_set = set((scopes or '').split())
    org = Organization.query.filter(
        Organization.secure_code == user.org_secure_code,
        Organization.is_deleted.is_(False),
    ).first()
    if org is None:
        raise ValueError('organization unavailable')
    claims = {
        'sub': user.secure_code,
        'org': {'key': org.secure_code, 'name': org.name,
                'domain': org.domain_name},
        'user_type': user.user_type,
    }
    if 'profile' in scope_set:
        claims.update(name=user.display_name,
                      employee_no=user.employee_id or None)
    if 'email' in scope_set:
        claims.update(email=user.email, email_verified=True)
    if 'scribe' in (client.extra_claims or []):
        claims['scribe_admin'] = _scribe_admin(user, org)
        claims['project_groups'] = _project_groups(user, org)
    return claims
