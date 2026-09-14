"""
FormWorkflow Module - Form Submit Service

送單核心邏輯(序號配發 -> 建立表單/流程實例 -> Start 節點入佇列),
供表單中心 Submit API(fc_fill.py)與外部發動閘道(external_trigger.py)共用,
避免兩處各自維護造成漂移。

規格: dev-notes/API_KEY_TRIGGER_SPEC.md §3
"""
import secrets
import logging
from datetime import datetime
from typing import Optional, Tuple

from app import db
from app.models import UserNumberingRule
from app.services.numbering_service import NumberingService
from flask_babel import gettext as _

from .sequence_code_service import (
    next_execution_code, next_form_serial_number, next_org_form_seq,
)

logger = logging.getLogger(__name__)


class SubmitError(Exception):
    """送單流程錯誤(訊息可直接回給呼叫端)"""


def allocate_serial_number(
    org_secure_code: str,
    is_test: bool,
    published=None,
) -> Tuple[str, Optional[int]]:
    """
    配發表單序號。

    測試模式: TEST-YYYYMMDD-NNNN
    正式模式: mapping 綁定的編號規則 > 企業預設 FORM 規則 > FORM-YYYYMMDD-NNNNN fallback

    Returns:
        (serial_number, org_form_seq)  -- org_form_seq 僅正式模式有值
    """
    date_str = datetime.now().strftime('%Y%m%d')

    if is_test:
        return next_form_serial_number(
            org_secure_code=org_secure_code,
            prefix='TEST-',
            date_str=date_str,
            digits=4,
        ), None

    # 正式模式：透過萬用編號系統取得企業專屬格式
    # 從 mapping 讀取編號規則（即時生效，不需重新發行）
    form_rule = None
    if published is not None:
        from ..models import FwFormWorkflowMapping
        mapping_obj = FwFormWorkflowMapping.query.filter_by(
            secure_code=published.source_mapping_secure_code,
            is_deleted=False
        ).first()
        if mapping_obj and mapping_obj.numbering_rule_secure_code:
            form_rule = UserNumberingRule.query.filter_by(
                secure_code=mapping_obj.numbering_rule_secure_code,
                org_secure_code=org_secure_code,
                is_active=True,
                is_deleted=False
            ).first()
    if not form_rule:
        form_rule = NumberingService.get_default_rule(
            org_secure_code, default_for='FORM'
        )

    if form_rule:
        detail = NumberingService.get_next_number_with_detail(
            form_rule, consume=True
        )
        serial_number = detail['number']
        # org_form_seq 獨立於編號規則，取企業層級最大值 +1
        # （序號池與 advisory lock 都在 sequence_code_service 內，見該檔 docstring）
        return serial_number, next_org_form_seq(org_secure_code=org_secure_code)

    # 無規則 fallback：FORM-YYYYMMDD-NNNNN
    return next_form_serial_number(
        org_secure_code=org_secure_code,
        prefix='FORM-',
        date_str=date_str,
        digits=5,
    ), None


def create_instance_and_start(
    *,
    org_secure_code: str,
    serial_number: str,
    org_form_seq: Optional[int],
    subject: str,
    form_data: dict,
    is_test: bool,
    source_type: str,
    source_ip: Optional[str],
    source_api_key: Optional[str] = None,
    # 表單/流程定義(呼叫端已依模式解析好)
    form_name=None, form_code=None, form_version=None,
    form_schema=None, form_builder_config=None,
    workflow_name=None, workflow_version=None, workflow_graph=None,
    source_form_template_id=None, source_form_template_secure_code=None,
    source_workflow_template_id=None, source_workflow_template_secure_code=None,
    published_sc=None,
    proc_prefix='PROC-',
    # 申請人
    applicant_secure_code=None, applicant_name=None,
    applicant_username=None, applicant_email=None, applicant_dept=None,
    # NoCode portal source tracking
    nocode_sub_system_sc=None, nocode_user_ref=None,
):
    """
    建立 FwFormInstance + FwWorkflowInstance(RUNNING) + Start 節點入佇列。
    在同一交易 commit;找不到起始節點時 rollback 並拋 SubmitError。

    Returns:
        (form_instance, workflow_instance)
    """
    from ..models import (
        FwFormInstance, FwWorkflowInstance, FwNodeExecutionQueue,
    )

    date_str = datetime.now().strftime('%Y%m%d')
    workflow_graph = workflow_graph or {}

    form_instance = FwFormInstance(
        secure_code=secrets.token_urlsafe(16),
        org_secure_code=org_secure_code,
        form_template_id=source_form_template_id,
        form_template_secure_code=source_form_template_secure_code,
        published_secure_code=published_sc,
        serial_number=serial_number,
        org_form_seq=org_form_seq,
        form_name=form_name,
        form_code=form_code,
        form_version=form_version,
        applicant_secure_code=applicant_secure_code,
        applicant_name=applicant_name,
        applicant_username=applicant_username,
        applicant_email=applicant_email,
        applicant_dept=applicant_dept,
        subject=subject,
        form_data=form_data,
        schema_snapshot=form_schema,
        builder_config=form_builder_config,
        status='INITIAL',
        source_type=source_type,
        source_ip=source_ip,
        source_api_key=source_api_key,
        submitted_at=datetime.utcnow(),
        is_test=is_test,
    )
    db.session.add(form_instance)
    db.session.flush()

    # 生成流程執行編號 -- 序號池與 advisory lock 都在 sequence_code_service 內
    # （唯一實作，見該檔 docstring）。
    execution_code = next_execution_code(
        org_secure_code=org_secure_code,
        prefix=proc_prefix,
        date_str=date_str,
    )
    variables = {}
    if nocode_sub_system_sc or nocode_user_ref:
        variables = {'nocode': {'sub': nocode_sub_system_sc, 'user': nocode_user_ref}}

    workflow_instance = FwWorkflowInstance(
        secure_code=secrets.token_urlsafe(16),
        org_secure_code=org_secure_code,
        form_instance_id=form_instance.id,
        form_instance_secure_code=form_instance.secure_code,
        workflow_template_id=source_workflow_template_id,
        workflow_template_secure_code=source_workflow_template_secure_code,
        published_secure_code=published_sc,
        execution_code=execution_code,
        workflow_name=workflow_name,
        workflow_version=workflow_version,
        graph_snapshot=workflow_graph,
        status='RUNNING',
        variables=variables,
        nocode_sub_system_sc=nocode_sub_system_sc,
        nocode_user_ref=nocode_user_ref,
        started_at=datetime.utcnow(),
    )
    db.session.add(workflow_instance)
    db.session.flush()

    form_instance.workflow_instance_id = workflow_instance.id
    form_instance.workflow_instance_secure_code = workflow_instance.secure_code

    # 找到起始節點
    nodes = workflow_graph.get('nodes', [])
    start_node = None
    for node in nodes:
        node_id = node.get('id', '')
        node_type = node.get('type', '')
        if node_id.startswith('node-Start') or node_type in ('Start', 'START'):
            start_node = node
            break

    if not start_node:
        db.session.rollback()
        raise SubmitError(_('流程中找不到起始節點'))

    queue_item = FwNodeExecutionQueue(
        secure_code=secrets.token_urlsafe(16),
        org_secure_code=org_secure_code,
        workflow_instance_secure_code=workflow_instance.secure_code,
        form_instance_secure_code=form_instance.secure_code,
        node_id=start_node.get('id'),
        node_type='Start',
        node_name=start_node.get('label') or start_node.get('data', {}).get('label') or '開始',
        node_config=start_node.get('config', {}),
        status='PENDING',
        priority=10,
        scheduled_at=datetime.utcnow(),
    )
    db.session.add(queue_item)
    db.session.commit()

    if nocode_sub_system_sc or nocode_user_ref:
        try:
            from .variable_service import VariableService
            if nocode_sub_system_sc:
                VariableService.set_flow_var(
                    workflow_instance.secure_code,
                    'nocode_sub_system',
                    nocode_sub_system_sc,
                    org_secure_code,
                )
            if nocode_user_ref:
                VariableService.set_flow_var(
                    workflow_instance.secure_code,
                    'nocode_user_ref',
                    nocode_user_ref,
                    org_secure_code,
                )
        except Exception:
            logger.exception(
                'Failed to persist NoCode portal workflow variables: workflow_instance=%s',
                workflow_instance.secure_code,
            )

    return form_instance, workflow_instance


def extract_schema_field_keys(form_schema) -> set:
    """
    從 form.io schema 遞迴收集 input=true 的欄位 key(含容器內巢狀元件),
    供 form_data 白名單驗證。
    """
    keys = set()

    def walk(components):
        if not isinstance(components, list):
            return
        for comp in components:
            if not isinstance(comp, dict):
                continue
            if comp.get('input') and comp.get('key'):
                keys.add(comp['key'])
            # 常見容器:components / columns[].components / rows[][].components
            walk(comp.get('components'))
            for col in comp.get('columns') or []:
                if isinstance(col, dict):
                    walk(col.get('components'))
            # 注意:rows 在 table 元件是二維陣列,但 textarea 的 rows 是整數
            # (form.io 的顯示列數),不加型別檢查會 TypeError
            rows = comp.get('rows')
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, list):
                        for cell in row:
                            if isinstance(cell, dict):
                                walk(cell.get('components'))

    if isinstance(form_schema, dict):
        walk(form_schema.get('components'))
    return keys
