"""
OpenDefense Module - Intake Service

接收正規化後的 OCSF 事件,執行:
  1. 冪等檢查(correlation_id)
  2. source_system 白名單比對
  3. event_class -> form_template 對應(查 OdFormTemplateMapping)
  4. 建立 FwFormInstance + 啟動 workflow
  5. 寫 OdIntakeEvent 並回填 case_secure_code
"""
import logging
import secrets
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

from app import db
from app.models.api_key import ApiKey
from app.utils.security import generate_secure_code

from ..models import OdIntakeEvent, OdFormTemplateMapping

logger = logging.getLogger(__name__)


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


def _lookup_form_template(org_secure_code: str, event_class: str) -> Optional[str]:
    """查 OdFormTemplateMapping 取得 form_template_secure_code"""
    mapping = OdFormTemplateMapping.query.filter_by(
        org_secure_code=org_secure_code,
        event_class=event_class,
        is_deleted=False,
    ).first()
    return mapping.form_template_secure_code if mapping else None


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
            f'form template {form_template_sc} 不存在或不屬於本企業',
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
            f'form template {form_template_sc} 尚無 Published 版本,'
            f'請先在表單設計器發行',
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
            '工作流模板缺 Start 節點',
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
                  or '開始'),
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
            f'source_system {source_system!r} 不在 key 允許清單',
            code='source_not_allowed', status=403,
        )

    # 3. mapping
    template_sc = _lookup_form_template(org_sc, event_class)
    if not template_sc:
        raise IntakeError(
            f'event_class {event_class!r} 在本企業無對應 form_template,'
            f'請至 /open-defense/intake-keys 設定 mapping',
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

    # 5. 啟 workflow
    finding = body.get('finding') or {}
    subject = finding.get('title') or f'{source_system} {event_class}'
    form_data = _build_form_data(body)

    try:
        _, workflow_instance_sc = _create_form_instance_and_start_workflow(
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
            f'啟動 workflow 失敗: {exc}',
            code='workflow_start_failed', status=500,
        )

    # 6. 回填 case_secure_code(= workflow_instance.secure_code)
    event.case_secure_code = workflow_instance_sc
    db.session.commit()

    logger.info(
        'intake processed correlation_id=%s event_sc=%s workflow_sc=%s',
        correlation_id, event.secure_code, workflow_instance_sc,
    )
    return event, False
