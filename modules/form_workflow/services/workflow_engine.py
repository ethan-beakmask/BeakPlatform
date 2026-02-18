"""
FormWorkflow Module - Workflow Engine
工作流執行引擎

負責啟動工作流、處理節點執行、推進流程。
適配 BeakPlatform 模組化架構。
"""
import logging
import secrets
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

from app import db
from app.platform.auth import current_user
from app.platform.data import get_current_org

from ..models import (
    FwFormTemplate,
    FwWorkflowTemplate,
    FwFormInstance,
    FwWorkflowInstance,
    FwApprovalRecord,
    FwNodeExecutionQueue,
)


class WorkflowEngine:
    """工作流執行引擎"""

    @staticmethod
    def get_effective_graph(workflow_instance) -> dict:
        """取得工作流的有效流程圖（快照優先，設計圖 fallback）"""
        if workflow_instance.graph_snapshot:
            return workflow_instance.graph_snapshot
        # 向下相容：舊實例無 graph_snapshot，回退到設計圖
        from ..models import FwWorkflowTemplate
        template = FwWorkflowTemplate.query.filter_by(
            secure_code=workflow_instance.workflow_template_secure_code,
            is_deleted=False
        ).first()
        if template:
            return template.graph or {}
        return {}

    @staticmethod
    def generate_execution_code(org_secure_code: str) -> str:
        """
        生成流程執行代碼

        Args:
            org_secure_code: 組織安全碼

        Returns:
            str: 執行代碼 (格式: ORG-YYYYMMDD-XXXX)
        """
        import random
        import string
        date_str = datetime.utcnow().strftime('%Y%m%d')
        random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        return f"{org_secure_code[:4]}-{date_str}-{random_str}"

    @staticmethod
    def start_workflow(
        form_instance_secure_code: str,
        workflow_template_secure_code: Optional[str] = None,
        is_test: bool = True
    ) -> FwWorkflowInstance:
        """
        啟動工作流

        Args:
            form_instance_secure_code: 表單實例 secure_code
            workflow_template_secure_code: 工作流模板 secure_code（可選）
            is_test: 是否為測試模式

        Returns:
            FwWorkflowInstance: 工作流實例
        """
        # 1. 取得表單實例
        form_instance = FwFormInstance.query.filter_by(
            secure_code=form_instance_secure_code,
            is_deleted=False
        ).first()

        if not form_instance:
            raise ValueError(f'表單實例 {form_instance_secure_code} 不存在')

        # 2. 取得工作流模板
        if workflow_template_secure_code:
            workflow_template = FwWorkflowTemplate.query.filter_by(
                secure_code=workflow_template_secure_code,
                org_secure_code=form_instance.org_secure_code,
                is_deleted=False
            ).first()
        else:
            # 自動查找關聯的工作流模板
            form_template = FwFormTemplate.query.filter_by(
                secure_code=form_instance.form_template_secure_code,
                is_deleted=False
            ).first()

            if form_template and form_template.workflow_template_secure_code:
                workflow_template = FwWorkflowTemplate.query.filter_by(
                    secure_code=form_template.workflow_template_secure_code,
                    is_deleted=False
                ).first()
            else:
                raise ValueError('找不到對應的工作流模板')

        if not workflow_template:
            raise ValueError(f'工作流模板不存在')

        # 3. 取得流程定義並保存快照
        graph = workflow_template.graph
        if not graph or 'nodes' not in graph:
            raise ValueError('工作流模板缺少 graph 資料')

        # 4. 創建工作流實例（保存 graph_snapshot，確保流程執行期間使用發行時的圖）
        timeout_at = None
        if workflow_template.timeout_minutes:
            timeout_at = datetime.utcnow() + timedelta(minutes=workflow_template.timeout_minutes)

        execution_code = WorkflowEngine.generate_execution_code(form_instance.org_secure_code)

        workflow_instance = FwWorkflowInstance(
            org_secure_code=form_instance.org_secure_code,
            workflow_template_secure_code=workflow_template.secure_code,
            form_instance_secure_code=form_instance_secure_code,
            is_test=is_test,
            execution_code=execution_code,
            status='RUNNING',
            current_node_id=None,
            graph_snapshot=graph,
            timeout_at=timeout_at,
            created_by_secure_code=form_instance.applicant_secure_code
        )

        db.session.add(workflow_instance)
        db.session.flush()  # 取得 secure_code

        # 5. 從 graph 中找到 START 節點並加入佇列
        graph_nodes = graph.get('nodes', [])
        start_nodes = []

        for node in graph_nodes:
            node_id = node.get('id')
            node_type = node.get('type')

            # 推斷節點類型
            if not node_type:
                if node_id and node_id.startswith('node-Start'):
                    node_type = 'Start'
                elif node_id and node_id.startswith('node-End'):
                    node_type = 'End'
                else:
                    node_data = node.get('data', {})
                    node_type = node_data.get('type', 'UNKNOWN')

            if node_type == 'Start':
                display_name = node.get('label') or node.get('data', {}).get('label') or ''
                start_nodes.append({
                    'id': node_id,
                    'config': node.get('data', {}).get('config', {}),
                    'display_name': display_name
                })

        if not start_nodes:
            raise ValueError('工作流模板缺少 Start 節點')

        # 6. 將 START 節點加入執行佇列
        for start_node in start_nodes:
            queue_item = FwNodeExecutionQueue(
                org_secure_code=workflow_instance.org_secure_code,
                workflow_instance_secure_code=workflow_instance.secure_code,
                node_id=start_node['id'],
                node_type='Start',
                node_name=start_node.get('display_name', ''),
                node_config=start_node['config'],
                status='PENDING',
                scheduled_at=datetime.utcnow()
            )
            db.session.add(queue_item)

            # 更新當前節點
            if not workflow_instance.current_node_id:
                workflow_instance.current_node_id = start_node['id']

        # 更新表單實例狀態
        form_instance.status = 'PROCESSING'
        form_instance.submitted_at = datetime.utcnow()

        db.session.commit()

        return workflow_instance

    @staticmethod
    def start_pure_workflow(
        workflow_template_secure_code: str,
        org_secure_code: str,
        applicant_secure_code: Optional[str] = None,
        applicant_name: Optional[str] = "系統"
    ) -> FwWorkflowInstance:
        """
        啟動純流程（無需預先建立表單）

        Args:
            workflow_template_secure_code: 工作流模板 secure_code
            org_secure_code: 組織安全碼
            applicant_secure_code: 申請人 secure_code
            applicant_name: 申請人名稱

        Returns:
            FwWorkflowInstance: 工作流實例
        """
        # 取得工作流模板
        workflow_template = FwWorkflowTemplate.query.filter_by(
            secure_code=workflow_template_secure_code,
            org_secure_code=org_secure_code,
            is_deleted=False
        ).first()

        if not workflow_template:
            raise ValueError(f'工作流模板 {workflow_template_secure_code} 不存在')

        # 建立流程記錄單作為 FormInstance
        record_instance = FwFormInstance(
            org_secure_code=org_secure_code,
            form_template_secure_code=None,  # 純流程無表單模板
            title=f'流程記錄 - {workflow_template.name}',
            applicant_secure_code=applicant_secure_code,
            applicant_name=applicant_name,
            status='PROCESSING',
            form_data={'_workflow_record': True}
        )
        db.session.add(record_instance)
        db.session.flush()

        # 啟動工作流
        return WorkflowEngine.start_workflow(
            form_instance_secure_code=record_instance.secure_code,
            workflow_template_secure_code=workflow_template_secure_code
        )

    @staticmethod
    def get_next_nodes(graph: dict, current_node_id: str) -> List[str]:
        """
        從 graph 中找到下一個節點

        Args:
            graph: 流程圖結構 {'nodes': [...], 'edges': [...]}
            current_node_id: 當前節點 ID

        Returns:
            List[str]: 下一個節點 ID 列表
        """
        next_nodes = []

        if not graph or 'edges' not in graph:
            return next_nodes

        for edge in graph['edges']:
            # 支援兩種格式
            edge_data = edge.get('data', edge)
            if edge_data.get('source') == current_node_id:
                target = edge_data.get('target')
                if target:
                    next_nodes.append(target)

        return next_nodes

    @staticmethod
    def get_node_info(graph: dict, node_id: str) -> Optional[dict]:
        """
        從 graph 中取得節點資訊

        Args:
            graph: 流程圖結構
            node_id: 節點 ID

        Returns:
            節點資訊字典
        """
        if not graph or 'nodes' not in graph:
            return None

        for node in graph['nodes']:
            nid = node.get('id') or node.get('data', {}).get('id')
            if nid == node_id:
                return node

        return None

    @staticmethod
    def get_next_node_by_edge(graph: dict, edge_id: str) -> List[str]:
        """
        根據 edge ID 取得目標節點

        Args:
            graph: 流程圖結構
            edge_id: 邊的 ID

        Returns:
            List[str]: 目標節點 ID 列表（通常只有一個）
        """
        if not graph or 'edges' not in graph:
            return []

        for edge in graph['edges']:
            edge_data = edge.get('data', edge)
            eid = edge_data.get('id') or edge.get('id')
            if eid == edge_id:
                target = edge_data.get('target')
                if target:
                    return [target]

        return []

    @staticmethod
    def advance_workflow(
        workflow_instance_secure_code: str,
        completed_node_id: str,
        selected_path: Optional[str] = None
    ) -> List[FwNodeExecutionQueue]:
        """
        推進工作流到下一個節點

        Args:
            workflow_instance_secure_code: 工作流實例 secure_code
            completed_node_id: 已完成的節點 ID
            selected_path: 選擇的路徑 edge ID（用於 FormAdapter 等需要選擇的節點）

        Returns:
            新建立的佇列項目列表
        """
        workflow_instance = FwWorkflowInstance.query.filter_by(
            secure_code=workflow_instance_secure_code,
            is_deleted=False
        ).first()

        if not workflow_instance:
            return []

        # 取得有效流程圖（快照優先）
        graph = WorkflowEngine.get_effective_graph(workflow_instance)
        if not graph:
            return []

        # 找到下一個節點
        # 如果有 selected_path（字符串，edge ID），只取該路徑的目標節點
        if selected_path and isinstance(selected_path, str):
            next_node_ids = WorkflowEngine.get_next_node_by_edge(graph, selected_path)
        else:
            next_node_ids = WorkflowEngine.get_next_nodes(graph, completed_node_id)

        if not next_node_ids:
            return []

        # 為每個下一節點建立佇列項目
        # 逐筆 commit，配合 partial unique index 防止 race condition 重複建立
        new_items = []
        for next_node_id in next_node_ids:
            node_info = WorkflowEngine.get_node_info(graph, next_node_id)
            if not node_info:
                continue

            # 推斷節點類型
            node_type = node_info.get('type') or node_info.get('data', {}).get('type')
            if not node_type:
                if next_node_id.startswith('node-End'):
                    node_type = 'End'
                elif next_node_id.startswith('node-Start'):
                    node_type = 'Start'
                else:
                    node_type = 'UNKNOWN'

            node_config = node_info.get('config') or node_info.get('data', {}).get('config') or {}
            display_name = node_info.get('label') or node_info.get('data', {}).get('label') or ''

            # 檢查是否已存在未完成的相同節點
            existing = FwNodeExecutionQueue.query.filter(
                FwNodeExecutionQueue.workflow_instance_secure_code == workflow_instance.secure_code,
                FwNodeExecutionQueue.node_id == next_node_id,
                FwNodeExecutionQueue.status.in_(['PENDING', 'RUNNING', 'WAITING'])
            ).first()

            if existing:
                logger.debug(f'[advance_workflow] 節點 {next_node_id} 已有 {existing.status} 項目，跳過')
                continue

            queue_item = FwNodeExecutionQueue(
                org_secure_code=workflow_instance.org_secure_code,
                workflow_instance_secure_code=workflow_instance.secure_code,
                form_instance_secure_code=workflow_instance.form_instance_secure_code,
                node_id=next_node_id,
                node_type=node_type,
                node_name=display_name,
                node_config=node_config,
                status='PENDING',
                scheduled_at=datetime.utcnow()
            )
            try:
                with db.session.begin_nested():
                    db.session.add(queue_item)
                    db.session.flush()
            except IntegrityError:
                # Race condition：另一個 executor 已為此節點建立了 queue item
                # begin_nested 只回滾 savepoint，不影響整個 session
                logger.info(f'[advance_workflow] 節點 {next_node_id} 已被其他 executor 建立，跳過')
                continue

            new_items.append(queue_item)

            # 更新當前節點
            workflow_instance.current_node_id = next_node_id

        db.session.commit()
        return new_items

    @staticmethod
    def complete_workflow(
        workflow_instance_secure_code: str,
        status: str = 'COMPLETED',
        end_message: Optional[str] = None
    ):
        """
        完成工作流

        Args:
            workflow_instance_secure_code: 工作流實例 secure_code
            status: 最終狀態 (COMPLETED, REJECTED, CANCELLED, ERROR)
            end_message: 結束訊息
        """
        workflow_instance = FwWorkflowInstance.query.filter_by(
            secure_code=workflow_instance_secure_code,
            is_deleted=False
        ).first()

        if not workflow_instance:
            return

        workflow_instance.status = status
        workflow_instance.completed_at = datetime.utcnow()

        # 子流程不更新 form_instance 狀態（form_instance 由主流程管理）
        if workflow_instance.parent_instance_code:
            logger.info(f'子流程完成，跳過 form_instance 狀態更新 '
                        f'(child={workflow_instance.secure_code}, parent={workflow_instance.parent_instance_code})')
            db.session.commit()
            return

        # 更新表單實例狀態（僅主流程）
        form_instance = FwFormInstance.query.filter_by(
            secure_code=workflow_instance.form_instance_secure_code,
            is_deleted=False
        ).first()

        if form_instance:
            if status == 'COMPLETED':
                form_instance.status = 'APPROVED'
            elif status == 'REJECTED':
                form_instance.status = 'REJECTED'
            elif status == 'CANCELLED':
                form_instance.status = 'CANCELLED'
            else:
                form_instance.status = 'ERROR'

            form_instance.completed_at = datetime.utcnow()

        db.session.commit()

        # SQL Sync：流程結束時寫入企業 DB（終態資料，含簽核者修改）
        if form_instance and form_instance.published_secure_code:
            try:
                from ..services.sql_sync.sync_service import enqueue_sync_safe
                if enqueue_sync_safe(form_instance, form_instance.published_secure_code):
                    db.session.commit()
            except Exception as e:
                logger.warning(f'SQL Sync enqueue 失敗: {e}')

    @staticmethod
    def cancel_pending_nodes(
        workflow_instance_secure_code: str,
        exclude_queue_item_id: int = None
    ):
        """
        取消工作流中所有未完成的節點（cancel 模式用）

        Args:
            workflow_instance_secure_code: 工作流實例 secure_code
            exclude_queue_item_id: 排除的佇列項目 ID（End 節點自己）
        """
        query = FwNodeExecutionQueue.query.filter(
            FwNodeExecutionQueue.workflow_instance_secure_code == workflow_instance_secure_code,
            FwNodeExecutionQueue.status.in_(['PENDING', 'RUNNING', 'WAITING'])
        )

        if exclude_queue_item_id:
            query = query.filter(FwNodeExecutionQueue.id != exclude_queue_item_id)

        pending_nodes = query.all()

        for node in pending_nodes:
            node.cancel()

        if pending_nodes:
            db.session.commit()
            logger.info(f'cancel 模式：已取消 {len(pending_nodes)} 個未完成節點 '
                        f'(workflow={workflow_instance_secure_code})')

    @staticmethod
    def process_approval(
        queue_item_secure_code: str,
        action: str,
        approver_secure_code: str,
        comment: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        處理簽核動作

        Args:
            queue_item_secure_code: 佇列項目 secure_code
            action: 動作 ('APPROVE' or 'REJECT')
            approver_secure_code: 審批人 secure_code
            comment: 意見

        Returns:
            Tuple[bool, str]: (是否成功, 訊息)
        """
        queue_item = FwNodeExecutionQueue.query.filter_by(
            secure_code=queue_item_secure_code
        ).first()

        if not queue_item:
            return False, '佇列項目不存在'

        if queue_item.status not in ['PENDING', 'WAITING']:
            return False, f'佇列項目狀態為 {queue_item.status}，無法處理'

        try:
            # 更新佇列項目
            queue_item.status = 'SUCCESS' if action == 'APPROVE' else 'FAILED'
            queue_item.completed_at = datetime.utcnow()
            queue_item.result = {
                'action': action,
                'comment': comment,
                'approver_secure_code': approver_secure_code
            }

            # 建立簽核記錄
            approval_record = FwApprovalRecord(
                secure_code=secrets.token_urlsafe(16),
                org_secure_code=queue_item.org_secure_code,
                workflow_instance_secure_code=queue_item.workflow_instance_secure_code,
                form_instance_secure_code=queue_item.form_instance_secure_code,
                node_id=queue_item.node_id,
                node_name=queue_item.node_name,
                approver_secure_code=approver_secure_code,
                action=action,
                comment=comment,
                acted_at=datetime.utcnow(),
            )
            db.session.add(approval_record)

            # 根據動作處理
            if action == 'APPROVE':
                # 推進到下一個節點
                WorkflowEngine.advance_workflow(
                    queue_item.workflow_instance_secure_code,
                    queue_item.node_id,
                    queue_item.result
                )
            else:
                # 拒絕，結束工作流
                WorkflowEngine.complete_workflow(
                    queue_item.workflow_instance_secure_code,
                    status='REJECTED',
                    end_message=comment
                )

            db.session.commit()
            return True, '處理成功'

        except Exception as e:
            db.session.rollback()
            return False, f'處理失敗: {str(e)}'

    @staticmethod
    def get_pending_tasks(
        user_secure_code: str,
        org_secure_code: Optional[str] = None
    ) -> List[Dict]:
        """
        取得用戶的待處理任務

        Args:
            user_secure_code: 用戶 secure_code
            org_secure_code: 組織代碼（可選）

        Returns:
            List[Dict]: 任務列表
        """
        query = FwNodeExecutionQueue.query.filter(
            FwNodeExecutionQueue.status.in_(['PENDING', 'WAITING'])
        )

        if org_secure_code:
            query = query.filter_by(org_secure_code=org_secure_code)

        # TODO: 根據指派邏輯過濾
        # 目前返回所有待處理任務

        queue_items = query.order_by(
            FwNodeExecutionQueue.scheduled_at.asc()
        ).all()

        tasks = []
        for item in queue_items:
            workflow_instance = FwWorkflowInstance.query.filter_by(
                secure_code=item.workflow_instance_secure_code
            ).first()

            if not workflow_instance:
                continue

            form_instance = FwFormInstance.query.filter_by(
                secure_code=workflow_instance.form_instance_secure_code
            ).first()

            tasks.append({
                'queue_secure_code': item.secure_code,
                'node_id': item.node_id,
                'node_type': item.node_type,
                'node_name': item.node_name,
                'status': item.status,
                'workflow_instance_secure_code': workflow_instance.secure_code,
                'form_instance_secure_code': form_instance.secure_code if form_instance else None,
                'form_title': form_instance.title if form_instance else None,
                'applicant_name': form_instance.applicant_name if form_instance else None,
                'scheduled_at': item.scheduled_at.isoformat() if item.scheduled_at else None,
            })

        return tasks
