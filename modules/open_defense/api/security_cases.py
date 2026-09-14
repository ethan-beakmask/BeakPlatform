"""
OpenDefense Module - 資安案件處置中心 API（原子 4845）

唯讀聚合查詢，完全共用 form_workflow 引擎與資料表：
- GET /api/open_defense/cases                 案件清單（嚴重度排序、SLA、待簽核鍵）
- GET /api/open_defense/cases/stats           頂部統計帶
- GET /api/open_defense/cases/<wi_sc>/decisions  案件關聯防禦決策
- GET /api/open_defense/cases/<wi_sc>/cross-source  PF-106：跨系統關聯（即時查 防禦節點 ClickHouse）

簽核動作（1-click 處置）不在此實作——前端直接呼叫既有
/api/form-center/pending-tasks 的 lock/approve（不 clone 引擎）。

[標準 TENANT-01] 所有查詢帶 org_secure_code
"""
from datetime import datetime, timedelta

from flask import current_app, g, jsonify, request
from flask_login import current_user

from app import db
from app.security.decorators import module_access_required, page_keys_required
from app.platform.data import get_current_org
from app.utils.timezone import local_day_start_utc

from . import api_bp
from ..models import OdDefenseDecision, OdPayloadProfile

# SLA（分鐘）：severity>=4 快速通道 15 分、=3 標準 60 分；低危自動歸檔無 SLA
SLA_MINUTES_HIGH = 15
SLA_MINUTES_MEDIUM = 60

# PF-106：跨系統關聯查詢的時間窗，以案件的 submitted_at~completed_at 為基準
# 前後各加這麼多緩衝——SOC 交叉驗證通常發生在案發前後一天內，且視窗越寬
# ClickHouse 查詢成本越高（雖然有 PARTITION BY day 天然限制掃描範圍）。
CROSS_SOURCE_WINDOW_PAD = timedelta(hours=24)

# SOC 簽核節點型別（與 fc_pending 同一組）
_APPROVAL_NODE_TYPES = ('Approve', 'FormAdapter', 'FORMADAPTER')
# mine=1 反查時掃描的 WAITING 簽核佇列上限（開發環境現況全企業 68 筆，留足餘裕）
_WAITING_SCAN_LIMIT = 3000
_PAYLOAD_ROW_LIMIT = 500
_PAYLOAD_COLUMN_LIMIT = 40
_PAYLOAD_COLUMN_SCAN_LIMIT = 20
_PAYLOAD_EXCLUDED_FIELD_KEYS = {
    'severity_id', 'actor_ip', 'target_host', 'source_system',
    'finding_rule_id', 'occurred_at',
    'risk_score', 'recommended_action', 'correlation_id',
    'actor_xff',  # PF-105：在表單「攻擊者」panel 單獨呈現，不重複列在通用明細區
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


def _waiting_queues_by_case(org_sc, wi_scs=None):
    from modules.form_workflow.models import FwNodeExecutionQueue

    if wi_scs == []:
        return {}

    query = FwNodeExecutionQueue.query.filter(
        FwNodeExecutionQueue.org_secure_code == org_sc,
        FwNodeExecutionQueue.status == 'WAITING',
        FwNodeExecutionQueue.node_type.in_(_APPROVAL_NODE_TYPES),
    )
    if wi_scs is not None:
        query = query.filter(
            FwNodeExecutionQueue.workflow_instance_secure_code.in_(wi_scs),
        )
        queues = query.all()
    else:
        queues = query.order_by(FwNodeExecutionQueue.id.desc()).limit(
            _WAITING_SCAN_LIMIT + 1,
        ).all()
        if len(queues) > _WAITING_SCAN_LIMIT:
            current_app.logger.warning(
                'WAITING approval queue scan exceeded limit; mine=1 list may be incomplete',
            )
            queues = queues[:_WAITING_SCAN_LIMIT]

    grouped = {}
    for q in queues:
        grouped.setdefault(q.workflow_instance_secure_code, []).append(q)
    return grouped


def _pick_waiting(queues, user_sc, org_sc, actor):
    from modules.form_workflow.services.task_authorizer import can_act_on_task

    if not queues:
        return None, False

    first = queues[0]
    for q in queues:
        if can_act_on_task(q, user_sc, org_sc, actor):
            return q, True
    return first, False


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


def _attach_flow_labels(items, rows, org_secure_code):
    """補上「這件案子是由哪個發行版本運行的」。

    來源是案件當初綁定的 `fw_workflow_instances.published_secure_code`，
    **不是配對目前生效的版本**——流程改版後舊案件仍跑舊快照，
    顯示現行版本會讓人誤判當時走過的路徑。

    名稱取 `form_snapshot['name']`（與 /forms/mappings 的「發行名稱」同一個來源）。
    快照本身的 `name` 欄位是「表單名 + 流程名」的組合字串，過長不適合放在欄位格裡。
    """
    from modules.form_workflow.models import FwPublishedFormWorkflow

    wi_to_pub = {
        wi.secure_code: wi.published_secure_code
        for _, wi in rows if wi.published_secure_code
    }
    if not wi_to_pub:
        return

    pubs = FwPublishedFormWorkflow.query.filter(
        FwPublishedFormWorkflow.secure_code.in_(list(set(wi_to_pub.values()))),
        FwPublishedFormWorkflow.org_secure_code == org_secure_code,
        FwPublishedFormWorkflow.is_deleted == False,  # noqa: E712
    ).all()

    pub_map = {}
    for pub in pubs:
        snapshot = pub.form_snapshot or {}
        name = snapshot.get('name') if isinstance(snapshot, dict) else None
        pub_map[pub.secure_code] = {
            'flow_name': name or pub.name,
            'flow_version': pub.publish_version,
        }

    for item in items:
        info = pub_map.get(wi_to_pub.get(item['workflow_instance_secure_code']))
        if not info:
            continue
        item['flow_name'] = info['flow_name']
        item['flow_version'] = info['flow_version']
        # 格式沿用使用者指定的樣式：名稱直接接 v 版號，不加空格
        item['flow_label'] = f"{info['flow_name']}v{info['flow_version']}"


@api_bp.route('/cases')
@module_access_required('open_defense', False)
@page_keys_required('open_defense.security_cases')  # PF-145：API 不吃雙鑰匙，須自掛 Key1+Key2
def list_cases():
    """
    案件清單。

    Query:
        status: open(預設，流程進行中) / closed / all
        mine:   1/true 時只回傳當前帳號有權簽核的案件（can_act），
                值班人員預設視角；closed 案件無待簽核節點，帶此參數會全空
        limit:  最多筆數（預設 200）

    回傳順序為 SQL 的 submitted_at DESC（最新在前），細部排序由前端負責。
    """
    from modules.form_workflow.models import FwWorkflowInstance
    from modules.form_workflow.services.task_authorizer import build_actor

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    status = request.args.get('status', 'open')
    only_mine = str(request.args.get('mine', '')).lower() in ('1', 'true')
    limit = min(int(request.args.get('limit', 200)), 500)

    query = _security_case_query(org.secure_code)
    if status == 'open':
        query = query.filter(db.text("fw_workflow_instances.status = 'RUNNING'"))
    elif status == 'closed':
        query = query.filter(db.text("fw_workflow_instances.status != 'RUNNING'"))

    user_sc = current_user.secure_code
    actor = build_actor(user_sc, org.secure_code)

    actionable = {}
    if only_mine:
        grouped = _waiting_queues_by_case(org.secure_code)
        for wi_sc, queues in grouped.items():
            picked, can_act = _pick_waiting(queues, user_sc, org.secure_code, actor)
            if can_act:
                actionable[wi_sc] = picked
        if not actionable:
            return jsonify({'success': True, 'data': [], 'truncated': False})
        query = query.filter(
            FwWorkflowInstance.secure_code.in_(list(actionable.keys())),
        )

    rows = query.order_by(db.text('fw_form_instances.submitted_at DESC')
                          ).limit(limit + 1).all()
    truncated = len(rows) > limit
    rows = rows[:limit]

    if only_mine:
        picked_map = {
            wi.secure_code: (actionable[wi.secure_code], True)
            for _, wi in rows
        }
    else:
        grouped = _waiting_queues_by_case(
            org.secure_code,
            [wi.secure_code for _, wi in rows],
        )
        picked_map = {
            wi_sc: _pick_waiting(queues, user_sc, org.secure_code, actor)
            for wi_sc, queues in grouped.items()
        }

    result = []
    by_template = {}
    for fi, wi in rows:
        fd = fi.form_data or {}
        severity = fd.get('severity_id')
        picked, can_act = picked_map.get(wi.secure_code, (None, False))
        waiting = ({
            'queue_secure_code': picked.secure_code,
            'node_id': picked.node_id,
            'node_name': picked.node_name,
            'assignees': ((picked.result or {}).get('data') or {}).get('assignees', []),
        } if picked else None)
        item = {
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
            'can_act': can_act,
        }
        result.append(item)
        by_template.setdefault(fi.form_template_secure_code, []).append(item)

    # EGRESS-01:form_data 衍生欄位過 list 語境政策（資源=fw_form:<模板SC>，
    # 未設政策 no-op；masked 欄位下發哨兵由前端 BkEgress 渲染）
    from app.services import egress_service
    for template_sc, items in by_template.items():
        egress_service.apply(
            f'fw_form:{template_sc}', 'list', items,
            record_sc_key='form_instance_secure_code',
        )

    # 出口政策之後才補：flow_* 不是 form_data 衍生欄位，不受 fw_form 政策管轄
    _attach_flow_labels(result, rows, org.secure_code)

    return jsonify({'success': True, 'data': result, 'truncated': truncated})


@api_bp.route('/cases/stats')
@module_access_required('open_defense', False)
@page_keys_required('open_defense.security_cases')  # PF-145：API 不吃雙鑰匙，須自掛 Key1+Key2
def case_stats():
    """頂部統計帶：進行中 / 待簽核 / SLA 逾時 / 今日封鎖 / 今日新案。"""
    from modules.form_workflow.models import FwNodeExecutionQueue

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    now = datetime.utcnow()
    today_start = local_day_start_utc(
        getattr(g, 'timezone', 'Asia/Taipei'), now)

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
@page_keys_required('open_defense.security_cases')  # PF-145：API 不吃雙鑰匙，須自掛 Key1+Key2
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
@page_keys_required('open_defense.security_cases')  # PF-145：API 不吃雙鑰匙，須自掛 Key1+Key2
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


def _cross_source_window(form_instance):
    """本案件的關聯查詢時間窗：submitted_at ~ completed_at（進行中案件無
    completed_at，用現在時間頂替），前後各加 CROSS_SOURCE_WINDOW_PAD。"""
    start = form_instance.submitted_at or datetime.utcnow()
    end = form_instance.completed_at or datetime.utcnow()
    if end < start:
        end = start
    return start - CROSS_SOURCE_WINDOW_PAD, end + CROSS_SOURCE_WINDOW_PAD


@api_bp.route('/cases/<wi_sc>/cross-source')
@module_access_required('open_defense', False)
@page_keys_required('open_defense.security_cases')  # PF-145：API 不吃雙鑰匙，須自掛 Key1+Key2
def case_cross_source(wi_sc):
    """
    PF-106：同 actor_ip 在時間窗內、防禦節點 各資安套件（coraza/suricata/...）的
    關聯事件。即時查詢 ClickHouse，唯讀，不寫任何資料。

    租戶隔離：ClickHouse 沒有 org 概念，本端點先用既有的 org 過濾查詢
    （_security_case_query）驗過案件屬於當前企業，才把驗證過的 actor_ip
    交給 cross_source_service——不提供任何未經此驗證的 ClickHouse 查詢管道。

    ClickHouse 不可用（未設定/連線失敗/逾時）時仍回 200，
    data.available=false，前端據此隱藏「跨系統關聯」與各套件分頁，
    不讓案件頁整頁失敗（VERIFY-01 驗收項 5）。
    """
    from ..services.cross_source_service import get_cross_source

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
    actor_ip = form_data.get('actor_ip')

    window_start, window_end = _cross_source_window(form_instance)
    data = get_cross_source(actor_ip, window_start, window_end)

    # EGRESS-01：target_host / actor_xff 沿用該案件表單的既有出口政策
    # （resource=fw_form:<模板SC>，與 _apply_payload_egress 同一套資源代碼），
    # 未設政策時 apply() 是 no-op，事件列表原樣通過。
    if data.get('events'):
        from app.services import egress_service

        rows = [
            {
                'form_instance_secure_code': form_instance.secure_code,
                'target_host': ev.get('target_host'),
                'actor_xff': ev.get('actor_xff'),
            }
            for ev in data['events']
        ]
        filtered = egress_service.apply(
            f'fw_form:{form_instance.form_template_secure_code}', 'detail',
            rows, record_sc_key='form_instance_secure_code',
        )
        for ev, filt in zip(data['events'], filtered):
            ev['target_host'] = filt.get('target_host')
            ev['actor_xff'] = filt.get('actor_xff')

    return jsonify({'success': True, 'data': data})
