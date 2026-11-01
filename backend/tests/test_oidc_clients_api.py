"""System-level OIDC client administration API tests."""
import json
import sys
from pathlib import Path

import pytest
from werkzeug.security import check_password_hash

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db
from app.models import OidcClient, OidcClientOrg, Organization, Role, SystemSetting
from backend.tests.conftest import _login_user_directly


APP_PREFIX = '/beakplatform'
BASE = APP_PREFIX + '/api/oidc-clients/'


@pytest.fixture
def system_client(client, app, system_admin, test_org):
    _login_user_directly(client, app, system_admin, test_org)
    return client


@pytest.fixture
def employee_client(client, app, test_user, test_org):
    _login_user_directly(client, app, test_user, test_org)
    return client


def _payload(**updates):
    data = {
        'name': 'BeakScribe',
        'redirect_uris': ['https://scribe.example.com/callback'],
        'allowed_user_types': ['ORG_ADMIN', 'EMPLOYEE'],
        'extra_claims': [],
    }
    data.update(updates)
    return data


def _create(client, **updates):
    return client.post(BASE, json=_payload(**updates))


def _active_org(code, secure_code, active=True):
    org = Organization(
        secure_code=secure_code,
        code=code,
        name=code,
        domain_name=f'{code.lower()}.local',
        is_active=active,
        is_deleted=False,
    )
    db.session.add(org)
    db.session.commit()
    return org


def test_create_returns_secret_once_and_never_serializes_hash(system_client):
    response = _create(system_client)
    assert response.status_code == 201
    body = response.get_json()['client']
    secret = body['client_secret']
    record = OidcClient.query.filter_by(secure_code=body['secure_code']).one()

    assert secret
    assert check_password_hash(record.client_secret_hash, secret)
    assert all(secret not in str(getattr(record, column.name))
               for column in record.__table__.columns)

    listing = system_client.get(BASE).get_json()
    detail = system_client.get(BASE + record.secure_code).get_json()
    serialized = json.dumps({'listing': listing, 'detail': detail})
    assert 'client_secret' not in serialized
    assert 'client_secret_hash' not in serialized
    assert record.client_secret_hash not in serialized


@pytest.mark.parametrize('redirect_uris', [
    ['http://scribe.example.com/callback'],
    ['https://scribe.example.com/callback#fragment'],
    ['https://*.example.com/callback'],
    ['/callback'],
    [],
])
def test_redirect_uri_rejections(system_client, redirect_uris):
    response = _create(system_client, redirect_uris=redirect_uris)
    assert response.status_code == 400


def test_http_redirect_can_be_enabled_explicitly(system_client):
    SystemSetting.set(
        'oidc_allow_http_redirect', True, value_type='boolean', category='general')
    response = _create(
        system_client, redirect_uris=['http://localhost:8080/callback'])
    assert response.status_code == 201


@pytest.mark.parametrize('allowed_user_types', [
    ['EXTERNAL'], ['ORG_ADMIN', 'UNKNOWN'], [],
])
def test_allowed_user_types_rejections(system_client, allowed_user_types):
    response = _create(system_client, allowed_user_types=allowed_user_types)
    assert response.status_code == 400


def test_org_authorization_validation_and_scribe_seeding(system_client):
    active = _active_org('ACTIVE_ORG', 'active_org_000000001')
    inactive = _active_org('INACTIVE_ORG', 'inactive_org_0000001', active=False)
    no_scribe = _create(system_client).get_json()['client']

    rejected = system_client.post(
        BASE + no_scribe['secure_code'] + '/orgs',
        json={'org_secure_code': inactive.secure_code})
    accepted = system_client.post(
        BASE + no_scribe['secure_code'] + '/orgs',
        json={'org_secure_code': active.secure_code})
    duplicate = system_client.post(
        BASE + no_scribe['secure_code'] + '/orgs',
        json={'org_secure_code': active.secure_code})

    assert rejected.status_code == 400
    assert accepted.status_code == 201
    assert duplicate.status_code == 409
    assert Role.query.filter_by(
        org_secure_code=active.secure_code, code='SCRIBE_ADMIN').count() == 0

    upgraded = system_client.put(
        BASE + no_scribe['secure_code'], json={'extra_claims': ['scribe']})
    assert upgraded.status_code == 200
    assert Role.query.filter_by(
        org_secure_code=active.secure_code, code='SCRIBE_ADMIN').count() == 1


def test_scribe_client_seeds_role_when_org_is_added(system_client):
    org = _active_org('SCRIBE_ORG', 'scribe_org_000000001')
    client = _create(system_client, extra_claims=['scribe']).get_json()['client']

    response = system_client.post(
        BASE + client['secure_code'] + '/orgs',
        json={'org_secure_code': org.secure_code})

    assert response.status_code == 201
    role = Role.query.filter_by(
        org_secure_code=org.secure_code, code='SCRIBE_ADMIN').one()
    assert role.description == '可處理 BeakScribe 中同企業離職者的資料轉移與刪除'
    assert OidcClientOrg.query.filter_by(
        client_secure_code=client['secure_code'],
        org_secure_code=org.secure_code).count() == 1


def test_secret_rotation_immediately_invalidates_old_secret(system_client):
    created = _create(system_client).get_json()['client']
    old_secret = created['client_secret']
    response = system_client.post(
        BASE + created['secure_code'] + '/rotate-secret')
    new_secret = response.get_json()['client_secret']
    record = OidcClient.query.filter_by(secure_code=created['secure_code']).one()

    assert response.status_code == 200
    assert not check_password_hash(record.client_secret_hash, old_secret)
    assert check_password_hash(record.client_secret_hash, new_secret)


def test_meta_without_system_base_url_has_null_issuer(system_client):
    assert SystemSetting.query.filter_by(key='system_base_url').count() == 0
    response = system_client.get(BASE + 'meta')
    assert response.status_code == 200
    assert response.get_json()['issuer'] is None
    assert response.get_json()['discovery_url'] is None


@pytest.mark.parametrize('method,path,payload', [
    ('get', '', None),
    ('post', '', _payload()),
    ('get', 'dummy', None),
    ('put', 'dummy', {'name': 'x'}),
    ('post', 'dummy/rotate-secret', None),
    ('delete', 'dummy', None),
    ('post', 'dummy/orgs', {'org_secure_code': 'dummy'}),
    ('delete', 'dummy/orgs/org', None),
    ('get', 'signing-keys', None),
    ('post', 'signing-keys/rotate', None),
    ('get', 'meta', None),
])
@pytest.mark.parametrize('client_fixture', ['admin_client', 'employee_client'])
def test_non_system_users_are_rejected_by_every_api(
    request, client_fixture, method, path, payload
):
    test_client = request.getfixturevalue(client_fixture)
    response = getattr(test_client, method)(BASE + path, json=payload)
    assert response.status_code in (302, 403)
