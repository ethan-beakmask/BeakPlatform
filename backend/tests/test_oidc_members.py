"""P3 membership scope and PF-396 external login coverage."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import base64
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from joserfc import jwt
from joserfc.jwk import KeySet

from app import db, limiter
from app.models import (OidcRefreshToken, OrganizationalUnit, Organization,
                        SystemSetting, User, UserUnitMembership)
from app.services.oidc_claims import build_claims
from app.services.rate_limit_service import RateLimitService
from backend.tests.test_oidc_provider import (
    oidc_setup, P, SECRET, _params, _resume_target, _token, _refresh)


@pytest.fixture(autouse=True)
def members_limits(app):
    app.config['RATELIMIT_ENABLED'] = True
    app.config['RATELIMIT_STORAGE_URI'] = 'memory://'
    limiter.init_app(app)
    limiter.reset()
    RateLimitService._cached_settings = None
    yield
    limiter.reset()
    limiter.enabled = False
    RateLimitService._cached_settings = None


def group(org, code, parent=None):
    unit = OrganizationalUnit(org_secure_code=org.secure_code, code=code,
        name=code, unit_type='GROUP', is_active=True, is_deleted=False,
        parent_secure_code=parent.secure_code if parent else None)
    db.session.add(unit); db.session.flush()
    return unit


def user(org, name, kind='EMPLOYEE', active=True):
    account = User(org_secure_code=org.secure_code, username=name + '@example.test',
        email=name + '@example.test', display_name=name, user_type=kind,
        is_active=active, is_deleted=False)
    account.set_password('password123')
    db.session.add(account); db.session.flush()
    return account


def membership(org, unit, account, role='MEMBER', **kw):
    row = UserUnitMembership(org_secure_code=org.secure_code,
        unit_secure_code=unit.secure_code, user_secure_code=account.secure_code,
        role_type=role, **kw)
    db.session.add(row); db.session.flush()
    return row


def members(client, sc, secret=SECRET):
    basic = base64.b64encode(f'scribe-client:{secret}'.encode()).decode()
    return client.get(P + f'/oauth/project-groups/{sc}/members',
                      headers={'Authorization': 'Basic ' + basic})


def test_members_bad_basic(client, oidc_setup, monkeypatch):
    from app.api import oidc_provider

    authenticate = oidc_provider.authenticate_client
    attempts = []
    def counted_authenticate():
        attempts.append(True)
        return authenticate()
    monkeypatch.setattr(oidc_provider, 'authenticate_client', counted_authenticate)
    response = members(client, 'missing', secret='wrong')
    assert response.status_code == 401
    assert response.get_json() == {'error': 'invalid_client'}
    assert response.headers['WWW-Authenticate'] == 'Basic realm="oauth/project-groups"'
    members(client, 'missing')
    assert len(attempts) == 2  # Each request authenticates once, including after a failure.


def test_three_hidden_group_cases_match(client, test_org, oidc_setup):
    outside = group(test_org, 'OUTSIDE')
    other = Organization(code='OTHER', name='Other', domain_name='other.local',
                         is_active=True, is_deleted=False)
    db.session.add(other); db.session.flush()
    other_unit = group(other, 'PRIVATE', group(other, 'PROJECTS_GROUPCLASS'))
    db.session.commit()
    responses = [members(client, sc) for sc in
                 (outside.secure_code, other_unit.secure_code, 'missing')]
    # JSON dicts are unhashable: freeze their items to compare the entire body.
    outcomes = {(r.status_code, tuple(sorted(r.get_json().items()))) for r in responses}
    assert len(outcomes) == 1
    assert responses[0].status_code == 404
    assert responses[0].get_json() == {'error': 'not_found'}


def test_vendor_and_deep_project_tree(client, test_org, oidc_setup):
    vendor = group(test_org, 'V', group(test_org, 'EXTERNAL_VENDORS'))
    project = group(test_org, 'P3', group(test_org, 'P2',
                    group(test_org, 'P1', group(test_org, 'PROJECTS_GROUPCLASS'))))
    db.session.commit()
    for unit, tree in ((vendor, 'vendor'), (project, 'project')):
        response = members(client, unit.secure_code)
        assert response.status_code == 200
        assert response.get_json()['group']['tree'] == tree
        assert response.headers['Cache-Control'] == 'no-store'


def test_member_claims_share_effective_population(client, test_org, oidc_setup):
    oidc_setup.extra_claims = ['scribe']
    unit = group(test_org, 'POPULATION', group(test_org, 'PROJECTS_GROUPCLASS'))
    inactive = user(test_org, 'inactive', active=False)
    external = user(test_org, 'vendor', 'EXTERNAL')
    expired = user(test_org, 'expired')
    duplicate = user(test_org, 'duplicate')
    membership(test_org, unit, inactive)
    membership(test_org, unit, external)
    membership(test_org, unit, expired, end_date=test_org.local_today() - timedelta(days=1))
    membership(test_org, unit, duplicate)
    membership(test_org, unit, duplicate, 'DEPUTY')
    db.session.commit()
    rows = members(client, unit.secure_code).get_json()['members']
    claim_population = {u.secure_code for u in (inactive, external, expired, duplicate)
        if any(g['key'] == unit.secure_code for g in
               build_claims(u, 'openid', oidc_setup)['project_groups'])}
    assert {r['sub'] for r in rows} == claim_population == {duplicate.secure_code}
    assert len(rows) == 1 and rows[0]['role'] == 'manager'


def test_members_rate_limit(client, oidc_setup):
    SystemSetting.set('ratelimit_oidc_members', '2 per minute', value_type='string')
    RateLimitService._cached_settings = None
    responses = [members(client, 'missing') for _ in range(3)]
    assert [r.status_code for r in responses] == [404, 404, 429]
    assert responses[-1].get_json() == {'error': 'rate_limited'}


def test_external_login_through_refresh_revocation(client, test_org, oidc_setup):
    SystemSetting.set('oidc_external_users_enabled', True, value_type='boolean')
    oidc_setup.extra_claims = ['scribe']
    vendor = user(test_org, 'external', 'EXTERNAL')
    vendor.employee_id = 'DCX001'  # 平台給廠商的編號不得外流，claims 與名單都要是 null
    vendor_group = group(test_org, 'VENDOR', group(test_org, 'EXTERNAL_VENDORS'))
    project = group(test_org, 'PROJECT', group(test_org, 'PROJECTS_GROUPCLASS'))
    membership(test_org, vendor_group, vendor)
    db.session.commit()
    first = client.get(P + '/oauth/authorize', query_string=_params(org_hint='test.local'))
    assert first.status_code == 302
    assert first.headers['Location'].endswith('/auth/org/test.local/public/login')
    with client.session_transaction() as sess:
        assert 'org_hint' not in sess['oidc_pending']
    login = client.post(first.headers['Location'], json={
        'email': vendor.email, 'password': 'password123'})
    assert login.get_json()['redirect'].endswith('/oauth/authorize/resume')
    resumed = client.get(login.get_json()['redirect'])
    code = parse_qs(urlparse(_resume_target(resumed)).query)['code'][0]
    issued = _token(client, code)
    assert issued.status_code == 200
    tokens = issued.get_json()
    claims = jwt.decode(tokens['id_token'], KeySet.import_key_set(
        client.get(P + '/oauth/jwks').get_json()), algorithms=['RS256']).claims
    assert claims['user_type'] == 'EXTERNAL'
    assert claims['scribe_admin'] is False and claims['employee_no'] is None
    assert claims['project_groups'] == [{'key': vendor_group.secure_code,
        'name': vendor_group.name, 'tree': 'vendor', 'role': 'member'}]
    rows = members(client, vendor_group.secure_code).get_json()['members']
    assert [(r['sub'], r['user_type'], r['employee_no']) for r in rows] == [
        (vendor.secure_code, 'EXTERNAL', None)]
    # Rotate once so family revocation must cover multiple rows.
    rotated = _refresh(client, tokens['refresh_token']).get_json()
    family = OidcRefreshToken.query.filter_by(user_secure_code=vendor.secure_code).first().family_id
    SystemSetting.set('oidc_external_users_enabled', False, value_type='boolean')
    denied = _refresh(client, rotated['refresh_token'])
    assert denied.status_code == 400 and denied.get_json() == {'error': 'invalid_grant'}
    db.session.expire_all()
    assert all(r.revoked_at is not None for r in
               OidcRefreshToken.query.filter_by(family_id=family).all())
    assert members(client, vendor_group.secure_code).get_json()['members'] == []


def test_org_hint_fallback_indistinguishable(client, oidc_setup):
    SystemSetting.set('oidc_external_users_enabled', False, value_type='boolean')
    disabled = client.get(P + '/oauth/authorize', query_string=_params(org_hint='test.local'))
    SystemSetting.set('oidc_external_users_enabled', True, value_type='boolean')
    missing = client.get(P + '/oauth/authorize', query_string=_params(org_hint='missing.local'))
    assert (disabled.status_code, disabled.headers['Location']) == (
        missing.status_code, missing.headers['Location'])
    assert disabled.headers['Location'].endswith('/auth/login')
