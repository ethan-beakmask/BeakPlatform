"""
FormWorkflow Module - Start Handler
開始節點處理器

流程的起始點，執行初始化邏輯。
"""
from datetime import datetime
from typing import Dict, Any
from .base import BaseNodeHandler


class StartHandler(BaseNodeHandler):
    """開始節點處理器"""

    def handle(self) -> Dict[str, Any]:
        """
        處理開始節點

        開始節點的職責：
        1. 記錄流程開始
        2. 執行初始化邏輯（如果有配置）
        3. 立即完成並推進到下一個節點

        Returns:
            執行結果
        """
        self.report_running()

        self.log_info('開始節點啟動', {
            'workflow_instance': self.queue_item.workflow_instance_secure_code,
            'node_id': self.queue_item.node_id
        })

        # 取得配置
        init_config = self.get_config_value('init', {})

        # 執行初始化邏輯
        if init_config:
            self._execute_init(init_config)

        self.log_info('開始節點執行完成')

        return {
            'status': 'success',
            'message': '流程已開始',
            'data': {
                'started_at': datetime.utcnow().isoformat()
            }
        }

    def _execute_init(self, init_config: dict):
        """
        執行初始化配置

        Args:
            init_config: 初始化配置
        """
        # 設定初始變數
        init_vars = init_config.get('variables', {})
        for var_name, var_value in init_vars.items():
            self.log_info(f'設定初始變數: {var_name} = {var_value}')
            # TODO: 實作變數服務
