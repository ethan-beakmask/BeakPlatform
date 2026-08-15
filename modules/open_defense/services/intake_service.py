"""
OpenDefense Module - Intake Service

接收正規化後的 OCSF 事件,執行:
  1. 冪等檢查(correlation_id)
  2. source_system 白名單比對
  3. 規則式路由決定 form_template(查 OdFormTemplateMapping)
  4. 聚合降噪:同 攻擊者IP+rule_id 於時間窗內合併升級既有案件,不開新案
  5. 建立 FwFormInstance(含情報 enrichment 欄位) + 啟動 workflow
  6. 寫 OdIntakeEvent 並回填 case_secure_code
"""
import logging
import secrets
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

from flask_babel import gettext as _

from app import db
from app.models.api_key import ApiKey
from app.utils.security import generate_secure_code

from ..models import OdIntakeEvent
from . import payload_profile_service
from .routing_service import resolve_form_template

logger = logging.getLogger(__name__)

# 聚合降噪:同 攻擊者IP+rule_id 在此時間窗內合併進既有案件(原子 4844)
AGGREGATION_WINDOW_MINUTES = 60
# 情報 enrichment:「同源事件數」的回看範圍
REPEAT_LOOKBACK_HOURS = 24
# 風險分數達此值時建議封鎖
RISK_BLOCK_THRESHOLD = 60


class IntakeError(Exception):
    """Intake 處理錯誤"""
    def __init__(self, message: str, code: str = 'intake_error',
                 status: int = 422):
        super().__init__(message)
        self.code = code
        self.status = status


def _build_form_data(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    從 OCSF event 抽出供 form 用的初始欄位。

    禁止把整段 raw_body 寫進 form_data:
      - 可能含 PII
      - 大小不可控
      - 後續查表會被拖慢

    只取「workflow 節點 / decision_writer 會引用」的少量關鍵欄位。
    """
    actor = event.get('actor') or {}
    target = event.get('target') or {}
    finding = event.get('finding') or {}
    detector_hint = event.get('detector_hint') or {}

    return {
        'correlation_id': event.get('correlation_id'),
        'source_system': event.get('source_system'),
        'event_class': event.get('event_class'),
        'occurred_at': event.get('occurred_at'),
        'severity_id': event.get('severity_id'),
        'confidence': event.get('confidence'),

        'actor_ip': actor.get('ip'),
        'actor_asn': actor.get('asn'),
        'actor_country': actor.get('country'),
        'actor_user_agent': actor.get('user_agent'),
        # PF-105：完整 XFF 鏈原文（證據欄位，不參與聚合/風險分數判定，判定一律看 actor_ip）
        'actor_xff': actor.get('xff'),

        'target_host': target.get('host'),
        'target_url': target.get('url'),
        'target_service': target.get('service'),

        'finding_title': finding.get('title'),
        'finding_summary': finding.get('summary'),
        'finding_rule_id': finding.get('rule_id'),
        'finding_rule_set': finding.get('rule_set'),

        'detector_hint_action': detector_hint.get('action'),
        'detector_hint_ttl_sec': detector_hint.get('ttl_sec'),
    }


def _compute_risk(severity_id, repeat_count, history_block_count) -> Tuple[int, str]:
    """
    規則式風險分數(0-100)與建議處置。

    severity 權重最高,重複出現與歷史封鎖紀錄加成;
    等資料量足夠再考慮 ML(交接文件已與用戶議定初期用規則)。
    """
    sev = int(severity_id or 0)
    repeat = int(repeat_count or 0)
    history = int(history_block_count or 0)
    score = min(100, sev * 15 + min(repeat, 6) * 5 + min(history, 3) * 10)
    action = 'block' if score >= RISK_BLOCK_THRESHOLD else 'observe'
    return score, action


def _enrich_form_data(org_secure_code: str, form_data: Dict[str, Any]) -> None:
    """
    情報 enrichment(就地補欄位):同源事件數、歷史封鎖次數、
    風險分數與建議處置。封閉網路 v1 只查內部資料源;
    外部情資(VT/ASN mirror)留待 SOC-4 節點化。
    """
    from datetime import timedelta
    from ..models import OdDefenseDecision

    actor_ip = form_data.get('actor_ip')

    repeat_count = 0
    history_block_count = 0
    if actor_ip:
        from modules.form_workflow.models import FwWorkflowInstance, FwFormInstance

        lookback = datetime.utcnow() - timedelta(hours=REPEAT_LOOKBACK_HOURS)
        # 比對走案件表單的共同軸線 actor_ip,不讀 raw_body(PF-75)。
        # OCSF 的 raw_body 是 {actor:{ip}},原生 payload 是來源系統的原始結構,
        # 讀 raw_body['actor']['ip'] 對原生事件恆為 NULL ->
        # repeat_count 永遠 0 -> 風險分數被低估 -> 建議處置偏向 observe。
        # form_data 的 6 個共同軸線才是兩種格式的交會點。
        # 這裡刻意不做格式隔離:同一 IP 被不同偵測器看到,正是風險升高的訊號。
        repeat_count = db.session.query(OdIntakeEvent).join(
            FwWorkflowInstance,
            OdIntakeEvent.case_secure_code == FwWorkflowInstance.secure_code,
        ).join(
            FwFormInstance,
            FwFormInstance.secure_code == FwWorkflowInstance.form_instance_secure_code,
        ).filter(
            OdIntakeEvent.org_secure_code == org_secure_code,
            OdIntakeEvent.received_at >= lookback,
            FwWorkflowInstance.org_secure_code == org_secure_code,
            FwWorkflowInstance.is_deleted.is_(False),
            FwFormInstance.form_data['actor_ip'].astext == actor_ip,
        ).count()
        history_block_count = OdDefenseDecision.query.filter_by(
            org_secure_code=org_secure_code,
            action='block',
            target_type='ip',
            target_value=actor_ip,
            is_deleted=False,
        ).count()

    risk_score, recommended = _compute_risk(
        form_data.get('severity_id'), repeat_count, history_block_count)

    now_iso = datetime.utcnow().isoformat() + 'Z'
    form_data.update({
        'od_event_count': 1,
        'od_repeat_count': repeat_count,
        'od_history_block_count': history_block_count,
        'risk_score': risk_score,
        'recommended_action': recommended,
        'od_first_seen': form_data.get('occurred_at') or now_iso,
        'od_last_seen': form_data.get('occurred_at') or now_iso,
    })


def _find_mergeable_case(
    org_secure_code: str,
    actor_ip: Optional[str],
    rule_id: Optional[str],
    severity_id: Optional[int],
    payload_kind: str,
    source_system: Optional[str] = None,
):
    """
    聚合降噪:找時間窗內同 攻擊者IP+rule_id 的既有案件。

    - 一般情況只合併進「流程仍在跑(RUNNING)」的案件
    - 低危(severity<=2)雜訊連已結案的窗內案件也合併(純計數,避免灌出海量歸檔案)

    Returns:
        FwWorkflowInstance 或 None
    """
    if not actor_ip or not rule_id:
        return None

    if payload_kind not in ('ocsf', 'native'):
        logger.warning('intake aggregation skipped: invalid payload_kind=%r', payload_kind)
        return None

    if payload_kind == 'native' and not source_system:
        logger.warning('native intake aggregation skipped: missing source_system')
        return None

    from modules.form_workflow.models import FwWorkflowInstance, FwFormInstance

    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(minutes=AGGREGATION_WINDOW_MINUTES)

    query = db.session.query(FwWorkflowInstance).join(
        OdIntakeEvent,
        OdIntakeEvent.case_secure_code == FwWorkflowInstance.secure_code,
    ).join(
        FwFormInstance,
        FwFormInstance.secure_code == FwWorkflowInstance.form_instance_secure_code,
    ).filter(
        OdIntakeEvent.org_secure_code == org_secure_code,
        OdIntakeEvent.received_at >= cutoff,
        OdIntakeEvent.case_secure_code.isnot(None),
        FwWorkflowInstance.org_secure_code == org_secure_code,
        FwWorkflowInstance.is_deleted.is_(False),
        FwFormInstance.form_data['actor_ip'].astext == actor_ip,
        FwFormInstance.form_data['finding_rule_id'].astext == rule_id,
    )

    if payload_kind == 'native':
        query = query.filter(
            OdIntakeEvent.event_class == 'native',
            OdIntakeEvent.source_system == source_system,
        )
    else:
        query = query.filter(OdIntakeEvent.event_class != 'native')

    candidates = query.order_by(
        OdIntakeEvent.received_at.desc()
    ).limit(20).all()

    merge_closed_ok = (severity_id or 0) <= 2
    for workflow_instance in candidates:
        if workflow_instance.status == 'RUNNING' or merge_closed_ok:
            return workflow_instance
    return None


def _merge_event_into_case(event: OdIntakeEvent, workflow_instance) -> None:
    """
    把新事件合併進既有案件:計數累加、severity 取 max、
    last_seen 更新、風險分數重算。severity 升高視為案件升級(記 log)。
    """
    from modules.form_workflow.models import FwFormInstance

    form_instance = FwFormInstance.query.filter_by(
        secure_code=workflow_instance.form_instance_secure_code,
    ).first()

    event.case_secure_code = workflow_instance.secure_code

    if form_instance is None:
        return

    fd = dict(form_instance.form_data or {})
    fd['od_event_count'] = int(fd.get('od_event_count') or 1) + 1

    old_sev = int(fd.get('severity_id') or 0)
    new_sev = int(event.severity_id or 0)
    escalated = new_sev > old_sev
    if escalated:
        fd['severity_id'] = new_sev

    fd['od_last_seen'] = ((event.raw_body or {}).get('occurred_at')
                          or datetime.utcnow().isoformat() + 'Z')
    fd['risk_score'], fd['recommended_action'] = _compute_risk(
        fd.get('severity_id'),
        max(int(fd.get('od_repeat_count') or 0), fd['od_event_count']),
        fd.get('od_history_block_count'),
    )
    form_instance.form_data = fd

    if escalated:
        logger.warning(
            'intake merge escalated case=%s severity %s -> %s (event %s)',
            workflow_instance.execution_code, old_sev, new_sev,
            event.correlation_id,
        )


def _generate_serial_number(org_secure_code: str) -> str:
    """OD 專用流水號:OD-YYYYMMDD-<8 hex>"""
    date_str = datetime.utcnow().strftime('%Y%m%d')
    return f'OD-{date_str}-{secrets.token_hex(4).upper()}'


def _create_form_instance_and_start_workflow(
    org_secure_code: str,
    form_template_sc: str,
    form_data: Dict[str, Any],
    subject: str,
    source_ip: Optional[str],
) -> Tuple[str, str]:
    """
    依 form_template_sc 找最新已發行(Published)的 PublishedFormWorkflow,
    建立 form_instance + workflow_instance + 起始節點 queue_item。

    參考 modules/form_workflow/api/fc_fill.py 的「正式模式」路徑。
    Webhook 不支援測試模式 -- form_template 必須已發行才能接收事件。

    Returns:
        (form_instance_secure_code, workflow_instance_secure_code)
    """
    from sqlalchemy import text
    from modules.form_workflow.models import (
        FwFormTemplate, FwPublishedFormWorkflow,
        FwFormInstance, FwWorkflowInstance, FwNodeExecutionQueue,
    )

    template = FwFormTemplate.query.filter_by(
        secure_code=form_template_sc,
        org_secure_code=org_secure_code,
        is_deleted=False,
    ).first()
    if not template:
        raise IntakeError(
            _('form template %(form_template_sc)s 不存在或不屬於本企業',
              form_template_sc=form_template_sc),
            code='template_not_found', status=500,
        )

    published = FwPublishedFormWorkflow.query.filter_by(
        source_form_template_secure_code=form_template_sc,
        org_secure_code=org_secure_code,
        status='Published',
        is_deleted=False,
    ).order_by(FwPublishedFormWorkflow.published_at.desc()).first()
    if not published:
        raise IntakeError(
            _('form template %(form_template_sc)s 尚無 Published 版本,請先在表單設計器發行',
              form_template_sc=form_template_sc),
            code='form_not_published', status=422,
        )

    published.mark_as_used()

    form_snapshot = published.form_snapshot or {}
    workflow_snapshot = published.workflow_snapshot or {}
    workflow_graph = (workflow_snapshot.get('graph')
                      or workflow_snapshot.get('cytoscape_config') or {})

    # 起始節點檢查(早 fail)
    start_node = None
    for node in workflow_graph.get('nodes', []):
        node_id = node.get('id', '')
        node_type = node.get('type', '')
        if node_id.startswith('node-Start') or node_type in ('Start', 'START'):
            start_node = node
            break
    if not start_node:
        raise IntakeError(
            _('工作流模板缺 Start 節點'),
            code='workflow_no_start', status=500,
        )

    # form_instance
    form_instance = FwFormInstance(
        secure_code=generate_secure_code(),
        org_secure_code=org_secure_code,
        form_template_id=published.source_form_template_id,
        form_template_secure_code=published.source_form_template_secure_code,
        published_secure_code=published.secure_code,
        serial_number=_generate_serial_number(org_secure_code),
        form_name=form_snapshot.get('name'),
        form_code=form_snapshot.get('code'),
        form_version=published.source_form_version,
        applicant_secure_code=None,
        applicant_name='OpenDefense Webhook',
        subject=(subject or 'OpenDefense Event')[:500],
        form_data=form_data,
        schema_snapshot=form_snapshot.get('schema'),
        builder_config=form_snapshot.get('builder_config'),
        status='INITIAL',
        source_type='WEBHOOK_OD',
        source_ip=source_ip,
        submitted_at=datetime.utcnow(),
        is_test=False,
    )
    db.session.add(form_instance)
    db.session.flush()

    # 流程編號 -- SELECT MAX+1 在並發時會撞 unique key,
    # 用 PostgreSQL transaction-scoped advisory lock 強制序列化(per org+date 鍵)。
    # 鎖在 commit/rollback 自動釋放,不會 leak。
    date_str = datetime.utcnow().strftime('%Y%m%d')
    lock_key = f'od_exec_seq:{org_secure_code}:{date_str}'
    db.session.execute(
        text('SELECT pg_advisory_xact_lock(hashtext(:key))'),
        {'key': lock_key},
    )
    proc_seq = db.session.execute(
        text("""
            SELECT COALESCE(MAX(CAST(SUBSTRING(execution_code FROM '\\d{4}$')
                AS INTEGER)), 0) + 1
            FROM fw_workflow_instances
            WHERE execution_code LIKE :pattern
        """),
        {'pattern': f'OD-{date_str}-%'},
    ).scalar() or 1
    execution_code = f'OD-{date_str}-{str(proc_seq).zfill(4)}'

    workflow_instance = FwWorkflowInstance(
        secure_code=generate_secure_code(),
        org_secure_code=org_secure_code,
        form_instance_id=form_instance.id,
        form_instance_secure_code=form_instance.secure_code,
        workflow_template_id=published.source_workflow_template_id,
        workflow_template_secure_code=published.source_workflow_template_secure_code,
        published_secure_code=published.secure_code,
        execution_code=execution_code,
        workflow_name=workflow_snapshot.get('name'),
        workflow_version=published.source_workflow_version,
        graph_snapshot=workflow_graph,
        status='RUNNING',
        started_at=datetime.utcnow(),
    )
    db.session.add(workflow_instance)
    db.session.flush()

    form_instance.workflow_instance_id = workflow_instance.id
    form_instance.workflow_instance_secure_code = workflow_instance.secure_code

    # 起始節點入佇列
    queue_item = FwNodeExecutionQueue(
        secure_code=generate_secure_code(),
        org_secure_code=org_secure_code,
        workflow_instance_secure_code=workflow_instance.secure_code,
        form_instance_secure_code=form_instance.secure_code,
        node_id=start_node.get('id'),
        node_type='Start',
        node_name=(start_node.get('label')
                  or start_node.get('data', {}).get('label')
                  or _('開始')),
        node_config=start_node.get('config', {}),
        status='PENDING',
        priority=10,
        scheduled_at=datetime.utcnow(),
    )
    db.session.add(queue_item)
    db.session.flush()

    return form_instance.secure_code, workflow_instance.secure_code


def process_intake(
    *,
    api_key: ApiKey,
    body: Dict[str, Any],
    source_ip: Optional[str] = None,
) -> Tuple[OdIntakeEvent, bool]:
    """
    主處理函式。P2 起收平台 ApiKey,source 白名單讀
    scopes['od_intake']['source_systems']。

    Returns:
        (event_record, duplicate_flag)
    Raises:
        IntakeError: 業務錯誤(source 不允許 / 無 mapping / workflow 啟動失敗)
    """
    correlation_id = body['correlation_id']
    source_system = body['source_system']
    event_class = body['event_class']
    org_sc = api_key.org_secure_code

    # 1. 冪等
    existing = OdIntakeEvent.query.filter_by(
        correlation_id=correlation_id,
    ).first()
    if existing:
        logger.info('intake duplicate correlation_id=%s key=%s',
                   correlation_id, api_key.key_id)
        return existing, True

    # 2. source 白名單(od_intake scope)
    od_scope = (api_key.scopes or {}).get('od_intake') or {}
    allowed = od_scope.get('source_systems') or []
    if source_system not in allowed:
        raise IntakeError(
            _('source_system %(source_system)r 不在 key 允許清單',
              source_system=source_system),
            code='source_not_allowed', status=403,
        )

    # 3. routing
    template_sc = resolve_form_template(org_sc, body)
    if not template_sc:
        raise IntakeError(
            _('event_class %(event_class)r 在本企業無命中的 form_template 路由規則,請至 /open-defense/routing-rules 設定',
              event_class=event_class),
            code='no_mapping', status=422,
        )

    # 4. 先寫 OdIntakeEvent(無 case_secure_code,後面回填),確保 unique 約束保證冪等
    event = OdIntakeEvent(
        secure_code=generate_secure_code(),
        org_secure_code=org_sc,
        correlation_id=correlation_id,
        intake_key_secure_code=api_key.secure_code,  # P2 起為平台 ApiKey 的 SC
        source_system=source_system,
        event_class=event_class,
        severity_id=body.get('severity_id'),
        raw_body=body,
        signature_verified=True,
        case_secure_code=None,
        received_at=datetime.utcnow(),
    )
    db.session.add(event)
    try:
        db.session.flush()
    except Exception:
        # 競賽:同 correlation_id 並發插入,unique 約束打回。回查並回傳 existing。
        db.session.rollback()
        existing = OdIntakeEvent.query.filter_by(
            correlation_id=correlation_id,
        ).first()
        if existing:
            return existing, True
        raise

    # 5. 聚合降噪:時間窗內同 攻擊者IP+rule_id 合併進既有案件,不開新案
    actor = body.get('actor') or {}
    finding = body.get('finding') or {}
    mergeable = _find_mergeable_case(
        org_secure_code=org_sc,
        actor_ip=actor.get('ip'),
        rule_id=finding.get('rule_id'),
        severity_id=body.get('severity_id'),
        payload_kind='ocsf',
    )
    if mergeable is not None:
        _merge_event_into_case(event, mergeable)
        db.session.commit()
        logger.info(
            'intake merged correlation_id=%s into case=%s',
            correlation_id, mergeable.execution_code,
        )
        return event, False

    # 6. 啟 workflow(含情報 enrichment)
    subject = finding.get('title') or f'{source_system} {event_class}'
    form_data = _build_form_data(body)
    _enrich_form_data(org_sc, form_data)

    try:
        # 這裡不能用 `_` 當拋棄式變數:模組層有 `from flask_babel import gettext as _`,
        # 函式內任何一處對 `_` 賦值,整個函式的 `_` 就變成區域變數,
        # 導致本函式前段(第 440/449 行)的 `_('...')` 拋 UnboundLocalError
        # ——本該回 403/400 的清楚錯誤變成 500,而 500 會讓 Vector 無限重試。
        _form_instance_sc, workflow_instance_sc = _create_form_instance_and_start_workflow(
            org_secure_code=org_sc,
            form_template_sc=template_sc,
            form_data=form_data,
            subject=subject,
            source_ip=source_ip,
        )
    except IntakeError:
        db.session.rollback()
        raise
    except Exception as exc:
        db.session.rollback()
        logger.exception('intake workflow start failed')
        raise IntakeError(
            _('啟動 workflow 失敗: %(error)s', error=exc),
            code='workflow_start_failed', status=500,
        )

    # 7. 回填 case_secure_code(= workflow_instance.secure_code)
    event.case_secure_code = workflow_instance_sc
    db.session.commit()

    logger.info(
        'intake processed correlation_id=%s event_sc=%s workflow_sc=%s',
        correlation_id, event.secure_code, workflow_instance_sc,
    )
    return event, False


def _native_subject(payload: Dict[str, Any], profile, axis: Dict[str, Any]) -> str:
    details = payload_profile_service.extract_details(
        payload,
        profile.detail_path,
        profile.detail_item_key,
    ) if profile.detail_path else []
    # 明細列的標題欄位名由 profile 指定,不同來源的欄位名不同,不可寫死
    event_name = None
    if profile.subject_detail_key and details and isinstance(details[0], dict):
        event_name = details[0].get(profile.subject_detail_key)

    parts = [
        value for value in (axis.get('finding_rule_id'), event_name)
        if value
    ]
    if parts:
        return ' '.join(str(value) for value in parts)
    return f'{profile.source_system} {profile.code}'


def process_native_intake(
    *,
    api_key: ApiKey,
    payload: Dict[str, Any],
    profile,
    source_ip: Optional[str] = None,
) -> Tuple[OdIntakeEvent, bool]:
    """
    原生格式事件接收。與 process_intake 共用冪等/聚合/建案，差別只在
    payload 解析方式與路由的 payload_kind。
    """
    org_sc = api_key.org_secure_code
    correlation_id = payload_profile_service.resolve_correlation_id(payload, profile)
    if not correlation_id:
        raise IntakeError(
            _('缺少 correlation_id'),
            code='missing_correlation_id', status=400,
        )

    existing = OdIntakeEvent.query.filter_by(
        correlation_id=correlation_id,
    ).first()
    if existing:
        logger.info('native intake duplicate correlation_id=%s key=%s',
                    correlation_id, api_key.key_id)
        return existing, True

    od_scope = (api_key.scopes or {}).get('od_intake') or {}
    allowed = od_scope.get('source_systems') or []
    if profile.source_system not in allowed:
        raise IntakeError(
            _('source_system %(source_system)r 不在 key 允許清單',
              source_system=profile.source_system),
            code='source_not_allowed', status=403,
        )

    axis = payload_profile_service.normalize_axis_fields(payload, profile)

    template_sc = resolve_form_template(org_sc, payload, payload_kind='native')
    if not template_sc:
        raise IntakeError(
            _('原生 payload 在本企業無命中的 form_template 路由規則,請至 /open-defense/routing-rules 設定'),
            code='no_mapping', status=422,
        )

    event = OdIntakeEvent(
        secure_code=generate_secure_code(),
        org_secure_code=org_sc,
        correlation_id=correlation_id,
        intake_key_secure_code=api_key.secure_code,
        source_system=profile.source_system,
        event_class='native',
        severity_id=axis.get('severity_id'),
        raw_body=payload,
        signature_verified=True,
        case_secure_code=None,
        received_at=datetime.utcnow(),
    )
    db.session.add(event)
    try:
        db.session.flush()
    except Exception:
        db.session.rollback()
        existing = OdIntakeEvent.query.filter_by(
            correlation_id=correlation_id,
        ).first()
        if existing:
            return existing, True
        raise

    mergeable = None
    if axis.get('actor_ip') and axis.get('finding_rule_id'):
        mergeable = _find_mergeable_case(
            org_secure_code=org_sc,
            actor_ip=axis.get('actor_ip'),
            rule_id=axis.get('finding_rule_id'),
            severity_id=axis.get('severity_id'),
            payload_kind='native',
            source_system=profile.source_system,
        )
    if mergeable is not None:
        _merge_event_into_case(event, mergeable)
        db.session.commit()
        logger.info(
            'native intake merged correlation_id=%s into case=%s',
            correlation_id, mergeable.execution_code,
        )
        return event, False

    form_data = payload_profile_service.build_native_form_data(payload, profile)
    _enrich_form_data(org_sc, form_data)
    subject = _native_subject(payload, profile, axis)

    try:
        _form_instance_sc, workflow_instance_sc = _create_form_instance_and_start_workflow(
            org_secure_code=org_sc,
            form_template_sc=template_sc,
            form_data=form_data,
            subject=subject,
            source_ip=source_ip,
        )
    except IntakeError:
        db.session.rollback()
        raise
    except Exception as exc:
        db.session.rollback()
        logger.exception('native intake workflow start failed')
        raise IntakeError(
            _('啟動 workflow 失敗: %(error)s', error=exc),
            code='workflow_start_failed', status=500,
        )

    event.case_secure_code = workflow_instance_sc
    db.session.commit()

    logger.info(
        'native intake processed correlation_id=%s event_sc=%s workflow_sc=%s',
        correlation_id, event.secure_code, workflow_instance_sc,
    )
    return event, False
