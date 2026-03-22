"""
FormWorkflow Module - ParallelFork Handler
並行分支節點處理器

到達即往所有出線同時推進，本身不做任何邏輯。
"""
from typing import Dict, Any
from .base import BaseNodeHandler


class ParallelForkHandler(BaseNodeHandler):
    """並行分支節點處理器"""

    def handle(self) -> Dict[str, Any]:
        """
        處理並行分支節點

        直接返回 success，engine 的 advance_workflow 會自動
        將所有出線的目標節點加入執行佇列。
        """
        self.report_running()

        self.log_info('並行分支節點啟動', {
            'node_id': self.queue_item.node_id
        })

        return {
            'status': 'success',
            'message': '並行分支已展開',
            'data': {}
        }
