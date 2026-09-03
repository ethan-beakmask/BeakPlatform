"""
表單中心 - 流程監控（執行路徑、執行日誌、表單詳情）

2026-09-04 PF-237：移除從未被任何前端呼叫的 /workflow-progress/<sc>
（序列化用了 FwApprovalRecord 沒有的 decision／approved_at，有簽核紀錄即 500）。
"""
import logging

from flask import jsonify, request
from flask_login import current_user

from app.security.decorators import module_access_required
from app.platform.data import get_current_org
from app import db

from .form_center import form_center_bp
from flask_babel import gettext as _

logger = logging.getLogger(__name__)


@form_center_bp.route('/form-detail/<secure_code>')
@module_access_required('form_workflow', False)
def get_form_detail(secure_code):
    """
    取得表單詳情（用於歷史表單查看）

    包含：表單內容、schema、簽核歷史
    """
    from ..models import FwFormInstance, FwWorkflowInstance, FwApprovalRecord

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    # 查詢表單實例
    form_instance = FwFormInstance.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not form_instance:
        return jsonify({'success': False, 'error': _('找不到指定的表單')}), 404

    # 取得簽核歷史
    approvals = []
    if form_instance.workflow_instance_secure_code:
        approval_records = FwApprovalRecord.query.filter_by(
            workflow_instance_secure_code=form_instance.workflow_instance_secure_code
        ).order_by(FwApprovalRecord.acted_at.asc()).all()

        for approval in approval_records:
            approvals.append({
                'node_id': approval.node_id,
                'node_name': approval.node_name,
                'approver_name': approval.approver_name,
                'delegate_from_name': approval.delegate_from_name,
                'action': approval.action,
                'comment': approval.comment,
                'acted_at': approval.acted_at.isoformat() if approval.acted_at else None,
            })

    return jsonify({
        'success': True,
        'data': {
            'secure_code': form_instance.secure_code,
            'serial_number': form_instance.serial_number,
            'form_name': form_instance.form_name,
            'form_subject': form_instance.subject,
            'form_code': form_instance.form_code,
            'status': form_instance.status,
            'applicant_name': form_instance.applicant_name,
            'applicant_dept': form_instance.applicant_dept,
            'submitted_at': form_instance.submitted_at.isoformat() if form_instance.submitted_at else None,
            'completed_at': form_instance.completed_at.isoformat() if form_instance.completed_at else None,
            'form_data': form_instance.form_data,
            'schema': form_instance.schema_snapshot,
            'builder_config': form_instance.builder_config,
            'approvals': approvals
        }
    })


@form_center_bp.route('/executions/<instance_id>/path')
@module_access_required('form_workflow', False)
def get_execution_path(instance_id):
    """
    取得流程執行路徑（用於監控與追蹤）

    Args:
        instance_id: 工作流實例 secure_code 或 execution_code
    """
    from ..models import FwWorkflowInstance, FwNodeExecutionQueue, FwFormInstance
    from sqlalchemy import or_, func

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    # 查詢流程實例（支援 secure_code 或 execution_code）
    instance = FwWorkflowInstance.query.filter(
        FwWorkflowInstance.org_secure_code == org.secure_code,
        or_(
            FwWorkflowInstance.secure_code == instance_id,
            FwWorkflowInstance.execution_code == instance_id
        )
    ).first()

    if not instance:
        return jsonify({'success': False, 'error': _('流程實例 %(instance_id)s 不存在', instance_id=instance_id)}), 404

    # 查詢此流程實例的所有節點執行記錄
    nodes = FwNodeExecutionQueue.query.filter_by(
        workflow_instance_secure_code=instance.secure_code
    ).all()

    # 分類節點狀態
    active_nodes = [n.node_id for n in nodes if n.status == 'RUNNING']
    completed_nodes = [n.node_id for n in nodes if n.status == 'SUCCESS']
    failed_nodes = [n.node_id for n in nodes if n.status in ('FAILED', 'ERROR', 'TIMEOUT')]
    pending_nodes = [n.node_id for n in nodes if n.status == 'PENDING']
    waiting_nodes = [n.node_id for n in nodes if n.status == 'WAITING']

    # 計算活動路徑（已完成 -> 執行中/等待中的連線）
    active_paths = []
    graph = instance.graph_snapshot or {}
    if graph:
        edges = graph.get('edges', [])
        for edge in edges:
            source = edge.get('source')
            target = edge.get('target')
            edge_id = edge.get('id')
            if (source in completed_nodes and
                (target in active_nodes or target in waiting_nodes or target in pending_nodes)):
                active_paths.append(edge_id)

    # 查詢執行歷程（同一表單實例的所有節點記錄，包含子流程）
    # 依 started_at 排序以呈現真實執行順序
    execution_history = FwNodeExecutionQueue.query.filter_by(
        form_instance_secure_code=instance.form_instance_secure_code
    ).order_by(
        func.coalesce(FwNodeExecutionQueue.started_at, FwNodeExecutionQueue.scheduled_at).asc()
    ).all()

    # 收集所有相關的 workflow_instance（主流程 + 子流程）
    workflow_instance_codes = list(set([item.workflow_instance_secure_code for item in execution_history]))
    workflow_instances = FwWorkflowInstance.query.filter(
        FwWorkflowInstance.secure_code.in_(workflow_instance_codes)
    ).all()

    # 建立映射表
    workflow_map = {wi.secure_code: wi for wi in workflow_instances}

    # 查詢對應的 workflow_template code（供流程大圖匹配 childFlowId 用）
    from ..models import FwWorkflowTemplate
    template_codes = {}
    template_scs = list(set(
        wi.workflow_template_secure_code for wi in workflow_instances
        if wi.workflow_template_secure_code
    ))
    if template_scs:
        templates = FwWorkflowTemplate.query.filter(
            FwWorkflowTemplate.secure_code.in_(template_scs)
        ).all()
        template_codes = {t.secure_code: t.code for t in templates}

    # 準備 workflow_tabs（流程分頁）
    workflow_tabs = []
    for wi in workflow_instances:
        # 計算該流程的狀態
        sub_nodes = [n for n in execution_history if n.workflow_instance_secure_code == wi.secure_code]
        has_running = any(n.status == 'RUNNING' for n in sub_nodes)
        has_failed = any(n.status in ('FAILED', 'ERROR', 'TIMEOUT') for n in sub_nodes)
        has_waiting = any(n.status == 'WAITING' for n in sub_nodes)
        all_completed = all(n.status == 'SUCCESS' for n in sub_nodes) if sub_nodes else False

        if has_running:
            tab_status = 'RUNNING'
        elif has_failed:
            tab_status = 'ERROR'
        elif has_waiting:
            tab_status = 'WAITING'
        elif all_completed:
            tab_status = 'COMPLETED'
        else:
            tab_status = 'INITIAL'

        workflow_tabs.append({
            'instance_id': wi.secure_code,
            'secure_code': wi.secure_code,
            'execution_code': wi.execution_code,
            'name': wi.workflow_name or '未命名流程',
            'is_main': wi.secure_code == instance.secure_code,
            'status': tab_status,
            'graph': wi.graph_snapshot,
            'workflow_code': template_codes.get(wi.workflow_template_secure_code, '')
        })

    # 確保主流程排在最前面
    workflow_tabs.sort(key=lambda x: (not x['is_main'], x.get('execution_code', '')))

    # 轉換執行歷程為前端格式
    history_data = []
    for queue_item in execution_history:
        wi = workflow_map.get(queue_item.workflow_instance_secure_code)
        is_subprocess = queue_item.calling_instance_code is not None
        workflow_name = wi.workflow_name if wi else '未知流程'

        history_data.append({
            'node_id': queue_item.node_id,
            'node_name': queue_item.node_name or queue_item.node_id,
            'display_name': queue_item.node_name or '',
            'node_type': queue_item.node_type,
            'status': queue_item.status,
            'scheduled_at': queue_item.scheduled_at.isoformat() if queue_item.scheduled_at else None,
            'started_at': queue_item.started_at.isoformat() if queue_item.started_at else None,
            'completed_at': queue_item.completed_at.isoformat() if queue_item.completed_at else None,
            'error_message': queue_item.error_message,
            'retry_count': queue_item.retry_count or 0,
            'is_subprocess': is_subprocess,
            'workflow_name': workflow_name,
            'workflow_instance_id': queue_item.workflow_instance_secure_code
        })

    return jsonify({
        'success': True,
        'data': {
            'active_nodes': active_nodes,
            'completed_nodes': completed_nodes,
            'failed_nodes': failed_nodes,
            'pending_nodes': pending_nodes,
            'waiting_nodes': waiting_nodes,
            'active_paths': active_paths,
            'instance_status': instance.status,
            'current_node_id': instance.current_node_id,
            'execution_history': history_data,
            'workflow_tabs': workflow_tabs
        }
    })


@form_center_bp.route('/executions/<instance_id>/logs')
@module_access_required('form_workflow', False)
def get_execution_logs(instance_id):
    """
    取得流程執行日誌（用於 Debug 和追蹤）

    Args:
        instance_id: 工作流實例 secure_code 或 execution_code

    Query Params:
        level: 過濾日誌等級 (INFO, WARNING, ERROR, DEBUG)
        limit: 限制筆數，預設 500
    """
    from ..models import (
        FwWorkflowInstance, FwNodeExecutionLog,
        FwWorkflowVariable, FwNodeExecutionQueue
    )
    from sqlalchemy import or_

    logger.info(f'[LOGS API] 查詢執行日誌: instance_id={instance_id}')

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    # 查詢流程實例（支援 secure_code 或 execution_code）
    instance = FwWorkflowInstance.query.filter(
        FwWorkflowInstance.org_secure_code == org.secure_code,
        or_(
            FwWorkflowInstance.secure_code == instance_id,
            FwWorkflowInstance.execution_code == instance_id
        )
    ).first()

    if not instance:
        return jsonify({'success': False, 'error': _('流程實例 %(instance_id)s 不存在', instance_id=instance_id)}), 404

    # 取得查詢參數
    level_filter = request.args.get('level')
    limit = request.args.get('limit', 500, type=int)

    # 取得所有相關的流程實例（主流程 + 子流程）
    # 使用 root_instance_code 或 form_instance_secure_code 來查詢整個流程樹
    all_instances = FwWorkflowInstance.query.filter(
        FwWorkflowInstance.org_secure_code == org.secure_code,
        FwWorkflowInstance.form_instance_secure_code == instance.form_instance_secure_code
    ).all()

    all_instance_ids = [wi.id for wi in all_instances]
    all_instance_codes = [wi.secure_code for wi in all_instances]
    logger.info(f'[LOGS API] 找到 {len(all_instances)} 個相關流程實例, IDs: {all_instance_ids}')

    # 建立 workflow_instance_id -> workflow_name 映射
    workflow_name_map = {}
    for wi in all_instances:
        workflow_name_map[wi.id] = wi.workflow_name or '未命名流程'
        workflow_name_map[wi.secure_code] = wi.workflow_name or '未命名流程'

    # 取得節點顯示名稱映射（從執行佇列）
    node_display_names = {}  # key: (workflow_instance_secure_code, node_id)
    queue_items = FwNodeExecutionQueue.query.filter(
        FwNodeExecutionQueue.workflow_instance_secure_code.in_(all_instance_codes)
    ).all()
    for item in queue_items:
        key = (item.workflow_instance_secure_code, item.node_id)
        node_display_names[key] = item.node_name or item.node_id

    # 查詢執行日誌
    log_query = FwNodeExecutionLog.query.filter(
        FwNodeExecutionLog.workflow_instance_id.in_(all_instance_ids)
    )
    if level_filter:
        log_query = log_query.filter(FwNodeExecutionLog.log_level == level_filter.upper())
    log_query = log_query.order_by(
        FwNodeExecutionLog.created_at.asc()
    ).limit(limit)

    logs = []
    log_results = log_query.all()
    logger.info(f'[LOGS API] 查詢到 {len(log_results)} 筆日誌')
    for log in log_results:
        # 找到對應的 workflow instance
        wi = next((w for w in all_instances if w.id == log.workflow_instance_id), None)
        workflow_name = wi.workflow_name if wi else '未知流程'
        node_id = log.node_id or ''

        # 嘗試取得節點顯示名稱
        display_name_key = (wi.secure_code if wi else '', node_id)
        display_name = node_display_names.get(display_name_key, node_id.replace('node-', '') if node_id else '')

        logs.append({
            'timestamp': log.created_at.strftime('%Y-%m-%d %H:%M:%S') if log.created_at else '',
            'level': log.log_level or 'INFO',
            'node_id': node_id,
            'workflow_instance_id': wi.secure_code if wi else None,
            'workflow_name': workflow_name,
            'display_name': display_name,
            'message': log.log_message or '',
            'data': log.log_data if log.log_data else None
        })

    # 查詢檔案存取記錄（upload/download/delete），合併至日誌
    from app.models.file_access_log import FileAccessLog
    form_instance_sc = instance.form_instance_secure_code
    if form_instance_sc:
        file_logs = FileAccessLog.query.filter(
            FileAccessLog.org_secure_code == org.secure_code,
            FileAccessLog.context_id == form_instance_sc,
            FileAccessLog.is_deleted == False,
        ).order_by(FileAccessLog.created_at.asc()).all()

        action_label = {'upload': '上傳', 'download': '下載', 'delete': '刪除'}
        for fl in file_logs:
            logs.append({
                'timestamp': fl.created_at.strftime('%Y-%m-%d %H:%M:%S') if fl.created_at else '',
                'level': 'FILE',
                'node_id': '',
                'workflow_instance_id': None,
                'workflow_name': '附件',
                'display_name': action_label.get(fl.action, fl.action),
                'message': f'{fl.username} {action_label.get(fl.action, fl.action)} {fl.original_name}',
                'data': {'ip': fl.ip_address} if fl.ip_address else None,
            })

    # 依時間重新排序（合併後）
    logs.sort(key=lambda x: x.get('timestamp', ''))

    # 查詢所有相關流程的變數值（只取 GLOBAL 範圍）
    # 注意：資料庫實際欄位是 workflow_instance_secure_code 和 var_type
    variables = {}
    vars_query = FwWorkflowVariable.query.filter(
        FwWorkflowVariable.workflow_instance_secure_code.in_(all_instance_codes),
        FwWorkflowVariable.var_type == 'FLOW'
    ).all()
    logger.info(f'[LOGS API] 查詢到 {len(vars_query)} 個變數')
    for v in vars_query:
        # 使用 workflow_name::var_name 格式區分不同流程的變數
        wi = next((w for w in all_instances if w.secure_code == v.workflow_instance_secure_code), None)
        wf_name = wi.workflow_name if wi else ''
        var_key = f"{wf_name}::{v.var_name}" if wf_name and v.workflow_instance_secure_code != instance.secure_code else v.var_name
        variables[var_key] = v.var_value

    return jsonify({
        'success': True,
        'data': {
            'instance': {
                'secure_code': instance.secure_code,
                'execution_code': instance.execution_code,
                'status': instance.status,
                'started_at': instance.started_at.strftime('%Y-%m-%d %H:%M:%S') if instance.started_at else None,
                'completed_at': instance.completed_at.strftime('%Y-%m-%d %H:%M:%S') if instance.completed_at else None,
                'template_name': instance.workflow_name
            },
            'logs': logs,
            'variables': variables
        }
    })
