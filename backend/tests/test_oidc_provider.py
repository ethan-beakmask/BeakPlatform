"""End-to-end coverage for the PF-327 OIDC provider."""
import base64
import hashlib
import html
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from joserfc import jwt
from joserfc.jwk import KeySet
from werkzeug.security import generate_password_hash

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db
from app.models import (MembershipRole, OidcClient, OidcClientOrg,
                        OrganizationalUnit, Organization, Role, SystemSetting,
                        User, UserUnitMembership)
from app.models.organizational_unit import UnitType
from app.services.oidc_claims import build_claims
from app.services.oidc_org_defaults import (ensure_projects_group_class,
                                            ensure_scribe_org_defaults)
from app.services.role_assignment_service import assign_role
from backend.tests.conftest import _login_user_directly


P = '/beakplatform'
REDIRECT = 'https://scribe.test/callback'
SECRET = 'client-secret-for-tests'
VERIFIER = 'a' * 64
CHALLENGE = base64.urlsafe_b64encode(
    hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b'=').decode()


@pytest.fixture
def oidc_setup(app, test_org, test_user):
    app.config['SESSION_COOKIE_PATH'] = '/'
    SystemSetting.set('system_base_url', 'https://platform.test',
                      value_type='string', category='general')
    test_org.is_system_org = True
    client = OidcClient(
        client_id='scribe-client', client_secret_hash=generate_password_hash(SECRET),
        name='Scribe', redirect_uris=[REDIRECT],
        allowed_user_types=['EMPLOYEE', 'ORG_ADMIN', 'SYSTEM_ADMIN'],
        extra_claims=[])
    db.session.add(client); db.session.flush()
    db.session.add(OidcClientOrg(client_secure_code=client.secure_code,
                                org_secure_code=test_org.secure_code))
    db.session.commit()
    return client


def _params(**updates):
    values = {'client_id': 'scribe-client', 'redirect_uri': REDIRECT,
              'response_type': 'code', 'scope': 'openid profile email',
              'state': 'state-1', 'nonce': 'nonce-1',
              'code_challenge': CHALLENGE, 'code_challenge_method': 'S256'}
    values.update(updates)
    return values


def _authorize_logged_in(client, app, user, org, **updates):
    _login_user_directly(client, app, user, org)
    response = client.get(P + '/oauth/authorize', query_string=_params(**updates))
    return response


def _code(response):
    return parse_qs(urlparse(response.headers['Location']).query)['code'][0]


def _resume_target(response):
    html_ = response.get_data(as_text=True)
    url = re.search(r'content="0;url=([^"]+)"', html_).group(1)
    return html.unescape(url)


def _token(client, code, verifier=VERIFIER):
    basic = base64.b64encode(f'scribe-client:{SECRET}'.encode()).decode()
    return client.post(P + '/oauth/token', data={
        'grant_type': 'authorization_code', 'code': code,
        'redirect_uri': REDIRECT, 'code_verifier': verifier},
        headers={'Authorization': 'Basic ' + basic})


def _refresh(client, value):
    return client.post(P + '/oauth/token', data={
        'grant_type': 'refresh_token', 'refresh_token': value,
        'client_id': 'scribe-client', 'client_secret': SECRET})


def test_complete_login_resume_token_jwks_and_userinfo(
        client, app, test_user, test_org, oidc_setup):
    first = client.get(P + '/oauth/authorize', query_string=_params())
    assert first.status_code == 302
    assert first.headers['Location'].endswith('/auth/login')
    with client.session_transaction() as sess:
        assert sess['oidc_pending']['client_id'] == 'scribe-client'
    login = client.post(P + '/auth/login', json={
        'account': 'testuser@test.local', 'password': 'password123'})
    assert login.status_code == 200
    assert login.get_json()['redirect'].endswith('/oauth/authorize/resume')
    resumed = client.get(P + '/oauth/authorize/resume')
    # 中繼頁（200）而非 302：登入表單 POST 的 302 鏈會被 CSP form-action 'self' 擋下
    assert resumed.status_code == 200
    assert 'Location' not in resumed.headers
    assert resumed.headers['Cache-Control'] == 'no-store'
    query = parse_qs(urlparse(_resume_target(resumed)).query)
    assert query.get('state') == ['state-1'], resumed.data
    assert query['iss'] == ['https://platform.test/beakplatform']

    issued = _token(client, query['code'][0])
    assert issued.status_code == 200
    body = issued.get_json()
    jwks = client.get(P + '/oauth/jwks').get_json()
    claims = jwt.decode(body['id_token'], KeySet.import_key_set(jwks),
                        algorithms=['RS256']).claims
    assert claims['iss'] == 'https://platform.test/beakplatform'
    assert claims['aud'] == 'scribe-client'
    assert claims['nonce'] == 'nonce-1'
    assert claims['exp'] > int(datetime.utcnow().timestamp())
    info = client.get(P + '/oauth/userinfo', headers={
        'Authorization': 'Bearer ' + body['access_token']})
    assert info.status_code == 200
    assert info.get_json()['sub'] == claims['sub']
    assert info.get_json()['email'] == claims['email']


@pytest.mark.parametrize(('updates', 'error'), [
    ({'code_challenge': ''}, 'invalid_request'),
    ({'code_challenge_method': 'plain'}, 'invalid_request'),
])
def test_authorize_rejects_non_s256_pkce(client, app, test_user, test_org,
                                         oidc_setup, updates, error):
    response = _authorize_logged_in(client, app, test_user, test_org, **updates)
    assert parse_qs(urlparse(response.headers['Location']).query)['error'] == [error]


def test_wrong_pkce_verifier_is_invalid_grant(client, app, test_user, test_org,
                                               oidc_setup):
    response = _authorize_logged_in(client, app, test_user, test_org)
    assert _token(client, _code(response), verifier='b' * 64).get_json() == {
        'error': 'invalid_grant'}


@pytest.mark.parametrize('uri', [
    REDIRECT + '/', 'https://SCRIBE.test/callback', REDIRECT + '?extra=1'])
def test_redirect_uri_requires_exact_match(client, oidc_setup, uri):
    response = client.get(P + '/oauth/authorize',
                          query_string=_params(redirect_uri=uri))
    assert response.status_code == 400
    assert response.status_code != 302


def test_code_replay_revokes_refresh_token(client, app, test_user, test_org,
                                            oidc_setup):
    code = _code(_authorize_logged_in(client, app, test_user, test_org))
    first = _token(client, code).get_json()
    assert _token(client, code).get_json()['error'] == 'invalid_grant'
    assert _refresh(client, first['refresh_token']).get_json()['error'] == 'invalid_grant'


def test_refresh_rotation_and_family_reuse_detection(client, app, test_user,
                                                      test_org, oidc_setup):
    code = _code(_authorize_logged_in(client, app, test_user, test_org))
    original = _token(client, code).get_json()['refresh_token']
    rotated = _refresh(client, original)
    assert rotated.status_code == 200
    replacement = rotated.get_json()['refresh_token']
    assert _refresh(client, original).get_json()['error'] == 'invalid_grant'
    assert _refresh(client, replacement).get_json()['error'] == 'invalid_grant'


@pytest.mark.parametrize('mutation', ['user_inactive', 'user_deleted',
                                      'org_inactive', 'org_removed',
                                      'client_inactive'])
def test_refresh_reflects_current_disablement(client, app, test_user, test_org,
                                              oidc_setup, mutation):
    code = _code(_authorize_logged_in(client, app, test_user, test_org))
    refresh = _token(client, code).get_json()['refresh_token']
    if mutation == 'user_inactive': test_user.is_active = False
    elif mutation == 'user_deleted': test_user.is_deleted = True
    elif mutation == 'org_inactive': test_org.is_active = False
    elif mutation == 'org_removed':
        OidcClientOrg.query.delete()
    else: oidc_setup.is_active = False
    db.session.commit()
    assert _refresh(client, refresh).get_json()['error'] == 'invalid_grant'


def test_resume_expiry_does_not_redirect_to_client(client, oidc_setup):
    with client.session_transaction() as sess:
        sess['oidc_pending'] = {**_params(),
                                'created_at': (datetime.utcnow() - timedelta(minutes=11)).timestamp()}
    response = client.get(P + '/oauth/authorize/resume')
    assert response.status_code == 400
    assert REDIRECT.encode() not in response.data


def test_userinfo_rechecks_user_state(client, app, test_user, test_org,
                                      oidc_setup):
    code = _code(_authorize_logged_in(client, app, test_user, test_org))
    access = _token(client, code).get_json()['access_token']
    test_user.is_active = False; db.session.commit()
    response = client.get(P + '/oauth/userinfo', headers={
        'Authorization': 'Bearer ' + access})
    assert response.status_code == 401


def test_all_provider_endpoints_disabled_without_base_url(client):
    for method, path in [
        ('get', '/.well-known/openid-configuration'), ('get', '/oauth/jwks'),
        ('get', '/oauth/authorize'), ('get', '/oauth/authorize/resume'),
        ('post', '/oauth/token'), ('get', '/oauth/userinfo')]:
        response = getattr(client, method)(P + path)
        assert response.status_code == 503
        assert response.get_json() == {'error': 'oidc_disabled'}


def test_project_groups_employee_number_and_mutable_email_claims(
        client, app, test_user, test_org, oidc_setup):
    root = ensure_projects_group_class(test_org)
    outside = OrganizationalUnit(org_secure_code=test_org.secure_code,
        unit_type=UnitType.GROUP, code='OUTSIDE', name='Outside', is_active=True)
    db.session.add(outside); db.session.flush()
    level1 = OrganizationalUnit(org_secure_code=test_org.secure_code,
        unit_type=UnitType.GROUP, code='P1', name='Alpha', is_active=True,
        parent_secure_code=root.secure_code)
    db.session.add(level1); db.session.flush()
    level2 = OrganizationalUnit(org_secure_code=test_org.secure_code,
        unit_type=UnitType.GROUP, code='P2', name='Beta', is_active=True,
        parent_secure_code=level1.secure_code)
    expired = OrganizationalUnit(org_secure_code=test_org.secure_code,
        unit_type=UnitType.GROUP, code='OLD', name='Old', is_active=True,
        parent_secure_code=root.secure_code)
    db.session.add_all([level2, expired]); db.session.flush()
    today = test_org.local_today()
    db.session.add_all([
        UserUnitMembership(org_secure_code=test_org.secure_code,
            user_secure_code=test_user.secure_code,
            unit_secure_code=level1.secure_code,
            role_type=MembershipRole.MANAGER),
        UserUnitMembership(org_secure_code=test_org.secure_code,
            user_secure_code=test_user.secure_code,
            unit_secure_code=level2.secure_code,
            role_type=MembershipRole.DEPUTY),
        UserUnitMembership(org_secure_code=test_org.secure_code,
            user_secure_code=test_user.secure_code,
            unit_secure_code=outside.secure_code,
            role_type=MembershipRole.MEMBER),
        UserUnitMembership(org_secure_code=test_org.secure_code,
            user_secure_code=test_user.secure_code,
            unit_secure_code=expired.secure_code,
            role_type=MembershipRole.MEMBER, end_date=today - timedelta(days=1)),
    ])
    test_user.employee_id = ''
    oidc_setup.extra_claims = ['scribe']; db.session.commit()
    first = build_claims(test_user, 'openid profile email', oidc_setup)
    assert first['employee_no'] is None
    assert [(g['name'], g['role']) for g in first['project_groups']] == [
        ('Alpha', 'manager'), ('Beta', 'manager')]
    old_sub = first['sub']; test_user.email = 'changed@example.com'; db.session.commit()
    changed = build_claims(test_user, 'openid email', oidc_setup)
    assert changed['sub'] == old_sub
    assert changed['email'] == 'changed@example.com'
    oidc_setup.extra_claims = []; db.session.commit()
    assert 'project_groups' not in build_claims(test_user, 'openid', oidc_setup)


def test_project_groups_member_role_and_duplicate_memberships(
        client, app, test_user, test_org, oidc_setup):
    root = ensure_projects_group_class(test_org)
    db.session.flush()
    plain = OrganizationalUnit(org_secure_code=test_org.secure_code,
        unit_type=UnitType.GROUP, code='PLAIN', name='Plain', is_active=True,
        parent_secure_code=root.secure_code)
    both = OrganizationalUnit(org_secure_code=test_org.secure_code,
        unit_type=UnitType.GROUP, code='BOTH', name='Both', is_active=True,
        parent_secure_code=root.secure_code)
    db.session.add_all([plain, both]); db.session.flush()
    db.session.add_all([
        UserUnitMembership(org_secure_code=test_org.secure_code,
            user_secure_code=test_user.secure_code,
            unit_secure_code=plain.secure_code,
            role_type=MembershipRole.MEMBER),
        UserUnitMembership(org_secure_code=test_org.secure_code,
            user_secure_code=test_user.secure_code,
            unit_secure_code=both.secure_code,
            role_type=MembershipRole.MEMBER),
        UserUnitMembership(org_secure_code=test_org.secure_code,
            user_secure_code=test_user.secure_code,
            unit_secure_code=both.secure_code,
            role_type=MembershipRole.MANAGER),
    ])
    oidc_setup.extra_claims = ['scribe']; db.session.commit()
    groups = build_claims(test_user, 'openid', oidc_setup)['project_groups']
    assert [(g['name'], g['role']) for g in groups] == [
        ('Both', 'manager'), ('Plain', 'member')]


def test_scribe_admin_regular_true_and_standby_false(
        app, test_org, test_user, test_admin, oidc_setup):
    role = ensure_scribe_org_defaults(test_org); db.session.commit()
    oidc_setup.extra_claims = ['scribe']
    assign_role(test_org.secure_code, test_user.secure_code, role.secure_code,
                operator=test_admin)
    assert build_claims(test_user, 'openid', oidc_setup)['scribe_admin'] is True
    standby = User(org_secure_code=test_org.secure_code, username='standby',
        email='standby@test.local', display_name='Standby', is_active=True,
        is_deleted=False)
    standby.set_password('password123'); db.session.add(standby); db.session.commit()
    assign_role(test_org.secure_code, standby.secure_code, role.secure_code,
                kind='standby', grant_reason='OIDC claim test',
                operator=test_admin)
    assert build_claims(standby, 'openid', oidc_setup)['scribe_admin'] is False
    assert build_claims(test_admin, 'openid', oidc_setup)['scribe_admin'] is True


def test_forced_password_change_resumes_only_after_change(
        client, test_user, test_org, oidc_setup):
    test_user.must_change_password = True; db.session.commit()
    client.get(P + '/oauth/authorize', query_string=_params())
    login = client.post(P + '/auth/login', json={
        'account': 'testuser@test.local', 'password': 'password123'})
    assert login.get_json()['redirect'].endswith('/auth/change-password')
    changed = client.post(P + '/auth/change-password', data={
        'current_password': 'password123',
        'new_password': 'a-new-password-123',
        'confirm_password': 'a-new-password-123'})
    assert changed.status_code == 302
    assert changed.headers['Location'].endswith('/oauth/authorize/resume')
    resumed = client.get(changed.headers['Location'])
    assert resumed.status_code == 200
    assert 'code=' in _resume_target(resumed)


@pytest.mark.parametrize('case', [
    'unauthorized_org', 'external', 'original_admin', 'system_admin_wrong_org'])
def test_authorize_denies_ineligible_identities(
        client, app, test_user, test_org, oidc_setup, case):
    user, org = test_user, test_org
    if case in ('unauthorized_org', 'system_admin_wrong_org'):
        org = Organization(code='OTHER', name='Other', domain_name='other.test',
                           is_active=True, is_deleted=False,
                           is_system_org=False)
        db.session.add(org); db.session.flush()
        user = User(org_secure_code=org.secure_code, username='other-user',
                    email='other@test.local', display_name='Other User',
                    is_active=True, is_deleted=False,
                    user_type=('SYSTEM_ADMIN' if case == 'system_admin_wrong_org'
                               else 'EMPLOYEE'))
        user.set_password('password123'); db.session.add(user); db.session.flush()
        if case == 'system_admin_wrong_org':
            db.session.add(OidcClientOrg(
                client_secure_code=oidc_setup.secure_code,
                org_secure_code=org.secure_code))
    elif case == 'external':
        user.user_type = 'EXTERNAL'
        oidc_setup.allowed_user_types = list(oidc_setup.allowed_user_types) + ['EXTERNAL']
    else:
        user.is_original_admin = True
    db.session.commit()
    response = _authorize_logged_in(client, app, user, org)
    assert parse_qs(urlparse(response.headers['Location']).query)['error'] == [
        'access_denied']
