"""
OpenDefense Module - 資安案件處置中心 API（原子 4845）

唯讀聚合查詢，完全共用 form_workflow 引擎與資料表：
- GET /api/open_defense/cases                 案件清單（嚴重度排序、SLA、待簽核鍵）
- GET /api/open_defense/cases/stats           頂部統計帶
- GET /api/open_defense/cases/<wi_sc>/decisions  案件關聯防禦決策

簽核動作（1-click 處置）不在此實作——前端直接呼叫既有
/api/form-center/pending-tasks 的 lock/approve（不 clone 引擎）。

[標準 TENANT-01] 所有查詢帶 org_secure_code
"""
from datetime import datetime, timedelta

from flask import jsonify, request
from flask_login import current_user

from app import db
from app.security.decorators import module_access_required
from app.platform.data import get_current_org

from . import api_bp
from ..models import OdDefenseDecision, OdPayloadProfile

# SLA（分鐘）：severity>=4 快速通道 15 分、=3 標準 60 分；低危自動歸檔無 SLA
SLA_MINUTES_HIGH = 15
SLA_MINUTES_MEDIUM = 60

# SOC 簽核節點型別（與 fc_pending 同一組）
_APPROVAL_NODE_TYPES = ('Approve', 'FormAdapter', 'FORMADAPTER')
_PAYLOAD_ROW_LIMIT = 500
_PAYLOAD_COLUMN_LIMIT = 40
_PAYLOAD_COLUMN_SCAN_LIMIT = 20
_PAYLOAD_EXCLUDED_FIELD_KEYS = {
    'severity_id', 'actor_ip', 'target_host', 'source_system',
    'finding_rule_id', 'occurred_at',
    'risk_score', 'recommended_action', 'correlation_id',
}


def _sla_minutes(severity_id) -> int:
    sev = int(severity_id or 0)
    if sev >= 4:
        return SLA_MINUTES_HIGH
    if sev == 3:
        return SLA_MINUTES_MEDIUM
    return 0


def _security_case_query(org_sc):
    """資安分類案件的基礎查詢（form_instance + workflow_instance + 分類）。"""
    from sqlalchemy.orm import aliased
    from modules.form_workflow.models import (
        FwFormInstance, FwWorkflowInstance, FwFormTemplate,
    )
    from modules.form_workflow.services.security_center import (
        SECURITY_CATEGORY_PREFIX,
    )

    FT = aliased(FwFormTemplate)
    return db.session.query(FwFormInstance, FwWorkflowInstance).join(
        FwWorkflowInstance,
        FwFormInstance.workflow_instance_secure_code == FwWorkflowInstance.secure_code,
    ).join(
        FT, FwFormInstance.form_template_id == FT.id,
    ).filter(
        FwFormInstance.org_secure_code == org_sc,
        FwFormInstance.is_deleted == False,  # noqa: E712
        FT.category_secure_code.like(f'{SECURITY_CATEGORY_PREFIX}%'),
    )


def _payload_detail_key(profile):
    if not profile or not profile.detail_path:
        return None
    return str(profile.detail_path).split('.')[-1]


def _payload_detail_columns(profile, rows):
    configured = profile.detail_columns if profile else None
    columns = []
    seen = set()

    if isinstance(configured, list):
        for col in configured:
            if not isinstance(col, dict):
                continue
            key = str(col.get('key') or '').strip()
            if not key or key in seen:
                continue
            label = str(col.get('label') or key)
            columns.append({'key': key, 'label': label})
            seen.add(key)
            if len(columns) >= _PAYLOAD_COLUMN_LIMIT:
                break
        if columns:
            return columns

    for row in rows[:_PAYLOAD_COLUMN_SCAN_LIMIT]:
        if not isinstance(row, dict):
            continue
        for key in row.keys():
            key = str(key)
            if not key or key in seen:
                continue
            columns.append({'key': key, 'label': key})
            seen.add(key)
            if len(columns) >= _PAYLOAD_COLUMN_LIMIT:
                return columns
    return columns


def _payload_scalar_fields(form_data, detail_key):
    excluded = set(_PAYLOAD_EXCLUDED_FIELD_KEYS)
    if detail_key:
        excluded.add(detail_key)

    fields = []
    for key in sorted(form_data.keys()):
        if key in excluded or key.startswith('od_'):
            continue
        value = form_data.get(key)
        if isinstance(value, (dict, list)):
            continue
        fields.append({'key': key, 'value': value})
    return fields


def _apply_payload_egress(form_instance, fields, rows, columns):
    from app.services import egress_service

    payload = {
        'form_instance_secure_code': form_instance.secure_code,
    }
    for field in fields:
        payload[field['key']] = field['value']

    column_keys = [col['key'] for col in columns]
    for key in column_keys:
        if key in payload:
            continue
        for row in rows:
            if isinstance(row, dict) and key in row:
                payload[key] = row.get(key)
                break

    filtered = egress_service.apply(
        f'fw_form:{form_instance.form_template_secure_code}', 'detail',
        [payload], record_sc_key='form_instance_secure_code',
    )[0]

    visible_fields = [
        {'key': field['key'], 'value': filtered[field['key']]}
        for field in fields
        if field['key'] in filtered
    ]
    visible_columns = [
        col for col in columns
        if col['key'] in filtered or col['key'] not in payload
    ]

    visible_rows = []
    for row in rows:
        if not isinstance(row, dict):
            visible_rows.append(row)
            continue
        visible_row = {}
        for col in visible_columns:
            key = col['key']
            if (key in filtered and isinstance(filtered[key], dict) and
                    filtered[key].get('__masked')):
                visible_row[key] = filtered[key]
            elif key in row:
                visible_row[key] = row.get(key)
        visible_rows.append(visible_row)

    return visible_fields, visible_rows, visible_columns


@api_bp.route('/cases')
@module_access_required('open_defense', False)
def list_cases():
    """
    案件清單。

    Query:
        status: open(預設，流程進行中) / closed / all
        limit:  最多筆數（預設 200）
    """
    from modules.form_workflow.models import FwNodeExecutionQueue
    from modules.form_workflow.services.task_authorizer import (
        can_act_on_task, build_actor,
    )

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    status = request.args.get('status', 'open')
    limit = min(int(request.args.get('limit', 200)), 500)

    query = _security_case_query(org.secure_code)
    if status == 'open':
        query = query.filter(db.text("fw_workflow_instances.status = 'RUNNING'"))
    elif status == 'closed':
        query = query.filter(db.text("fw_workflow_instances.status != 'RUNNING'"))

    rows = query.order_by(db.text('fw_form_instances.submitted_at DESC')
                          ).limit(limit).all()

    # 批次查各案件的待簽核節點（1-click 處置的入口鍵）
    wi_scs = [wi.secure_code for _, wi in rows]
    waiting_map = {}
    queue_map = {}
    if wi_scs:
        waiting = FwNodeExecutionQueue.query.filter(
            FwNodeExecutionQueue.org_secure_code == org.secure_code,
            FwNodeExecutionQueue.workflow_instance_secure_code.in_(wi_scs),
            FwNodeExecutionQueue.status == 'WAITING',
            FwNodeExecutionQueue.node_type.in_(_APPROVAL_NODE_TYPES),
        ).all()
        for q in waiting:
            waiting_map[q.workflow_instance_secure_code] = {
                'queue_secure_code': q.secure_code,
                'node_id': q.node_id,
                'node_name': q.node_name,
                'assignees': ((q.result or {}).get('data') or {}).get('assignees', []),
            }
            queue_map[q.workflow_instance_secure_code] = q

    user_sc = current_user.secure_code
    actor = build_actor(user_sc, org.secure_code)
    result = []
    for fi, wi in rows:
        fd = fi.form_data or {}
        severity = fd.get('severity_id')
        waiting = waiting_map.get(wi.secure_code)
        result.append({
            'workflow_instance_secure_code': wi.secure_code,
            'form_instance_secure_code': fi.secure_code,
            'execution_code': wi.execution_code,
            'serial_number': fi.serial_number,
            'subject': fi.subject,
            'form_name': fi.form_name,
            'status': wi.status,
            'severity_id': severity,
            'actor_ip': fd.get('actor_ip'),
            'source_system': fd.get('source_system'),
            'risk_score': fd.get('risk_score'),
            'recommended_action': fd.get('recommended_action'),
            'od_event_count': fd.get('od_event_count'),
            'finding_rule_id': fd.get('finding_rule_id'),
            'submitted_at': fi.submitted_at.isoformat() if fi.submitted_at else None,
            'completed_at': fi.completed_at.isoformat() if fi.completed_at else None,
            'sla_minutes': _sla_minutes(severity),
            'waiting_node': waiting,
            'can_act': bool(
                waiting and can_act_on_task(
                    queue_map.get(wi.secure_code),
                    user_sc,
                    org.secure_code,
                    actor,
                )
            ),
        })

    # EGRESS-01:form_data 衍生欄位過 list 語境政策（資源=fw_form:<模板SC>，
    # 未設政策 no-op；masked 欄位下發哨兵由前端 BkEgress 渲染）
    from app.services import egress_service
    by_template = {}
    for (fi, wi), item in zip(rows, result):
        by_template.setdefault(fi.form_template_secure_code, []).append(item)
    for template_sc, items in by_template.items():
        egress_service.apply(
            f'fw_form:{template_sc}', 'list', items,
            record_sc_key='form_instance_secure_code',
        )

    # 進行中在前，嚴重度高在前，其次新案在前
    result.sort(key=lambda c: (
        c['status'] != 'RUNNING',
        -(int(c['severity_id'] or 0) if isinstance(c['severity_id'], (int, str))
          and str(c['severity_id']).isdigit() else 0),
        c['submitted_at'] or '',
    ))

    return jsonify({'success': True, 'data': result})


@api_bp.route('/cases/stats')
@module_access_required('open_defense', False)
def case_stats():
    """頂部統計帶：進行中 / 待簽核 / SLA 逾時 / 今日封鎖 / 今日新案。"""
    from modules.form_workflow.models import FwNodeExecutionQueue

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    open_rows = _security_case_query(org.secure_code).filter(
        db.text("fw_workflow_instances.status = 'RUNNING'")).all()

    wi_scs = [wi.secure_code for _, wi in open_rows]
    waiting_scs = set()
    if wi_scs:
        waiting_scs = {
            q.workflow_instance_secure_code
            for q in FwNodeExecutionQueue.query.filter(
                FwNodeExecutionQueue.org_secure_code == org.secure_code,
                FwNodeExecutionQueue.workflow_instance_secure_code.in_(wi_scs),
                FwNodeExecutionQueue.status == 'WAITING',
                FwNodeExecutionQueue.node_type.in_(_APPROVAL_NODE_TYPES),
            ).all()
        }

    overdue = 0
    for fi, wi in open_rows:
        if wi.secure_code not in waiting_scs or not fi.submitted_at:
            continue
        sla = _sla_minutes((fi.form_data or {}).get('severity_id'))
        if sla and now > fi.submitted_at + timedelta(minutes=sla):
            overdue += 1

    today_blocks = OdDefenseDecision.query.filter(
        OdDefenseDecision.org_secure_code == org.secure_code,
        OdDefenseDecision.action == 'block',
        OdDefenseDecision.decided_at >= today_start,
        OdDefenseDecision.is_deleted == False,  # noqa: E712
    ).count()

    today_cases = _security_case_query(org.secure_code).filter(
        db.text('fw_form_instances.submitted_at >= :ts').bindparams(
            ts=today_start)).count()

    return jsonify({'success': True, 'data': {
        'open_count': len(open_rows),
        'waiting_count': len(waiting_scs),
        'overdue_count': overdue,
        'today_block_count': today_blocks,
        'today_case_count': today_cases,
    }})


@api_bp.route('/cases/<wi_sc>/payload')
@module_access_required('open_defense', False)
def case_payload(wi_sc):
    """案件原生 payload 明細與扁平欄位（detail 語境出口政策）。"""
    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    row = _security_case_query(org.secure_code).filter(
        db.text('fw_workflow_instances.secure_code = :wi_sc').bindparams(
            wi_sc=wi_sc)
    ).first()
    if not row:
        return jsonify({'success': False, 'error': 'Not found'}), 404

    form_instance, _workflow_instance = row
    form_data = form_instance.form_data or {}

    profile = None
    detail = None
    detail_key = None
    rows = []
    columns = []
    truncated = False

    profile_code = form_data.get('od_payload_profile')
    if profile_code:
        profile = OdPayloadProfile.query.filter_by(
            org_secure_code=org.secure_code,
            code=profile_code,
            is_deleted=False,
        ).first()

    if profile:
        detail_key = _payload_detail_key(profile)
        detail_rows = form_data.get(detail_key) if detail_key else None
        if isinstance(detail_rows, list):
            truncated = len(detail_rows) > _PAYLOAD_ROW_LIMIT
            rows = detail_rows[:_PAYLOAD_ROW_LIMIT]
            columns = _payload_detail_columns(profile, rows)
            detail = {
                'key': detail_key,
                'columns': columns,
                'rows': rows,
            }

    fields = _payload_scalar_fields(form_data, detail_key)
    if detail:
        fields, rows, columns = _apply_payload_egress(
            form_instance, fields, rows, columns)
        detail = {
            'key': detail_key,
            'columns': columns,
            'rows': rows,
        }
    else:
        fields, _rows, _columns = _apply_payload_egress(
            form_instance, fields, [], [])

    data = {
        'profile': ({
            'code': profile.code,
            'name': profile.name,
        } if profile else None),
        'detail': detail,
        'fields': fields,
    }
    if truncated:
        data['truncated'] = True

    return jsonify({'success': True, 'data': data})


@api_bp.route('/cases/<wi_sc>/decisions')
@module_access_required('open_defense', False)
def case_decisions(wi_sc):
    """案件關聯的防禦決策（DecisionWriter 以 case_secure_code 回鏈）。"""
    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    decisions = OdDefenseDecision.query.filter_by(
        org_secure_code=org.secure_code,
        case_secure_code=wi_sc,
        is_deleted=False,
    ).order_by(OdDefenseDecision.decided_at.desc()).all()

    return jsonify({'success': True,
                    'data': [d.to_dict() for d in decisions]})
