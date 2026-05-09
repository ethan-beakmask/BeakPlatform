"""
OpenDefense Module - Service Account API

POST /api/open_defense/sa/login -- 對外執行端登入,回傳短期 JWT
其他 SA CRUD(管理員用)在 TICKET-7 UI ticket 中補。
"""
import logging

from flask import request, jsonify
from flask_limiter.util import get_remote_address

from app import limiter, csrf
from app.security.decorators import public_route

from . import api_bp
from ..services.service_account_service import (
    authenticate, ServiceAccountError, _get_jwt_ttl_sec,
)

logger = logging.getLogger(__name__)


@api_bp.route('/sa/login', methods=['POST'])
@csrf.exempt
@limiter.limit('10 per minute', key_func=get_remote_address)
@public_route
def sa_login():
    """
    Service Account 登入,回傳短期 JWT(契約 §3.2)。

    Request:
        { "sa_id": "sa_xxx", "sa_secret": "<base64url 32-byte>" }

    Response 200:
        { "access_token": "<jwt>", "expires_in": 900, "token_type": "Bearer" }

    Response 401:
        { "error": "invalid_credentials" | "locked" }

    限速:每來源 IP 每分鐘 10 次(防憑證爆破)。
    """
    try:
        body = request.get_json(force=True, silent=False) or {}
    except Exception:
        return jsonify({'error': 'invalid_json'}), 400

    sa_id = (body.get('sa_id') or '').strip()
    sa_secret = (body.get('sa_secret') or '').strip()
    if not sa_id or not sa_secret:
        return jsonify({'error': 'missing_credentials'}), 400

    try:
        record, token = authenticate(
            sa_id=sa_id,
            secret_b64=sa_secret,
            source_ip=request.remote_addr,
        )
    except ServiceAccountError as exc:
        # 不洩漏哪個欄位錯,統一回 401
        if exc.code == 'locked':
            return jsonify({'error': 'locked', 'message': str(exc)}), 401
        return jsonify({'error': 'invalid_credentials'}), 401

    return jsonify({
        'access_token': token,
        'expires_in': _get_jwt_ttl_sec(),
        'token_type': 'Bearer',
    }), 200
