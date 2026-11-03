"""OIDC claims, recalculated from current tenant data for every token use."""
import logging

from app.models import (
    MembershipRole, OrganizationalUnit, Organization, Role, UserRoleAssignment,
    UserUnitMembership,
)
from app.models.associations import AssignmentKind
from app.models.organizational_unit import UnitType


logger = logging.getLogger(__name__)


def _employee_no(user):
    # 契約 6.6：廠商帳號的 employee_no 恆為 null（平台給廠商的臨時編號不對外）
    if user.user_type == 'EXTERNAL':
        return None
    return user.employee_id or None


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


def oidc_group_tree(org) -> dict[str, str]:
    """Active GROUP descendants of the two system roots, excluding the roots."""
    units = OrganizationalUnit.query.filter(
        OrganizationalUnit.org_secure_code == org.secure_code,
        OrganizationalUnit.unit_type == UnitType.GROUP,
        OrganizationalUnit.is_deleted.is_(False),
        OrganizationalUnit.is_active.is_(True),
    ).all()
    by_parent = {}
    for unit in units:
        by_parent.setdefault(unit.parent_secure_code, []).append(unit)
    roots = {u.secure_code: ('project' if u.code == 'PROJECTS_GROUPCLASS' else 'vendor')
             for u in units if u.code in ('PROJECTS_GROUPCLASS', 'EXTERNAL_VENDORS')}
    tree = {}
    for root_sc, kind in roots.items():
        visited = set(roots)
        stack = list(by_parent.get(root_sc, []))
        while stack:
            unit = stack.pop()
            if unit.secure_code in visited:
                continue
            visited.add(unit.secure_code)
            tree[unit.secure_code] = kind
            stack.extend(by_parent.get(unit.secure_code, []))
    return tree


def oidc_unit_tree(org, unit) -> str | None:
    return oidc_group_tree(org).get(unit.secure_code)


def effective_memberships(org, unit_scs, user_sc=None) -> list[UserUnitMembership]:
    from sqlalchemy import or_
    from app.models import User

    today = org.local_today()
    query = UserUnitMembership.query.join(
        User, User.secure_code == UserUnitMembership.user_secure_code).filter(
        UserUnitMembership.org_secure_code == org.secure_code,
        UserUnitMembership.unit_secure_code.in_(unit_scs),
        UserUnitMembership.is_deleted.is_(False),
        User.org_secure_code == org.secure_code,
        User.is_active.is_(True), User.is_deleted.is_(False),
        or_(UserUnitMembership.start_date.is_(None), UserUnitMembership.start_date <= today),
        or_(UserUnitMembership.end_date.is_(None), UserUnitMembership.end_date >= today),
    )
    if user_sc is not None:
        query = query.filter(UserUnitMembership.user_secure_code == user_sc)
    return query.all()


def _project_groups(user, org):
    tree = oidc_group_tree(org)
    memberships = effective_memberships(org, list(tree), user.secure_code)
    roles = {}
    for m in memberships:
        manager = m.role_type in (MembershipRole.MANAGER, MembershipRole.DEPUTY)
        roles[m.unit_secure_code] = roles.get(m.unit_secure_code, False) or manager
    units = {u.secure_code: u for u in OrganizationalUnit.query.filter(
        OrganizationalUnit.org_secure_code == org.secure_code,
        OrganizationalUnit.secure_code.in_(roles)).all()}
    ordered = sorted(roles, key=lambda sc: (units[sc].name, sc))
    if len(ordered) > 200:
        logger.warning('OIDC project_groups truncated to 200 for user %s', user.secure_code)
    return [{'key': sc, 'name': units[sc].name,
             'role': 'manager' if roles[sc] else 'member', 'tree': tree[sc]}
            for sc in ordered[:200]]


def group_members(client, org, unit) -> list[dict]:
    from app.services.oidc_server import user_type_allowed

    members = {}
    for membership in effective_memberships(org, [unit.secure_code]):
        user = membership.user
        if not user_type_allowed(client, user):
            continue
        manager = membership.role_type in (MembershipRole.MANAGER, MembershipRole.DEPUTY)
        if user.secure_code not in members:
            members[user.secure_code] = {
                'sub': user.secure_code, 'name': user.display_name,
                'email': user.email, 'employee_no': _employee_no(user),
                'role': 'member', 'user_type': user.user_type}
        if manager:
            members[user.secure_code]['role'] = 'manager'
    ordered = sorted(members.values(), key=lambda m: (m['name'], m['sub']))
    if len(ordered) > 200:
        logger.warning('OIDC group members truncated to 200 for group %s', unit.secure_code)
    return ordered[:200]


def authorized_member_group(client, group_sc):
    """Resolve only within the authenticated client's explicit organization grants.

    Protocol authentication is client based; no browser-user ResourceGateway scope.
    """
    from app.models import OidcClientOrg

    if not client.is_active or client.is_deleted:
        return None
    row = OrganizationalUnit.query.join(
        Organization, Organization.secure_code == OrganizationalUnit.org_secure_code
    ).join(OidcClientOrg, OidcClientOrg.org_secure_code == Organization.secure_code).filter(
        OidcClientOrg.client_secure_code == client.secure_code,
        OrganizationalUnit.org_secure_code == OidcClientOrg.org_secure_code,
        OrganizationalUnit.secure_code == group_sc,
        OrganizationalUnit.is_deleted.is_(False), OrganizationalUnit.is_active.is_(True),
        OrganizationalUnit.unit_type == UnitType.GROUP,
        Organization.is_deleted.is_(False), Organization.is_active.is_(True),
    ).with_entities(OrganizationalUnit, Organization).first()
    if row is None:
        return None
    unit, org = row
    tree = oidc_unit_tree(org, unit)
    return (unit, org, tree) if tree else None


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
        claims.update(name=user.display_name, employee_no=_employee_no(user))
    if 'email' in scope_set:
        claims.update(email=user.email, email_verified=True)
    if 'scribe' in (client.extra_claims or []):
        claims['scribe_admin'] = _scribe_admin(user, org)
        from app.services.oidc_server import user_type_allowed
        claims['project_groups'] = (_project_groups(user, org)
                                    if user_type_allowed(client, user) else [])
    return claims
