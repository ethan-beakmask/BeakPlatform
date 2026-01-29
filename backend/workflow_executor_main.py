#!/usr/bin/env python3
"""
BeakPlatform - 工作流執行器啟動腳本

此腳本啟動背景輪詢器，負責處理待執行的工作流節點。

用法：
    python workflow_executor_main.py
    或透過 systemd: sudo systemctl start beakplatform-executor
"""
import sys
import signal
import logging

# 設定 logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """主程式入口"""
    logger.info('啟動 BeakPlatform 工作流執行器...')

    # 加入專案路徑
    sys.path.insert(0, '/opt/BeakPlatform/backend')
    sys.path.insert(0, '/opt/BeakPlatform')

    from modules.form_workflow.services.workflow_executor import (
        start_executor,
        stop_executor,
        get_executor
    )

    # 設定信號處理
    def signal_handler(signum, frame):
        logger.info(f'收到信號 {signum}，停止執行器...')
        stop_executor()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 啟動執行器（不傳 app，讓它自行建立）
    start_executor()

    # 保持主程序運行
    executor = get_executor()
    try:
        while executor.running:
            signal.pause()
    except Exception:
        pass

    logger.info('BeakPlatform 工作流執行器已停止')


if __name__ == '__main__':
    main()
