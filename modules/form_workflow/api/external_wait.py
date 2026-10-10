"""ExternalWait public callback endpoint."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from app import csrf, limiter
from app.security.client_ip import get_client_ip
from app.security.decorators import public_route
from modules.form_workflow.services.external_wait_service import (
    INSTANCE_CODE_RE,
    MAX_PAYLOAD_BYTES,
    NODE_ID_RE,
    TOKEN_RE,
    receive_callback,
)

external_wait_bp = Blueprint(
    'form_workflow_external_wait',
    __name__,
    url_prefix='/api/external-wait',
)


@external_wait_bp.route('/callback/<instance_code>/<node_id>/<token>', methods=['POST'])
@csrf.exempt
@limiter.limit('60 per minute; 600 per hour')
@public_route
def callback(instance_code, node_id, token):
    if (
        not INSTANCE_CODE_RE.match(instance_code or '')
        or not NODE_ID_RE.match(node_id or '')
        or not TOKEN_RE.match(token or '')
    ):
        return jsonify({'error': 'not_found'}), 404

    content_length = request.content_length
    if content_length is not None and content_length > MAX_PAYLOAD_BYTES:
        return jsonify({'error': 'payload_too_large'}), 413

    raw_body = request.get_data(cache=False) or b''
    status, body = receive_callback(
        instance_code,
        node_id,
        token,
        raw_body,
        get_client_ip(),
    )
    return jsonify(body), status
