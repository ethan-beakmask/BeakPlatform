"""
FormWorkflow Module - End Handler
結束節點處理器

三種結束模式：
- detach (分離執行): 直接結束流程，不處理其他未完成節點（由 executor 自然清理）
- cancel (取消/終止): 結束流程並主動取消所有未完成節點
- strict (嚴格等待): 等待所有其他節點完成後才結束流程；若有節點失敗則流程標記失敗

子流程結束：
- 當 workflow_instance.parent_instance_code 不為 None 時，為子流程
- 子流程結束後，喚醒父流程的 SubFlow 節點並推進父流程
"""
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional
from .base import BaseNodeHandler

logger = logging.getLogger(__name__)


class EndHandler(BaseNodeHandler):
    """結束節點處理器"""

    FINISH_MODE_NAMES = {
        'detach': '分離執行',
        'cancel': '取消/終止',
        'strict': '嚴格等待',
    }

    def handle(self) -> Dict[str, Any]:
        """
        處理結束節點

        雙路徑：
        1. 子流程 → _handle_subflow_end()（完成子流程 + 喚醒父流程）
        2. 主流程 → _handle_main_flow_end()（原有邏輯）
        """
        self.report_running()

        # 判斷是否為子流程
        from ...models import FwWorkflowInstance
        workflow_instance = FwWorkflowInstance.query.filter_by(
            secure_code=self.queue_item.workflow_instance_secure_code,
            is_deleted=False
        ).first()

        if workflow_instance and workflow_instance.parent_instance_code:
            return self._handle_subflow_end(workflow_instance)

        return self._handle_main_flow_end()

    def _handle_main_flow_end(self) -> Dict[str, Any]:
        """主流程結束處理（原有邏輯）"""
        finish_mode = self.node_config.get('finish_mode', 'detach')
        wait_seconds = self.node_config.get('wait_seconds', 3)
        mode_name = self.FINISH_MODE_NAMES.get(finish_mode, finish_mode)

        self.log_info('結束節點啟動', {
            'workflow_instance': self.queue_item.workflow_instance_secure_code,
            'node_id': self.queue_item.node_id,
            'finish_mode': finish_mode,
            'wait_seconds': wait_seconds
        })

        # 等待指定秒數（給平行分支一點收尾時間）
        if wait_seconds > 0:
            self.log_info(f'等待 {wait_seconds} 秒後執行結束模式: {mode_name}')
            time.sleep(wait_seconds)

        # 根據模式執行
        if finish_mode == 'strict':
            return self._handle_strict(mode_name)

        # detach / cancel 都是直接完成，差異由 node_runner 處理
        self.log_info(f'流程結束（{mode_name}模式）')
        return {
            'status': 'complete_workflow',
            'message': f'流程已結束（{mode_name}）',
            'data': {
                'finish_mode': finish_mode,
                'completed_at': datetime.utcnow().isoformat()
            }
        }

    def _handle_subflow_end(self, workflow_instance) -> Dict[str, Any]:
        """
        子流程結束處理

        1. 找到父流程的 SubFlow 節點 queue item
        2. 更新父 SubFlow 節點為 SUCCESS
        3. 推進父流程到下一個節點
        4. 返回 complete_workflow 讓 node_runner 完成子流程
        """
        from app import db

        parent_code = workflow_instance.parent_instance_code
        child_code = workflow_instance.secure_code

        self.log_info('子流程結束節點啟動', {
            'child_instance': child_code,
            'parent_instance': parent_code,
            'depth': workflow_instance.workflow_depth
        })

        # 等待 1 秒（給子流程其他分支收尾）
        wait_seconds = self.node_config.get('wait_seconds', 1)
        if wait_seconds > 0:
            time.sleep(wait_seconds)

        try:
            # 找到父流程中的 SubFlow 節點 ID
            parent_node_id = self._find_parent_node_id(child_code)
            if not parent_node_id:
                self.log_warning('找不到父流程 SubFlow 節點 ID，子流程將正常結束但父流程可能卡住')
                return self._subflow_complete_result(parent_code)

            # 更新父流程 SubFlow 節點為 SUCCESS
            self._complete_parent_subflow_node(parent_code, parent_node_id, child_code)

            # 推進父流程
            self._trigger_parent_next_nodes(parent_code, parent_node_id)

            self.log_info('子流程結束，已喚醒父流程', {
                'parent_node_id': parent_node_id,
                'parent_instance': parent_code
            })

        except Exception as e:
            logger.error(f'子流程結束喚醒父流程失敗: {e}', exc_info=True)
            self.log_error(f'喚醒父流程失敗: {str(e)}')

        return self._subflow_complete_result(parent_code)

    def _find_parent_node_id(self, child_instance_code: str) -> Optional[str]:
        """
        從子流程的 START queue item 取得原始 parent_node_id

        原理：SubFlowHandler 建立子流程 START 節點時會設定 parent_node_id，
        而後續由 advance_workflow() 建立的節點不會攜帶此欄位。
        所以需要回查 START 節點的 queue item。
        """
        from ...models import FwNodeExecutionQueue

        start_item = FwNodeExecutionQueue.query.filter(
            FwNodeExecutionQueue.workflow_instance_secure_code == child_instance_code,
            FwNodeExecutionQueue.node_type == 'Start',
            FwNodeExecutionQueue.parent_node_id.isnot(None)
        ).first()

        if start_item:
            return start_item.parent_node_id

        return None

    def _complete_parent_subflow_node(
        self,
        parent_instance_code: str,
        parent_node_id: str,
        child_instance_code: str
    ):
        """更新父流程中 SubFlow queue item 為 SUCCESS"""
        from app import db
        from ...models import FwNodeExecutionQueue

        parent_queue_item = FwNodeExecutionQueue.query.filter(
            FwNodeExecutionQueue.workflow_instance_secure_code == parent_instance_code,
            FwNodeExecutionQueue.node_id == parent_node_id,
            FwNodeExecutionQueue.status == 'WAITING'
        ).first()

        if parent_queue_item:
            parent_queue_item.success({
                'status': 'success',
                'message': '子流程已完成',
                'data': {
                    'child_instance_code': child_instance_code,
                    'completed_at': datetime.utcnow().isoformat()
                }
            })
            db.session.commit()
            self.log_info(f'父流程 SubFlow 節點已更新為 SUCCESS: {parent_node_id}')
        else:
            self.log_warning(f'找不到父流程 WAITING 狀態的 SubFlow 節點: {parent_node_id}')

    def _trigger_parent_next_nodes(self, parent_instance_code: str, parent_node_id: str):
        """調用 WorkflowEngine.advance_workflow() 推進父流程"""
        from ..workflow_engine import WorkflowEngine

        new_items = WorkflowEngine.advance_workflow(
            parent_instance_code,
            parent_node_id
        )

        if new_items:
            node_names = [item.node_name or item.node_id for item in new_items]
            self.log_info(f'父流程已推進，新節點: {node_names}')
        else:
            self.log_info('父流程推進完成（無新節點，可能已到 End）')

    def _subflow_complete_result(self, parent_code: str) -> Dict[str, Any]:
        """子流程完成的返回結果"""
        return {
            'status': 'complete_workflow',
            'message': '子流程已結束',
            'data': {
                'finish_mode': 'subflow_end',
                'parent_instance_code': parent_code,
                'completed_at': datetime.utcnow().isoformat()
            }
        }

    def _handle_strict(self, mode_name: str) -> Dict[str, Any]:
        """
        嚴格等待模式：等待所有其他節點完成後才結束

        - 仍有 PENDING/RUNNING/WAITING 節點 → 返回 waiting，30 秒後重試
        - 有 FAILED 節點 → 結束流程並標記失敗
        - 全部完成 → 正常結束流程
        """
        from ...models import FwNodeExecutionQueue

        wf_code = self.queue_item.workflow_instance_secure_code

        # 查詢同一工作流中的其他未完成節點（排除自己）
        unfinished = FwNodeExecutionQueue.query.filter(
            FwNodeExecutionQueue.workflow_instance_secure_code == wf_code,
            FwNodeExecutionQueue.id != self.queue_item.id,
            FwNodeExecutionQueue.status.in_(['PENDING', 'RUNNING', 'WAITING'])
        ).all()

        if unfinished:
            node_info = [f"{n.node_name or n.node_id}({n.status})" for n in unfinished]
            self.log_info(f'嚴格等待：仍有 {len(unfinished)} 個未完成節點', {
                'unfinished_nodes': node_info
            })
            return {
                'status': 'waiting',
                'message': f'等待 {len(unfinished)} 個節點完成',
                'data': {
                    'finish_mode': 'strict',
                    'unfinished_count': len(unfinished),
                    'retry_after_seconds': 30
                }
            }

        # 檢查是否有失敗的節點
        failed = FwNodeExecutionQueue.query.filter(
            FwNodeExecutionQueue.workflow_instance_secure_code == wf_code,
            FwNodeExecutionQueue.id != self.queue_item.id,
            FwNodeExecutionQueue.status == 'FAILED'
        ).all()

        if failed:
            node_info = [n.node_name or n.node_id for n in failed]
            self.log_warning(f'嚴格等待：{len(failed)} 個節點失敗', {
                'failed_nodes': node_info
            })
            return {
                'status': 'complete_workflow',
                'message': f'流程結束（{mode_name}，{len(failed)} 個節點失敗）',
                'data': {
                    'finish_mode': 'strict',
                    'has_failures': True,
                    'failed_count': len(failed),
                    'completed_at': datetime.utcnow().isoformat()
                }
            }

        # 所有節點都已完成
        self.log_info('嚴格等待：所有節點已完成，結束流程')
        return {
            'status': 'complete_workflow',
            'message': f'流程已結束（{mode_name}，所有節點完成）',
            'data': {
                'finish_mode': 'strict',
                'has_failures': False,
                'completed_at': datetime.utcnow().isoformat()
            }
        }
