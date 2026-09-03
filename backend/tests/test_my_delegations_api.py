from datetime import date

from app import db
from app.models import Delegation, DelegationStatus, DelegationType, Organization, User, UserType


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


def _delegation(sc, org, delegator, delegate, **overrides):
    delegation = Delegation(
        secure_code=sc,
        org_secure_code=org.secure_code,
        delegator_secure_code=delegator.secure_code,
        delegate_secure_code=delegate.secure_code,
        delegation_type=overrides.pop('delegation_type', DelegationType.FULL),
        status=overrides.pop('status', DelegationStatus.PENDING),
        effective_from=overrides.pop('effective_from', date(2026, 10, 1)),
        effective_until=overrides.pop('effective_until', date(2026, 10, 3)),
        reason=overrides.pop('reason', 'Test delegation'),
        created_by=overrides.pop('created_by', delegator.display_name),
        **overrides,
    )
    db.session.add(delegation)
    db.session.commit()
    return delegation


def _post_create(client, **payload):
    data = {
        'delegate_secure_code': payload.pop('delegate_secure_code'),
        'effective_from': payload.pop('effective_from', '2026-10-01'),
        'effective_until': payload.pop('effective_until', '2026-10-03'),
        'reason': payload.pop('reason', 'Annual leave'),
    }
    data.update(payload)
    return client.post('/beakplatform/api/my-delegations', json=data)


def test_employee_create_forces_self_and_full(auth_client, test_org, test_user):
    delegate = _user('mydel_delegate_0001', test_org, 'mydel_delegate', 'Delegate User')
    intruder = _user('mydel_intruder_0001', test_org, 'mydel_intruder', 'Intruder User')

    resp = _post_create(
        auth_client,
        delegate_secure_code=delegate.secure_code,
        delegator_secure_code=intruder.secure_code,
        delegation_type=DelegationType.SPECIFIC,
    )

    data = resp.get_json()
    row = Delegation.query.filter_by(delegate_secure_code=delegate.secure_code).one()
    assert resp.status_code == 201
    assert data['success'] is True
    assert row.delegator_secure_code == test_user.secure_code
    assert row.delegation_type == DelegationType.FULL
    assert row.created_by == test_user.display_name
    assert data['data']['status'] in (DelegationStatus.PENDING, DelegationStatus.ACTIVE)


def test_create_rejects_self_delegate(auth_client, test_user):
    resp = _post_create(auth_client, delegate_secure_code=test_user.secure_code)

    assert resp.status_code == 400
    assert resp.get_json()['error'] == 'invalid_delegate'


def test_create_rejects_external_delegate(auth_client, test_org):
    external = _user('mydel_external_0001', test_org, 'mydel_external', 'External User', UserType.EXTERNAL)

    resp = _post_create(auth_client, delegate_secure_code=external.secure_code)

    assert resp.status_code == 400
    assert resp.get_json()['error'] == 'invalid_delegate'


def test_create_rejects_inactive_delegate(auth_client, test_org):
    inactive = _user('mydel_inactive_001', test_org, 'mydel_inactive', 'Inactive User', is_active=False)

    resp = _post_create(auth_client, delegate_secure_code=inactive.secure_code)

    assert resp.status_code == 400
    assert resp.get_json()['error'] == 'invalid_delegate'


def test_create_rejects_other_org_delegate(auth_client):
    other_org = _org()
    other_user = _user('mydel_otherorg_001', other_org, 'mydel_otherorg', 'Other Org User')

    resp = _post_create(auth_client, delegate_secure_code=other_user.secure_code)

    assert resp.status_code == 400
    assert resp.get_json()['error'] == 'invalid_delegate'


def test_create_rejects_invalid_date_ranges(auth_client, test_org):
    delegate = _user('mydel_dates_00001', test_org, 'mydel_dates', 'Dates User')

    bad_range = _post_create(
        auth_client,
        delegate_secure_code=delegate.secure_code,
        effective_from='2026-10-04',
        effective_until='2026-10-03',
    )
    expired = _post_create(
        auth_client,
        delegate_secure_code=delegate.secure_code,
        effective_from='2020-01-01',
        effective_until='2020-01-02',
    )
    invalid = _post_create(
        auth_client,
        delegate_secure_code=delegate.secure_code,
        effective_from='2026/10/01',
    )

    assert bad_range.status_code == 400
    assert bad_range.get_json()['error'] == 'invalid_range'
    assert expired.status_code == 400
    assert expired.get_json()['error'] == 'expired_range'
    assert invalid.status_code == 400
    assert invalid.get_json()['error'] == 'invalid_date'


def test_external_and_system_admin_are_forbidden(client, app, test_org, system_admin):
    external = _user('mydel_ext_login01', test_org, 'mydel_ext_login', 'External Login', UserType.EXTERNAL)
    _login_user_directly(client, external, test_org)
    get_resp = client.get('/beakplatform/api/my-delegations')
    post_resp = client.post('/beakplatform/api/my-delegations', json={})

    _login_user_directly(client, system_admin, test_org)
    system_resp = client.get('/beakplatform/api/my-delegations')

    assert get_resp.status_code == 403
    assert get_resp.get_json()['error'] == 'forbidden'
    assert post_resp.status_code == 403
    assert post_resp.get_json()['error'] == 'forbidden'
    assert system_resp.status_code == 403


def test_list_only_returns_given_and_received(auth_client, test_org, test_user):
    delegate = _user('mydel_list_del01', test_org, 'mydel_list_del', 'List Delegate')
    delegator = _user('mydel_list_giv01', test_org, 'mydel_list_giv', 'List Giver')
    unrelated_a = _user('mydel_list_oth01', test_org, 'mydel_list_oth_a', 'Other A')
    unrelated_b = _user('mydel_list_oth02', test_org, 'mydel_list_oth_b', 'Other B')
    given = _delegation('mydel_given_00001', test_org, test_user, delegate)
    received = _delegation('mydel_recv_000001', test_org, delegator, test_user)
    other = _delegation('mydel_other_00001', test_org, unrelated_a, unrelated_b)

    resp = auth_client.get('/beakplatform/api/my-delegations')

    payload = resp.get_json()['data']
    assert resp.status_code == 200
    assert [d['secure_code'] for d in payload['given']] == [given.secure_code]
    assert [d['secure_code'] for d in payload['received']] == [received.secure_code]
    assert other.secure_code not in {d['secure_code'] for d in payload['given'] + payload['received']}


def test_candidates_filter_to_same_org_active_members(auth_client, test_org, test_user, test_admin):
    employee = _user('mydel_cand_emp01', test_org, 'mydel_cand_emp', 'Candidate Employee', employee_id='E001')
    _user('mydel_cand_ext01', test_org, 'mydel_cand_ext', 'Candidate External', UserType.EXTERNAL)
    _user('mydel_cand_off01', test_org, 'mydel_cand_off', 'Candidate Off', is_active=False)
    _user('mydel_cand_svc01', test_org, 'mydel_cand_svc', 'Candidate Service', is_service_account=True)
    other_org = _org('cand_other_org_001', 'CANDOTHER')
    _user('mydel_cand_oth01', other_org, 'mydel_cand_oth', 'Candidate Other Org')

    resp = auth_client.get('/beakplatform/api/my-delegations/candidates')

    codes = {item['secure_code'] for item in resp.get_json()['data']}
    assert resp.status_code == 200
    assert employee.secure_code in codes
    assert test_admin.secure_code in codes
    assert test_user.secure_code not in codes
    assert 'mydel_cand_ext01' not in codes
    assert 'mydel_cand_off01' not in codes
    assert 'mydel_cand_svc01' not in codes
    assert 'mydel_cand_oth01' not in codes


def test_revoke_only_own_given_delegations(auth_client, test_org, test_user):
    delegate = _user('mydel_revoke_del', test_org, 'mydel_revoke_del', 'Revoke Delegate')
    delegator = _user('mydel_revoke_giv', test_org, 'mydel_revoke_giv', 'Revoke Giver')
    other_a = _user('mydel_revoke_a01', test_org, 'mydel_revoke_a', 'Revoke A')
    other_b = _user('mydel_revoke_b01', test_org, 'mydel_revoke_b', 'Revoke B')
    own = _delegation('mydel_revoke_own', test_org, test_user, delegate)
    received = _delegation('mydel_revoke_rec', test_org, delegator, test_user)
    unrelated = _delegation('mydel_revoke_oth', test_org, other_a, other_b)

    first = auth_client.post(f'/beakplatform/api/my-delegations/{own.secure_code}/revoke', json={})
    db.session.refresh(own)
    second = auth_client.post(f'/beakplatform/api/my-delegations/{own.secure_code}/revoke', json={})
    received_resp = auth_client.post(f'/beakplatform/api/my-delegations/{received.secure_code}/revoke', json={})
    unrelated_resp = auth_client.post(f'/beakplatform/api/my-delegations/{unrelated.secure_code}/revoke', json={})

    assert first.status_code == 200
    assert first.get_json()['data']['status'] == DelegationStatus.REVOKED
    assert own.revoked_by == test_user.display_name
    assert second.status_code == 400
    assert second.get_json()['error'] == 'already_revoked'
    assert received_resp.status_code == 404
    assert unrelated_resp.status_code == 404


def test_personal_settings_renders_member_block(auth_client, admin_client):
    employee_resp = auth_client.get('/beakplatform/personal-settings')
    admin_resp = admin_client.get('/beakplatform/personal-settings')

    assert employee_resp.status_code == 200
    assert b'id="my-delegations"' in employee_resp.data
    assert admin_resp.status_code == 200
    assert b'id="my-delegations"' in admin_resp.data


def test_personal_settings_hides_block_for_external(client, app, test_org):
    external = _user('mydel_page_ext01', test_org, 'mydel_page_ext', 'External Page', UserType.EXTERNAL)
    _login_user_directly(client, external, test_org)

    resp = client.get('/beakplatform/personal-settings')

    assert resp.status_code == 200
    assert b'id="my-delegations"' not in resp.data


def test_unauthenticated_post_is_rejected(client):
    resp = client.post('/beakplatform/api/my-delegations', json={})

    assert resp.status_code in (302, 401)
