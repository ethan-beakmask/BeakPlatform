"""
FormWorkflow Module - Delay Handler
延遲節點處理器

在指定時間後繼續執行流程。
"""
from datetime import datetime, timedelta
from typing import Dict, Any
from .base import BaseNodeHandler


class DelayHandler(BaseNodeHandler):
    """延遲節點處理器"""

    def handle(self) -> Dict[str, Any]:
        """
        處理延遲節點

        延遲節點的職責：
        1. 檢查是否已過延遲時間
        2. 若未到時間，設為 WAITING 狀態
        3. 若已到時間，完成並推進

        Returns:
            執行結果
        """
        # 注意：延遲節點不呼叫 report_running()，因為可能被多次呼叫
        # 只在第一次執行時記錄 started_at
        if not self.queue_item.started_at:
            self.queue_item.started_at = datetime.utcnow()
            from app import db
            db.session.commit()

        self.log_info('延遲節點啟動', {
            'node_id': self.queue_item.node_id
        })

        # 取得延遲配置
        delay_seconds = self.get_config_value('delay_seconds', 0)
        delay_minutes = self.get_config_value('delay_minutes', 0)
        delay_hours = self.get_config_value('delay_hours', 0)
        delay_until = self.get_config_value('delay_until')  # ISO 格式時間字串

        # 計算總延遲秒數
        total_delay_seconds = delay_seconds + (delay_minutes * 60) + (delay_hours * 3600)

        # 計算目標時間
        if delay_until:
            try:
                target_time = datetime.fromisoformat(delay_until.replace('Z', '+00:00'))
            except ValueError:
                self.log_error(f'無效的延遲時間格式: {delay_until}')
                return {
                    'status': 'error',
                    'message': f'無效的延遲時間格式: {delay_until}'
                }
        elif total_delay_seconds > 0:
            # 使用節點首次執行時間計算
            start_time = self.queue_item.started_at or datetime.utcnow()
            target_time = start_time + timedelta(seconds=total_delay_seconds)
        else:
            # 無延遲設定，直接完成
            self.log_info('無延遲設定，直接完成')
            return {
                'status': 'success',
                'message': '延遲節點完成（無延遲）',
                'data': {}
            }

        # 檢查是否已過目標時間
        now = datetime.utcnow()
        if now >= target_time:
            self.log_info('延遲時間已到，繼續執行', {
                'target_time': target_time.isoformat(),
                'now': now.isoformat()
            })
            return {
                'status': 'success',
                'message': '延遲時間已到',
                'data': {
                    'target_time': target_time.isoformat(),
                    'completed_at': now.isoformat()
                }
            }
        else:
            # 設定下次檢查時間
            remaining_seconds = (target_time - now).total_seconds()
            self.log_info(f'延遲中，剩餘 {remaining_seconds:.0f} 秒', {
                'target_time': target_time.isoformat(),
                'remaining_seconds': remaining_seconds
            })

            # 更新 scheduled_at 為目標時間
            from app import db
            self.queue_item.scheduled_at = target_time
            db.session.commit()

            return {
                'status': 'waiting',
                'message': f'延遲中，剩餘 {remaining_seconds:.0f} 秒',
                'data': {
                    'target_time': target_time.isoformat(),
                    'remaining_seconds': remaining_seconds
                }
            }
