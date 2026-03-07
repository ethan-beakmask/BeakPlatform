"""
BeakMask Audit Logger
稽核日誌 after_request hook

在每個回應後，根據 audit_level 自動記錄操作到 audit_logs 表。
認證事件 (LOGIN/LOGOUT) 在 auth.py 中直接呼叫 AuditService，不經此 hook。
"""
import logging
from flask import Flask, request, g
from flask_login import current_user

logger = logging.getLogger(__name__)

# 不記錄的路徑前綴
SKIP_PREFIXES = (
    '/static/',
    '/favicon.ico',
    '/health',
)

# 認證相關路徑 (在 auth.py 已專門處理，hook 不重複記錄)
AUTH_PATHS = (
    '/auth/login',
    '/auth/logout',
    '/auth/org/',
)


def register_audit_logger(app: Flask) -> None:
    """
    註冊稽核日誌 after_request hook。
    必須在 blueprints 註冊之後呼叫。
    """

    @app.after_request
    def audit_log_request(response):
        """after_request hook: 記錄操作到 audit_logs"""
        path = request.path

        # 跳過靜態資源和健康檢查
        if path.startswith(SKIP_PREFIXES):
            return response

        # 跳過認證路徑 (auth.py 已處理)
        if any(path.startswith(p) for p in AUTH_PATHS):
            return response

        # 必須是已認證用戶才記錄
        if not current_user or not current_user.is_authenticated:
            return response

        # 取得 org_secure_code (FK 約束必須有值)
        org_sc = getattr(g, 'current_org_secure_code', None)
        if not org_sc:
            org_sc = getattr(current_user, 'org_secure_code', None)
        if not org_sc:
            return response

        try:
            from ..services.audit_service import AuditService
            from .. import db

            AuditService.log_request(
                response_status_code=response.status_code,
                org_secure_code=org_sc,
                user_secure_code=current_user.secure_code,
            )
            db.session.commit()
        except Exception as e:
            try:
                from .. import db as _db
                _db.session.rollback()
            except Exception:
                pass
            logger.error(f"Audit log commit failed: {e}")

        return response
