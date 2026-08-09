"""
OpenDefense Module - Native Intake Webhook View

POST /api/open_defense/intake/native
"""
import json
import logging

from flask import request, jsonify, g

from app import limiter
from app.security.client_ip import get_client_ip
from app.security.decorators import webhook_hmac_required
from app.security.rate_limiter import (
    key_func_from_intake_key, auth_failure_limit_kwargs,
)

from . import api_bp
from ..models import OdPayloadProfile
from ..services.intake_service import process_native_intake, IntakeError

logger = logging.getLogger(__name__)

MAX_NATIVE_PAYLOAD_BYTES = 256 * 1024


@api_bp.route('/intake/native', methods=['POST'])
@limiter.limit(
    '100 per minute; 5000 per hour',
    key_func=key_func_from_intake_key,
)
@limiter.limit(**auth_failure_limit_kwargs())
@webhook_hmac_required
def intake_native():
    """原生 SOC payload 接收 webhook。"""
    od_scope = (g.api_key.scopes or {}).get('od_intake')
    if not isinstance(od_scope, dict):
        logger.warning(
            'native intake scope denied key=%s ip=%s',
            g.api_key.key_id, get_client_ip(),
        )
        return jsonify({'error': 'scope_denied'}), 403

    profile_code = (request.args.get('profile') or '').strip()
    if not profile_code:
        return jsonify({'error': 'profile_required'}), 400

    profile = OdPayloadProfile.query.filter_by(
        org_secure_code=g.api_key.org_secure_code,
        code=profile_code,
        is_deleted=False,
        is_active=True,
    ).first()
    if not profile:
        return jsonify({'error': 'profile_not_found'}), 400

    allowed_profiles = od_scope.get('payload_profiles')
    if allowed_profiles is not None:
        if not isinstance(allowed_profiles, list) or profile.code not in allowed_profiles:
            return jsonify({'error': 'profile_not_allowed'}), 403

    try:
        body = request.get_json(force=True, silent=False)
    except Exception:
        return jsonify({'error': 'invalid_json'}), 400

    if not isinstance(body, dict):
        return jsonify({'error': 'invalid_payload'}), 400

    try:
        payload_size = len(json.dumps(body, ensure_ascii=False).encode('utf-8'))
    except (TypeError, ValueError):
        logger.warning('native intake payload size calculation failed key=%s',
                       g.api_key.key_id)
        return jsonify({'error': 'invalid_payload'}), 400
    if payload_size > MAX_NATIVE_PAYLOAD_BYTES:
        return jsonify({'error': 'payload_too_large'}), 413

    try:
        event, is_dup = process_native_intake(
            api_key=g.api_key,
            payload=body,
            profile=profile,
            source_ip=get_client_ip(),
        )
    except IntakeError as exc:
        logger.warning(
            'native intake business error key=%s code=%s msg=%s',
            g.api_key.key_id, exc.code, exc,
        )
        return jsonify({
            'error': exc.code,
            'message': str(exc),
        }), exc.status

    if is_dup:
        return jsonify({
            'success': True,
            'duplicate': True,
            'case_secure_code': event.case_secure_code,
        }), 200

    return jsonify({
        'success': True,
        'duplicate': False,
        'case_secure_code': event.case_secure_code,
        'workflow_started': event.case_secure_code is not None,
    }), 200
