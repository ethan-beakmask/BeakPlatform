"""
FormWorkflow Module - SubFlow Handler
子流程節點處理器

負責啟動子流程：載入子流程模板並將節點加入執行佇列
"""
from typing import Dict, Any
from datetime import datetime
from .base import BaseNodeHandler


class SubFlowHandler(BaseNodeHandler):
    """
    子流程處理器

    子流程設計：
    - 子流程創建獨立的 FwWorkflowInstance
    - 子流程透過 parent_instance_code 關聯回父流程
    - 子流程完成後通知父流程繼續

    配置參數：
    - childFlowId: 子流程模板的 code
    - paramMapping: 參數映射（可選）
      - input: {父變數: 子變數} 輸入映射
      - output: {子變數: 父變數} 輸出映射
    """

    def validate(self) -> bool:
        """
        驗證節點配置

        必要配置：
        - childFlowId: 子流程的流程編號

        註：如果沒有配置 childFlowId，節點會直接完成（不啟動子流程）
        """
        child_flow_id = self.get_config_value('childFlowId')

        if not child_flow_id:
            self.log_info(
                'SubFlow 節點沒有配置 childFlowId，將直接完成（不啟動子流程）',
                {'node_id': self.queue_item.node_id}
            )
            return True

        # 檢查子流程是否存在
        from ...models import FwWorkflowTemplate

        subflow = FwWorkflowTemplate.query.filter_by(
            code=child_flow_id,
            org_secure_code=self.queue_item.org_secure_code
        ).first()

        if not subflow:
            raise ValueError(f'找不到子流程: {child_flow_id}')

        return True

    def handle(self) -> Dict[str, Any]:
        """處理 SubFlow 節點"""
        child_flow_id = self.get_config_value('childFlowId')

        # 如果沒有 childFlowId，直接完成
        if not child_flow_id:
            return {
                'status': 'success',
                'message': 'SubFlow 節點沒有配置 childFlowId，直接完成',
                'data': {}
            }

        # 循環上限（PF-200）：子流程可被同一節點重複執行（迴圈是合理應用），
        # 但平台不自動偵測無限循環。設定 max_iterations 時超過即失敗。
        # 計數記在「本層」（含這個 SubFlow 節點的 instance）的流程變數——
        # 每次執行子流程都是全新 instance，記在子流程身上永遠是 1。
        max_iterations = self.get_config_value('max_iterations')
        run_count = 0
        try:
            max_iterations = int(max_iterations) if max_iterations else 0
        except (TypeError, ValueError):
            max_iterations = 0
        if max_iterations > 0:
            from ..variable_service import VariableService
            instance_code = self.queue_item.workflow_instance_secure_code
            counter_name = f'{self.queue_item.node_id}_runs'
            try:
                run_count = int(VariableService.get_flow_var(instance_code, counter_name) or 0)
            except (TypeError, ValueError):
                run_count = 0
            if run_count >= max_iterations:
                msg = (f'子流程節點已達執行次數上限 max_iterations={max_iterations}'
                       f'（已執行 {run_count} 次），中止以防止無限循環')
                self.log_error(msg, {'child_flow_id': child_flow_id})
                return {'status': 'error', 'message': msg,
                        'data': {'max_iterations': max_iterations, 'run_count': run_count}}
            VariableService.set_flow_var(
                instance_code, counter_name, run_count + 1,
                org_code=self.queue_item.org_secure_code,
                source_node_id=self.queue_item.node_id)

        self.log_info(f'啟動子流程: {child_flow_id}', {
            'child_flow_id': child_flow_id
        })

        try:
            from ...models import FwWorkflowTemplate, FwWorkflowInstance, FwNodeExecutionQueue
            from app import db
            import secrets

            # 1. 優先從發行快照載入子流程 graph，找不到則查 DB（fallback）
            snapshot_graph = self._get_subflow_graph_from_snapshot(child_flow_id)

            if snapshot_graph:
                self.log_info(f'從發行快照讀取子流程 graph: {child_flow_id}')
                child_graph = snapshot_graph
                # 仍需查 DB 取得 subflow 模板（用於建 instance 的 workflow_template_secure_code）
                subflow = FwWorkflowTemplate.query.filter_by(
                    code=child_flow_id,
                    org_secure_code=self.queue_item.org_secure_code
                ).first()
                if not subflow:
                    raise ValueError(f'找不到子流程模板: {child_flow_id}')
            else:
                self.log_info(f'快照無子流程資料，從 DB 載入: {child_flow_id}')
                subflow = FwWorkflowTemplate.query.filter_by(
                    code=child_flow_id,
                    org_secure_code=self.queue_item.org_secure_code
                ).first()
                if not subflow:
                    raise ValueError(f'找不到子流程: {child_flow_id}')
                child_graph = subflow.graph

            if not child_graph or 'nodes' not in child_graph:
                raise ValueError(f'子流程 {child_flow_id} 的 graph 資料不正確')

            # 2. 處理輸入參數映射（如果配置了 paramMapping）
            param_mapping = self.get_config_value('paramMapping', {})
            input_mapping = param_mapping.get('input', {})

            if input_mapping:
                self.log_info('處理子流程輸入參數映射', {
                    'input_mapping': input_mapping
                })
                # 透過 TREE scope 共享變數（父子流程共享 root_instance_code）
                # 將 input_mapping 中的父流程變數寫入 TREE scope
                for parent_var, child_var in input_mapping.items():
                    value = self.get_var(parent_var)
                    if value is not None:
                        self.set_tree_var(child_var, value)
                        self.log_info(f'TREE 變數映射: {parent_var}={value} → {child_var}')

            # 3. 取得父流程實例
            parent_instance = FwWorkflowInstance.query.filter_by(
                secure_code=self.queue_item.workflow_instance_secure_code
            ).first()

            if not parent_instance:
                raise ValueError(f'找不到父流程實例: {self.queue_item.workflow_instance_secure_code}')

            # 4. 計算子流程深度
            child_depth = (parent_instance.workflow_depth or 0) + 1

            # 計算 root_instance_code
            root_code = parent_instance.root_instance_code or parent_instance.secure_code

            # 子流程使用帶後綴的 execution_code
            base_code = parent_instance.execution_code or parent_instance.secure_code
            node_suffix = self.queue_item.node_id.split('-')[-1] if self.queue_item.node_id else '0'
            execution_code = f"{base_code}-SUB{child_depth}-{node_suffix}"

            # 5. 創建子流程實例（保存 graph_snapshot，確保子流程執行期間使用啟動時的圖）
            child_instance = FwWorkflowInstance(
                secure_code=secrets.token_urlsafe(16),
                org_secure_code=self.queue_item.org_secure_code,
                workflow_template_secure_code=subflow.secure_code,
                form_instance_secure_code=self.queue_item.form_instance_secure_code,
                execution_code=execution_code,
                status='RUNNING',
                started_at=datetime.utcnow(),
                parent_instance_code=parent_instance.secure_code,
                root_instance_code=root_code,
                workflow_depth=child_depth,
                graph_snapshot=child_graph
            )
            db.session.add(child_instance)
            db.session.flush()

            self.log_info('已創建子流程實例', {
                'child_instance_code': child_instance.secure_code,
                'parent_instance_code': parent_instance.secure_code,
                'child_flow_template': child_flow_id
            })

            # 6. 只加入 START 節點到佇列
            nodes_added = []
            start_nodes = []

            for node in child_graph['nodes']:
                node_id = node['id']

                # 推斷節點類型
                node_type = node.get('type')
                if not node_type:
                    node_type = self._infer_node_type(node_id)

                # 只處理 START 節點
                if not node_type or node_type.lower() != 'start':
                    continue

                # 取得節點配置
                node_config = node.get('data', {}).get('config', {})
                display_name = node.get('label') or node.get('data', {}).get('label') or ''

                # 建立 START 節點佇列項目
                new_queue_item = FwNodeExecutionQueue(
                    secure_code=secrets.token_urlsafe(16),
                    org_secure_code=self.queue_item.org_secure_code,
                    workflow_instance_secure_code=child_instance.secure_code,
                    form_instance_secure_code=self.queue_item.form_instance_secure_code,
                    node_id=node_id,
                    node_type=node_type,
                    node_name=display_name,
                    node_config=node_config,
                    calling_instance_code=parent_instance.secure_code,
                    parent_node_id=self.queue_item.node_id,
                    status='PENDING',
                    priority=5,
                    scheduled_at=datetime.utcnow()
                )

                db.session.add(new_queue_item)
                nodes_added.append(node_id)
                start_nodes.append(node_id)

            db.session.commit()

            self.log_info('子流程 START 節點已加入佇列', {
                'child_flow_id': child_flow_id,
                'start_nodes_count': len(start_nodes),
                'start_nodes': start_nodes
            })

            return {
                'status': 'waiting_subflow',  # 等待子流程完成
                'message': f'子流程已啟動，等待完成: {child_flow_id}',
                'data': {
                    'child_flow_id': child_flow_id,
                    'child_instance_code': child_instance.secure_code,
                    'nodes_added': nodes_added,
                    'start_nodes': start_nodes
                }
            }

        except Exception as e:
            error_msg = f'啟動子流程失敗: {str(e)}'
            self.log_error(error_msg, {'child_flow_id': child_flow_id})

            return {
                'status': 'error',
                'message': error_msg,
                'data': {
                    'error': str(e)
                }
            }

    def _get_subflow_graph_from_snapshot(self, child_flow_code: str):
        """
        嘗試從發行快照取得子流程 graph

        透過 queue_item → workflow_instance → root instance → published version
        取得 workflow_snapshot.sub_workflows 中對應子流程的 graph。

        Returns:
            dict or None: 子流程 graph，找不到則 None
        """
        try:
            from ...models import FwWorkflowInstance, FwPublishedFormWorkflow

            # 找到當前 workflow instance
            instance = FwWorkflowInstance.query.filter_by(
                secure_code=self.queue_item.workflow_instance_secure_code
            ).first()
            if not instance:
                return None

            # 找到 root instance（向上追溯）
            root_code = instance.root_instance_code or instance.secure_code
            root_instance = FwWorkflowInstance.query.filter_by(
                secure_code=root_code
            ).first()
            if not root_instance:
                return None

            # 取得 published_secure_code（優先從 workflow instance，再從 form instance）
            pub_code = root_instance.published_secure_code
            if not pub_code and root_instance.form_instance_secure_code:
                from ...models import FwFormInstance
                form_inst = FwFormInstance.query.filter_by(
                    secure_code=root_instance.form_instance_secure_code
                ).first()
                if form_inst:
                    pub_code = form_inst.published_secure_code

            if not pub_code:
                return None

            published = FwPublishedFormWorkflow.query.filter_by(
                secure_code=pub_code
            ).first()
            if not published or not published.workflow_snapshot:
                return None

            sub_workflows = published.workflow_snapshot.get('sub_workflows', {})
            sub_entry = sub_workflows.get(child_flow_code)
            if sub_entry:
                return sub_entry.get('graph')
            return None
        except Exception:
            return None

    def _infer_node_type(self, node_id: str) -> str:
        """根據節點 ID 推斷類型"""
        node_id_upper = node_id.upper()

        if 'START' in node_id_upper:
            return 'Start'
        elif 'END' in node_id_upper:
            return 'End'
        elif 'APPROVE' in node_id_upper:
            return 'Approve'
        elif 'DELAY' in node_id_upper:
            return 'Delay'
        elif 'BRANCH' in node_id_upper:
            return 'Branch'
        elif 'SWITCH' in node_id_upper:
            return 'Switch'
        elif 'CONVERGE' in node_id_upper:
            return 'Converge'
        elif 'OPSET' in node_id_upper:
            return 'OpSet'
        elif 'NOTIFY' in node_id_upper:
            return 'Notify'
        elif 'SUBFLOW' in node_id_upper or 'SUBPROCESS' in node_id_upper:
            return 'SubFlow'
        else:
            return 'Unknown'
