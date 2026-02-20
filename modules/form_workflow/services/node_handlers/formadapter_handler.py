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
        2. 產生可選路徑列表（支援自定義決策選項）
        3. 評估來向變數控制（input_variables）
        4. 設定狀態為等待簽核
        5. 等待簽核者透過 API 提交選擇

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
        min_comment_length = int(self.get_config_value('min_comment_length', 0))
        use_custom_decisions = self.get_config_value('use_custom_decisions', False)
        output_variable = self.get_config_value('output_variable', '')

        # 根據模式取得決策選項
        if use_custom_decisions:
            available_paths = self._get_custom_decision_options()
        else:
            available_paths = self._get_available_paths()

        if not available_paths:
            self.log_error('FormAdapter 節點沒有出線，無法繼續')
            return {
                'status': 'error',
                'message': 'FormAdapter 節點沒有出線'
            }

        # 評估來向變數控制
        input_variable_results = self._resolve_input_variables()

        # 解析簽核者
        assignees = self._resolve_assignees(assignee_type, assignee_value)

        self.log_info('FormAdapter 節點等待簽核', {
            'node_id': self.queue_item.node_id,
            'assignee_type': assignee_type,
            'assignee_value': assignee_value,
            'assignees': assignees,
            'selection_mode': selection_mode,
            'use_custom_decisions': use_custom_decisions,
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
                'min_comment_length': min_comment_length,
                'use_custom_decisions': use_custom_decisions,
                'output_variable': output_variable,
                'available_paths': available_paths,
                'input_variable_results': input_variable_results,
                'waiting_since': datetime.utcnow().isoformat()
            }
        }

    def _get_custom_decision_options(self) -> List[Dict[str, Any]]:
        """
        從 config.decision_options 產生自定義決策選項列表

        Returns:
            list: 決策選項列表，每個選項包含 id, label, value, target_edges, style, visible_when
        """
        decision_options = self.get_config_value('decision_options', [])
        if not decision_options:
            return []

        # 取得合法 edge IDs 用於驗證
        graph = self._get_workflow_graph()
        valid_edge_ids = set()
        if graph:
            edges = graph.get('edges', [])
            current_node_id = self.queue_item.node_id
            for edge in edges:
                edge_data = edge.get('data', edge)
                if edge_data.get('source') == current_node_id:
                    eid = edge_data.get('id', edge.get('id'))
                    if eid:
                        valid_edge_ids.add(eid)

        result = []
        for opt in decision_options:
            opt_id = opt.get('id', '')
            target_edges = opt.get('target_edges', [])

            # 驗證 target_edges 合法性（空 target_edges 表示終態）
            validated_edges = []
            for eid in target_edges:
                if eid in valid_edge_ids:
                    validated_edges.append(eid)
                else:
                    self.log_warning(f'決策選項 {opt_id} 引用了無效的 edge: {eid}')

            result.append({
                'id': opt_id,
                'label': opt.get('label', ''),
                'value': opt.get('value', ''),
                'target_edges': validated_edges,
                'style': opt.get('style', 'default'),
                'visible_when': opt.get('visible_when')
            })

        return result

    def _resolve_input_variables(self) -> Dict[str, Any]:
        """
        評估 config.input_variables 中定義的來向變數控制規則

        Returns:
            dict: 評估結果
            {
                'hidden_option_ids': ['opt-uuid1', ...],    # 應隱藏的決策選項 ID
                'field_permission_overrides': {              # 動態欄位權限覆蓋
                    'amount': 'editable',
                    'reason': 'hidden'
                }
            }
        """
        input_variables = self.get_config_value('input_variables', [])
        if not input_variables:
            return {}

        hidden_option_ids = set()
        visible_option_ids = set()
        field_permission_overrides = {}
        has_visibility_rules = False

        for var_def in input_variables:
            var_name = var_def.get('var_name', '')
            if not var_name:
                continue

            actual_value = self.get_var(var_name, '')
            controls = var_def.get('controls', [])

            for ctrl in controls:
                ctrl_type = ctrl.get('type', '')
                condition = ctrl.get('condition', {})

                # 評估條件
                if not self._evaluate_input_condition(actual_value, condition):
                    continue

                if ctrl_type == 'decision_visibility':
                    has_visibility_rules = True
                    target_ids = ctrl.get('target_option_ids', [])
                    visible_option_ids.update(target_ids)

                elif ctrl_type == 'field_permission':
                    field_key = ctrl.get('field_key', '')
                    permission = ctrl.get('permission', 'readonly')
                    if field_key:
                        field_permission_overrides[field_key] = permission

        result = {}

        # 計算 hidden_option_ids：如果有 visibility 規則，不在 visible 集合中的都隱藏
        if has_visibility_rules:
            all_option_ids = set()
            decision_options = self.get_config_value('decision_options', [])
            for opt in decision_options:
                all_option_ids.add(opt.get('id', ''))
            hidden_option_ids = all_option_ids - visible_option_ids
            result['hidden_option_ids'] = list(hidden_option_ids)

        if field_permission_overrides:
            result['field_permission_overrides'] = field_permission_overrides

        return result

    @staticmethod
    def _evaluate_input_condition(actual_value: Any, condition: Dict) -> bool:
        """
        評估單一條件

        Args:
            actual_value: 實際變數值
            condition: {'operator': '==', 'value': 'high'}

        Returns:
            bool: 條件是否成立
        """
        operator = condition.get('operator', '==')
        expected = condition.get('value', '')

        try:
            actual_str = str(actual_value) if actual_value is not None else ''
            expected_str = str(expected)

            if operator == '==':
                return actual_str == expected_str
            elif operator == '!=':
                return actual_str != expected_str
            elif operator == '>':
                return float(actual_str) > float(expected_str)
            elif operator == '>=':
                return float(actual_str) >= float(expected_str)
            elif operator == '<':
                return float(actual_str) < float(expected_str)
            elif operator == '<=':
                return float(actual_str) <= float(expected_str)
            elif operator == 'contains':
                return expected_str in actual_str
            elif operator == 'not_empty':
                return actual_str.strip() != ''
            elif operator == 'empty':
                return actual_str.strip() == ''
            else:
                return False
        except (ValueError, TypeError):
            return False

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
        """取得工作流圖形定義（快照優先，設計圖 fallback）"""
        if not self.workflow_instance:
            return {}
        from ..workflow_engine import WorkflowEngine
        return WorkflowEngine.get_effective_graph(self.workflow_instance)

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
            if self.form_instance and self.form_instance.applicant_secure_code:
                return [self.form_instance.applicant_secure_code]
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

        elif assignee_type == 'ROLE':
            # 查詢該角色下的所有用戶
            if assignee_value:
                return self._resolve_role_users(assignee_value)
            return []

        elif assignee_type == 'DEPARTMENT':
            # 查詢該部門下的所有用戶
            if assignee_value:
                return self._resolve_department_users(assignee_value)
            return []

        return []

    def _resolve_role_users(self, role_secure_code: str) -> List[str]:
        """查詢指定角色下的所有用戶 secure_code（排除已刪除和停用的帳號）"""
        from app.models.associations import UserRoleAssignment
        from app.models.user import User
        org_code = self.queue_item.org_secure_code

        assignments = UserRoleAssignment.query.join(
            User, UserRoleAssignment.user_secure_code == User.secure_code
        ).filter(
            UserRoleAssignment.role_secure_code == role_secure_code,
            UserRoleAssignment.org_secure_code == org_code,
            UserRoleAssignment.is_deleted == False,
            User.is_active == True,
            User.is_deleted == False
        ).all()

        user_codes = [a.user_secure_code for a in assignments if a.user_secure_code]
        if not user_codes:
            logger.warning(f'角色 {role_secure_code} 下無用戶')
        return user_codes

    def _resolve_department_users(self, dept_secure_code: str) -> List[str]:
        """查詢指定部門下的所有用戶 secure_code"""
        from app.models.user import User
        org_code = self.queue_item.org_secure_code

        users = User.query.filter(
            User.primary_unit_secure_code == dept_secure_code,
            User.org_secure_code == org_code,
            User.is_active == True,
            User.is_deleted == False
        ).all()

        user_codes = [u.secure_code for u in users]
        if not user_codes:
            logger.warning(f'部門 {dept_secure_code} 下無用戶')
        return user_codes


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

    # 取得有效流程圖（快照優先，設計圖 fallback）
    from ..workflow_engine import WorkflowEngine
    graph = WorkflowEngine.get_effective_graph(workflow_instance)
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
