"""
OpenDefense Module - Decisions API

對外契約 §5:
  GET   /api/open_defense/decisions          -- 拉取待執行決策
  PATCH /api/open_defense/decisions/<sc>     -- 回報執行結果

兩個端點都套 @service_account_required,
limiter key_func 用 sa_id(契約 §4.5/§5.4)。
"""
import logging
from datetime import datetime

from flask import request, jsonify, g

from app import limiter
from app.security.decorators import service_account_required
from app.security.rate_limiter import key_func_from_sa_id

from . import api_bp
from ..services.decision_service import (
    list_decisions_for_sa,
    update_decision_status,
    DecisionStatusError,
)

logger = logging.getLogger(__name__)


def _serialize(d):
    """對外回傳格式(契約 §5.1)"""
    return {
        'secure_code': d.secure_code,
        'action': d.action,
        'target_type': d.target_type,
        'target_value': d.target_value,
        'enforcement_points': d.enforcement_points or [],
        'severity': d.severity,
        'ttl_seconds': d.ttl_seconds,
        'expires_at': d.expires_at.isoformat() if d.expires_at else None,
        'reason': d.reason,
        'decided_at': d.decided_at.isoformat() if d.decided_at else None,
        'case_secure_code': d.case_secure_code,
        'created_at': d.created_at.isoformat() if d.created_at else None,
        'status': d.status,
    }


@api_bp.route('/decisions', methods=['GET'])
@limiter.limit(
    '60 per minute; 3000 per hour; 50000 per day',
    key_func=key_func_from_sa_id,
)
@service_account_required
def list_decisions():
    """執行端拉取決策"""
    sa = g.service_account

    status = (request.args.get('status') or 'pending').strip()
    if status not in ('pending', 'picked_up', 'applied',
                      'partial', 'failed', 'expired', 'revoked'):
        return jsonify({'error': 'invalid_status'}), 400

    enforcement_point = request.args.get('enforcement_point') or None

    try:
        limit = int(request.args.get('limit', '100'))
    except ValueError:
        return jsonify({'error': 'invalid_limit'}), 400

    since_str = request.args.get('since')
    since = None
    if since_str:
        try:
            since = datetime.fromisoformat(since_str.replace('Z', '+00:00'))
            if since.tzinfo is not None:
                since = since.astimezone(tz=None).replace(tzinfo=None)
        except ValueError:
            return jsonify({'error': 'invalid_since',
                           'message': 'since 必須為 ISO-8601 字串'}), 400

    rows = list_decisions_for_sa(
        org_secure_code=sa.org_secure_code,
        sa_allowed_eps=sa.allowed_enforcement_points or [],
        status=status,
        enforcement_point=enforcement_point,
        limit=limit,
        since=since,
    )

    next_since = (rows[-1].created_at.isoformat()
                  if rows else (since.isoformat() if since else None))

    return jsonify({
        'decisions': [_serialize(r) for r in rows],
        'next_since': next_since,
        'count': len(rows),
    }), 200


@api_bp.route('/decisions/<secure_code>', methods=['PATCH'])
@limiter.limit('300 per minute', key_func=key_func_from_sa_id)
@service_account_required
def patch_decision(secure_code):
    """執行端回報狀態"""
    sa = g.service_account

    try:
        body = request.get_json(force=True, silent=False) or {}
    except Exception:
        return jsonify({'error': 'invalid_json'}), 400

    target_status = (body.get('status') or '').strip()
    if not target_status:
        return jsonify({'error': 'missing_status'}), 400

    applied_by = body.get('applied_by')
    application_result = body.get('application_result')
    error_message = body.get('error_message')

    try:
        record = update_decision_status(
            secure_code=secure_code,
            org_secure_code=sa.org_secure_code,
            target_status=target_status,
            applied_by=applied_by,
            application_result=application_result,
            error_message=error_message,
        )
    except DecisionStatusError as exc:
        return jsonify({'error': exc.code, 'message': str(exc)}), exc.status

    return jsonify({
        'success': True,
        'decision': _serialize(record),
    }), 200
