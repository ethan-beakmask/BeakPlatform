"""Admin API:dashboard 統計"""
from datetime import datetime, timedelta

from flask import jsonify
from flask_login import current_user
from sqlalchemy import func

from app import db
from app.security.decorators import page_keys_required

from . import admin_bp
from ...models import (
    OdDefenseDecision, OdIntakeEvent, OdServiceAccount,
)


@admin_bp.route('/dashboard/stats', methods=['GET'])
@page_keys_required('open_defense.dashboard')  # PERM-01 試點：與 dashboard 頁共用雙鑰匙
def dashboard_stats():
    org_sc = current_user.org_secure_code
    today_start = datetime.utcnow().replace(
        hour=0, minute=0, second=0, microsecond=0)

    def _count(model, **filters):
        q = model.query.filter_by(org_secure_code=org_sc, is_deleted=False)
        for k, v in filters.items():
            q = q.filter(getattr(model, k) == v)
        return q.count()

    decisions_pending = _count(OdDefenseDecision, status='pending')
    decisions_picked  = _count(OdDefenseDecision, status='picked_up')
    decisions_applied = _count(OdDefenseDecision, status='applied')
    decisions_failed  = _count(OdDefenseDecision, status='failed')
    decisions_expired = _count(OdDefenseDecision, status='expired')

    today_intake = OdIntakeEvent.query.filter(
        OdIntakeEvent.org_secure_code == org_sc,
        OdIntakeEvent.is_deleted.is_(False),
        OdIntakeEvent.received_at >= today_start,
    ).count()

    today_decisions = OdDefenseDecision.query.filter(
        OdDefenseDecision.org_secure_code == org_sc,
        OdDefenseDecision.is_deleted.is_(False),
        OdDefenseDecision.created_at >= today_start,
    ).count()

    # P2 起 intake key 為平台 ApiKey(具 od_intake scope)
    from app.models.api_key import ApiKey, STATUS_ACTIVE
    intake_keys_active = ApiKey.query.filter(
        ApiKey.org_secure_code == org_sc,
        ApiKey.status == STATUS_ACTIVE,
        ApiKey.is_deleted.is_(False),
        ApiKey.scopes.has_key('od_intake'),
    ).count()

    sa_active = OdServiceAccount.query.filter_by(
        org_secure_code=org_sc, is_active=True, is_deleted=False).count()

    # 最近 5 筆事件
    recent_events = OdIntakeEvent.query.filter_by(
        org_secure_code=org_sc, is_deleted=False
    ).order_by(OdIntakeEvent.received_at.desc()).limit(5).all()

    # 最近 5 筆 pending 決策
    recent_pending = OdDefenseDecision.query.filter_by(
        org_secure_code=org_sc, status='pending', is_deleted=False
    ).order_by(OdDefenseDecision.created_at.desc()).limit(5).all()

    return jsonify({
        'stats': {
            'decisions_pending': decisions_pending,
            'decisions_picked_up': decisions_picked,
            'decisions_applied': decisions_applied,
            'decisions_failed': decisions_failed,
            'decisions_expired': decisions_expired,
            'today_intake': today_intake,
            'today_decisions': today_decisions,
            'intake_keys_active': intake_keys_active,
            'service_accounts_active': sa_active,
        },
        'recent_events': [{
            'secure_code': e.secure_code,
            'correlation_id': e.correlation_id,
            'source_system': e.source_system,
            'event_class': e.event_class,
            'severity_id': e.severity_id,
            'received_at': e.received_at.isoformat() if e.received_at else None,
            'case_secure_code': e.case_secure_code,
            'actor_ip': (e.raw_body or {}).get('actor', {}).get('ip'),
            'actor_country': (e.raw_body or {}).get('actor', {}).get('country'),
        } for e in recent_events],
        'recent_pending': [{
            'secure_code': d.secure_code,
            'action': d.action,
            'target_type': d.target_type,
            'target_value': d.target_value,
            'enforcement_points': d.enforcement_points or [],
            'created_at': d.created_at.isoformat() if d.created_at else None,
        } for d in recent_pending],
    })
