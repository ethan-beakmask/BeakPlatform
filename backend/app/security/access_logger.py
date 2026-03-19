"""
BeakMask Access Logger
HTTP 存取日誌 - 所有請求記錄到檔案

記錄格式類似 Apache Combined Log Format，方便用 GoAccess 等工具分析。
輸出位置: /opt/tmp/BeakPlatform-access.log
"""
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from flask import Flask, request


LOG_PATH = '/opt/tmp/BeakPlatform-access.log'


def register_access_logger(app: Flask) -> None:
    """註冊 HTTP 存取日誌 after_request hook"""

    # 專用 logger，不干擾 app logger
    access_logger = logging.getLogger('beakmask.access')
    access_logger.setLevel(logging.INFO)
    access_logger.propagate = False

    handler = RotatingFileHandler(
        LOG_PATH,
        maxBytes=50 * 1024 * 1024,  # 50MB
        backupCount=5,
        encoding='utf-8'
    )
    handler.setFormatter(logging.Formatter('%(message)s'))
    access_logger.addHandler(handler)

    @app.after_request
    def log_access(response):
        # 跳過靜態資源
        if request.path.startswith(('/static/', '/favicon.ico')):
            return response

        ip = request.headers.get('CF-Connecting-IP',
             request.headers.get('X-Forwarded-For', request.remote_addr))
        if ip and ',' in ip:
            ip = ip.split(',')[0].strip()

        country = request.headers.get('CF-IPCountry', '-')
        user_agent = request.headers.get('User-Agent', '-')
        now = datetime.now().strftime('%d/%b/%Y:%H:%M:%S %z').strip()

        access_logger.info(
            f'{ip} [{country}] [{now}] '
            f'"{request.method} {request.full_path.rstrip("?")} {request.environ.get("SERVER_PROTOCOL", "HTTP/1.1")}" '
            f'{response.status_code} {response.content_length or 0} '
            f'"{request.referrer or "-"}" "{user_agent}"'
        )

        return response
