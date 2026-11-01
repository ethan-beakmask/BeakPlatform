"""Business rules for system-level OIDC client administration."""
import json
import secrets
from datetime import datetime
from urllib.parse import urlparse

from flask_babel import gettext as _
from werkzeug.security import generate_password_hash

from app import db
from app.models import OidcClient, OidcClientOrg, Organization, SystemSetting
from app.services.audit_service import AuditService
from app.services.oidc_org_defaults import ensure_scribe_org_defaults


VALID_USER_TYPES = frozenset({'ORG_ADMIN', 'EMPLOYEE', 'SYSTEM_ADMIN'})
VALID_EXTRA_CLAIMS = frozenset({'scribe'})
DEFAULT_USER_TYPES = ['ORG_ADMIN', 'EMPLOYEE', 'SYSTEM_ADMIN']


class OidcClientError(ValueError):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def _audit(action, resource_id, actor_secure_code, details=None):
    AuditService.log(
        action=action,
        resource_type='OIDC_CLIENT',
        user_secure_code=actor_secure_code,
        resource_id=resource_id,
        details=json.dumps(details or {}, ensure_ascii=False),
    )


def _validate_name(value):
    if not isinstance(value, str):
        raise OidcClientError(_('名稱長度必須為 1 到 100 字'))
    value = value.strip()
    if not 1 <= len(value) <= 100:
        raise OidcClientError(_('名稱長度必須為 1 到 100 字'))
    return value


def _validate_redirect_uris(value):
    if not isinstance(value, list) or not value:
        raise OidcClientError(_('redirect_uris 必須是非空陣列'))
    allow_http = bool(SystemSetting.get('oidc_allow_http_redirect', False))
    allowed_schemes = {'https'} | ({'http'} if allow_http else set())
    normalized = []
    for uri in value:
        if not isinstance(uri, str) or not uri.strip():
            raise OidcClientError(_('redirect URI 必須是絕對網址'))
        uri = uri.strip()
        parsed = urlparse(uri)
        if (parsed.scheme not in allowed_schemes or not parsed.netloc or
                parsed.fragment or '*' in uri):
            if parsed.fragment:
                raise OidcClientError(_('redirect URI 不可包含 fragment'))
            if '*' in uri:
                raise OidcClientError(_('redirect URI 不可包含萬用字元'))
            if parsed.scheme == 'http' and not allow_http:
                raise OidcClientError(_('redirect URI 必須使用 https'))
            raise OidcClientError(_('redirect URI 必須是絕對網址'))
        normalized.append(uri)
    return normalized


def _validate_user_types(value):
    if not isinstance(value, list) or not value:
        raise OidcClientError(_('allowed_user_types 必須是非空陣列'))
    if any(not isinstance(item, str) for item in value):
        raise OidcClientError(_('allowed_user_types 含有不支援的值'))
    if not set(value).issubset(VALID_USER_TYPES):
        raise OidcClientError(_('allowed_user_types 含有不支援的值'))
    return list(dict.fromkeys(value))


def _validate_extra_claims(value):
    if not isinstance(value, list):
        raise OidcClientError(_('extra_claims 必須是陣列'))
    if any(not isinstance(item, str) for item in value):
        raise OidcClientError(_('extra_claims 含有不支援的值'))
    if not set(value).issubset(VALID_EXTRA_CLAIMS):
        raise OidcClientError(_('extra_claims 含有不支援的值'))
    return list(dict.fromkeys(value))


def _new_client_id():
    while True:
        value = 'bpc_' + secrets.token_urlsafe(24)
        if OidcClient.query.filter_by(client_id=value).first() is None:
            return value


def _new_secret():
    return secrets.token_urlsafe(32)


def get_client(secure_code):
    record = OidcClient.query.filter_by(
        secure_code=secure_code, is_deleted=False).first()
    if record is None:
        raise OidcClientError(_('找不到 OIDC client'), 404)
    return record


def serialize_client(record, org_count=None):
    result = {
        'secure_code': record.secure_code,
        'client_id': record.client_id,
        'name': record.name,
        'is_active': bool(record.is_active),
        'redirect_uris': list(record.redirect_uris or []),
        'allowed_user_types': list(record.allowed_user_types or []),
        'extra_claims': list(record.extra_claims or []),
        'created_at': record.created_at.isoformat() if record.created_at else None,
    }
    if org_count is not None:
        result['authorized_org_count'] = org_count
    return result


def list_clients():
    records = OidcClient.query.filter_by(is_deleted=False).order_by(
        OidcClient.created_at.desc()).all()
    counts = dict(db.session.query(
        OidcClientOrg.client_secure_code,
        db.func.count(OidcClientOrg.id),
    ).group_by(OidcClientOrg.client_secure_code).all())
    return [serialize_client(r, counts.get(r.secure_code, 0)) for r in records]


def client_detail(record):
    result = serialize_client(record)
    rows = db.session.query(OidcClientOrg, Organization).join(
        Organization,
        Organization.secure_code == OidcClientOrg.org_secure_code,
    ).filter(
        OidcClientOrg.client_secure_code == record.secure_code,
        Organization.is_deleted.is_(False),
    ).order_by(Organization.name).all()
    result['organizations'] = [{
        'secure_code': org.secure_code,
        'code': org.code,
        'name': org.name,
        'domain_name': org.domain_name,
    } for _, org in rows]
    result['available_organizations'] = [{
        'secure_code': org.secure_code,
        'code': org.code,
        'name': org.name,
        'domain_name': org.domain_name,
    } for org in Organization.query.filter(
        Organization.is_deleted.is_(False),
        Organization.is_active.is_(True),
    ).order_by(Organization.name).all()]
    return result


def create_client(data, actor_secure_code):
    if not isinstance(data, dict):
        raise OidcClientError(_('請提供有效的 JSON 物件'))
    secret = _new_secret()
    record = OidcClient(
        client_id=_new_client_id(),
        client_secret_hash=generate_password_hash(secret),
        name=_validate_name(data.get('name')),
        redirect_uris=_validate_redirect_uris(data.get('redirect_uris')),
        allowed_user_types=_validate_user_types(
            data.get('allowed_user_types', DEFAULT_USER_TYPES)),
        extra_claims=_validate_extra_claims(data.get('extra_claims', [])),
        created_by_user_secure_code=actor_secure_code,
    )
    db.session.add(record)
    db.session.flush()
    _audit('CREATE', record.secure_code, actor_secure_code,
           {'client_id': record.client_id, 'name': record.name})
    db.session.commit()
    return record, secret


def update_client(record, data, actor_secure_code):
    if not isinstance(data, dict):
        raise OidcClientError(_('請提供有效的 JSON 物件'))
    old_claims = set(record.extra_claims or [])
    was_active = bool(record.is_active)
    if 'name' in data:
        record.name = _validate_name(data['name'])
    if 'redirect_uris' in data:
        record.redirect_uris = _validate_redirect_uris(data['redirect_uris'])
    if 'allowed_user_types' in data:
        record.allowed_user_types = _validate_user_types(data['allowed_user_types'])
    if 'extra_claims' in data:
        record.extra_claims = _validate_extra_claims(data['extra_claims'])
    if 'is_active' in data:
        if not isinstance(data['is_active'], bool):
            raise OidcClientError(_('is_active 必須是布林值'))
        record.is_active = data['is_active']
    record.updated_at = datetime.utcnow()

    if 'scribe' not in old_claims and 'scribe' in set(record.extra_claims or []):
        orgs = Organization.query.join(
            OidcClientOrg,
            OidcClientOrg.org_secure_code == Organization.secure_code,
        ).filter(
            OidcClientOrg.client_secure_code == record.secure_code,
            Organization.is_deleted.is_(False),
        ).all()
        for org in orgs:
            ensure_scribe_org_defaults(org)

    _audit('UPDATE', record.secure_code, actor_secure_code,
           {'updated_fields': sorted(data.keys())})
    if was_active and not record.is_active:
        _audit('DEACTIVATE', record.secure_code, actor_secure_code)
    db.session.commit()
    return record


def rotate_secret(record, actor_secure_code):
    secret = _new_secret()
    record.client_secret_hash = generate_password_hash(secret)
    record.updated_at = datetime.utcnow()
    _audit('ROTATE_SECRET', record.secure_code, actor_secure_code)
    db.session.commit()
    return secret


def delete_client(record, actor_secure_code):
    record.is_deleted = True
    record.is_active = False
    record.updated_at = datetime.utcnow()
    _audit('DELETE', record.secure_code, actor_secure_code)
    db.session.commit()


def authorize_org(record, org_secure_code, actor_secure_code):
    org = Organization.query.filter(
        Organization.secure_code == org_secure_code,
        Organization.is_deleted.is_(False),
        Organization.is_active.is_(True),
    ).first()
    if org is None:
        raise OidcClientError(_('只可授權有效企業'))
    existing = OidcClientOrg.query.filter_by(
        client_secure_code=record.secure_code,
        org_secure_code=org.secure_code,
    ).first()
    if existing is not None:
        raise OidcClientError(_('此企業已授權'), 409)
    grant = OidcClientOrg(
        client_secure_code=record.secure_code,
        org_secure_code=org.secure_code,
        created_by_user_secure_code=actor_secure_code,
    )
    db.session.add(grant)
    if 'scribe' in (record.extra_claims or []):
        ensure_scribe_org_defaults(org)
    _audit('AUTHORIZE_ORG', record.secure_code, actor_secure_code,
           {'org_secure_code': org.secure_code})
    db.session.commit()
    return grant


def revoke_org(record, org_secure_code, actor_secure_code):
    grant = OidcClientOrg.query.filter_by(
        client_secure_code=record.secure_code,
        org_secure_code=org_secure_code,
    ).first()
    if grant is None:
        raise OidcClientError(_('找不到企業授權'), 404)
    db.session.delete(grant)
    _audit('REVOKE_ORG', record.secure_code, actor_secure_code,
           {'org_secure_code': org_secure_code})
    db.session.commit()
