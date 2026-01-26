"""
FormWorkflow Module - Workflow Executor
工作流執行器

負責輪詢待處理的節點，並以 subprocess 啟動獨立程序執行。
適配 BeakPlatform 模組化架構。
"""
import os
import subprocess
import sys
import threading
import time
import logging
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import and_, or_

from app import db

logger = logging.getLogger(__name__)

# PENDING 節點輪詢間隔（秒）
PENDING_POLL_INTERVAL_SECONDS = 120

# 模組根目錄
MODULE_ROOT = '/opt/BeakPlatform'
# Backend 目錄（node_runner 需要從這裡執行）
BACKEND_ROOT = '/opt/BeakPlatform/backend'


class WorkflowExecutor:
    """工作流執行器"""

    def __init__(self, poll_interval: int = 5):
        """
        初始化執行器

        Args:
            poll_interval: 輪詢間隔（秒）
        """
        self.poll_interval = poll_interval
        self.running = False
        self.thread = None
        self.app = None
        self.last_pending_poll = None

    def start(self):
        """啟動執行器"""
        if self.running:
            logger.warning('執行器已在運行中')
            return

        self.running = True

        # 取得 Flask app
        from app import create_app
        self.app = create_app()

        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        logger.info(f'工作流執行器已啟動（輪詢間隔: {self.poll_interval} 秒）')

    def stop(self):
        """停止執行器"""
        if not self.running:
            logger.warning('執行器未在運行')
            return

        self.running = False
        if self.thread:
            self.thread.join(timeout=10)
        logger.info('工作流執行器已停止')

    def _run(self):
        """執行器主迴圈"""
        with self.app.app_context():
            while self.running:
                try:
                    # 1. 處理 PENDING 節點
                    self._poll_and_execute()

                    # 2. 定期處理等待中的節點
                    now = datetime.utcnow()
                    if (self.last_pending_poll is None or
                            (now - self.last_pending_poll).total_seconds() >= PENDING_POLL_INTERVAL_SECONDS):
                        self._poll_waiting_nodes()
                        self.last_pending_poll = now

                except Exception as e:
                    logger.error(f'執行器錯誤: {str(e)}', exc_info=True)
                    # 重要：rollback 以清除失敗的交易
                    try:
                        db.session.rollback()
                    except Exception:
                        pass

                time.sleep(self.poll_interval)

    def _poll_and_execute(self):
        """輪詢並執行待處理的節點"""
        from ..models import FwNodeExecutionQueue, FwWorkflowInstance

        # 查詢 PENDING 狀態的節點
        pending_nodes = FwNodeExecutionQueue.query.filter(
            and_(
                FwNodeExecutionQueue.status == 'PENDING',
                or_(
                    FwNodeExecutionQueue.scheduled_at.is_(None),
                    FwNodeExecutionQueue.scheduled_at <= datetime.utcnow()
                )
            )
        ).order_by(
            FwNodeExecutionQueue.scheduled_at.asc()
        ).limit(10).all()

        if not pending_nodes:
            return

        logger.info(f'發現 {len(pending_nodes)} 個待處理節點')

        for queue_item in pending_nodes:
            try:
                # 檢查流程狀態
                workflow_instance = FwWorkflowInstance.query.filter_by(
                    secure_code=queue_item.workflow_instance_secure_code
                ).first()

                if not workflow_instance:
                    logger.warning(f'流程實例不存在，跳過節點: {queue_item.node_id}')
                    queue_item.status = 'FAILED'
                    queue_item.error_message = '流程實例不存在'
                    db.session.commit()
                    continue

                if workflow_instance.status in ('COMPLETED', 'CANCELLED', 'ERROR'):
                    logger.warning(f'流程已結束，跳過節點: {queue_item.node_id}')
                    queue_item.cancel()
                    db.session.commit()
                    continue

                # 啟動節點執行
                self._launch_node_process(queue_item)

            except Exception as e:
                logger.error(f'啟動節點失敗 {queue_item.secure_code}: {str(e)}', exc_info=True)
                db.session.rollback()

    def _launch_node_process(self, queue_item):
        """
        啟動節點執行程序

        Args:
            queue_item: 節點佇列項目
        """
        from ..models import FwNodeExecutionQueue

        logger.info(f'啟動節點: {queue_item.node_type} ({queue_item.node_id})')

        # 更新狀態為 RUNNING
        queue_item.start()
        db.session.commit()

        # 啟動 subprocess 執行 node_runner
        # 需要設定 PYTHONPATH 以便找到 app 模組
        env = os.environ.copy()
        env['PYTHONPATH'] = f"{BACKEND_ROOT}:{MODULE_ROOT}:{env.get('PYTHONPATH', '')}"

        cmd = [
            sys.executable,
            '-m', 'modules.form_workflow.services.node_runner',
            '--queue-item-code', queue_item.secure_code
        ]

        logger.info(f'啟動 subprocess: {" ".join(cmd)}')

        try:
            # 使用 DEVNULL 避免 PIPE 緩衝區滿造成阻塞
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=MODULE_ROOT,
                env=env,
                start_new_session=True  # 讓子進程獨立運行
            )

            logger.info(f'節點程序已啟動: queue_code={queue_item.secure_code}, PID={process.pid}')

            # 更新 process_id
            queue_item.process_id = process.pid
            db.session.commit()

        except Exception as e:
            logger.error(f'啟動 subprocess 失敗: {str(e)}')
            queue_item.fail(str(e))
            db.session.commit()

    def _poll_waiting_nodes(self):
        """輪詢等待中的節點"""
        from ..models import FwNodeExecutionQueue

        waiting_nodes = FwNodeExecutionQueue.query.filter(
            FwNodeExecutionQueue.status == 'WAITING',
            or_(
                FwNodeExecutionQueue.scheduled_at.is_(None),
                FwNodeExecutionQueue.scheduled_at <= datetime.utcnow()
            )
        ).limit(10).all()

        if not waiting_nodes:
            return

        logger.info(f'發現 {len(waiting_nodes)} 個等待中節點')

        for queue_item in waiting_nodes:
            try:
                # 重新設為 PENDING 以便重新執行
                queue_item.status = 'PENDING'
                queue_item.scheduled_at = datetime.utcnow()
                db.session.commit()

            except Exception as e:
                logger.error(f'喚醒節點失敗 {queue_item.secure_code}: {str(e)}')
                db.session.rollback()


# 全域執行器實例
_executor_instance: Optional[WorkflowExecutor] = None


def get_executor() -> WorkflowExecutor:
    """取得全域執行器實例"""
    global _executor_instance
    if _executor_instance is None:
        _executor_instance = WorkflowExecutor()
    return _executor_instance


def start_executor():
    """啟動全域執行器"""
    executor = get_executor()
    executor.start()


def stop_executor():
    """停止全域執行器"""
    executor = get_executor()
    executor.stop()
