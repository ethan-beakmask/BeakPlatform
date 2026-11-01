"""OIDC provider persistence models (PF-327 P1)."""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, LargeBinary
from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from .. import db
from ..utils.security import generate_secure_code


def _default_allowed_user_types():
    return ['ORG_ADMIN', 'EMPLOYEE', 'SYSTEM_ADMIN']


class OidcClient(db.Model):
    __tablename__ = 'oidc_clients'

    id = Column(Integer, primary_key=True)
    secure_code = Column(String(32), unique=True, nullable=False,
                         default=generate_secure_code, index=True)
    client_id = Column(String(64), unique=True, nullable=False, index=True)
    client_secret_hash = Column(String(255), nullable=False)
    name = Column(String(100), nullable=False)
    redirect_uris = Column(JSONB, nullable=False, default=list)
    post_logout_redirect_uris = Column(JSONB, nullable=False, default=list)
    allowed_user_types = Column(
        JSONB, nullable=False, default=_default_allowed_user_types)
    extra_claims = Column(JSONB, nullable=False, default=list)
    is_active = Column(Boolean, nullable=False, default=True)
    is_deleted = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow,
                        onupdate=datetime.utcnow)
    created_by_user_secure_code = Column(String(32), nullable=True)


class OidcClientOrg(db.Model):
    __tablename__ = 'oidc_client_orgs'
    __table_args__ = (
        UniqueConstraint('client_secure_code', 'org_secure_code',
                         name='uq_oidc_client_org'),
    )

    id = Column(Integer, primary_key=True)
    secure_code = Column(String(32), unique=True, nullable=False,
                         default=generate_secure_code, index=True)
    client_secure_code = Column(
        String(32), ForeignKey('oidc_clients.secure_code'), nullable=False,
        index=True)
    org_secure_code = Column(
        String(32), ForeignKey('organizations.secure_code'), nullable=False,
        index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_by_user_secure_code = Column(String(32), nullable=True)


class OidcAuthorizationCode(db.Model):
    __tablename__ = 'oidc_authorization_codes'

    id = Column(Integer, primary_key=True)
    code_hash = Column(String(64), unique=True, nullable=False, index=True)
    client_secure_code = Column(
        String(32), ForeignKey('oidc_clients.secure_code'), nullable=False,
        index=True)
    user_secure_code = Column(
        String(32), ForeignKey('users.secure_code'), nullable=False, index=True)
    org_secure_code = Column(
        String(32), ForeignKey('organizations.secure_code'), nullable=False,
        index=True)
    redirect_uri = Column(Text, nullable=False)
    scope = Column(String(255), nullable=False)
    nonce = Column(String(255), nullable=True)
    code_challenge = Column(String(128), nullable=False)
    code_challenge_method = Column(String(10), nullable=False)
    auth_time = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class OidcRefreshToken(db.Model):
    __tablename__ = 'oidc_refresh_tokens'

    id = Column(Integer, primary_key=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    client_secure_code = Column(
        String(32), ForeignKey('oidc_clients.secure_code'), nullable=False,
        index=True)
    user_secure_code = Column(
        String(32), ForeignKey('users.secure_code'), nullable=False, index=True)
    org_secure_code = Column(
        String(32), ForeignKey('organizations.secure_code'), nullable=False,
        index=True)
    scope = Column(String(255), nullable=False)
    family_id = Column(String(64), nullable=False, index=True)
    auth_code_hash = Column(String(64), nullable=True, index=True)
    issued_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    absolute_expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    replaced_by_hash = Column(String(64), nullable=True)


class OidcSigningKey(db.Model):
    __tablename__ = 'oidc_signing_keys'

    id = Column(Integer, primary_key=True)
    kid = Column(String(64), unique=True, nullable=False, index=True)
    algorithm = Column(String(10), nullable=False, default='RS256')
    public_jwk = Column(JSONB, nullable=False)
    secret_ciphertext = Column(LargeBinary, nullable=False)
    secret_file_nonce = Column(LargeBinary, nullable=False)
    secret_wrapped_dek = Column(String(255), nullable=False)
    secret_dek_nonce = Column(String(64), nullable=False)
    # KeyManager.decrypt_file also needs the exact wrapping Org Key version.
    secret_encryption_key_sc = Column(String(32), nullable=False)
    status = Column(String(10), nullable=False, default='active', index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    retired_at = Column(DateTime, nullable=True, index=True)
