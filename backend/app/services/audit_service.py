"""
BeakMask Audit Service
稽核記錄服務 - 集中管理操作稽核日誌
"""
import logging
from typing import Optional

from flask import request
from flask_login import current_user

from ..security.client_ip import get_client_ip
from ..models.audit_log import AuditLog
from ..models.system_setting import SystemSetting
from .. import db

logger = logging.getLogger(__name__)


def get_real_ip() -> Optional[str]:
    """取得真實用戶 IP。

    NET-01：實作已收斂到 security/client_ip.py。舊版直接讀 X-Forwarded-For
    的第一段，任何直連者自帶該 header 即可偽造稽核日誌裡的來源 IP。
    """
    return get_client_ip()

# 稽核等級
AUDIT_LEVEL_MINIMAL = 'MINIMAL'    # 僅登入/登出 + 失敗嘗試
AUDIT_LEVEL_STANDARD = 'STANDARD'  # 登入/登出 + 所有寫入操作
AUDIT_LEVEL_VERBOSE = 'VERBOSE'    # 全部請求 (含 GET)

VALID_AUDIT_LEVELS = {AUDIT_LEVEL_MINIMAL, AUDIT_LEVEL_STANDARD, AUDIT_LEVEL_VERBOSE}

# 寫入操作的 HTTP methods
WRITE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}


class AuditService:
    """稽核記錄服務"""

    _cached_level = None
    _cache_miss_count = 0

    @classmethod
    def get_audit_level(cls) -> str:
        """
        取得當前稽核等級。
        帶簡易快取，每 100 次請求重新讀取 DB。
        """
        cls._cache_miss_count += 1
        if cls._cached_level is None or cls._cache_miss_count >= 100:
            cls._cached_level = SystemSetting.get('audit_level', AUDIT_LEVEL_STANDARD)
            cls._cache_miss_count = 0
        return cls._cached_level

    @classmethod
    def set_audit_level(cls, level: str) -> bool:
        """設定稽核等級"""
        level = level.upper()
        if level not in VALID_AUDIT_LEVELS:
            return False
        SystemSetting.set(
            key='audit_level',
            value=level,
            value_type='string',
            category='security',
            description='稽核記錄等級: MINIMAL(僅登入登出), STANDARD(登入登出+寫入操作), VERBOSE(全部請求)'
        )
        cls._cached_level = level
        return True

    @classmethod
    def invalidate_cache(cls):
        """強制清除快取"""
        cls._cached_level = None
        cls._cache_miss_count = 0

    @classmethod
    def log(
        cls,
        action: str,
        resource_type: str,
        org_secure_code: Optional[str] = None,
        user_secure_code: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[str] = None,
        request_method: Optional[str] = None,
        request_path: Optional[str] = None,
        status_code: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        """
        寫入一筆稽核記錄。

        Args:
            action: 操作類型 (LOGIN, LOGOUT, CREATE, UPDATE, DELETE, etc.)
            resource_type: 資源類型 (AUTH, USER, ROLE, etc.)
            org_secure_code: 企業 secure_code (NULL 表示無法對應企業)
            user_secure_code: 操作者 secure_code
            resource_id: 資源識別碼
            details: 詳細描述
            request_method: HTTP method
            request_path: URL path
            status_code: HTTP status code
            ip_address: 來源 IP
            user_agent: 瀏覽器 User-Agent
        """
        try:
            log_entry = AuditLog(
                org_secure_code=org_secure_code,
                user_secure_code=user_secure_code,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details,
                request_method=request_method,
                request_path=request_path,
                status_code=status_code,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            db.session.add(log_entry)
            # 不在此處 commit，讓呼叫端決定 commit 時機
            # 對 after_request hook，會在寫入後獨立 commit
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")

    @classmethod
    def log_auth_event(
        cls,
        action: str,
        org_secure_code: Optional[str] = None,
        user_secure_code: Optional[str] = None,
        details: Optional[str] = None,
        status_code: Optional[int] = None,
    ):
        """
        記錄認證事件 (登入/登出/失敗)。
        自動擷取 request 的真實 IP 和 User-Agent。
        所有稽核等級都會記錄。
        """
        cls.log(
            action=action,
            resource_type='AUTH',
            org_secure_code=org_secure_code,
            user_secure_code=user_secure_code,
            details=details,
            request_method=request.method if request else None,
            request_path=request.path if request else None,
            status_code=status_code,
            ip_address=get_real_ip(),
            user_agent=request.headers.get('User-Agent', '')[:500] if request else None,
        )
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to commit auth audit log: {e}")

    @classmethod
    def log_request(
        cls,
        response_status_code: int,
        org_secure_code: str,
        user_secure_code: Optional[str] = None,
    ):
        """
        記錄 HTTP 請求 (由 after_request hook 呼叫)。
        根據 audit_level 決定是否記錄。
        """
        method = request.method
        path = request.path
        level = cls.get_audit_level()

        # MINIMAL: 不記錄一般請求
        if level == AUDIT_LEVEL_MINIMAL:
            return

        # STANDARD: 只記錄寫入操作
        if level == AUDIT_LEVEL_STANDARD and method not in WRITE_METHODS:
            return

        # VERBOSE: 記錄所有請求 (已通過前面的 skip 邏輯)

        # 從 path 推導 resource_type 和 action
        resource_type = cls._extract_resource_type(path)
        action = cls._method_to_action(method)

        cls.log(
            action=action,
            resource_type=resource_type,
            org_secure_code=org_secure_code,
            user_secure_code=user_secure_code,
            request_method=method,
            request_path=path,
            status_code=response_status_code,
            ip_address=get_real_ip(),
            user_agent=request.headers.get('User-Agent', '')[:500],
        )

    @staticmethod
    def _method_to_action(method: str) -> str:
        """HTTP method 轉換為操作類型"""
        mapping = {
            'POST': 'CREATE',
            'PUT': 'UPDATE',
            'PATCH': 'UPDATE',
            'DELETE': 'DELETE',
            'GET': 'READ',
        }
        return mapping.get(method, method)

    @staticmethod
    def _extract_resource_type(path: str) -> str:
        """
        從 URL path 提取資源類型。
        例如 /api/users/xxx → USER
             /api/roles/xxx → ROLE
             /forms/templates/xxx → FORM_TEMPLATE
        """
        # 移除前導斜線，分割路徑
        parts = [p for p in path.strip('/').split('/') if p]

        if not parts:
            return 'UNKNOWN'

        # 跳過 api 前綴
        if parts[0] == 'api' and len(parts) > 1:
            parts = parts[1:]

        # 取第一段有意義的路徑作為資源類型
        resource = parts[0] if parts else 'UNKNOWN'

        # 常見路徑映射
        mapping = {
            'users': 'USER',
            'roles': 'ROLE',
            'departments': 'DEPARTMENT',
            'groups': 'GROUP',
            'menu': 'MENU',
            'modules': 'MODULE',
            'organizations': 'ORGANIZATION',
            'contracts': 'CONTRACT',
            'forms': 'FORM',
            'data-crud': 'DATA_CRUD',
            'units': 'ORG_UNIT',
            'job-levels': 'JOB_LEVEL',
            'job-families': 'JOB_FAMILY',
            'job-titles': 'JOB_TITLE',
            'external-users': 'EXTERNAL_USER',
            'auth': 'AUTH',
            'admin': 'ADMIN',
            'personal-settings': 'PERSONAL_SETTINGS',
            'org-admins': 'ORG_ADMIN',
            'org-databases': 'ORG_DATABASE',
            'hostconfig': 'HOST_CONFIG',
            'sys-accounts': 'SYS_ACCOUNT',
            'system-settings': 'SYSTEM_SETTINGS',
        }

        return mapping.get(resource, resource.upper().replace('-', '_'))
