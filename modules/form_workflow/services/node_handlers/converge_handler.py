"""
FormWorkflow Module - Converge Handler
匯聚節點處理器

等待多條前驅路徑完成後匯聚。
"""
from typing import Dict, Any, List
from .base import BaseNodeHandler


class ConvergeHandler(BaseNodeHandler):
    """
    匯聚節點處理器

    配置參數：
    - mode: 'ALL' (等待全部) 或 'ANY' (任一完成)，預設 ALL
    """

    MODE_ALL = 'ALL'
    MODE_ANY = 'ANY'

    def validate(self) -> bool:
        """驗證節點配置"""
        mode = self.get_config_value('mode', self.MODE_ALL)
        if mode not in [self.MODE_ALL, self.MODE_ANY]:
            raise ValueError(f'無效的模式: {mode}，必須是 ALL 或 ANY')
        return True

    def handle(self) -> Dict[str, Any]:
        """
        處理匯聚節點

        1. 從 graph 中找到指向此節點的前驅節點
        2. 檢查這些前驅節點的完成狀態
        3. 根據模式決定是否繼續或等待
        """
        mode = self.get_config_value('mode', self.MODE_ALL)

        self.log_info(f'Converge 節點檢查中', {
            'mode': mode,
            'node_id': self.queue_item.node_id
        })

        # 取得前驅節點列表
        predecessor_node_ids = self._get_predecessor_node_ids()

        if not predecessor_node_ids:
            self.log_info('沒有前驅節點，直接通過')
            return {
                'status': 'success',
                'message': '沒有前驅節點，直接通過',
                'data': {
                    'predecessor_count': 0,
                    'all_completed': True
                }
            }

        # 查詢前驅節點的完成狀態
        from ...models import FwNodeExecutionQueue

        predecessor_items = FwNodeExecutionQueue.query.filter(
            FwNodeExecutionQueue.workflow_instance_secure_code == self.queue_item.workflow_instance_secure_code,
            FwNodeExecutionQueue.node_id.in_(predecessor_node_ids)
        ).all()

        # 建立狀態統計
        queue_map = {item.node_id: item for item in predecessor_items}
        completed_nodes = []
        pending_nodes = []

        for node_id in predecessor_node_ids:
            if node_id in queue_map:
                item = queue_map[node_id]
                if item.status == 'SUCCESS':
                    completed_nodes.append(node_id)
                else:
                    pending_nodes.append({
                        'node_id': node_id,
                        'status': item.status
                    })
            else:
                pending_nodes.append({
                    'node_id': node_id,
                    'status': 'NOT_IN_QUEUE'
                })

        all_completed = len(pending_nodes) == 0
        any_completed = len(completed_nodes) > 0

        self.log_info(f'前驅節點檢查結果', {
            'total': len(predecessor_node_ids),
            'completed': len(completed_nodes),
            'pending': len(pending_nodes)
        })

        # 根據模式決定行為
        if mode == self.MODE_ANY:
            if any_completed:
                return {
                    'status': 'success',
                    'message': f'ANY 模式：有 {len(completed_nodes)} 個前驅節點完成',
                    'data': {
                        'mode': mode,
                        'predecessor_count': len(predecessor_node_ids),
                        'completed_count': len(completed_nodes),
                        'completed_nodes': completed_nodes,
                        'all_completed': all_completed
                    }
                }
            else:
                return {
                    'status': 'pending',
                    'message': f'ANY 模式：等待任一前驅節點完成',
                    'data': {
                        'mode': mode,
                        'predecessor_count': len(predecessor_node_ids),
                        'completed_count': 0,
                        'pending_nodes': pending_nodes
                    }
                }

        else:  # MODE_ALL
            if all_completed:
                return {
                    'status': 'success',
                    'message': f'ALL 模式：所有前驅節點已完成',
                    'data': {
                        'mode': mode,
                        'predecessor_count': len(predecessor_node_ids),
                        'completed_count': len(completed_nodes),
                        'completed_nodes': completed_nodes,
                        'all_completed': True
                    }
                }
            else:
                return {
                    'status': 'pending',
                    'message': f'ALL 模式：等待前驅節點完成（{len(completed_nodes)}/{len(predecessor_node_ids)}）',
                    'data': {
                        'mode': mode,
                        'predecessor_count': len(predecessor_node_ids),
                        'completed_count': len(completed_nodes),
                        'pending_nodes': pending_nodes
                    }
                }

    def _get_predecessor_node_ids(self) -> List[str]:
        """從 graph 中取得前驅節點 ID 列表"""
        from ...models import FwWorkflowTemplate

        if not self.workflow_instance:
            return []

        workflow_template = FwWorkflowTemplate.query.filter_by(
            secure_code=self.workflow_instance.workflow_template_secure_code
        ).first()

        if not workflow_template or not workflow_template.graph:
            return []

        edges = workflow_template.graph.get('edges', [])
        current_node_id = self.queue_item.node_id

        predecessor_ids = []
        for edge in edges:
            edge_data = edge.get('data', edge)
            if edge_data.get('target') == current_node_id:
                source_id = edge_data.get('source')
                if source_id:
                    predecessor_ids.append(source_id)

        return predecessor_ids
