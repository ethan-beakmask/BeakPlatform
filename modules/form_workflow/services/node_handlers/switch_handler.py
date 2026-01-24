"""
FormWorkflow Module - Switch Handler
無條件分支節點處理器

流程到此節點後，所有出線的目標節點都會並行執行。
"""
from typing import Dict, Any
from .base import BaseNodeHandler


class SwitchHandler(BaseNodeHandler):
    """
    無條件分支處理器

    功能：流程到達此節點後，所有出線都會並行執行
    不需要任何條件配置，純粹用於流程分支
    """

    def validate(self) -> bool:
        """驗證節點配置（無需配置）"""
        return True

    def handle(self) -> Dict[str, Any]:
        """
        處理 Switch 節點

        邏輯：直接返回 success，讓 node_runner 將所有出線的節點都加入佇列
        """
        self.log_info('無條件分支節點執行', {
            'node_id': self.queue_item.node_id,
            'message': '所有出線將並行執行'
        })

        return {
            'status': 'success',
            'message': '無條件分支完成，所有出線並行執行',
            'data': {
                'parallel_execution': True
            }
        }
