"""
AiAgent usage and quota administration API.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from flask import jsonify, request
from flask_babel import gettext as _

from app import db
from app.platform.auth import require_permission
from app.platform.data import get_current_org
from app.security.decorators import module_access_required

from ..models.ai_usage_record import FwAiUsageRecord
from ..services import ai_usage_service
from . import api_bp


KNOWN_CONFIG_KEYS = tuple(ai_usage_service.HARDCODED_DEFAULTS.keys())
RUN_KEYS = {'daily_max_runs', 'monthly_max_runs'}
COST_KEYS = {'daily_max_cost_usd', 'monthly_max_cost_usd'}
STATUSES = (
    FwAiUsageRecord.STATUS_RUNNING,
    FwAiUsageRecord.STATUS_SUCCESS,
    FwAiUsageRecord.STATUS_FAILED,
    FwAiUsageRecord.STATUS_BLOCKED,
)


def _org_or_error():
    org = get_current_org()
    if not org:
        return None, (jsonify({
            'success': False,
            'error': 'organization_not_found',
            'message': _('找不到企業'),
        }), 400)
    return org, None


def _dt_iso(value):
    return value.isoformat() if value else None


def _current_config_payload(org):
    return {
        'config': ai_usage_service.get_effective_config(org),
        'items': ai_usage_service.get_config_with_source(org),
    }


def _validate_updates(payload):
    updates = {}
    ignored = []
    for key, value in (payload or {}).items():
        if key == 'clear':
            continue
        if key not in KNOWN_CONFIG_KEYS:
            ignored.append(key)
            continue
        if key == 'enabled':
            if not isinstance(value, bool):
                return None, ignored, key
            updates[key] = value
            continue
        if key in RUN_KEYS:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                return None, ignored, key
            updates[key] = value
            continue
        if key in COST_KEYS:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                return None, ignored, key
            updates[key] = float(value)
    return updates, ignored, None


def _parse_local_date(value, tz_name, *, end=False):
    try:
        local_date = datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        raise ValueError('invalid_date')
    if end:
        local_date = local_date + timedelta(days=1)
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo('Asia/Taipei')
    local_dt = datetime.combine(local_date, time.min).replace(tzinfo=tz)
    return local_dt.astimezone(ZoneInfo('UTC')).replace(tzinfo=None)


@api_bp.route('/ai-usage/config', methods=['GET'])
@module_access_required('form_workflow')
@require_permission('form_workflow.admin')
def get_ai_usage_config():
    org, error = _org_or_error()
    if error:
        return error
    return jsonify({'success': True, 'data': _current_config_payload(org)})


@api_bp.route('/ai-usage/config', methods=['PUT'])
@module_access_required('form_workflow')
@require_permission('form_workflow.admin')
def update_ai_usage_config():
    org, error = _org_or_error()
    if error:
        return error

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({
            'success': False,
            'error': 'invalid_payload',
            'message': _('請提供 JSON 物件'),
        }), 400

    clear_keys = payload.get('clear', [])
    if clear_keys is None:
        clear_keys = []
    if not isinstance(clear_keys, list) or any(not isinstance(key, str) for key in clear_keys):
        return jsonify({
            'success': False,
            'error': 'invalid_clear',
            'message': _('回復系統預設欄位格式不正確'),
        }), 400

    updates, unknown_keys, invalid_key = _validate_updates(payload)
    if invalid_key:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'invalid_value',
            'message': _('配額設定值格式不正確或超出範圍'),
            'field': invalid_key,
        }), 400

    # 先清除企業覆寫，再寫入本次更新；避免「清除」被舊值立刻寫回。
    ai_usage_service.clear_org_config(org, clear_keys)
    ignored_keys = ai_usage_service.set_org_config(org, updates)
    db.session.commit()

    data = _current_config_payload(org)
    data['ignored_keys'] = sorted(set(unknown_keys + ignored_keys))
    return jsonify({'success': True, 'data': data})


@api_bp.route('/ai-usage/summary', methods=['GET'])
@module_access_required('form_workflow')
@require_permission('form_workflow.admin')
def get_ai_usage_summary():
    org, error = _org_or_error()
    if error:
        return error

    org_code = org.secure_code
    tz_name = org.get_setting('timezone', 'Asia/Taipei')
    config = ai_usage_service.get_effective_config(org)
    usage = ai_usage_service.get_period_usage(org_code, tz_name)
    month_summary = ai_usage_service.summarize(org_code, tz_name)

    return jsonify({
        'success': True,
        'data': {
            'enabled': bool(config['enabled']),
            'timezone': tz_name,
            'daily': {
                'runs': int(usage['daily_runs']),
                'runs_limit': int(config['daily_max_runs'] or 0),
                'cost': float(usage['daily_cost'] or 0),
                'cost_limit': float(config['daily_max_cost_usd'] or 0),
                'period_start': _dt_iso(usage['day_start']),
            },
            'monthly': {
                'runs': int(usage['monthly_runs']),
                'runs_limit': int(config['monthly_max_runs'] or 0),
                'cost': float(usage['monthly_cost'] or 0),
                'cost_limit': float(config['monthly_max_cost_usd'] or 0),
                'period_start': _dt_iso(usage['month_start']),
            },
            'recent_blocked': int(
                month_summary['status_counts'].get(FwAiUsageRecord.STATUS_BLOCKED, 0)
            ),
        },
    })


@api_bp.route('/ai-usage/records', methods=['GET'])
@module_access_required('form_workflow')
@require_permission('form_workflow.admin')
def get_ai_usage_records():
    org, error = _org_or_error()
    if error:
        return error

    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
    except (TypeError, ValueError):
        return jsonify({
            'success': False,
            'error': 'invalid_pagination',
            'message': _('分頁參數格式不正確'),
        }), 400
    if page < 1 or per_page < 1:
        return jsonify({
            'success': False,
            'error': 'invalid_pagination',
            'message': _('分頁參數格式不正確'),
        }), 400
    per_page = min(per_page, 100)

    status = request.args.get('status')
    if status and status not in STATUSES:
        status = None

    tz_name = org.get_setting('timezone', 'Asia/Taipei')
    try:
        start = _parse_local_date(request.args['start'], tz_name) if request.args.get('start') else None
        end = _parse_local_date(request.args['end'], tz_name, end=True) if request.args.get('end') else None
    except ValueError:
        return jsonify({
            'success': False,
            'error': 'invalid_date',
            'message': _('日期格式不正確'),
        }), 400
    if start and end and start >= end:
        return jsonify({
            'success': False,
            'error': 'invalid_date_range',
            'message': _('結束日期必須晚於開始日期'),
        }), 400

    query = FwAiUsageRecord.query.filter(
        FwAiUsageRecord.org_secure_code == org.secure_code,
        FwAiUsageRecord.is_deleted == False,
    )
    if status:
        query = query.filter(FwAiUsageRecord.status == status)
    if start:
        query = query.filter(FwAiUsageRecord.started_at >= start)
    if end:
        query = query.filter(FwAiUsageRecord.started_at < end)

    total = query.count()
    records = query.order_by(FwAiUsageRecord.started_at.desc()).offset(
        (page - 1) * per_page
    ).limit(per_page).all()

    return jsonify({
        'success': True,
        'data': {
            'items': [record.to_dict() for record in records],
            'total': total,
            'page': page,
            'per_page': per_page,
        },
    })
