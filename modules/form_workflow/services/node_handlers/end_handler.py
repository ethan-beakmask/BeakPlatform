"""
FormWorkflow Module - End Handler
結束節點處理器

三種結束模式：
- detach (分離執行): 直接結束流程，不處理其他未完成節點（由 executor 自然清理）
- cancel (取消/終止): 結束流程並主動取消所有未完成節點
- strict (嚴格等待): 等待所有其他節點完成後才結束流程；若有節點失敗則流程標記失敗
"""
import time
from datetime import datetime
from typing import Dict, Any
from .base import BaseNodeHandler


class EndHandler(BaseNodeHandler):
    """結束節點處理器"""

    FINISH_MODE_NAMES = {
        'detach': '分離執行',
        'cancel': '取消/終止',
        'strict': '嚴格等待',
    }

    def handle(self) -> Dict[str, Any]:
        """處理結束節點"""
        self.report_running()

        # 讀取配置（前端存放在 config 頂層）
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
