"""
BeakMask URL Access Control
URL 層級存取控制

[標準 URL-01] URL 層級存取控制
1. 不能透過 URL 直接存取未授權頁面
2. URL 參數不可被猜測利用
3. 使用 secure_code 取代自增 ID

安全機制：
1. 全域認證攔截 (auth_interceptor.py)
2. 頁面角色守衛 (page_role_guard.py)
3. 路由權限 decorator (decorators.py)
4. ResourceGateway 租戶過濾 (resource_gateway.py)

本模組僅保留 after_request 存取稽核日誌。
"""
import logging
from flask import request
from flask_login import current_user

logger = logging.getLogger(__name__)


def register_url_access_logger(app):
    """
    註冊 URL 存取日誌記錄器。

    在 after_request 記錄所有存取，用於安全審計。
    """

    @app.after_request
    def log_request(response):
        """記錄請求結果"""
        # 只記錄非靜態資源
        if not request.path.startswith('/static'):
            user_id = getattr(current_user, 'id', None) if current_user else None

            # 記錄失敗的存取嘗試
            if response.status_code in (401, 403, 404):
                logger.warning(
                    f"Access denied: {request.method} {request.path} "
                    f"status={response.status_code} "
                    f"user_id={user_id} ip={request.remote_addr}"
                )

        return response
