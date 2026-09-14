"""Proxy assignment helpers.

代理指派只代理職務角色，不代理 user_type 對應的層界身分角色。EMPLOYEE
雙方通常都有，代理它是雜訊；ORG_ADMIN 若被代理會把管理員選單與權限整包交給代理人，
比舊 FULL delegation 的簽核語意更寬。
"""
from datetime import date

from flask_babel import gettext as _

from app import db
from app.models import Organization, Role, User
from app.models.associations import AssignmentKind, UserRoleAssignment
from app.models.organizational_unit import OrganizationalUnit

IDENTITY_ROLE_CODES = ('SYSTEM_ADMIN', 'ORG_ADMIN', 'EMPLOYEE', 'EXTERNAL_USERS')


def _org_today(org_sc: str) -> date:
    org = Organization.query.filter(
        Organization.secure_code == org_sc,
        Organization.is_deleted == False,  # noqa: E712
    ).first()
    if not org:
        raise ValueError(_('企業不存在'))
    return org.local_today()


def proxyable_regular_assignments(org_sc, user_sc, today) -> list[UserRoleAssignment]:
    """本人今天有效、可代理出去的 regular 角色指派。"""
    rows = UserRoleAssignment.query.join(
        Role,
        db.and_(
            Role.secure_code == UserRoleAssignment.role_secure_code,
            Role.org_secure_code == org_sc,
            Role.is_deleted == False,  # noqa: E712
            ~Role.code.in_(IDENTITY_ROLE_CODES),
        ),
    ).outerjoin(
        OrganizationalUnit,
        db.and_(
            OrganizationalUnit.secure_code == UserRoleAssignment.unit_secure_code,
            OrganizationalUnit.org_secure_code == org_sc,
            OrganizationalUnit.is_deleted == False,  # noqa: E712
        ),
    ).filter(
        UserRoleAssignment.org_secure_code == org_sc,
        UserRoleAssignment.user_secure_code == user_sc,
        UserRoleAssignment.assignment_kind == AssignmentKind.REGULAR,
        UserRoleAssignment.is_deleted == False,  # noqa: E712
    ).order_by(
        Role.name.asc(),
        OrganizationalUnit.name.asc().nullsfirst(),
        UserRoleAssignment.id.asc(),
    ).all()
    return [row for row in rows if row.is_valid_on(today)]


def list_proxy_assignments(org_sc, user_sc) -> dict:
    today = _org_today(org_sc)
    rows = UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org_sc,
        UserRoleAssignment.assignment_kind == AssignmentKind.PROXY,
        UserRoleAssignment.is_deleted == False,  # noqa: E712
        db.or_(
            UserRoleAssignment.acting_for_user_secure_code == user_sc,
            UserRoleAssignment.user_secure_code == user_sc,
        ),
    ).all()

    role_map = _role_map(org_sc, {row.role_secure_code for row in rows})
    unit_map = _unit_map(org_sc, {row.unit_secure_code for row in rows if row.unit_secure_code})
    counterpart_codes = set()
    for row in rows:
        if row.acting_for_user_secure_code == user_sc:
            counterpart_codes.add(row.user_secure_code)
        if row.user_secure_code == user_sc:
            counterpart_codes.add(row.acting_for_user_secure_code)
    user_map = _user_map(org_sc, counterpart_codes)

    given = []
    received = []
    for row in rows:
        if row.acting_for_user_secure_code == user_sc:
            given.append(_assignment_payload(row, role_map, unit_map, user_map.get(row.user_secure_code), today))
        if row.user_secure_code == user_sc:
            received.append(_assignment_payload(
                row, role_map, unit_map, user_map.get(row.acting_for_user_secure_code), today))

    given.sort(key=_sort_key)
    received.sort(key=_sort_key)
    return {'given': given, 'received': received, 'today': today.isoformat()}


def revoke_own_proxy(org_sc, user_sc, assignment_sc) -> dict:
    from app.services import role_assignment_service

    row = UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org_sc,
        UserRoleAssignment.secure_code == assignment_sc,
        UserRoleAssignment.assignment_kind == AssignmentKind.PROXY,
        UserRoleAssignment.is_deleted == False,  # noqa: E712
        db.or_(
            UserRoleAssignment.acting_for_user_secure_code == user_sc,
            UserRoleAssignment.user_secure_code == user_sc,
        ),
    ).first()
    if not row:
        raise LookupError(assignment_sc)
    return role_assignment_service.revoke_assignment(org_sc, assignment_sc)


def has_covering_proxy(org_sc, user_sc, start_date, end_date) -> bool:
    sources = UserRoleAssignment.query.join(
        Role,
        db.and_(
            Role.secure_code == UserRoleAssignment.role_secure_code,
            Role.org_secure_code == org_sc,
            Role.is_deleted == False,  # noqa: E712
            ~Role.code.in_(IDENTITY_ROLE_CODES),
        ),
    ).filter(
        UserRoleAssignment.org_secure_code == org_sc,
        UserRoleAssignment.user_secure_code == user_sc,
        UserRoleAssignment.assignment_kind == AssignmentKind.REGULAR,
        UserRoleAssignment.is_deleted == False,  # noqa: E712
        db.or_(UserRoleAssignment.valid_from.is_(None), UserRoleAssignment.valid_from <= end_date),
        db.or_(UserRoleAssignment.valid_until.is_(None), UserRoleAssignment.valid_until >= start_date),
    ).all()
    if not sources:
        return False

    for source in sources:
        query = UserRoleAssignment.query.filter(
            UserRoleAssignment.org_secure_code == org_sc,
            UserRoleAssignment.role_secure_code == source.role_secure_code,
            UserRoleAssignment.assignment_kind == AssignmentKind.PROXY,
            UserRoleAssignment.acting_for_user_secure_code == user_sc,
            UserRoleAssignment.is_deleted == False,  # noqa: E712
            UserRoleAssignment.valid_from <= start_date,
            UserRoleAssignment.valid_until >= end_date,
        )
        if source.unit_secure_code:
            query = query.filter(UserRoleAssignment.unit_secure_code == source.unit_secure_code)
        else:
            query = query.filter(UserRoleAssignment.unit_secure_code.is_(None))
        if not query.first():
            return False
    return True


def proxy_request_published_code(org_secure_code):
    """出廠「代理指定申請單」目前發行版本的 secure_code；查不到回 None。

    呼叫端自己組網址（url_for('form_workflow_web.center') + '?fill=' + sc），
    這裡不回路徑字串——回路徑會讓每個呼叫端都要再拆一次 query。
    """
    if not org_secure_code:
        return None
    try:
        from modules.form_workflow.models import (
            FwFormTemplate, FwFormWorkflowMapping, FwPublishedFormWorkflow,
        )
    except ImportError:
        return None

    form_tpl = FwFormTemplate.query.filter_by(
        org_secure_code=org_secure_code,
        code='PROXY_REQUEST',
        is_deleted=False,
    ).first()
    if not form_tpl:
        return None
    mapping = FwFormWorkflowMapping.query.filter_by(
        org_secure_code=org_secure_code,
        form_template_secure_code=form_tpl.secure_code,
        is_deleted=False,
    ).first()
    if not mapping:
        return None
    published = FwPublishedFormWorkflow.query.filter_by(
        org_secure_code=org_secure_code,
        source_mapping_secure_code=mapping.secure_code,
        status='Published',
        is_deleted=False,
    ).order_by(FwPublishedFormWorkflow.publish_version.desc()).first()
    if not published:
        return None
    return published.secure_code


def proxy_request_fill_url(org_secure_code):
    """出廠「代理指定申請單」填寫頁的網址（含 nginx 前綴）；查不到回 None。"""
    published_sc = proxy_request_published_code(org_secure_code)
    if not published_sc:
        return None

    from flask import current_app, request, url_for

    if 'form_workflow_web.center' in current_app.view_functions:
        base = url_for('form_workflow_web.center')
    else:
        # 模組 blueprint 只註冊在進程內第一個 app（測試會建多個），沒註冊時
        # url_for 會拋 BuildError。手動補 script_root 是等價結果，仍帶得到
        # nginx 的 /beakplatform 前綴（FRONT-10）。
        base = (request.script_root or '') + '/forms/center'
    return base + '?fill=' + published_sc


def _assignment_payload(row, role_map, unit_map, counterpart, today) -> dict:
    role = role_map.get(row.role_secure_code)
    return {
        'assignment_secure_code': row.secure_code,
        'role_secure_code': row.role_secure_code,
        'role_name': role.name if role else row.role_secure_code,
        'role_code': role.code if role else '',
        'unit_secure_code': row.unit_secure_code,
        'unit_name': unit_map.get(row.unit_secure_code, ''),
        'counterpart': {
            'secure_code': counterpart.secure_code if counterpart else '',
            'display_name': _display_name(counterpart) if counterpart else '',
        },
        'valid_from': row.valid_from.isoformat() if row.valid_from else None,
        'valid_until': row.valid_until.isoformat() if row.valid_until else None,
        'status': _status(row, today),
        'grant_reason': row.grant_reason or '',
        'allowed_form_templates_count': (
            len(row.allowed_form_templates) if isinstance(row.allowed_form_templates, list) else 0
        ),
        'source_ref': row.source_ref or '',
        'can_revoke': True,
    }


def _status(row, today) -> str:
    if row.valid_from and today < row.valid_from:
        return 'PENDING'
    if row.valid_until and today > row.valid_until:
        return 'EXPIRED'
    return 'ACTIVE'


def _sort_key(item):
    status_order = {'ACTIVE': 0, 'PENDING': 1, 'EXPIRED': 2}
    return (
        status_order.get(item.get('status'), 99),
        item.get('valid_from') or '',
        item.get('role_name') or '',
    )


def _role_map(org_sc, role_scs) -> dict:
    if not role_scs:
        return {}
    roles = Role.query.filter(
        Role.org_secure_code == org_sc,
        Role.secure_code.in_(role_scs),
        Role.is_deleted == False,  # noqa: E712
    ).all()
    return {role.secure_code: role for role in roles}


def _unit_map(org_sc, unit_scs) -> dict:
    if not unit_scs:
        return {}
    units = OrganizationalUnit.query.filter(
        OrganizationalUnit.org_secure_code == org_sc,
        OrganizationalUnit.secure_code.in_(unit_scs),
        OrganizationalUnit.is_deleted == False,  # noqa: E712
    ).all()
    return {unit.secure_code: unit.name for unit in units}


def _user_map(org_sc, user_scs) -> dict:
    if not user_scs:
        return {}
    users = User.query.filter(
        User.org_secure_code == org_sc,
        User.secure_code.in_(user_scs),
        User.is_deleted == False,  # noqa: E712
    ).all()
    return {user.secure_code: user for user in users}


def _display_name(user) -> str:
    return user.display_name or user.username or user.secure_code
