"""
FormWorkflow Module - Abandon Handler
中止節點處理器

固定使用 cancel 模式，但與 End 有一處不可替代的差異：

- 結束流程並主動取消所有未完成節點
- **回傳 `data.workflow_status='CANCELLED'`，讓流程與表單被記成「已中止」**。
  End 的三種 finish_mode 都會落到 COMPLETED，`complete_workflow()` 再把表單記成
  APPROVED——也就是「被中止的申請單顯示已核准」，而且會以那個終態 upsert 進企業
  獨立資料庫（SQL Sync 不看狀態、無回收路徑）。Abandon 是唯一避開這件事的節點。
- 子流程中止時，同樣喚醒父流程的 SubFlow 節點並推進父流程

2026-08-31 之前本節點與 `End(finish_mode='cancel')` 完全等價（原始設計動機是
「舊版只允許一個 End，支線各拉一條線到 End 太亂」，該理由在允許多個 End 之後已消失）。
上面那條終態差異就是它現在的存在理由，詳見 `dev-notes/ABANDON_SPEC.md`。
"""
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional
from .base import BaseNodeHandler

logger = logging.getLogger(__name__)

# wait_seconds 上限保護（秒）。node_config 是自由 JSON，可被 API 直接 PUT 改，
# 沒有後端驗證時 time.sleep() 會無上限阻塞該節點的 OS 子行程。
# 300 秒與設計器面板 input[max] 一致（wf-accordion-flow.js::renderAbandonPanel）。
MAX_WAIT_SECONDS = 300


class AbandonHandler(BaseNodeHandler):
    """中止節點處理器（固定 cancel 模式的簡化 End）"""

    def _clamp_wait_seconds(self, raw) -> float:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return 1
        if value < 0:
            return 0
        if value > MAX_WAIT_SECONDS:
            self.log_warning(
                f'wait_seconds={value} 超過上限 {MAX_WAIT_SECONDS}，已夾限')
            return MAX_WAIT_SECONDS
        return value

    def handle(self) -> Dict[str, Any]:
        self.report_running()

        # 判斷是否為子流程
        from ...models import FwWorkflowInstance
        workflow_instance = FwWorkflowInstance.query.filter_by(
            secure_code=self.queue_item.workflow_instance_secure_code,
            is_deleted=False
        ).first()

        if workflow_instance and workflow_instance.parent_instance_code:
            return self._handle_subflow_abandon(workflow_instance)

        return self._handle_main_flow_abandon()

    def _handle_main_flow_abandon(self) -> Dict[str, Any]:
        """主流程中止"""
        wait_seconds = self._clamp_wait_seconds(self.node_config.get('wait_seconds', 1))

        self.log_info('中止節點啟動', {
            'workflow_instance': self.queue_item.workflow_instance_secure_code,
            'node_id': self.queue_item.node_id,
            'wait_seconds': wait_seconds
        })

        if wait_seconds > 0:
            self.log_info(f'等待 {wait_seconds} 秒後中止流程')
            time.sleep(wait_seconds)

        self.log_info('流程中止（cancel 模式）')
        return {
            'status': 'complete_workflow',
            'message': '流程已中止',
            'data': {
                'finish_mode': 'cancel',
                'workflow_status': 'CANCELLED',
                'completed_at': datetime.utcnow().isoformat()
            }
        }

    def _handle_subflow_abandon(self, workflow_instance) -> Dict[str, Any]:
        """子流程中止：喚醒父流程 SubFlow 節點並推進"""
        from app import db

        parent_code = workflow_instance.parent_instance_code
        child_code = workflow_instance.secure_code

        self.log_info('子流程中止節點啟動', {
            'child_instance': child_code,
            'parent_instance': parent_code,
            'depth': workflow_instance.workflow_depth
        })

        wait_seconds = self._clamp_wait_seconds(self.node_config.get('wait_seconds', 1))
        if wait_seconds > 0:
            time.sleep(wait_seconds)

        try:
            parent_node_id = self._find_parent_node_id(child_code)
            if not parent_node_id:
                self.log_warning('找不到父流程 SubFlow 節點 ID，子流程將中止但父流程可能卡住')
                return self._abandon_result(parent_code)

            self._complete_parent_subflow_node(parent_code, parent_node_id, child_code)
            self._trigger_parent_next_nodes(parent_code, parent_node_id)

            self.log_info('子流程已中止，已喚醒父流程', {
                'parent_node_id': parent_node_id,
                'parent_instance': parent_code
            })
        except Exception as e:
            logger.error(f'子流程中止喚醒父流程失敗: {e}', exc_info=True)
            self.log_error(f'喚醒父流程失敗: {str(e)}')

        return self._abandon_result(parent_code)

    def _find_parent_node_id(self, child_instance_code: str) -> Optional[str]:
        """從子流程的 START queue item 取得 parent_node_id"""
        from ...models import FwNodeExecutionQueue

        start_item = FwNodeExecutionQueue.query.filter(
            FwNodeExecutionQueue.workflow_instance_secure_code == child_instance_code,
            FwNodeExecutionQueue.node_type == 'Start',
            FwNodeExecutionQueue.parent_node_id.isnot(None)
        ).first()

        return start_item.parent_node_id if start_item else None

    def _complete_parent_subflow_node(self, parent_instance_code, parent_node_id, child_instance_code):
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
                'message': '子流程已中止',
                'data': {
                    'child_instance_code': child_instance_code,
                    'abandoned': True,
                    'completed_at': datetime.utcnow().isoformat()
                }
            })
            db.session.commit()
            self.log_info(f'父流程 SubFlow 節點已更新為 SUCCESS: {parent_node_id}')
        else:
            self.log_warning(f'找不到父流程 WAITING 狀態的 SubFlow 節點: {parent_node_id}')

    def _trigger_parent_next_nodes(self, parent_instance_code, parent_node_id):
        """推進父流程"""
        from ..workflow_engine import WorkflowEngine

        new_items = WorkflowEngine.advance_workflow(
            parent_instance_code,
            parent_node_id
        )

        if new_items:
            node_names = [item.node_name or item.node_id for item in new_items]
            self.log_info(f'父流程已推進，新節點: {node_names}')
        else:
            self.log_info('父流程推進完成（無新節點）')

    def _abandon_result(self, parent_code: str) -> Dict[str, Any]:
        return {
            'status': 'complete_workflow',
            'message': '子流程已中止',
            'data': {
                'finish_mode': 'cancel',
                'workflow_status': 'CANCELLED',
                'parent_instance_code': parent_code,
                'abandoned': True,
                'completed_at': datetime.utcnow().isoformat()
            }
        }
