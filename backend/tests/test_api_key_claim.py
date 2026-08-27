import base64
import os
from datetime import datetime, timedelta

import pytest

os.environ.setdefault("SYSTEM_ORG_CODE", "system.local")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app import db
from app.models import ApiKey, Organization, User
from app.models.api_key import STATUS_ACTIVE
from app.services import api_key_claim_service


SECRET_BYTES = b'0123456789abcdef0123456789abcdef'
PUBLIC_ERROR = '無法領取 API Key'


def _api_key(org_secure_code, secure_code='api_key_claim_test_key', status=STATUS_ACTIVE):
    record = ApiKey(
        secure_code=secure_code,
        org_secure_code=org_secure_code,
        key_id=f'ak_{secure_code[-8:]}',
        name='Claim Test Key',
        secret_ciphertext=b'ciphertext',
        secret_file_nonce=b'file_nonce',
        secret_wrapped_dek='wrapped_dek',
        secret_dek_nonce='dek_nonce',
        secret_encryption_key_sc='enc_key_sc',
        status=status,
        scopes={'form_template': ['form_tpl_1']},
        is_deleted=False,
    )
    db.session.add(record)
    db.session.commit()
    return record


def _user(org_secure_code, secure_code, username):
    user = User(
        secure_code=secure_code,
        org_secure_code=org_secure_code,
        username=username,
        email=f'{username}@example.test',
        display_name=username,
        is_active=True,
        is_deleted=False,
    )
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()
    return user


def _other_org():
    org = Organization(
        secure_code='claim_other_org_0001',
        code='CLAIM_OTHER',
        name='Claim Other Organization',
        domain_name='claim-other.local',
        is_active=True,
        is_deleted=False,
    )
    db.session.add(org)
    db.session.commit()
    return org


def _claim(api_key, user, ttl_hours=72):
    return api_key_claim_service.create_claim(
        api_key_secure_code=api_key.secure_code,
        org_secure_code=api_key.org_secure_code,
        beneficiary_user_secure_code=user.secure_code,
        form_instance_secure_code='form_instance_claim_test',
        ttl_hours=ttl_hours,
    )


def test_beneficiary_can_claim_once(app, test_org, test_user, monkeypatch):
    api_key = _api_key(test_org.secure_code)
    claim = _claim(api_key, test_user)
    monkeypatch.setattr(
        api_key_claim_service.api_key_service,
        'decrypt_secret',
        lambda record: SECRET_BYTES,
    )

    record, secret_b64 = api_key_claim_service.claim_once(
        claim.secure_code,
        test_user.secure_code,
        test_org.secure_code,
        source_ip='203.0.113.10',
    )

    db.session.refresh(claim)
    assert record.secure_code == api_key.secure_code
    assert secret_b64 == base64.urlsafe_b64encode(SECRET_BYTES).decode('ascii')
    assert claim.claimed_at is not None
    assert claim.claimed_ip == '203.0.113.10'


def test_second_claim_is_rejected_without_decrypt(app, test_org, test_user, monkeypatch):
    api_key = _api_key(test_org.secure_code, secure_code='api_key_second_claim')
    claim = _claim(api_key, test_user)
    decrypt_calls = []

    def fake_decrypt(record):
        decrypt_calls.append(record.secure_code)
        return SECRET_BYTES

    monkeypatch.setattr(api_key_claim_service.api_key_service, 'decrypt_secret', fake_decrypt)
    api_key_claim_service.claim_once(
        claim.secure_code, test_user.secure_code, test_org.secure_code,
        source_ip='198.51.100.1',
    )

    with pytest.raises(api_key_claim_service.ClaimError) as exc_info:
        api_key_claim_service.claim_once(
            claim.secure_code, test_user.secure_code, test_org.secure_code,
            source_ip='198.51.100.2',
        )

    db.session.refresh(claim)
    assert str(exc_info.value) == PUBLIC_ERROR
    assert decrypt_calls == [api_key.secure_code]
    assert claim.claimed_ip == '198.51.100.1'


def test_non_beneficiary_is_rejected(app, test_org, test_user, monkeypatch):
    api_key = _api_key(test_org.secure_code, secure_code='api_key_wrong_user')
    claim = _claim(api_key, test_user)
    other_user = _user(test_org.secure_code, 'claim_other_user_0001', 'claim_other')

    def fail_if_called(record):
        raise AssertionError(f'decrypt must not be called for {record.secure_code}')

    monkeypatch.setattr(api_key_claim_service.api_key_service, 'decrypt_secret', fail_if_called)

    with pytest.raises(api_key_claim_service.ClaimError) as exc_info:
        api_key_claim_service.claim_once(
            claim.secure_code, other_user.secure_code, test_org.secure_code)

    db.session.refresh(claim)
    assert str(exc_info.value) == PUBLIC_ERROR
    assert claim.claimed_at is None
    assert claim.beneficiary_user_secure_code == test_user.secure_code


def test_expired_claim_is_rejected(app, test_org, test_user, monkeypatch):
    api_key = _api_key(test_org.secure_code, secure_code='api_key_expired')
    claim = _claim(api_key, test_user)
    claim.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.session.commit()
    monkeypatch.setattr(
        api_key_claim_service.api_key_service,
        'decrypt_secret',
        lambda record: pytest.fail('expired claim decrypted a secret'),
    )

    with pytest.raises(api_key_claim_service.ClaimError) as exc_info:
        api_key_claim_service.claim_once(
            claim.secure_code, test_user.secure_code, test_org.secure_code)

    assert str(exc_info.value) == PUBLIC_ERROR
    assert claim.claimed_at is None
    assert claim.expires_at < datetime.utcnow()


def test_cross_org_claim_is_rejected(app, test_org, test_user, monkeypatch):
    other_org = _other_org()
    api_key = _api_key(test_org.secure_code, secure_code='api_key_cross_org')
    claim = _claim(api_key, test_user)
    decrypt_called = False

    def fake_decrypt(record):
        nonlocal decrypt_called
        decrypt_called = True
        return SECRET_BYTES

    monkeypatch.setattr(api_key_claim_service.api_key_service, 'decrypt_secret', fake_decrypt)

    with pytest.raises(api_key_claim_service.ClaimError) as exc_info:
        api_key_claim_service.claim_once(
            claim.secure_code, test_user.secure_code, other_org.secure_code)

    assert str(exc_info.value) == PUBLIC_ERROR
    assert decrypt_called is False
    assert claim.org_secure_code == test_org.secure_code
