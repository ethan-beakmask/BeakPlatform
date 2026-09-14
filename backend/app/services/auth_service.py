"""
BeakMask Authentication Service
認證相關業務邏輯
"""
import logging
from datetime import datetime
from typing import Optional

from ..models.user import User

logger = logging.getLogger(__name__)


class AuthService:
    """認證服務"""

    # authenticate() 已移除 — 登入邏輯統一由 api/auth.py _do_login() 處理
    # 該方法曾以 email 查詢且未過濾 org_secure_code，與多租戶架構不一致

    @staticmethod
    def request_password_reset(email: str) -> bool:
        """
        請求密碼重設。

        Args:
            email: 用戶 email

        Returns:
            True (always, to prevent email enumeration)
        """
        user = User.query.filter_by(email=email.lower()).first()

        if user and user.is_active:
            # TODO: Generate reset token and send email
            logger.info(f"Password reset requested for: {email}")
            pass

        return True

    @staticmethod
    def reset_password(token: str, new_password: str) -> bool:
        """
        使用 token 重設密碼。

        Args:
            token: 重設 token
            new_password: 新密碼

        Returns:
            True if successful, False otherwise
        """
        # TODO: Validate token and reset password
        logger.info("Password reset attempted")
        return False

    @staticmethod
    def validate_password_strength(password: str) -> tuple[bool, str]:
        """
        驗證密碼強度。

        Args:
            password: 密碼

        Returns:
            (is_valid, error_message)
        """
        if len(password) < 8:
            return False, "Password must be at least 8 characters"

        if not any(c.isupper() for c in password):
            return False, "Password must contain at least one uppercase letter"

        if not any(c.islower() for c in password):
            return False, "Password must contain at least one lowercase letter"

        if not any(c.isdigit() for c in password):
            return False, "Password must contain at least one digit"

        return True, ""
