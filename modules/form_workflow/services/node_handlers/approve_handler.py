"""
FormWorkflow Module - Approve Handler
簽核節點處理器

等待指定人員進行審批動作。
"""
from datetime import datetime
from typing import Dict, Any, List
from .base import BaseNodeHandler


class ApproveHandler(BaseNodeHandler):
    """
    簽核節點處理器

    配置參數：
    - assignee_type: 簽核者類型 (USER/ROLE/DEPARTMENT/INITIATOR/DYNAMIC)
    - assignee_value: 簽核者值
    - selection_mode: 選擇模式 (single/multiple)
    - allow_comment: 是否允許備註
    - min_comment_length: 最少意見字數 (0=不需要, >0=必須輸入指定字數)
    """

    def validate(self) -> bool:
        """驗證節點配置"""
        assignee_type = self.get_config_value('assignee_type')
        if not assignee_type:
            self.node_config['assignee_type'] = 'INITIATOR'

        selection_mode = self.get_config_value('selection_mode')
        if selection_mode not in [None, 'single', 'multiple']:
            raise ValueError(f'selection_mode 必須是 single 或 multiple')

        if not selection_mode:
            self.node_config['selection_mode'] = 'single'

        return True

    def handle(self) -> Dict[str, Any]:
        """
        處理簽核節點

        1. 解析簽核者
        2. 取得可選路徑
        3. 設定狀態為等待簽核
        """
        # 取得配置
        assignee_type = self.get_config_value('assignee_type', 'INITIATOR')
        assignee_value = self.get_config_value('assignee_value', '')
        selection_mode = self.get_config_value('selection_mode', 'single')
        allow_comment = self.get_config_value('allow_comment', True)
        # 向後相容：若無 min_comment_length 但有 require_comment=True，視為 1
        min_comment_length = self.get_config_value('min_comment_length', None)
        if min_comment_length is None:
            min_comment_length = 1 if self.get_config_value('require_comment', False) else 0
        min_comment_length = int(min_comment_length)

        # 取得可選路徑
        available_paths = self._get_available_paths()

        if not available_paths:
            self.log_error('簽核節點沒有出線')
            return {
                'status': 'error',
                'message': '簽核節點沒有出線'
            }

        # 解析簽核者
        assignees = self._resolve_assignees(assignee_type, assignee_value)

        self.log_info('簽核節點等待審批', {
            'assignee_type': assignee_type,
            'assignees': assignees,
            'available_paths': len(available_paths)
        })

        return {
            'status': 'waiting',
            'message': '等待簽核',
            'data': {
                'assignee_type': assignee_type,
                'assignee_value': assignee_value,
                'assignees': assignees,
                'selection_mode': selection_mode,
                'allow_comment': allow_comment,
                'min_comment_length': min_comment_length,
                'require_comment': min_comment_length > 0,
                'available_paths': available_paths,
                'waiting_since': datetime.utcnow().isoformat()
            }
        }

    def _get_available_paths(self) -> List[Dict[str, Any]]:
        """取得此節點的所有出線選項"""
        from ...models import FwWorkflowTemplate

        if not self.workflow_instance:
            return []

        workflow_template = FwWorkflowTemplate.query.filter_by(
            secure_code=self.workflow_instance.workflow_template_secure_code
        ).first()

        if not workflow_template or not workflow_template.graph:
            return []

        graph = workflow_template.graph
        edges = graph.get('edges', [])
        nodes = graph.get('nodes', [])

        # 建立 node id -> node data 映射
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

                target_node = node_map.get(target_node_id, {})
                target_node_type = target_node.get('type', 'UNKNOWN')
                target_node_label = target_node.get('label', target_node_type)

                display_label = edge_label if edge_label else target_node_label

                available_paths.append({
                    'edge_id': edge_id,
                    'target_node_id': target_node_id,
                    'target_node_type': target_node_type,
                    'target_node_label': target_node_label,
                    'label': display_label
                })

        return available_paths

    def _resolve_assignees(self, assignee_type: str, assignee_value: str) -> List[str]:
        """解析簽核者"""
        if assignee_type == 'INITIATOR':
            if self.form_instance and self.form_instance.applicant_secure_code:
                return [self.form_instance.applicant_secure_code]
            return []

        elif assignee_type == 'USER':
            if assignee_value:
                return [v.strip() for v in assignee_value.split(',') if v.strip()]
            return []

        elif assignee_type == 'DYNAMIC':
            # TODO: 實作動態解析
            return []

        elif assignee_type in ['ROLE', 'DEPARTMENT']:
            # TODO: 實作角色/部門解析
            return [f'{assignee_type}:{assignee_value}']

        return []
