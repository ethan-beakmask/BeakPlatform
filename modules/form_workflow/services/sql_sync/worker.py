"""
SQL Sync — Background Worker

獨立背景程序，輪詢 fw_sync_queue 處理同步任務。
使用 sync 低權限帳號 UPSERT 到企業專屬資料庫。

啟動方式:
    python scripts/sync_worker.py
"""
import time
import signal
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Worker 設定
POLL_INTERVAL = 2        # 秒，無任務時等待
BATCH_SIZE = 50          # 每次最多處理筆數
CLEANUP_INTERVAL = 60    # 秒，清理閒置連線


class SyncWorker:
    """SQL Sync 背景工作者"""

    def __init__(self, app):
        self.app = app
        self.running = False
        self._last_cleanup = time.time()

    def start(self):
        """啟動 Worker 主迴圈"""
        self.running = True
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        logger.info('SyncWorker: 啟動')

        with self.app.app_context():
            while self.running:
                try:
                    processed = self._process_batch()
                    if processed == 0:
                        time.sleep(POLL_INTERVAL)

                    # 定期清理閒置連線
                    now = time.time()
                    if now - self._last_cleanup > CLEANUP_INTERVAL:
                        from .pool import cleanup_idle_conns
                        cleanup_idle_conns()
                        self._last_cleanup = now

                except Exception as e:
                    logger.error(f'SyncWorker: 主迴圈異常: {e}', exc_info=True)
                    time.sleep(POLL_INTERVAL * 2)

        # 清理
        from .pool import close_all
        close_all()
        logger.info('SyncWorker: 已停止')

    def stop(self):
        """停止 Worker"""
        self.running = False

    def _handle_signal(self, signum, frame):
        logger.info(f'SyncWorker: 收到信號 {signum}，準備停止')
        self.stop()

    def _process_batch(self):
        """
        處理一批佇列項目

        Returns:
            int: 處理筆數
        """
        from app import db
        from ...models.sync_queue import FwSyncQueue
        from .sync_service import execute_sync

        # 撈取待處理項目
        items = FwSyncQueue.query.filter_by(
            status='pending',
            is_deleted=False,
        ).order_by(
            FwSyncQueue.queued_at.asc()
        ).limit(BATCH_SIZE).all()

        if not items:
            return 0

        processed = 0
        for item in items:
            if not self.running:
                break

            try:
                item.mark_processing()
                db.session.commit()

                execute_sync(item)

                item.mark_completed()
                db.session.commit()
                processed += 1

            except Exception as e:
                db.session.rollback()
                logger.warning(
                    f'SyncWorker: 同步失敗 (queue_id={item.id}, '
                    f'instance={item.form_instance_secure_code}): {e}'
                )
                try:
                    item.mark_failed(str(e))
                    db.session.commit()
                except Exception:
                    db.session.rollback()

        if processed > 0:
            logger.info(f'SyncWorker: 已處理 {processed}/{len(items)} 筆')

        return processed
