"""Central OIDC protocol implementation (issuer, client auth, code/refresh exchange, JWT)."""
import base64
import hashlib
import json
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote_plus, urlparse

from flask import request
from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey
from werkzeug.security import check_password_hash

from app import db
from app.models import (OidcAuthorizationCode, OidcClient, OidcClientOrg,
                        OidcRefreshToken, Organization, SystemSetting, User)
from app.services.audit_service import AuditService
from app.services.oidc_claims import build_claims
from app.services.oidc_keys import get_active_key, get_public_jwks, load_private_key
from app.utils.external_url import build_external_url, get_system_base_url


SCOPES = ('openid', 'profile', 'email')
logger = logging.getLogger(__name__)
CLAIMS = ('sub', 'name', 'employee_no', 'email', 'email_verified', 'org',
          'user_type', 'scribe_admin', 'project_groups')


def issuer():
    base = get_system_base_url()
    if not base:
        return None
    value = (build_external_url('') or '').rstrip('/')
    if urlparse(value).scheme == 'http' and not bool(
            SystemSetting.get('oidc_allow_http_redirect', False)):
        return None
    return value or None


def query_client(client_id, active_only=True):
    query = OidcClient.query.filter(OidcClient.client_id == client_id,
                                    OidcClient.is_deleted.is_(False))
    if active_only:
        query = query.filter(OidcClient.is_active.is_(True))
    return query.first()


def discovery_document():
    value = issuer()
    return {
        'issuer': value, 'authorization_endpoint': value + '/oauth/authorize',
        'token_endpoint': value + '/oauth/token',
        'userinfo_endpoint': value + '/oauth/userinfo',
        'jwks_uri': value + '/oauth/jwks', 'response_types_supported': ['code'],
        'grant_types_supported': ['authorization_code', 'refresh_token'],
        'subject_types_supported': ['public'],
        'id_token_signing_alg_values_supported': ['RS256'],
        'token_endpoint_auth_methods_supported': ['client_secret_basic', 'client_secret_post'],
        'code_challenge_methods_supported': ['S256'],
        'scopes_supported': list(SCOPES), 'claims_supported': list(CLAIMS),
    }


def token_hash(value): return hashlib.sha256(value.encode()).hexdigest()


def audit(action, client_id, reason, status=200, user=None, org_sc=None):
    AuditService.log_auth_event(
        action=action, org_secure_code=org_sc,
        user_secure_code=getattr(user, 'secure_code', None),
        details=json.dumps({'client_id': client_id, 'reason': reason}),
        status_code=status)


def validate_subject(client, user_sc, require_contract=False):
    user = User.query.filter(User.secure_code == user_sc,
                             User.is_deleted.is_(False),
                             User.is_active.is_(True)).first()
    if user is None: return None, None, 'user_inactive'
    if user.user_type == 'EXTERNAL' or user.user_type not in (client.allowed_user_types or []):
        return user, None, 'user_type_denied'
    org = Organization.query.filter(
        Organization.secure_code == user.org_secure_code,
        Organization.is_deleted.is_(False), Organization.is_active.is_(True)).first()
    if org is None: return user, None, 'organization_inactive'
    if user.user_type == 'SYSTEM_ADMIN' and not org.is_system_org:
        return user, org, 'system_admin_wrong_org'
    if require_contract and not org.is_contract_valid():
        return user, org, 'contract_invalid'
    grant = OidcClientOrg.query.filter_by(
        client_secure_code=client.secure_code,
        org_secure_code=org.secure_code).first()
    if grant is None: return user, org, 'organization_not_authorized'
    return user, org, None


def authenticate_client():
    """機密型 client 認證：client_secret_basic 或 client_secret_post，兩者擇一。

    傳輸是否允許 http 由 issuer()（oidc_allow_http_redirect）單一決定，這裡不另做判斷。
    """
    auth = request.authorization
    form_id = request.form.get('client_id')
    form_secret = request.form.get('client_secret')
    if auth is not None and auth.type == 'basic':
        if form_secret:
            return None  # RFC 6749 2.3：不得同時使用兩種認證方式
        # RFC 6749 2.3.1：Basic 的帳密先經 form-urlencoded 編碼
        client_id = unquote_plus(auth.username or '')
        secret = unquote_plus(auth.password or '')
    elif form_id and form_secret:
        client_id, secret = form_id, form_secret
    else:
        return None
    record = query_client(client_id, active_only=False)
    if record is None or not check_password_hash(record.client_secret_hash, secret):
        return None
    return record


def create_s256_code_challenge(verifier):
    digest = hashlib.sha256(verifier.encode('ascii')).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')


def _sign(claims):
    key_record = get_active_key()
    private = RSAKey.import_key(load_private_key(key_record))
    return jwt.encode({'alg': 'RS256', 'kid': key_record.kid}, claims,
                      private, algorithms=['RS256'])


def _tokens(client, user, org, scope, auth_time, nonce, family_id=None,
            absolute_expires_at=None, auth_code_hash=None):
    now = datetime.utcnow(); now_ts = int(time.time())
    access_claims = {'iss': issuer(), 'sub': user.secure_code,
                     'aud': client.client_id, 'client_id': client.client_id,
                     'org_key': org.secure_code, 'scope': scope,
                     'iat': now_ts, 'exp': now_ts + 900,
                     'jti': secrets.token_urlsafe(48)}
    id_claims = build_claims(user, scope, client)
    id_claims.update({'iss': issuer(), 'aud': client.client_id,
                      'iat': now_ts, 'exp': now_ts + 900,
                      'auth_time': int(auth_time.replace(tzinfo=timezone.utc).timestamp())})
    if nonce: id_claims['nonce'] = nonce
    refresh = secrets.token_urlsafe(48)
    absolute = absolute_expires_at or auth_time + timedelta(hours=8)
    expires = min(now + timedelta(hours=8), absolute)
    record = OidcRefreshToken(
        token_hash=token_hash(refresh), client_secure_code=client.secure_code,
        user_secure_code=user.secure_code, org_secure_code=org.secure_code,
        scope=scope, family_id=family_id or secrets.token_urlsafe(32),
        auth_code_hash=auth_code_hash, issued_at=now, expires_at=expires,
        absolute_expires_at=absolute)
    db.session.add(record)
    return {'access_token': _sign(access_claims), 'token_type': 'Bearer',
            'expires_in': 900, 'id_token': _sign(id_claims),
            'refresh_token': refresh, 'scope': scope}, record


def exchange_authorization_code(client):
    raw = request.form.get('code', '')
    # 鎖列：同一個 code 併發兌換時，第二個請求等第一個提交後才讀到 used_at
    record = OidcAuthorizationCode.query.filter_by(
        code_hash=token_hash(raw)).with_for_update().first()
    if (not client.is_active or client.is_deleted or record is None or
            record.client_secure_code != client.secure_code):
        audit('OIDC_TOKEN_DENIED', client.client_id, 'invalid_code', 400)
        return None, 'invalid_grant'
    now = datetime.utcnow()
    if record.used_at is not None:
        OidcRefreshToken.query.filter_by(auth_code_hash=record.code_hash).update(
            {'revoked_at': now}, synchronize_session=False)
        db.session.commit(); audit('OIDC_TOKEN_DENIED', client.client_id, 'code_replay', 400)
        return None, 'invalid_grant'
    if record.expires_at <= now or request.form.get('redirect_uri') != record.redirect_uri:
        audit('OIDC_TOKEN_DENIED', client.client_id,
              'code_expired_or_redirect_mismatch', 400)
        return None, 'invalid_grant'
    verifier = request.form.get('code_verifier', '')
    if not (43 <= len(verifier) <= 128):
        audit('OIDC_TOKEN_DENIED', client.client_id, 'invalid_verifier', 400)
        return None, 'invalid_grant'
    challenge = create_s256_code_challenge(verifier)
    if record.code_challenge_method != 'S256' or not secrets.compare_digest(challenge, record.code_challenge):
        audit('OIDC_TOKEN_DENIED', client.client_id, 'pkce_failed', 400)
        return None, 'invalid_grant'
    user, org, reason = validate_subject(client, record.user_secure_code)
    if reason:
        record.used_at = now; db.session.commit()
        audit('OIDC_TOKEN_DENIED', client.client_id, reason, 400, user, record.org_secure_code)
        return None, 'invalid_grant'
    record.used_at = now
    result, _ = _tokens(client, user, org, record.scope, record.auth_time,
                        record.nonce, auth_code_hash=record.code_hash)
    db.session.commit(); audit('OIDC_TOKEN_ISSUED', client.client_id, 'authorization_code', user=user, org_sc=org.secure_code)
    return result, None


def revoke_family(record, reason, client_id):
    now = datetime.utcnow()
    OidcRefreshToken.query.filter_by(family_id=record.family_id).update(
        {'revoked_at': now}, synchronize_session=False)
    db.session.commit(); audit('OIDC_REFRESH_DENIED', client_id, reason, 400,
                               org_sc=record.org_secure_code)


def exchange_refresh_token(client):
    raw = request.form.get('refresh_token', '')
    # 鎖列：同一張 refresh 併發使用時只會有一個成功，另一個視為重放
    record = OidcRefreshToken.query.filter_by(
        token_hash=token_hash(raw)).with_for_update().first()
    if record is None or record.client_secure_code != client.secure_code:
        audit('OIDC_REFRESH_DENIED', client.client_id, 'unknown_refresh', 400)
        return None, 'invalid_grant'
    if not client.is_active or client.is_deleted:
        revoke_family(record, 'client_inactive', client.client_id)
        return None, 'invalid_grant'
    if record.revoked_at is not None or record.replaced_by_hash:
        revoke_family(record, 'refresh_reuse', client.client_id); return None, 'invalid_grant'
    now = datetime.utcnow()
    if record.expires_at <= now or record.absolute_expires_at <= now:
        audit('OIDC_REFRESH_DENIED', client.client_id, 'refresh_expired', 400,
              org_sc=record.org_secure_code)
        return None, 'invalid_grant'
    user, org, reason = validate_subject(client, record.user_secure_code, require_contract=True)
    if reason:
        revoke_family(record, reason, client.client_id); return None, 'invalid_grant'
    auth_time = record.absolute_expires_at - timedelta(hours=8)
    result, new_record = _tokens(
        client, user, org, record.scope, auth_time, None,
        family_id=record.family_id,
        absolute_expires_at=record.absolute_expires_at,
        auth_code_hash=record.auth_code_hash)
    record.replaced_by_hash = new_record.token_hash; record.revoked_at = now
    db.session.commit(); audit('OIDC_TOKEN_ISSUED', client.client_id, 'refresh_token', user=user, org_sc=org.secure_code)
    return result, None


def decode_access_token(value):
    try:
        token = jwt.decode(value, KeySet.import_key_set(get_public_jwks()),
                           algorithms=['RS256'])
        claims = token.claims; now = int(time.time())
        if claims.get('iss') != issuer() or int(claims.get('exp', 0)) <= now:
            logger.warning('OIDC access token rejected: issuer_or_expiry')
            return None
        client = query_client(claims.get('client_id'))
        if client is None or claims.get('aud') != client.client_id:
            logger.warning('OIDC access token rejected: client_or_audience')
            return None
        user, org, reason = validate_subject(client, claims.get('sub'))
        if reason or org.secure_code != claims.get('org_key'):
            logger.warning('OIDC access token rejected: %s', reason or 'organization_mismatch')
            return None
        return claims, client, user
    except Exception as exc:
        logger.warning('OIDC access token validation failed: %s',
                       type(exc).__name__)
        return None
