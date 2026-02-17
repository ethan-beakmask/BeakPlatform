#!/usr/bin/env python3
"""
SQL Sync Worker — 背景同步服務啟動腳本

將 fw_sync_queue 中的待處理項目 UPSERT 到企業專屬資料庫。

啟動:
    cd /opt/BeakPlatform
    source venv/bin/activate
    set -a && source .env && set +a
    python scripts/sync_worker.py

systemd:
    systemctl start beakplatform-sync-worker
"""
import sys
import os
import logging

# 設定路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

# 設定 logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger('sync_worker')


def main():
    from app import create_app

    app = create_app()

    with app.app_context():
        from modules.form_workflow.services.sql_sync.worker import SyncWorker
        worker = SyncWorker(app)
        logger.info('=== SQL Sync Worker 啟動 ===')
        worker.start()
        logger.info('=== SQL Sync Worker 結束 ===')


if __name__ == '__main__':
    main()
