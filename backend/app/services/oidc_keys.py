"""OIDC RS256 signing-key lifecycle and encrypted private-key storage."""
import json
import secrets
from datetime import datetime, timedelta

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from joserfc.jwk import RSAKey

from app import db
from app.crypto.key_manager import KeyManager
from app.models import OidcSigningKey, Organization
from app.services.audit_service import AuditService


class OidcKeyError(RuntimeError):
    """Signing-key configuration or persistence failure."""


def _system_org():
    org = Organization.query.filter(
        Organization.is_system_org.is_(True),
        Organization.is_deleted.is_(False),
    ).first()
    if org is None:
        raise OidcKeyError('找不到系統企業，無法安全保存 OIDC 簽章私鑰')
    return org


def _new_key_record():
    org = _system_org()
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    kid = secrets.token_urlsafe(24)
    jwk = RSAKey.import_key(public_pem).as_dict(private=False)
    jwk.update({'kid': kid, 'alg': 'RS256', 'use': 'sig'})
    encrypted = KeyManager.encrypt_file(org.secure_code, private_pem)

    return OidcSigningKey(
        kid=kid,
        algorithm='RS256',
        public_jwk=jwk,
        secret_ciphertext=encrypted['ciphertext'],
        secret_file_nonce=encrypted['file_nonce'],
        secret_wrapped_dek=encrypted['wrapped_dek'],
        secret_dek_nonce=encrypted['dek_nonce'],
        secret_encryption_key_sc=encrypted['encryption_key_sc'],
        status='active',
    )


def get_active_key():
    record = OidcSigningKey.query.filter_by(status='active').order_by(
        OidcSigningKey.created_at.desc()).first()
    if record is not None:
        return record

    record = _new_key_record()
    db.session.add(record)
    db.session.commit()
    return record


def rotate_key(actor_secure_code):
    now = datetime.utcnow()
    active_records = OidcSigningKey.query.filter_by(status='active').all()
    for record in active_records:
        record.status = 'retired'
        record.retired_at = now

    new_record = _new_key_record()
    db.session.add(new_record)
    AuditService.log(
        action='ROTATE',
        resource_type='OIDC_SIGNING_KEY',
        org_secure_code=_system_org().secure_code,
        user_secure_code=actor_secure_code,
        resource_id=new_record.kid,
        details=json.dumps({'retired_kids': [r.kid for r in active_records]}),
    )
    db.session.commit()
    return new_record


def get_public_jwks():
    # JWKS itself is a first use of the signing facility, so it must never
    # silently return an empty key set on a fresh installation.
    get_active_key()
    cutoff = datetime.utcnow() - timedelta(days=30)
    records = OidcSigningKey.query.filter(
        (OidcSigningKey.status == 'active') |
        ((OidcSigningKey.status == 'retired') &
         (OidcSigningKey.retired_at >= cutoff))
    ).order_by(OidcSigningKey.created_at.desc()).all()
    return {'keys': [dict(record.public_jwk) for record in records]}


def load_private_key(record):
    org = _system_org()
    private_pem = KeyManager.decrypt_file(
        org_sc=org.secure_code,
        ciphertext=bytes(record.secret_ciphertext),
        file_nonce=bytes(record.secret_file_nonce),
        wrapped_dek_b64=record.secret_wrapped_dek,
        dek_nonce_b64=record.secret_dek_nonce,
        encryption_key_sc=record.secret_encryption_key_sc,
    )
    return serialization.load_pem_private_key(private_pem, password=None)
