"""
FormWorkflow Module - End Handler
結束節點處理器

流程的終點，執行清理和完成邏輯。
"""
from datetime import datetime
from typing import Dict, Any
from .base import BaseNodeHandler


class EndHandler(BaseNodeHandler):
    """結束節點處理器"""

    def handle(self) -> Dict[str, Any]:
        """
        處理結束節點

        結束節點的職責：
        1. 執行清理邏輯（如果有配置）
        2. 標記工作流為完成
        3. 更新相關狀態

        Returns:
            執行結果
        """
        self.report_running()

        self.log_info('結束節點啟動', {
            'workflow_instance': self.queue_item.workflow_instance_secure_code,
            'node_id': self.queue_item.node_id
        })

        # 取得配置
        end_config = self.get_config_value('end', {})
        end_mode = end_config.get('mode', 'normal')
        end_message = end_config.get('message', '流程已完成')

        # 執行清理邏輯
        if end_config.get('cleanup'):
            self._execute_cleanup(end_config['cleanup'])

        self.log_info('結束節點執行完成', {
            'end_mode': end_mode,
            'message': end_message
        })

        # 返回 complete_workflow 狀態，讓 node_runner 完成工作流
        return {
            'status': 'complete_workflow',
            'message': end_message,
            'data': {
                'end_mode': end_mode,
                'completed_at': datetime.utcnow().isoformat()
            }
        }

    def _execute_cleanup(self, cleanup_config: dict):
        """
        執行清理配置

        Args:
            cleanup_config: 清理配置
        """
        self.log_info('執行清理邏輯', cleanup_config)
        # TODO: 實作清理邏輯
