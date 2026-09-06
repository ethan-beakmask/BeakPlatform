from datetime import date

from app import db
from app.models import AssignmentKind, Organization, OrganizationalUnit, Role, RoleType, ScopeType, UnitType, User, UserRoleAssignment, UserType


def _login_user_directly(client, user, org):
    with client.session_transaction() as sess:
        sess['_user_id'] = user.get_id()
        sess['_fresh'] = True
        sess['org_secure_code'] = org.secure_code
        sess['org_domain'] = org.domain_name


def _user(sc, org, username, name, user_type=UserType.EMPLOYEE, **overrides):
    user = User(
        secure_code=sc,
        org_secure_code=org.secure_code,
        username=username,
        email=f'{username}@example.com',
        display_name=name,
        user_type=user_type,
        is_active=overrides.pop('is_active', True),
        is_deleted=overrides.pop('is_deleted', False),
        is_service_account=overrides.pop('is_service_account', False),
        employee_id=overrides.pop('employee_id', None),
        **overrides,
    )
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()
    return user


def _org(sc='other_org_000000001', code='OTHER'):
    org = Organization(
        secure_code=sc,
        code=code,
        name=f'{code} Organization',
        domain_name=f'{code.lower()}.local',
        is_active=True,
        is_deleted=False,
    )
    db.session.add(org)
    db.session.commit()
    return org


def _role(org, code, name=None, scope_type=ScopeType.DEPARTMENT):
    role = Role(
        org_secure_code=org.secure_code,
        code=code,
        name=name or code,
        role_type=RoleType.POSITION if code.startswith('DEPT_') else RoleType.ROLE,
        scope_type=scope_type,
        is_active=True,
        is_deleted=False,
    )
    db.session.add(role)
    db.session.commit()
    return role


def _unit(org, sc='mpa_unit_000000000001'):
    unit = OrganizationalUnit(
        secure_code=sc,
        org_secure_code=org.secure_code,
        code=sc[-6:],
        name='代理測試部',
        unit_type=UnitType.DEPARTMENT,
        is_active=True,
        is_deleted=False,
    )
    db.session.add(unit)
    db.session.commit()
    return unit


def _assign(org, user, role, unit=None, *, kind=AssignmentKind.REGULAR, acting_for=None,
            valid_from=None, valid_until=None, source_ref=None, reason='Test reason'):
    row = UserRoleAssignment(
        org_secure_code=org.secure_code,
        user_secure_code=user.secure_code,
        role_secure_code=role.secure_code,
        unit_secure_code=unit.secure_code if unit else None,
        assignment_kind=kind,
        acting_for_user_secure_code=acting_for.secure_code if acting_for else None,
        valid_from=valid_from,
        valid_until=valid_until,
        source_ref=source_ref,
        grant_reason=reason if kind != AssignmentKind.REGULAR else None,
        is_deleted=False,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _post_create(client, **payload):
    data = {
        'delegate_secure_code': payload.pop('delegate_secure_code'),
        'effective_from': payload.pop('effective_from', '2026-10-01'),
        'effective_until': payload.pop('effective_until', '2026-10-03'),
        'reason': payload.pop('reason', 'Annual leave'),
    }
    data.update(payload)
    return client.post('/beakplatform/api/my-proxy-assignments', json=data)


def test_employee_create_full_proxy_excludes_identity_role(auth_client, test_org, test_user):
    delegate = _user('mpa_delegate_000001', test_org, 'mpa_delegate', 'Delegate User')
    unit = _unit(test_org)
    manager = _role(test_org, 'DEPT_MANAGER', '部門正主管')
    employee = _role(test_org, 'EMPLOYEE', '企業成員', ScopeType.GLOBAL)
    _assign(test_org, test_user, manager, unit)
    _assign(test_org, test_user, employee)

    resp = _post_create(auth_client, delegate_secure_code=delegate.secure_code)

    rows = UserRoleAssignment.query.filter_by(
        org_secure_code=test_org.secure_code,
        user_secure_code=delegate.secure_code,
        assignment_kind=AssignmentKind.PROXY,
        is_deleted=False,
    ).all()
    assert resp.status_code == 201
    assert resp.get_json()['data'] == {'created': 1, 'skipped': 0}
    assert len(rows) == 1
    row = rows[0]
    assert row.acting_for_user_secure_code == test_user.secure_code
    assert row.role_secure_code == manager.secure_code
    assert row.unit_secure_code == unit.secure_code
    assert row.valid_from == date(2026, 10, 1)
    assert row.valid_until == date(2026, 10, 3)
    assert row.source_ref == f'self:{test_user.secure_code}'
    assert row.grant_reason == 'Annual leave'


def test_create_without_proxyable_roles_is_invalid_request(auth_client, test_org, test_user):
    delegate = _user('mpa_norole_del001', test_org, 'mpa_norole_del', 'No Role Delegate')
    employee = _role(test_org, 'EMPLOYEE', '企業成員', ScopeType.GLOBAL)
    _assign(test_org, test_user, employee)

    resp = _post_create(auth_client, delegate_secure_code=delegate.secure_code)

    assert resp.status_code == 400
    assert resp.get_json()['error'] == 'invalid_request'


def test_create_rejects_invalid_delegate_candidates(auth_client, test_org, test_user):
    external = _user('mpa_external_00001', test_org, 'mpa_external', 'External User', UserType.EXTERNAL)
    inactive = _user('mpa_inactive_0001', test_org, 'mpa_inactive', 'Inactive User', is_active=False)
    other_org = _org()
    other_user = _user('mpa_otherorg_0001', other_org, 'mpa_otherorg', 'Other Org User')

    for sc in (test_user.secure_code, external.secure_code, inactive.secure_code, other_user.secure_code):
        resp = _post_create(auth_client, delegate_secure_code=sc)
        assert resp.status_code == 400
        assert resp.get_json()['error'] == 'invalid_delegate'


def test_create_rejects_invalid_date_ranges_and_blank_reason(auth_client, test_org):
    delegate = _user('mpa_dates_0000001', test_org, 'mpa_dates', 'Dates User')

    cases = [
        ({'effective_from': '2026/10/01'}, 'invalid_date'),
        ({'effective_from': '2026-10-04', 'effective_until': '2026-10-03'}, 'invalid_range'),
        ({'effective_from': '2020-01-01', 'effective_until': '2020-01-02'}, 'expired_range'),
        ({'reason': '   '}, 'reason_required'),
    ]
    for payload, code in cases:
        resp = _post_create(auth_client, delegate_secure_code=delegate.secure_code, **payload)
        assert resp.status_code == 400
        assert resp.get_json()['error'] == code


def test_external_and_system_admin_are_forbidden(client, test_org, system_admin):
    external = _user('mpa_ext_login0001', test_org, 'mpa_ext_login', 'External Login', UserType.EXTERNAL)
    _login_user_directly(client, external, test_org)
    get_resp = client.get('/beakplatform/api/my-proxy-assignments')
    post_resp = client.post('/beakplatform/api/my-proxy-assignments', json={})

    _login_user_directly(client, system_admin, test_org)
    system_resp = client.get('/beakplatform/api/my-proxy-assignments')

    assert get_resp.status_code == 403
    assert get_resp.get_json()['error'] == 'forbidden'
    assert post_resp.status_code == 403
    assert post_resp.get_json()['error'] == 'forbidden'
    assert system_resp.status_code == 403


def test_duplicate_overlap_all_skipped_is_invalid_but_partial_creates(auth_client, test_org, test_user):
    delegate = _user('mpa_dup_delegate01', test_org, 'mpa_dup_delegate', 'Duplicate Delegate')
    unit = _unit(test_org)
    role_a = _role(test_org, 'DEPT_MANAGER', '部門正主管')
    _assign(test_org, test_user, role_a, unit)

    first = _post_create(auth_client, delegate_secure_code=delegate.secure_code)
    duplicate = _post_create(auth_client, delegate_secure_code=delegate.secure_code)

    role_b = _role(test_org, 'DEPT_HEAD', '部門主管')
    _assign(test_org, test_user, role_b, unit)
    partial = _post_create(auth_client, delegate_secure_code=delegate.secure_code)

    assert first.status_code == 201
    assert duplicate.status_code == 400
    assert duplicate.get_json()['error'] == 'invalid_request'
    assert '已經代理你全部的角色' in duplicate.get_json()['message']
    assert partial.status_code == 201
    assert partial.get_json()['data'] == {'created': 1, 'skipped': 1}


def test_list_only_returns_related_proxy_rows(auth_client, test_org, test_user):
    unit = _unit(test_org)
    role = _role(test_org, 'DEPT_MANAGER', '部門正主管')
    delegate = _user('mpa_list_del0001', test_org, 'mpa_list_del', 'List Delegate')
    delegator = _user('mpa_list_giv0001', test_org, 'mpa_list_giv', 'List Giver')
    other_a = _user('mpa_list_oth0001', test_org, 'mpa_list_oth_a', 'Other A')
    other_b = _user('mpa_list_oth0002', test_org, 'mpa_list_oth_b', 'Other B')
    given = _assign(test_org, delegate, role, unit, kind=AssignmentKind.PROXY, acting_for=test_user,
                    valid_from=date(2026, 10, 1), valid_until=date(2026, 10, 3))
    received = _assign(test_org, test_user, role, unit, kind=AssignmentKind.PROXY, acting_for=delegator,
                       valid_from=date(2026, 10, 1), valid_until=date(2026, 10, 3))
    other = _assign(test_org, other_b, role, unit, kind=AssignmentKind.PROXY, acting_for=other_a,
                    valid_from=date(2026, 10, 1), valid_until=date(2026, 10, 3))
    _assign(test_org, test_user, role, unit, kind=AssignmentKind.STANDBY)

    resp = auth_client.get('/beakplatform/api/my-proxy-assignments')

    payload = resp.get_json()['data']
    assert resp.status_code == 200
    assert [d['assignment_secure_code'] for d in payload['given']] == [given.secure_code]
    assert [d['assignment_secure_code'] for d in payload['received']] == [received.secure_code]
    assert other.secure_code not in {d['assignment_secure_code'] for d in payload['given'] + payload['received']}


def test_my_roles_excludes_employee(auth_client, test_org, test_user):
    unit = _unit(test_org)
    manager = _role(test_org, 'DEPT_MANAGER', '部門正主管')
    employee = _role(test_org, 'EMPLOYEE', '企業成員', ScopeType.GLOBAL)
    _assign(test_org, test_user, manager, unit)
    _assign(test_org, test_user, employee)

    resp = auth_client.get('/beakplatform/api/my-proxy-assignments/my-roles')

    codes = {row['role_secure_code'] for row in resp.get_json()['data']}
    assert resp.status_code == 200
    assert manager.secure_code in codes
    assert employee.secure_code not in codes


def test_revoke_given_received_and_reject_unrelated_or_standby(auth_client, test_org, test_user):
    unit = _unit(test_org)
    role = _role(test_org, 'DEPT_MANAGER', '部門正主管')
    delegate = _user('mpa_rev_del00001', test_org, 'mpa_rev_del', 'Revoke Delegate')
    delegator = _user('mpa_rev_giv00001', test_org, 'mpa_rev_giv', 'Revoke Giver')
    other_a = _user('mpa_rev_a0000001', test_org, 'mpa_rev_a', 'Revoke A')
    other_b = _user('mpa_rev_b0000001', test_org, 'mpa_rev_b', 'Revoke B')
    given = _assign(test_org, delegate, role, unit, kind=AssignmentKind.PROXY, acting_for=test_user,
                    valid_from=date(2026, 10, 1), valid_until=date(2026, 10, 3))
    received = _assign(test_org, test_user, role, unit, kind=AssignmentKind.PROXY, acting_for=delegator,
                       valid_from=date(2026, 10, 1), valid_until=date(2026, 10, 3))
    unrelated = _assign(test_org, other_b, role, unit, kind=AssignmentKind.PROXY, acting_for=other_a,
                        valid_from=date(2026, 10, 1), valid_until=date(2026, 10, 3))
    standby = _assign(test_org, test_user, role, unit, kind=AssignmentKind.STANDBY)

    first = auth_client.post(f'/beakplatform/api/my-proxy-assignments/{given.secure_code}/revoke', json={})
    second = auth_client.post(f'/beakplatform/api/my-proxy-assignments/{received.secure_code}/revoke', json={})
    unrelated_resp = auth_client.post(f'/beakplatform/api/my-proxy-assignments/{unrelated.secure_code}/revoke', json={})
    standby_resp = auth_client.post(f'/beakplatform/api/my-proxy-assignments/{standby.secure_code}/revoke', json={})

    assert first.status_code == 200
    assert second.status_code == 200
    assert unrelated_resp.status_code == 404
    assert standby_resp.status_code == 404
    assert UserRoleAssignment.query.filter_by(secure_code=given.secure_code).first().is_deleted is True
    assert UserRoleAssignment.query.filter_by(secure_code=received.secure_code).first().is_deleted is True


def test_personal_settings_renders_member_block(auth_client, admin_client):
    employee_resp = auth_client.get('/beakplatform/personal-settings')
    admin_resp = admin_client.get('/beakplatform/personal-settings')

    assert employee_resp.status_code == 200
    assert b'id="my-proxy-assignments"' in employee_resp.data
    assert admin_resp.status_code == 200
    assert b'id="my-proxy-assignments"' in admin_resp.data


def test_personal_settings_hides_block_for_external(client, test_org):
    external = _user('mpa_page_ext00001', test_org, 'mpa_page_ext', 'External Page', UserType.EXTERNAL)
    _login_user_directly(client, external, test_org)

    resp = client.get('/beakplatform/personal-settings')

    assert resp.status_code == 200
    assert b'id="my-proxy-assignments"' not in resp.data


def test_unauthenticated_post_is_rejected(client):
    resp = client.post('/beakplatform/api/my-proxy-assignments', json={})

    assert resp.status_code in (302, 401)
