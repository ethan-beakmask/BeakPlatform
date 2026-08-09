"""
OpenDefense Module - Intake Webhook View

POST /api/open_defense/intake

對外契約 §4。
"""
import logging

from flask import request, jsonify, g

from app import limiter
from app.security.decorators import webhook_hmac_required
from app.security.client_ip import get_client_ip
from app.security.rate_limiter import (
    key_func_from_intake_key, auth_failure_limit_kwargs,
)

from . import api_bp
from ..schemas.intake import validate_intake_body, IntakeValidationError
from ..services.intake_service import process_intake, IntakeError

logger = logging.getLogger(__name__)


@api_bp.route('/intake', methods=['POST'])
@limiter.limit(
    '100 per minute; 5000 per hour',
    key_func=key_func_from_intake_key,
)
@limiter.limit(**auth_failure_limit_kwargs())
@webhook_hmac_required
def intake():
    """事件接收 webhook(契約 §4)。P2 起認證走平台 ApiKey(g.api_key)。"""
    # 1. scope 授權:key 必須具備 od_intake scope
    if not isinstance((g.api_key.scopes or {}).get('od_intake'), dict):
        client_ip = get_client_ip()
        logger.warning(
            'intake scope denied key=%s ip=%s',
            g.api_key.key_id, client_ip,
        )
        return jsonify({'error': 'scope_denied'}), 403

    # 2. parse JSON
    try:
        body = request.get_json(force=True, silent=False)
    except Exception:
        return jsonify({'error': 'invalid_json'}), 400

    # 3. schema 驗證
    try:
        normalized = validate_intake_body(body)
    except IntakeValidationError as exc:
        logger.info(
            'intake schema rejected key=%s details=%s',
            g.api_key.key_id, exc.details,
        )
        return jsonify({
            'error': 'validation_error',
            'details': exc.details,
        }), 400

    # 4. 處理(冪等 + 啟流程)
    try:
        event, is_dup = process_intake(
            api_key=g.api_key,
            body=normalized,
            source_ip=get_client_ip(),
        )
    except IntakeError as exc:
        logger.warning(
            'intake business error key=%s code=%s msg=%s',
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
