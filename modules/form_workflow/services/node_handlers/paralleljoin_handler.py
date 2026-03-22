"""
FormWorkflow Module - ParallelJoin Handler
並行匯合節點處理器

等待所有入線的來源節點完成後才往下推進。
支援可選的逾時機制：逾時後走指定的逾時出線。
輪詢間隔 10 秒，每次檢查到齊狀態與逾時狀態。
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List

from .base import BaseNodeHandler

logger = logging.getLogger(__name__)

# 輪詢間隔（秒）
POLL_INTERVAL_SECONDS = 10


class ParallelJoinHandler(BaseNodeHandler):
    """並行匯合節點處理器"""

    def handle(self) -> Dict[str, Any]:
        """
        處理並行匯合節點

        每次被 executor 喚醒時：
        1. 從 graph 取得所有入線的 source node
        2. 查 execution queue 確認這些 source node 是否全部 SUCCESS
        3. 到齊 → success
        4. 沒到齊且未逾時 → waiting（scheduled_at +10s）
        5. 沒到齊且已逾時 → 最終確認後走逾時出線
        """
        # 第一次進入時記錄 started_at
        if not self.queue_item.started_at:
            self.queue_item.started_at = datetime.utcnow()
            from app import db
            db.session.commit()

        self.log_info('並行匯合節點檢查', {
            'node_id': self.queue_item.node_id
        })

        # 取得所有入線的 source node IDs
        incoming_source_ids = self._get_incoming_source_node_ids()
        if not incoming_source_ids:
            self.log_error('並行匯合節點沒有入線')
            return {
                'status': 'error',
                'message': '並行匯合節點沒有入線'
            }

        # 檢查到齊狀態
        arrived_count, total_count = self._check_arrivals(incoming_source_ids)
        all_arrived = (arrived_count >= total_count)

        self.log_info(f'入線到達狀態: {arrived_count}/{total_count}', {
            'arrived': arrived_count,
            'total': total_count,
            'all_arrived': all_arrived
        })

        # 到齊：走正常出線
        if all_arrived:
            self.log_info('所有入線已到齊，繼續執行')
            return {
                'status': 'success',
                'message': f'並行匯合完成（{arrived_count}/{total_count} 到齊）',
                'data': {
                    'arrived_count': arrived_count,
                    'total_count': total_count,
                    'timed_out': False
                }
            }

        # 沒到齊：檢查逾時
        enable_timeout = self.get_config_value('enable_timeout', False)
        timeout_minutes = self.get_config_value('timeout_minutes', 0)

        if enable_timeout and timeout_minutes > 0:
            started_at = self.queue_item.started_at
            deadline = started_at + timedelta(minutes=timeout_minutes)
            now = datetime.utcnow()

            if now >= deadline:
                # 逾時：最終確認一次（避免時間差）
                arrived_count, total_count = self._check_arrivals(incoming_source_ids)
                if arrived_count >= total_count:
                    self.log_info('逾時檢查時發現已到齊，走正常出線')
                    return {
                        'status': 'success',
                        'message': f'並行匯合完成（{arrived_count}/{total_count} 到齊）',
                        'data': {
                            'arrived_count': arrived_count,
                            'total_count': total_count,
                            'timed_out': False
                        }
                    }

                # 確定逾時，走逾時出線
                timeout_edge_id = self.get_config_value('timeout_edge_id', '')
                if not timeout_edge_id:
                    self.log_error('逾時但未設定逾時出線 (timeout_edge_id)')
                    return {
                        'status': 'error',
                        'message': '並行匯合逾時，但未設定逾時出線'
                    }

                self.log_info(f'並行匯合逾時，走逾時出線: {timeout_edge_id}', {
                    'arrived_count': arrived_count,
                    'total_count': total_count,
                    'timeout_minutes': timeout_minutes,
                    'timeout_edge_id': timeout_edge_id
                })

                return {
                    'status': 'success',
                    'message': f'並行匯合逾時（{arrived_count}/{total_count}），走逾時路徑',
                    'data': {
                        'arrived_count': arrived_count,
                        'total_count': total_count,
                        'timed_out': True,
                        'selected_edge': timeout_edge_id
                    }
                }

        # 沒到齊且沒逾時：設定下次輪詢時間
        from app import db
        next_check = datetime.utcnow() + timedelta(seconds=POLL_INTERVAL_SECONDS)
        self.queue_item.scheduled_at = next_check
        db.session.commit()

        remaining_info = ''
        if enable_timeout and timeout_minutes > 0:
            started_at = self.queue_item.started_at
            deadline = started_at + timedelta(minutes=timeout_minutes)
            remaining_seconds = (deadline - datetime.utcnow()).total_seconds()
            remaining_info = f'，逾時倒數 {remaining_seconds:.0f} 秒'

        self.log_info(
            f'等待入線到齊（{arrived_count}/{total_count}）{remaining_info}，'
            f'{POLL_INTERVAL_SECONDS} 秒後重新檢查'
        )

        return {
            'status': 'waiting',
            'message': f'等待入線到齊（{arrived_count}/{total_count}）{remaining_info}',
            'data': {
                'arrived_count': arrived_count,
                'total_count': total_count,
                'next_check': next_check.isoformat()
            }
        }

    def _get_incoming_source_node_ids(self) -> List[str]:
        """
        從 graph snapshot 取得所有入線的 source node ID

        與 FormAdapter 的 _get_available_paths 對稱：
        它找 source == current_node_id（出線），
        這裡找 target == current_node_id（入線）。
        """
        if not self.workflow_instance:
            return []

        from ..workflow_engine import WorkflowEngine
        graph = WorkflowEngine.get_effective_graph(self.workflow_instance)
        if not graph:
            return []

        edges = graph.get('edges', [])
        current_node_id = self.queue_item.node_id
        source_ids = []

        for edge in edges:
            edge_data = edge.get('data', edge)
            if edge_data.get('target') == current_node_id:
                source_id = edge_data.get('source')
                if source_id and source_id not in source_ids:
                    source_ids.append(source_id)

        return source_ids

    def _check_arrivals(self, source_node_ids: List[str]) -> tuple:
        """
        檢查入線來源節點的到達狀態

        Args:
            source_node_ids: 入線來源節點 ID 列表

        Returns:
            (arrived_count, total_count)
        """
        from ...models import FwNodeExecutionQueue

        wf_code = self.queue_item.workflow_instance_secure_code
        total_count = len(source_node_ids)
        arrived_count = 0

        for source_id in source_node_ids:
            exists = FwNodeExecutionQueue.query.filter(
                FwNodeExecutionQueue.workflow_instance_secure_code == wf_code,
                FwNodeExecutionQueue.node_id == source_id,
                FwNodeExecutionQueue.status == 'SUCCESS'
            ).first()

            if exists:
                arrived_count += 1

        return arrived_count, total_count
