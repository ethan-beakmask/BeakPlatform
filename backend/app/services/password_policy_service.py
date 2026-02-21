"""
BeakMask Password Policy Service
密碼複雜度政策服務

功能：
1. 密碼複雜度驗證
2. 密碼生成（符合複雜度要求）
3. 密碼歷史檢查
4. 登入失敗鎖定
"""
import re
import secrets
import string
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple, List

import bcrypt

from .. import db
from ..models.user import User
from ..models.password_history import PasswordHistory
from ..models.organization import Organization

logger = logging.getLogger(__name__)


# 預設密碼政策
DEFAULT_PASSWORD_POLICY = {
    'enabled': False,
    'min_length': 12,
    'require_uppercase': True,
    'require_lowercase': True,
    'require_digit': True,
    'require_special': True,
    'history_count': 5,              # 不能重複使用最近 N 次的密碼
    'max_failed_attempts': 5,        # 最大失敗次數
    'lockout_duration_minutes': 15,  # 基礎鎖定時間（分鐘）
    'lockout_multiplier': 2,         # 每次鎖定時間倍數
}


class PasswordPolicyService:
    """密碼政策服務"""

    @staticmethod
    def get_policy(org_secure_code: str) -> Dict[str, Any]:
        """
        取得企業的密碼政策

        Args:
            org_secure_code: 企業 secure_code

        Returns:
            密碼政策設定
        """
        org = Organization.query.filter_by(
            secure_code=org_secure_code,
            is_deleted=False
        ).first()

        if not org:
            return dict(DEFAULT_PASSWORD_POLICY)

        settings = org.get_settings()
        policy = settings.get('password_policy', {})

        # 合併預設值
        result = dict(DEFAULT_PASSWORD_POLICY)
        result.update(policy)
        return result

    @staticmethod
    def set_policy(org_secure_code: str, policy: Dict[str, Any]) -> bool:
        """
        設定企業的密碼政策

        Args:
            org_secure_code: 企業 secure_code
            policy: 密碼政策設定

        Returns:
            是否成功
        """
        org = Organization.query.filter_by(
            secure_code=org_secure_code,
            is_deleted=False
        ).first()

        if not org:
            return False

        org.set_setting('password_policy', policy)
        db.session.commit()
        return True

    @staticmethod
    def validate_password(
        password: str,
        org_secure_code: str,
        user_secure_code: Optional[str] = None,
        check_history: bool = True
    ) -> Tuple[bool, List[str]]:
        """
        驗證密碼是否符合政策

        Args:
            password: 密碼
            org_secure_code: 企業 secure_code
            user_secure_code: 用戶 secure_code（檢查歷史時需要）
            check_history: 是否檢查密碼歷史

        Returns:
            (是否通過, 錯誤訊息列表)
        """
        policy = PasswordPolicyService.get_policy(org_secure_code)
        errors = []

        # 未啟用則只檢查最小長度
        if not policy.get('enabled', False):
            if len(password) < 8:
                errors.append('密碼長度至少 8 個字元')
            return (len(errors) == 0, errors)

        # 長度檢查
        min_length = policy.get('min_length', 12)
        if len(password) < min_length:
            errors.append(f'密碼長度至少 {min_length} 個字元')

        # 大寫字母
        if policy.get('require_uppercase', True):
            if not re.search(r'[A-Z]', password):
                errors.append('密碼必須包含大寫字母')

        # 小寫字母
        if policy.get('require_lowercase', True):
            if not re.search(r'[a-z]', password):
                errors.append('密碼必須包含小寫字母')

        # 數字
        if policy.get('require_digit', True):
            if not re.search(r'\d', password):
                errors.append('密碼必須包含數字')

        # 特殊符號
        if policy.get('require_special', True):
            if not re.search(r'[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?]', password):
                errors.append('密碼必須包含特殊符號')

        # 密碼歷史檢查
        if check_history and user_secure_code:
            history_count = policy.get('history_count', 5)
            if history_count > 0:
                if PasswordPolicyService._check_password_history(
                    password, user_secure_code, history_count
                ):
                    errors.append(f'不能使用最近 {history_count} 次使用過的密碼')

        return (len(errors) == 0, errors)

    @staticmethod
    def _check_password_history(
        password: str,
        user_secure_code: str,
        history_count: int
    ) -> bool:
        """
        檢查密碼是否在歷史記錄中

        Returns:
            True 如果密碼在歷史中（不應使用）
        """
        histories = PasswordHistory.query.filter_by(
            user_secure_code=user_secure_code
        ).order_by(
            PasswordHistory.created_at.desc()
        ).limit(history_count).all()

        raw = password.encode('utf-8')
        if len(raw) > 72:
            return False
        for history in histories:
            if bcrypt.checkpw(raw, history.password_hash.encode('utf-8')):
                return True

        return False

    @staticmethod
    def save_password_history(user_secure_code: str, password_hash: str) -> None:
        """
        儲存密碼歷史

        Args:
            user_secure_code: 用戶 secure_code
            password_hash: bcrypt hash
        """
        history = PasswordHistory(
            user_secure_code=user_secure_code,
            password_hash=password_hash
        )
        db.session.add(history)
        # 不在這裡 commit，讓呼叫者決定

    @staticmethod
    def generate_password(org_secure_code: str, length: int = 16) -> str:
        """
        生成符合政策的密碼

        Args:
            org_secure_code: 企業 secure_code
            length: 密碼長度（預設 16）

        Returns:
            生成的密碼
        """
        policy = PasswordPolicyService.get_policy(org_secure_code)

        # 確保長度足夠
        min_length = max(policy.get('min_length', 12), length)

        # 字元集
        chars = ''
        required = []

        if policy.get('require_lowercase', True) or not policy.get('enabled', False):
            chars += string.ascii_lowercase
            required.append(secrets.choice(string.ascii_lowercase))

        if policy.get('require_uppercase', True) or not policy.get('enabled', False):
            chars += string.ascii_uppercase
            required.append(secrets.choice(string.ascii_uppercase))

        if policy.get('require_digit', True) or not policy.get('enabled', False):
            chars += string.digits
            required.append(secrets.choice(string.digits))

        if policy.get('require_special', True) or not policy.get('enabled', False):
            special = '!@#$%^&*()_+-=[]{}|;:,.<>?'
            chars += special
            required.append(secrets.choice(special))

        # 生成剩餘字元
        remaining_length = min_length - len(required)
        password_chars = required + [secrets.choice(chars) for _ in range(remaining_length)]

        # 打亂順序
        secrets.SystemRandom().shuffle(password_chars)

        return ''.join(password_chars)

    @staticmethod
    def generate_strong_password(length: int = 16) -> str:
        """
        生成高複雜度密碼（用於臨時密碼，不依賴企業設定）

        Args:
            length: 密碼長度

        Returns:
            高複雜度密碼
        """
        lowercase = string.ascii_lowercase
        uppercase = string.ascii_uppercase
        digits = string.digits
        special = '!@#$%^&*()_+-=[]{}|;:,.<>?'

        # 確保每種類型至少一個
        required = [
            secrets.choice(lowercase),
            secrets.choice(uppercase),
            secrets.choice(digits),
            secrets.choice(special),
        ]

        # 生成剩餘字元
        all_chars = lowercase + uppercase + digits + special
        remaining = [secrets.choice(all_chars) for _ in range(length - len(required))]

        # 合併並打亂
        password_chars = required + remaining
        secrets.SystemRandom().shuffle(password_chars)

        return ''.join(password_chars)

    @staticmethod
    def check_account_lock(user: User) -> Tuple[bool, Optional[str]]:
        """
        檢查帳號是否被鎖定

        Args:
            user: 用戶物件

        Returns:
            (是否被鎖定, 錯誤訊息)
        """
        if user.locked_until:
            now = datetime.utcnow()
            if now < user.locked_until:
                remaining = user.locked_until - now
                minutes = int(remaining.total_seconds() / 60) + 1
                return (True, f'帳號已鎖定，請 {minutes} 分鐘後再試')

            # 鎖定已過期，重置
            user.locked_until = None
            user.failed_login_count = 0

        return (False, None)

    @staticmethod
    def record_login_failure(user: User, org_secure_code: str) -> Optional[str]:
        """
        記錄登入失敗

        Args:
            user: 用戶物件
            org_secure_code: 企業 secure_code

        Returns:
            鎖定訊息（如果觸發鎖定）
        """
        policy = PasswordPolicyService.get_policy(org_secure_code)

        if not policy.get('enabled', False):
            return None

        max_attempts = policy.get('max_failed_attempts', 5)
        base_lockout = policy.get('lockout_duration_minutes', 15)
        multiplier = policy.get('lockout_multiplier', 2)

        user.failed_login_count = (user.failed_login_count or 0) + 1
        user.last_failed_login = datetime.utcnow()

        if user.failed_login_count >= max_attempts:
            # 計算鎖定時間（指數增長）
            lockout_times = user.failed_login_count - max_attempts + 1
            lockout_minutes = base_lockout * (multiplier ** (lockout_times - 1))
            lockout_minutes = min(lockout_minutes, 1440)  # 最多 24 小時

            user.locked_until = datetime.utcnow() + timedelta(minutes=lockout_minutes)

            logger.warning(
                f"用戶 {user.username}@{org_secure_code} 登入失敗 {user.failed_login_count} 次，"
                f"鎖定 {lockout_minutes} 分鐘"
            )

            return f'登入失敗次數過多，帳號已鎖定 {int(lockout_minutes)} 分鐘'

        remaining = max_attempts - user.failed_login_count
        if remaining <= 2:
            return f'密碼錯誤，還有 {remaining} 次嘗試機會'

        return None

    @staticmethod
    def record_login_success(user: User) -> None:
        """
        記錄登入成功，重置失敗計數

        Args:
            user: 用戶物件
        """
        user.failed_login_count = 0
        user.locked_until = None
        user.last_failed_login = None

    @staticmethod
    def get_password_requirements_text(org_secure_code: str) -> str:
        """
        取得密碼要求說明文字

        Args:
            org_secure_code: 企業 secure_code

        Returns:
            說明文字
        """
        policy = PasswordPolicyService.get_policy(org_secure_code)

        if not policy.get('enabled', False):
            return '密碼長度至少 8 個字元'

        requirements = []
        requirements.append(f"長度至少 {policy.get('min_length', 12)} 個字元")

        if policy.get('require_uppercase', True):
            requirements.append('包含大寫字母')
        if policy.get('require_lowercase', True):
            requirements.append('包含小寫字母')
        if policy.get('require_digit', True):
            requirements.append('包含數字')
        if policy.get('require_special', True):
            requirements.append('包含特殊符號')

        return '、'.join(requirements)

    @staticmethod
    def has_smtp_configured(org_secure_code: str) -> bool:
        """
        檢查企業是否有設定 SMTP

        Args:
            org_secure_code: 企業 secure_code

        Returns:
            是否有設定 SMTP
        """
        from ..models.smtp_config import SmtpConfig

        return SmtpConfig.query.filter_by(
            org_secure_code=org_secure_code,
            is_active=True,
            is_deleted=False
        ).first() is not None
