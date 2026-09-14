"""Admin API:decisions 列表(供 UI 用,可看所有 status,可手動撤銷)"""
from concurrent.futures import ThreadPoolExecutor
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
from ...services import bridge_client


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


def _remaining_seconds(expires_at, now):
    if not expires_at:
        return None
    return max(0, int((expires_at - now).total_seconds()))


def _active_query(now):
    return OdDefenseDecision.query.filter(
        OdDefenseDecision.org_secure_code == current_user.org_secure_code,
        OdDefenseDecision.is_deleted.is_(False),
        OdDefenseDecision.action.in_(('block', 'allow')),
        OdDefenseDecision.status.in_(('applied', 'partial')),
        (
            OdDefenseDecision.expires_at.is_(None)
            | (OdDefenseDecision.expires_at > now)
        ),
    )


def _serialize_active(d, same_target_count, now):
    data = _serialize(d)
    data['remaining_seconds'] = _remaining_seconds(d.expires_at, now)
    data['same_target_count'] = same_target_count
    data['same_target_other_count'] = max(0, same_target_count - 1)
    return data


def _contains_target(values, target):
    return target in (values or set())


def _nft_values_for_action(nft_state, action):
    if not nft_state:
        return set()
    if action == 'allow':
        return set(nft_state.get('allowlist') or [])
    values = set((nft_state.get('blocklist') or {}).keys())
    values.update((nft_state.get('blocklist6') or {}).keys())
    return values


def _downstream_sets(edl_block, edl_allow, nft_state):
    return {
        ('edl', 'block'): set(edl_block or []),
        ('edl', 'allow'): set(edl_allow or []),
        ('nftables', 'block'): _nft_values_for_action(nft_state, 'block'),
        ('nftables', 'allow'): _nft_values_for_action(nft_state, 'allow'),
    }


def _apply_verdicts(active_rows, bridge, downstream):
    for item in active_rows:
        checked = []
        missing = []
        eps = set(item.get('enforcement_points') or [])
        for point in ('edl', 'nftables'):
            if point not in eps:
                continue
            present = _contains_target(
                downstream.get((point, item['action'])),
                item['target_value'],
            )
            checked.append({'point': point, 'present': present})
            if not present:
                missing.append(point)
        item['reconciliation'] = {
            'verdict': 'missing_downstream' if missing else 'in_sync',
            'checked_points': checked,
            'missing_points': missing,
        }
    if not bridge['available']:
        for item in active_rows:
            item['reconciliation'] = {
                'verdict': 'unknown',
                'checked_points': [],
                'missing_points': [],
            }


def _orphan_rows(active_rows, downstream):
    active_keys = set()
    for row in active_rows:
        for point in row.get('enforcement_points') or []:
            if point in ('edl', 'nftables'):
                active_keys.add((point, row['action'], row['target_value']))

    rows = []
    for (point, action), values in downstream.items():
        for target in sorted(values):
            if (point, action, target) in active_keys:
                continue
            rows.append({
                'target_type': 'ip',
                'target_value': target,
                'action': action,
                'source': point,
                'reconciliation': {'verdict': 'orphan_downstream'},
            })
    return rows


def _bridge_snapshot():
    base_url = bridge_client.base_url()
    with ThreadPoolExecutor(max_workers=3) as executor:
        edl_block_f = executor.submit(bridge_client.get_edl_block, base_url)
        edl_allow_f = executor.submit(bridge_client.get_edl_allow, base_url)
        nft_state_f = executor.submit(bridge_client.get_nft_state, base_url)
        return {
            'base_url': base_url,
            'edl_block': edl_block_f.result(),
            'edl_allow': edl_allow_f.result(),
            'nft_state': nft_state_f.result(),
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


@admin_bp.route('/decisions/enforcement-state', methods=['GET'])
@page_keys_required('open_defense.decisions')
def enforcement_state_admin():
    now = datetime.utcnow()
    candidates = _active_query(now).order_by(
        OdDefenseDecision.target_value.asc(),
        OdDefenseDecision.decided_at.desc(),
    ).all()

    grouped = {}
    for row in candidates:
        key = row.target_value
        grouped.setdefault(key, []).append(row)

    active_rows = []
    for rows in grouped.values():
        latest = max(rows, key=lambda r: r.decided_at or r.created_at)
        active_rows.append(_serialize_active(latest, len(rows), now))
    active_rows.sort(
        key=lambda item: (item.get('decided_at') or item.get('created_at') or ''),
        reverse=True,
    )

    bridge_data = _bridge_snapshot()
    edl_block = bridge_data['edl_block']
    edl_allow = bridge_data['edl_allow']
    nft_state = bridge_data['nft_state']
    bridge_available = (
        edl_block is not None
        and edl_allow is not None
        and nft_state is not None
    )
    bridge = {
        'available': bridge_available,
        'base_url': bridge_data['base_url'],
    }
    downstream = _downstream_sets(edl_block, edl_allow, nft_state)
    _apply_verdicts(active_rows, bridge, downstream)

    orphans = []
    if bridge_available and getattr(current_user, 'is_system_admin', False):
        orphans = _orphan_rows(active_rows, downstream)

    summary = {
        'active_count': len(active_rows),
        'in_sync': sum(1 for r in active_rows if r['reconciliation']['verdict'] == 'in_sync'),
        'missing_downstream': sum(
            1 for r in active_rows
            if r['reconciliation']['verdict'] == 'missing_downstream'
        ),
        'orphan_downstream': len(orphans),
    }
    return jsonify({
        'active': active_rows,
        'orphans': orphans,
        'bridge': bridge,
        'summary': summary,
    })


@admin_bp.route('/decisions/target-history', methods=['GET'])
@page_keys_required('open_defense.decisions')
def target_history_admin():
    target = (request.args.get('target') or '').strip()
    target_type = (request.args.get('target_type') or '').strip()
    if not target:
        return jsonify({'error': 'target_required', 'message': _('target 為必填')}), 400
    try:
        limit = min(int(request.args.get('limit', '100')), 200)
    except ValueError:
        limit = 100

    q = OdDefenseDecision.query.filter(
        OdDefenseDecision.org_secure_code == current_user.org_secure_code,
        OdDefenseDecision.is_deleted.is_(False),
        OdDefenseDecision.target_value == target,
    )
    if target_type:
        q = q.filter(OdDefenseDecision.target_type == target_type)

    rows = q.order_by(OdDefenseDecision.decided_at.desc()).limit(limit).all()
    return jsonify({
        'history': [_serialize(r) for r in rows],
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
