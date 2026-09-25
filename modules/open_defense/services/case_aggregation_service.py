"""OpenDefense case aggregation service.

三條事件入口共用同一套分組鍵、候選查詢與案件累積邏輯。
"""
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from app import db

logger = logging.getLogger(__name__)

DEFAULT_AGGREGATION = {
    'enabled': True,
    'group_by': ['actor_ip', 'finding_rule_id'],
    'window_minutes': 60,
    'window_from': 'first_seen',
    'merge_closed_max_severity': 2,
}
GROUP_BY_ALLOWED = (
    'severity_id',
    'actor_ip',
    'target_host',
    'source_system',
    'finding_rule_id',
)
OD_EVENTS_MAX = 200
OD_EVENTS_HEAD = 100
CLIENT_KEY_MAX_LEN = 128


def effective_config(rule_aggregation: dict | None) -> dict:
    """Return aggregation config with defaults filled in."""
    config = dict(DEFAULT_AGGREGATION)
    if rule_aggregation:
        config.update(rule_aggregation)
    return config


def resolve_group_key(
    *,
    rule_secure_code: str | None,
    axis: dict,
    client_key: str | None,
    config: dict,
    payload_kind: str,
    source_system: str | None,
) -> str | None:
    """Resolve a conservative aggregation key, or None when no safe key exists."""
    if payload_kind not in ('ocsf', 'native', 'trigger'):
        logger.warning('case aggregation skipped: invalid payload_kind=%r', payload_kind)
        return None
    if payload_kind == 'native' and not source_system:
        logger.warning('native case aggregation skipped: missing source_system')
        return None

    if config.get('enabled') is False:
        return None

    text_key = client_key.strip() if isinstance(client_key, str) else ''
    if text_key:
        if len(text_key) > CLIENT_KEY_MAX_LEN:
            digest = hashlib.sha256(text_key.encode('utf-8')).hexdigest()[:32]
            return f'client:h:{digest}'
        return f'client:{text_key}'

    group_by = config.get('group_by') or []
    if not group_by:
        return None

    parts = []
    for key in group_by:
        value = axis.get(key)
        if value is None or value == '':
            return None
        parts.append(str(value))

    group_key = 'rule:' + (rule_secure_code or 'default') + ':' + '\x1f'.join(parts)
    if payload_kind == 'native':
        group_key += '\x1fsrc=' + str(source_system)
    elif payload_kind == 'ocsf':
        group_key += '\x1fkind=ocsf'
    else:
        group_key += '\x1fkind=trigger'
    return group_key


def find_mergeable_case(
    *,
    org_secure_code,
    form_template_secure_code,
    group_key,
    severity_id,
    config,
):
    """Find an existing workflow instance eligible for merge."""
    if not group_key:
        return None

    from modules.form_workflow.models import FwFormInstance, FwWorkflowInstance

    window_minutes = int(config.get('window_minutes') or 0)
    cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
    candidates = db.session.query(FwWorkflowInstance).join(
        FwFormInstance,
        FwFormInstance.secure_code == FwWorkflowInstance.form_instance_secure_code,
    ).filter(
        FwWorkflowInstance.org_secure_code == org_secure_code,
        FwWorkflowInstance.is_deleted.is_(False),
        FwFormInstance.org_secure_code == org_secure_code,
        FwFormInstance.form_template_secure_code == form_template_secure_code,
        FwFormInstance.is_deleted.is_(False),
        FwFormInstance.form_data['od_group_key'].astext == group_key,
    ).order_by(
        FwFormInstance.created_at.desc(),
    ).limit(20).all()

    merge_closed_max = int(config.get('merge_closed_max_severity', 2))
    merge_closed_ok = merge_closed_max >= 0 and int(severity_id or 0) <= merge_closed_max
    window_from = config.get('window_from') or 'first_seen'

    for workflow_instance in candidates:
        form_instance = getattr(workflow_instance, 'form_instance', None)
        if form_instance is None:
            form_instance = FwFormInstance.query.filter_by(
                secure_code=workflow_instance.form_instance_secure_code,
                org_secure_code=org_secure_code,
                is_deleted=False,
            ).first()
        if form_instance is None:
            continue

        if window_from == 'last_seen':
            reference = _parse_iso_utc((form_instance.form_data or {}).get('od_last_seen'))
            if reference is None or reference < cutoff:
                continue
        elif form_instance.created_at is None or form_instance.created_at < cutoff:
            continue

        if workflow_instance.status == 'RUNNING' or merge_closed_ok:
            return workflow_instance
    return None


def merge_event(*, workflow_instance, event_summary: dict, axis: dict) -> None:
    """Merge one event summary into an existing case form_data."""
    from modules.form_workflow.models import FwFormInstance
    from .intake_service import _compute_risk

    form_instance = FwFormInstance.query.filter_by(
        secure_code=workflow_instance.form_instance_secure_code,
        org_secure_code=workflow_instance.org_secure_code,
        is_deleted=False,
    ).first()
    if form_instance is None:
        return

    form_data = dict(form_instance.form_data or {})
    form_data['od_event_count'] = int(form_data.get('od_event_count') or 1) + 1

    old_severity = int(form_data.get('severity_id') or 0)
    new_severity = int(axis.get('severity_id') or event_summary.get('severity_id') or 0)
    escalated = new_severity > old_severity
    if escalated:
        form_data['severity_id'] = new_severity

    last_seen = event_summary.get('occurred_at') or datetime.utcnow().isoformat() + 'Z'
    form_data['od_last_seen'] = last_seen
    form_data['risk_score'], form_data['recommended_action'] = _compute_risk(
        form_data.get('severity_id'),
        max(int(form_data.get('od_repeat_count') or 0), form_data['od_event_count']),
        form_data.get('od_history_block_count'),
    )

    append_event(form_data, event_summary)
    _append_actor_ip(form_data, axis.get('actor_ip') or event_summary.get('actor_ip'))

    form_instance.form_data = form_data
    flag_modified(form_instance, 'form_data')

    if escalated:
        logger.warning(
            'case aggregation escalated case=%s severity %s -> %s event=%s',
            workflow_instance.execution_code, old_severity, new_severity,
            event_summary.get('event_sc'),
        )


def initial_case_fields(*, group_key, event_summary, axis) -> dict:
    """Build system fields written when creating a new aggregated case."""
    form_data = {
        'od_group_key': group_key,
        'od_events': [event_summary],
    }
    actor_ip = axis.get('actor_ip') or event_summary.get('actor_ip')
    if actor_ip:
        form_data['od_actor_ips'] = [str(actor_ip)]
    else:
        form_data['od_actor_ips'] = []
    return form_data


def build_event_summary(*, event_sc, received_at, axis, finding_title, source_system) -> dict:
    """Build the fixed event summary shape stored in form_data.od_events."""
    received = _iso(received_at)
    return {
        'event_sc': event_sc,
        'received_at': received,
        'occurred_at': axis.get('occurred_at'),
        'source_system': source_system,
        'severity_id': axis.get('severity_id'),
        'actor_ip': axis.get('actor_ip'),
        'target_host': axis.get('target_host'),
        'finding_rule_id': axis.get('finding_rule_id'),
        'finding_title': finding_title,
    }


def append_event(form_data: dict, summary: dict) -> None:
    """Append an event summary and keep earliest 100 plus latest 100 entries."""
    events = list(form_data.get('od_events') or [])
    events.append(summary)
    if len(events) > OD_EVENTS_MAX:
        dropped = len(events) - OD_EVENTS_MAX
        events = events[:OD_EVENTS_HEAD] + events[-(OD_EVENTS_MAX - OD_EVENTS_HEAD):]
        form_data['od_events_truncated'] = int(form_data.get('od_events_truncated') or 0) + dropped
    form_data['od_events'] = events


def _append_actor_ip(form_data: dict, actor_ip: Any) -> None:
    if actor_ip in (None, ''):
        form_data['od_actor_ips'] = list(form_data.get('od_actor_ips') or [])
        return
    text = str(actor_ip)
    ips = list(form_data.get('od_actor_ips') or [])
    if text not in ips and len(ips) < 500:
        ips.append(text)
    form_data['od_actor_ips'] = ips


def _parse_iso_utc(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.rstrip('Z'))
    except ValueError:
        return None


def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat() + 'Z'
    return str(value)
