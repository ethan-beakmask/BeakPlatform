"""
FormWorkflow Module - FormAdapter Handler
FormAdapter 節點處理器

負責簽核流程：等待指定人員選擇後續路徑。
"""
import logging
from typing import Dict, Any, List
from datetime import datetime
from .base import BaseNodeHandler

from app import db

logger = logging.getLogger(__name__)


class FormAdapterHandler(BaseNodeHandler):
    """FormAdapter 簽核節點處理器"""

    def validate(self) -> bool:
        """
        驗證節點配置

        必要配置：
        - assignee_type: 簽核者類型 (ROLE/USER/DEPARTMENT/INITIATOR/DYNAMIC)
        - selection_mode: 選擇模式 (single/multiple)

        Returns:
            bool: 是否通過驗證
        """
        assignee_type = self.get_config_value('assignee_type')
        if not assignee_type:
            # 預設為 INITIATOR（發起人自己簽核）
            self.node_config['assignee_type'] = 'INITIATOR'

        selection_mode = self.get_config_value('selection_mode')
        if selection_mode not in [None, 'single', 'multiple']:
            raise ValueError(f'selection_mode 必須是 single 或 multiple，而非 {selection_mode}')

        if not selection_mode:
            self.node_config['selection_mode'] = 'single'

        return True

    def handle(self) -> Dict[str, Any]:
        """
        處理 FormAdapter 節點

        1. 讀取此節點的所有出線
        2. 產生可選路徑列表
        3. 設定狀態為等待簽核
        4. 等待簽核者透過 API 提交選擇

        Returns:
            dict: 執行結果
        """
        self.report_running()

        # 取得配置
        assignee_type = self.get_config_value('assignee_type', 'INITIATOR')
        assignee_value = self.get_config_value('assignee_value', '')
        selection_mode = self.get_config_value('selection_mode', 'single')
        allow_comment = self.get_config_value('allow_comment', True)
        require_comment = self.get_config_value('require_comment', False)

        # 取得此節點的所有出線選項
        available_paths = self._get_available_paths()

        if not available_paths:
            self.log_error('FormAdapter 節點沒有出線，無法繼續')
            return {
                'status': 'error',
                'message': 'FormAdapter 節點沒有出線'
            }

        # 解析簽核者
        assignees = self._resolve_assignees(assignee_type, assignee_value)

        self.log_info('FormAdapter 節點等待簽核', {
            'node_id': self.queue_item.node_id,
            'assignee_type': assignee_type,
            'assignee_value': assignee_value,
            'assignees': assignees,
            'selection_mode': selection_mode,
            'available_paths': available_paths
        })

        # 返回等待簽核狀態
        return {
            'status': 'waiting_form_action',
            'message': '等待簽核',
            'data': {
                'assignee_type': assignee_type,
                'assignee_value': assignee_value,
                'assignees': assignees,
                'selection_mode': selection_mode,
                'allow_comment': allow_comment,
                'require_comment': require_comment,
                'available_paths': available_paths,
                'waiting_since': datetime.utcnow().isoformat()
            }
        }

    def _get_available_paths(self) -> List[Dict[str, Any]]:
        """
        取得此節點的所有出線選項

        Returns:
            list: 可選路徑列表
        """
        if not self.workflow_instance:
            return []

        # 取得流程定義
        graph = self._get_workflow_graph()
        if not graph:
            return []

        edges = graph.get('edges', [])
        nodes = graph.get('nodes', [])

        # 建立 node id -> node data 的映射
        node_map = {}
        for node in nodes:
            node_id = node.get('id')
            if node_id:
                node_map[node_id] = node

        # 找出從此節點出發的所有 edge
        current_node_id = self.queue_item.node_id
        available_paths = []

        for edge in edges:
            edge_data = edge.get('data', edge)
            source = edge_data.get('source')

            if source == current_node_id:
                target_node_id = edge_data.get('target')
                edge_id = edge_data.get('id', edge.get('id'))
                edge_label = edge_data.get('label', edge.get('label', ''))

                # 取得目標節點資訊
                target_node = node_map.get(target_node_id, {})
                target_node_type = target_node.get('type', 'UNKNOWN')
                target_node_label = target_node.get('label', target_node_type)

                # 決定顯示名稱：優先用 edge label，否則用目標節點 label
                display_label = edge_label if edge_label else target_node_label

                available_paths.append({
                    'edge_id': edge_id,
                    'target_node_id': target_node_id,
                    'target_node_type': target_node_type,
                    'target_node_label': target_node_label,
                    'label': display_label
                })

        return available_paths

    def _get_workflow_graph(self) -> Dict:
        """取得工作流圖形定義"""
        if not self.workflow_instance:
            return {}

        # 優先使用 workflow_instance 的 graph_snapshot（執行時快照）
        if hasattr(self.workflow_instance, 'graph_snapshot') and self.workflow_instance.graph_snapshot:
            return self.workflow_instance.graph_snapshot

        # 嘗試從 workflow_template 取得
        if hasattr(self.workflow_instance, 'workflow_template') and self.workflow_instance.workflow_template:
            template = self.workflow_instance.workflow_template
            return template.graph or template.cytoscape_config or {}

        return {}

    def _resolve_assignees(self, assignee_type: str, assignee_value: str) -> List[str]:
        """
        解析簽核者

        Args:
            assignee_type: 簽核者類型
            assignee_value: 簽核者值

        Returns:
            list: 簽核者 ID 列表
        """
        if assignee_type == 'INITIATOR':
            # 表單發起人
            if self.form_instance:
                # 使用 secure_code 或 owner_secure_code
                owner_code = getattr(self.form_instance, 'owner_secure_code', None)
                if owner_code:
                    return [str(owner_code)]
            return []

        elif assignee_type == 'USER':
            # 指定用戶（支援多用戶，以逗號分隔）
            if assignee_value:
                return [v.strip() for v in assignee_value.split(',') if v.strip()]
            return []

        elif assignee_type == 'DYNAMIC':
            # 從變數取得
            if assignee_value:
                value = self.get_var(assignee_value)
                if value:
                    if isinstance(value, list):
                        return [str(v) for v in value]
                    return [str(value)]
            return []

        elif assignee_type in ['ROLE', 'DEPARTMENT']:
            # 角色或部門需要查詢對應的用戶
            # TODO: 實作角色/部門 -> 用戶的解析
            return [f'{assignee_type}:{assignee_value}']

        return []


def complete_form_action(queue_item_secure_code: str, selected_edges: List[str],
                         user_secure_code: str, comment: str = None) -> Dict[str, Any]:
    """
    完成 FormAdapter 簽核動作

    此函數由簽核 API 呼叫，用於：
    1. 驗證用戶權限
    2. 記錄簽核結果
    3. 更新節點狀態為 SUCCESS
    4. 根據選擇的路徑建立後續節點

    Args:
        queue_item_secure_code: FwNodeExecutionQueue secure_code
        selected_edges: 選擇的 edge ID 列表
        user_secure_code: 簽核者 secure_code
        comment: 簽核備註

    Returns:
        dict: 執行結果
    """
    from ...models import FwNodeExecutionQueue, FwWorkflowInstance
    from ..workflow_log_service import WorkflowLogService

    # 取得 queue_item
    queue_item = FwNodeExecutionQueue.query.filter_by(
        secure_code=queue_item_secure_code
    ).first()

    if not queue_item:
        return {'success': False, 'error': '找不到簽核項目'}

    if queue_item.node_type != 'FormAdapter':
        return {'success': False, 'error': '此節點不是 FormAdapter 類型'}

    # 檢查狀態
    if queue_item.status == 'SUCCESS':
        return {'success': False, 'error': '此節點已完成簽核'}

    # 取得之前儲存的可選路徑
    result_data = queue_item.result or {}
    available_paths = result_data.get('data', {}).get('available_paths', [])
    selection_mode = result_data.get('data', {}).get('selection_mode', 'single')

    # 驗證選擇的 edge 是否有效
    valid_edge_ids = [p['edge_id'] for p in available_paths]
    for edge_id in selected_edges:
        if edge_id not in valid_edge_ids:
            return {'success': False, 'error': f'無效的選擇: {edge_id}'}

    # 單選模式只能選一個
    if selection_mode == 'single' and len(selected_edges) != 1:
        return {'success': False, 'error': '單選模式只能選擇一個選項'}

    # 複選模式至少選一個
    if selection_mode == 'multiple' and len(selected_edges) < 1:
        return {'success': False, 'error': '請至少選擇一個選項'}

    # 記錄簽核結果
    action_result = {
        'selected_edges': selected_edges,
        'selected_by': user_secure_code,
        'selected_at': datetime.utcnow().isoformat(),
        'comment': comment,
        'selection_mode': selection_mode
    }

    # 更新狀態
    queue_item.status = 'SUCCESS'
    queue_item.completed_at = datetime.utcnow()
    queue_item.result = {
        'status': 'success',
        'message': '簽核完成',
        'data': {
            **result_data.get('data', {}),
            'action_result': action_result
        }
    }

    db.session.commit()

    # 記錄日誌
    workflow_instance = FwWorkflowInstance.query.filter_by(
        secure_code=queue_item.workflow_instance_secure_code
    ).first()

    WorkflowLogService.log(
        workflow_instance_id=workflow_instance.id if workflow_instance else None,
        node_queue_id=queue_item.id,
        level='INFO',
        message='FormAdapter 簽核完成',
        data=action_result
    )

    # 建立選擇的後續節點
    _create_next_nodes(queue_item, selected_edges, available_paths)

    return {'success': True, 'message': '簽核完成'}


def _create_next_nodes(queue_item, selected_edges: List[str], available_paths: List[Dict]):
    """
    根據選擇的路徑建立後續節點

    Args:
        queue_item: FwNodeExecutionQueue 實例
        selected_edges: 選擇的 edge ID 列表
        available_paths: 可選路徑列表
    """
    import secrets
    from ...models import FwNodeExecutionQueue, FwWorkflowInstance
    from ..workflow_log_service import WorkflowLogService

    workflow_instance = FwWorkflowInstance.query.filter_by(
        secure_code=queue_item.workflow_instance_secure_code
    ).first()

    if not workflow_instance:
        return

    # 取得流程定義（優先使用執行快照）
    graph = None
    if hasattr(workflow_instance, 'graph_snapshot') and workflow_instance.graph_snapshot:
        graph = workflow_instance.graph_snapshot
    elif hasattr(workflow_instance, 'workflow_template') and workflow_instance.workflow_template:
        graph = workflow_instance.workflow_template.graph or workflow_instance.workflow_template.cytoscape_config or {}

    if not graph:
        return

    graph_nodes = graph.get('nodes', [])

    # 建立 node id -> node data 的映射
    node_map = {}
    for node in graph_nodes:
        node_id = node.get('id')
        if node_id:
            node_map[node_id] = node

    # 為每個選擇的 edge 建立對應的後續節點
    for edge_id in selected_edges:
        # 找到對應的路徑資訊
        path_info = None
        for p in available_paths:
            if p['edge_id'] == edge_id:
                path_info = p
                break

        if not path_info:
            continue

        target_node_id = path_info['target_node_id']
        target_node_type = path_info['target_node_type']

        # 從 graph 取得完整節點配置
        target_node_data = node_map.get(target_node_id, {})
        node_config = target_node_data.get('config', {})
        display_name = target_node_data.get('label') or target_node_data.get('data', {}).get('label') or ''

        # 檢查節點是否已存在且未完成
        existing = FwNodeExecutionQueue.query.filter(
            FwNodeExecutionQueue.workflow_instance_secure_code == workflow_instance.secure_code,
            FwNodeExecutionQueue.node_id == target_node_id,
            FwNodeExecutionQueue.calling_instance_code == queue_item.calling_instance_code,
            FwNodeExecutionQueue.status.in_(['PENDING', 'RUNNING', 'WAITING'])
        ).first()

        if existing:
            logger.info(f'節點執行中或等待中，跳過: {target_node_type} ({target_node_id}) status={existing.status}')
            continue

        logger.info(f'建立後續節點: {target_node_type} ({target_node_id})')

        new_queue_item = FwNodeExecutionQueue(
            secure_code=secrets.token_urlsafe(16),
            org_secure_code=workflow_instance.org_secure_code,
            workflow_instance_secure_code=workflow_instance.secure_code,
            form_instance_secure_code=getattr(workflow_instance, 'form_instance_secure_code', None),
            node_id=target_node_id,
            node_type=target_node_type,
            node_name=display_name,
            node_config=node_config,
            parent_node_id=queue_item.parent_node_id,
            calling_instance_code=queue_item.calling_instance_code,
            status='PENDING',
            priority=queue_item.priority
        )

        db.session.add(new_queue_item)

        WorkflowLogService.log(
            workflow_instance_id=workflow_instance.id,
            node_queue_id=None,
            level='INFO',
            message=f'FormAdapter 建立後續節點: {target_node_type}',
            data={
                'from_node': queue_item.node_id,
                'edge_id': edge_id,
                'target_node_id': target_node_id,
                'target_node_type': target_node_type
            }
        )

    db.session.commit()
