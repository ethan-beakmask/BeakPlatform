"""Public OpenID Connect provider endpoints."""
import secrets
import time
from datetime import datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flask import (Blueprint, jsonify, make_response as app_response, redirect,
                   render_template, request, session, url_for)
from flask_login import current_user
from flask_babel import gettext as _

from app import csrf, db, limiter
from app.models import OidcAuthorizationCode
from app.security.client_ip import client_ip_key
from app.security.decorators import public_route
from app.services.oidc_claims import build_claims
from app.services.oidc_keys import get_public_jwks
from app.services.oidc_login_resume import PENDING_MAX_AGE
from app.services.oidc_server import (
    audit, authenticate_client, decode_access_token, discovery_document,
    exchange_authorization_code, exchange_refresh_token, issuer, query_client,
    token_hash, validate_subject,
)
from app.services.rate_limit_service import RateLimitService


oidc_provider_bp = Blueprint('oidc_provider', __name__)
PENDING_FIELDS = ('client_id', 'redirect_uri', 'scope', 'state', 'nonce',
                  'code_challenge', 'code_challenge_method', 'response_type')


def _disabled():
    if issuer() is None:
        return jsonify({'error': 'oidc_disabled'}), 503
    return None


def _error_page(message):
    return render_template('pages/oidc/error.html', message=message), 400


def _redirect_error(uri, error, state, client_id, reason):
    audit('OIDC_AUTHORIZE_DENIED', client_id, reason, 400,
          user=current_user if current_user.is_authenticated else None,
          org_sc=getattr(current_user, 'org_secure_code', None))
    return redirect(_append_query(uri, error=error, state=state))


def _append_query(uri, **values):
    parts = urlsplit(uri)
    query = list(parse_qsl(parts.query, keep_blank_values=True))
    query.extend((key, value) for key, value in values.items()
                 if value is not None)
    return urlunsplit((parts.scheme, parts.netloc, parts.path,
                       urlencode(query), parts.fragment))


def _save_pending(params):
    session['oidc_pending'] = {
        **{field: params.get(field) for field in PENDING_FIELDS},
        'created_at': time.time(),
    }


def _authorize(params):
    client_id = params.get('client_id')
    client = query_client(client_id)
    if client is None:
        audit('OIDC_AUTHORIZE_DENIED', client_id, 'invalid_client', 400)
        return _error_page(_('無效或已停用的應用程式。'))
    redirect_uri = params.get('redirect_uri')
    if redirect_uri not in (client.redirect_uris or []):
        audit('OIDC_AUTHORIZE_DENIED', client_id, 'invalid_redirect_uri', 400)
        return _error_page(_('redirect_uri 不符合已登記的網址。'))
    state = params.get('state')
    if params.get('response_type') != 'code':
        return _redirect_error(redirect_uri, 'unsupported_response_type', state,
                               client_id, 'unsupported_response_type')
    if (not params.get('code_challenge') or
            params.get('code_challenge_method') != 'S256'):
        return _redirect_error(redirect_uri, 'invalid_request', state, client_id,
                               'pkce_s256_required')
    scopes = (params.get('scope') or '').split()
    if 'openid' not in scopes or any(scope not in ('openid', 'profile', 'email')
                                    for scope in scopes):
        return _redirect_error(redirect_uri, 'invalid_scope', state, client_id,
                               'invalid_scope')

    if not current_user.is_authenticated:
        _save_pending(params)
        return redirect(url_for('auth.login'))
    if current_user.must_change_password:
        _save_pending(params)
        return redirect(url_for('auth.change_password'))
    if current_user.is_original_admin:
        session.pop('oidc_pending', None)
        return _redirect_error(redirect_uri, 'access_denied', state, client_id,
                               'original_admin_denied')

    user, org, reason = validate_subject(client, current_user.secure_code)
    if reason:
        session.pop('oidc_pending', None)
        return _redirect_error(redirect_uri, 'access_denied', state, client_id,
                               reason)
    code = secrets.token_urlsafe(48)
    now = datetime.utcnow()
    auth_time = user.last_login_at or now
    record = OidcAuthorizationCode(
        code_hash=token_hash(code), client_secure_code=client.secure_code,
        user_secure_code=user.secure_code, org_secure_code=org.secure_code,
        redirect_uri=redirect_uri, scope=' '.join(scopes),
        nonce=params.get('nonce'), code_challenge=params['code_challenge'],
        code_challenge_method='S256', auth_time=auth_time,
        expires_at=now + timedelta(seconds=60))
    db.session.add(record); db.session.commit()
    session.pop('oidc_pending', None)
    audit('OIDC_AUTHORIZE_SUCCESS', client_id, 'code_issued', user=user,
          org_sc=org.secure_code)
    return redirect(_append_query(redirect_uri, code=code, state=state,
                                  iss=issuer()))


@oidc_provider_bp.route('/.well-known/openid-configuration')
@public_route
def discovery():
    disabled = _disabled()
    return disabled or jsonify(discovery_document())


@oidc_provider_bp.route('/oauth/jwks')
@public_route
def jwks():
    disabled = _disabled()
    return disabled or jsonify(get_public_jwks())


@oidc_provider_bp.route('/oauth/authorize')
@public_route
def authorize():
    disabled = _disabled()
    return disabled or _authorize(request.args)


@oidc_provider_bp.route('/oauth/authorize/resume')
@public_route
def authorize_resume():
    disabled = _disabled()
    if disabled: return disabled
    pending = session.get('oidc_pending')
    try:
        expired = (not isinstance(pending, dict) or
                   time.time() - float(pending['created_at']) > PENDING_MAX_AGE)
    except (KeyError, TypeError, ValueError):
        expired = True
    if expired:
        audit('OIDC_AUTHORIZE_DENIED',
              pending.get('client_id') if isinstance(pending, dict) else None,
              'pending_expired', 400)
        session.pop('oidc_pending', None)
        return _error_page(_('授權請求已過期，請回到原系統重新登入。'))
    result = _authorize(pending)
    # resume 是登入表單 POST 的 302 鏈末端，Chrome 對整條鏈套用 CSP form-action 'self'，
    # 跨來源的 redirect_uri 會被擋；改用 200 中繼頁做一般導航（不受 form-action 管）
    if result.status_code == 302:
        target = result.headers['Location']
        page = render_template('pages/oidc/redirect.html', target=target)
        response = app_response(page, 200)
        response.headers['Cache-Control'] = 'no-store'
        return response
    return result


@oidc_provider_bp.route('/oauth/token', methods=['POST'])
@public_route
@csrf.exempt
@limiter.limit(lambda: RateLimitService.get_limit('oidc_token'),
               key_func=client_ip_key)
def token():
    disabled = _disabled()
    if disabled: return disabled
    client = authenticate_client()
    if client is None:
        audit('OIDC_TOKEN_DENIED', request.form.get('client_id'),
              'invalid_client', 401)
        response = jsonify({'error': 'invalid_client'})
        response.status_code = 401
        response.headers['WWW-Authenticate'] = 'Basic realm="oauth/token"'
        return response
    grant_type = request.form.get('grant_type')
    if grant_type == 'authorization_code':
        result, error = exchange_authorization_code(client)
    elif grant_type == 'refresh_token':
        result, error = exchange_refresh_token(client)
    else:
        result, error = None, 'unsupported_grant_type'
    if error:
        return jsonify({'error': error}), 400
    response = jsonify(result)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Pragma'] = 'no-cache'
    return response


@oidc_provider_bp.route('/oauth/userinfo', methods=['GET', 'POST'])
@public_route
@csrf.exempt
def userinfo():
    disabled = _disabled()
    if disabled: return disabled
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return jsonify({'error': 'invalid_token'}), 401
    decoded = decode_access_token(auth[7:])
    if decoded is None:
        return jsonify({'error': 'invalid_token'}), 401
    claims, client, user = decoded
    return jsonify(build_claims(user, claims.get('scope', ''), client))
