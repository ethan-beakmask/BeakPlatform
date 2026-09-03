from app import db
from app.models import Delegation, User


def test_create_delegation_prefills_from_query(admin_client, test_user):
    resp = admin_client.get(
        f'/beakplatform/delegations/create?delegator={test_user.secure_code}'
        '&effective_from=2026-10-01&effective_until=2026-10-03'
        '&reason=Trip&next=/beakplatform/calendar/me'
    )
    body = resp.get_data(as_text=True)
    option_at = body.index(f'value="{test_user.secure_code}"')

    assert resp.status_code == 200
    assert 'selected' in body[option_at:option_at + 140]
    assert 'name="effective_from" required style="width: 100%;"\n                       value="2026-10-01"' in body
    assert 'name="effective_until" required style="width: 100%;"\n                       value="2026-10-03"' in body
    assert '>Trip</textarea>' in body
    assert 'name="next" value="/beakplatform/calendar/me"' in body


def test_create_delegation_redirects_to_safe_next(admin_client, test_user, test_admin):
    delegate = _other_user(test_user.org_secure_code)

    resp = admin_client.post('/beakplatform/delegations/create', data={
        'delegator_secure_code': test_user.secure_code,
        'delegate_secure_code': delegate.secure_code,
        'delegation_type': 'FULL',
        'effective_from': '2026-10-01',
        'effective_until': '2026-10-03',
        'reason': 'Trip',
        'next': '/beakplatform/calendar/me',
    })

    assert resp.status_code == 302
    assert resp.headers['Location'].endswith('/beakplatform/calendar/me')
    assert Delegation.query.filter_by(delegator_secure_code=test_user.secure_code,
                                      delegate_secure_code=delegate.secure_code).count() == 1


def test_create_delegation_rejects_external_next(admin_client, test_user):
    delegate = _other_user(test_user.org_secure_code)
    targets = ['https://evil.example/', '//evil.example']

    locations = []
    for idx, target in enumerate(targets):
        resp = admin_client.post('/beakplatform/delegations/create', data={
            'delegator_secure_code': test_user.secure_code,
            'delegate_secure_code': delegate.secure_code,
            'delegation_type': 'FULL',
            'effective_from': f'2026-10-0{idx + 4}',
            'effective_until': f'2026-10-0{idx + 4}',
            'reason': 'Trip',
            'next': target,
        })
        locations.append(resp.headers['Location'])

    assert all(location.endswith('/beakplatform/delegations/') for location in locations)
    assert not any('evil.example' in location for location in locations)


def _other_user(org_secure_code):
    suffix = User.query.count()
    user = User(
        secure_code=f'del_prefill_user_{suffix:04d}',
        org_secure_code=org_secure_code,
        username=f'del-prefill-{suffix}',
        email=f'del-prefill-{suffix}@example.com',
        display_name=f'Delegation Prefill {suffix}',
        is_active=True,
        is_deleted=False,
    )
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()
    return user
