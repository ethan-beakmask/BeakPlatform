"""OIDC encrypted RS256 signing-key tests."""
from datetime import datetime, timedelta

from app import db
from app.models import OidcSigningKey, Organization
from app.services.oidc_keys import (
    get_active_key,
    get_public_jwks,
    load_private_key,
    rotate_key,
)


def _system_org():
    org = Organization(
        secure_code='oidc_system_org_0001',
        code='OIDC_SYSTEM',
        name='OIDC System',
        domain_name='oidc-system.local',
        is_system_org=True,
        is_active=True,
        is_deleted=False,
    )
    db.session.add(org)
    db.session.commit()
    return org


def test_active_key_is_created_lazily_and_private_material_is_encrypted(app):
    _system_org()
    record = get_active_key()

    assert record.status == 'active'
    assert record.algorithm == 'RS256'
    assert record.public_jwk['kid'] == record.kid
    assert record.public_jwk['alg'] == 'RS256'
    assert b'PRIVATE KEY' not in bytes(record.secret_ciphertext)
    assert load_private_key(record).key_size == 3072
    assert get_active_key().id == record.id


def test_rotation_and_jwks_retention_window(app):
    _system_org()
    old = get_active_key()
    new = rotate_key(None)
    db.session.refresh(old)

    current_kids = {item['kid'] for item in get_public_jwks()['keys']}
    assert old.status == 'retired'
    assert old.retired_at is not None
    assert new.status == 'active'
    assert current_kids == {old.kid, new.kid}

    old.retired_at = datetime.utcnow() - timedelta(days=31)
    db.session.commit()
    retained_kids = {item['kid'] for item in get_public_jwks()['keys']}
    assert retained_kids == {new.kid}
    assert OidcSigningKey.query.count() == 2
