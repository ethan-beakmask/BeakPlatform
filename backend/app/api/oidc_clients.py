"""System-administrator API for OIDC clients and signing keys."""
import logging

from flask import Blueprint, jsonify, request
from flask_babel import gettext as _
from flask_login import current_user

from app import db
from app.models import OidcSigningKey
from app.security.decorators import system_admin_required
from app.services import oidc_client_service as clients
from app.services import oidc_keys
from app.utils.external_url import build_external_url


logger = logging.getLogger(__name__)

oidc_clients_api_bp = Blueprint(
    'oidc_clients_api', __name__, url_prefix='/api/oidc-clients')


def _error(message, status=400):
    return jsonify({'success': False, 'error': message}), status


def _handle_client_error(exc):
    return _error(str(exc), getattr(exc, 'status_code', 400))


@oidc_clients_api_bp.route('/', methods=['GET'])
@system_admin_required
def list_oidc_clients():
    return jsonify({'success': True, 'clients': clients.list_clients()})


@oidc_clients_api_bp.route('/', methods=['POST'])
@system_admin_required
def create_oidc_client():
    try:
        record, secret = clients.create_client(
            request.get_json(silent=True), current_user.secure_code)
        result = clients.serialize_client(record)
        result['client_secret'] = secret
        return jsonify({'success': True, 'client': result}), 201
    except clients.OidcClientError as exc:
        return _handle_client_error(exc)
    except Exception:
        db.session.rollback()
        logger.exception('OIDC client creation failed')
        return _error(_('建立 OIDC client 失敗'), 500)


@oidc_clients_api_bp.route('/meta', methods=['GET'])
@system_admin_required
def meta():
    issuer_url = build_external_url('')
    issuer = issuer_url.rstrip('/') if issuer_url else None
    return jsonify({
        'success': True,
        'issuer': issuer,
        'discovery_url': issuer + '/.well-known/openid-configuration'
        if issuer else None,
    })


@oidc_clients_api_bp.route('/signing-keys', methods=['GET'])
@system_admin_required
def signing_keys():
    records = OidcSigningKey.query.order_by(
        OidcSigningKey.created_at.desc()).all()
    return jsonify({'success': True, 'keys': [{
        'kid': record.kid,
        'status': record.status,
        'created_at': record.created_at.isoformat() if record.created_at else None,
        'retired_at': record.retired_at.isoformat() if record.retired_at else None,
    } for record in records]})


@oidc_clients_api_bp.route('/signing-keys/rotate', methods=['POST'])
@system_admin_required
def rotate_signing_key():
    try:
        record = oidc_keys.rotate_key(current_user.secure_code)
        return jsonify({'success': True, 'key': {
            'kid': record.kid,
            'status': record.status,
            'created_at': record.created_at.isoformat(),
            'retired_at': None,
        }})
    except Exception:
        db.session.rollback()
        logger.exception('OIDC signing-key rotation failed')
        return _error(_('輪替 OIDC 簽章金鑰失敗'), 500)


@oidc_clients_api_bp.route('/<secure_code>', methods=['GET'])
@system_admin_required
def get_oidc_client(secure_code):
    try:
        return jsonify({
            'success': True,
            'client': clients.client_detail(clients.get_client(secure_code)),
        })
    except clients.OidcClientError as exc:
        return _handle_client_error(exc)


@oidc_clients_api_bp.route('/<secure_code>', methods=['PUT'])
@system_admin_required
def update_oidc_client(secure_code):
    try:
        record = clients.update_client(
            clients.get_client(secure_code),
            request.get_json(silent=True),
            current_user.secure_code,
        )
        return jsonify({'success': True, 'client': clients.serialize_client(record)})
    except clients.OidcClientError as exc:
        return _handle_client_error(exc)
    except Exception:
        db.session.rollback()
        logger.exception('OIDC client update failed')
        return _error(_('更新 OIDC client 失敗'), 500)


@oidc_clients_api_bp.route('/<secure_code>/rotate-secret', methods=['POST'])
@system_admin_required
def rotate_client_secret(secure_code):
    try:
        record = clients.get_client(secure_code)
        secret = clients.rotate_secret(record, current_user.secure_code)
        return jsonify({'success': True, 'client_secret': secret})
    except clients.OidcClientError as exc:
        return _handle_client_error(exc)
    except Exception:
        db.session.rollback()
        logger.exception('OIDC client secret rotation failed')
        return _error(_('輪替 client secret 失敗'), 500)


@oidc_clients_api_bp.route('/<secure_code>', methods=['DELETE'])
@system_admin_required
def delete_oidc_client(secure_code):
    try:
        clients.delete_client(
            clients.get_client(secure_code), current_user.secure_code)
        return jsonify({'success': True})
    except clients.OidcClientError as exc:
        return _handle_client_error(exc)
    except Exception:
        db.session.rollback()
        logger.exception('OIDC client deletion failed')
        return _error(_('刪除 OIDC client 失敗'), 500)


@oidc_clients_api_bp.route('/<secure_code>/orgs', methods=['POST'])
@system_admin_required
def authorize_client_org(secure_code):
    data = request.get_json(silent=True)
    org_secure_code = data.get('org_secure_code') if isinstance(data, dict) else None
    if not isinstance(org_secure_code, str) or not org_secure_code.strip():
        return _error(_('請提供 org_secure_code'))
    try:
        clients.authorize_org(
            clients.get_client(secure_code), org_secure_code.strip(),
            current_user.secure_code)
        return jsonify({'success': True}), 201
    except clients.OidcClientError as exc:
        return _handle_client_error(exc)
    except Exception:
        db.session.rollback()
        logger.exception('OIDC organization authorization failed')
        return _error(_('新增企業授權失敗'), 500)


@oidc_clients_api_bp.route('/<secure_code>/orgs/<org_secure_code>',
                           methods=['DELETE'])
@system_admin_required
def revoke_client_org(secure_code, org_secure_code):
    try:
        clients.revoke_org(
            clients.get_client(secure_code), org_secure_code,
            current_user.secure_code)
        return jsonify({'success': True})
    except clients.OidcClientError as exc:
        return _handle_client_error(exc)
    except Exception:
        db.session.rollback()
        logger.exception('OIDC organization revocation failed')
        return _error(_('撤銷企業授權失敗'), 500)
