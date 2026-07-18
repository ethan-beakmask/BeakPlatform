"""Admin API:decisions 列表(供 UI 用,可看所有 status,可手動撤銷)"""
from datetime import datetime

from flask import request, jsonify
from flask_babel import gettext as _
from flask_login import current_user

from app import db
from app.security.decorators import page_keys_required
from app.services.capability_service import permission_required
from app.utils.security import generate_secure_code

from . import admin_bp
from ...models import OdDefenseDecision


def _serialize(d):
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
        'decided_via': d.decided_via,
        'decided_at': d.decided_at.isoformat() if d.decided_at else None,
        'status': d.status,
        'applied_by': d.applied_by,
        'applied_at': d.applied_at.isoformat() if d.applied_at else None,
        'error_message': d.error_message,
        'case_secure_code': d.case_secure_code,
        'created_at': d.created_at.isoformat() if d.created_at else None,
    }


@admin_bp.route('/decisions', methods=['GET'])
@page_keys_required('open_defense.decisions')
def list_decisions_admin():
    org_sc = current_user.org_secure_code
    q = OdDefenseDecision.query.filter_by(
        org_secure_code=org_sc, is_deleted=False)

    status = request.args.get('status')
    if status:
        q = q.filter(OdDefenseDecision.status == status)

    action = request.args.get('action')
    if action:
        q = q.filter(OdDefenseDecision.action == action)

    target_q = request.args.get('target')
    if target_q:
        q = q.filter(OdDefenseDecision.target_value.ilike(f'%{target_q}%'))

    try:
        limit = min(int(request.args.get('limit', '100')), 500)
    except ValueError:
        limit = 100

    rows = q.order_by(OdDefenseDecision.created_at.desc()).limit(limit).all()
    return jsonify({
        'decisions': [_serialize(r) for r in rows],
        'count': len(rows),
    })


@admin_bp.route('/decisions/<secure_code>/revoke', methods=['POST'])
@permission_required('open_defense.decision.write')
def revoke_decision_admin(secure_code):
    """
    手動撤銷一筆 applied 決策:產生對應 unblock 決策(同 target / EP)。
    對應 cron 自動 unblock,但這裡是人工觸發,理由由用戶填。
    """
    org_sc = current_user.org_secure_code
    record = OdDefenseDecision.query.filter_by(
        secure_code=secure_code, org_secure_code=org_sc, is_deleted=False,
    ).first()
    if not record:
        return jsonify({'error': 'not_found'}), 404
    if record.status != 'applied':
        return jsonify({
            'error': 'not_revocable',
            'message': _('只能撤銷 applied 狀態的決策(目前 %(status)s)', status=record.status),
        }), 409
    if record.action == 'unblock':
        return jsonify({
            'error': 'not_revocable',
            'message': _('unblock 決策無需再撤銷'),
        }), 400

    body = request.get_json(force=True, silent=True) or {}
    reason = (body.get('reason') or '').strip() or _('人工手動撤銷')

    now = datetime.utcnow()
    unblock = OdDefenseDecision(
        secure_code=generate_secure_code(),
        org_secure_code=org_sc,
        case_secure_code=record.case_secure_code,
        intake_event_secure_code=record.intake_event_secure_code,
        action='unblock',
        target_type=record.target_type,
        target_value=record.target_value,
        enforcement_points=record.enforcement_points or [],
        severity=record.severity,
        ttl_seconds=None,
        expires_at=None,
        reason=f'{reason}(原決策 {record.secure_code})',
        decided_via='human',
        decided_by_secure_code=current_user.secure_code,
        decided_at=now,
        status='pending',
        decision_metadata={'revoked_from': record.secure_code,
                          'revoked_by_user': current_user.secure_code},
    )
    db.session.add(unblock)
    db.session.flush()

    record.status = 'revoked'
    record.revoked_by_decision_secure_code = unblock.secure_code
    record.updated_at = now
    db.session.commit()

    return jsonify({
        'success': True,
        'unblock_secure_code': unblock.secure_code,
    })
