"""
BeakMask Password Reset Token Model
密碼重設 Token
"""
import secrets
import string
from datetime import datetime, timedelta
from sqlalchemy import Column, String, DateTime, Boolean
from .base import BaseModel


class PasswordResetToken(BaseModel):
    """
    密碼重設 Token

    二階段驗證流程:
    1. 用戶申請重設密碼，系統產生 verification_url_token + verification_code
    2. 系統寄送含 URL 的郵件到用戶信箱
    3. 用戶造訪 URL 並輸入 6 碼驗證碼
    4. 驗證成功後，系統寄送暫時密碼到用戶信箱
    """
    __tablename__ = 'password_reset_tokens'

    # 關聯的企業
    org_secure_code = Column(String(32), nullable=False, index=True)

    # 用戶 email (username@domain)
    email = Column(String(255), nullable=False)

    # URL Token (用於驗證頁面)
    verification_url_token = Column(String(64), unique=True, nullable=False, index=True)

    # 6 碼驗證碼
    verification_code = Column(String(6), nullable=False)

    # 驗證碼驗證時間
    verified_at = Column(DateTime, nullable=True)

    # 暫時密碼是否已寄出
    temp_password_sent = Column(Boolean, default=False)

    # 過期時間 (預設 10 分鐘)
    expires_at = Column(DateTime, nullable=False)

    # 使用時間 (用戶成功登入暫時密碼後標記)
    used_at = Column(DateTime, nullable=True)

    @classmethod
    def generate_verification_code(cls) -> str:
        """產生 6 碼數字驗證碼"""
        return ''.join(secrets.choice(string.digits) for _ in range(6))

    @classmethod
    def generate_url_token(cls) -> str:
        """產生 URL Token (32 bytes = 43 chars in base64)"""
        return secrets.token_urlsafe(32)

    @classmethod
    def generate_temp_password(cls) -> str:
        """
        產生暫時密碼 (12 碼)

        組成: 小寫字母 + 數字，避免混淆字元 (0/O, 1/l)
        """
        alphabet = 'abcdefghjkmnpqrstuvwxyz23456789'
        return ''.join(secrets.choice(alphabet) for _ in range(12))

    @classmethod
    def create_for_user(cls, org_secure_code: str, email: str, expire_minutes: int = 10) -> 'PasswordResetToken':
        """
        為用戶建立密碼重設 Token

        Args:
            org_secure_code: 企業 secure_code
            email: 用戶 email
            expire_minutes: 過期時間 (分鐘)

        Returns:
            PasswordResetToken: 新建立的 token
        """
        token = cls(
            org_secure_code=org_secure_code,
            email=email,
            verification_url_token=cls.generate_url_token(),
            verification_code=cls.generate_verification_code(),
            expires_at=datetime.utcnow() + timedelta(minutes=expire_minutes)
        )
        return token

    @property
    def is_expired(self) -> bool:
        """檢查是否已過期"""
        from datetime import timezone
        now = datetime.now(timezone.utc)
        # 確保 expires_at 有時區資訊
        if self.expires_at.tzinfo is None:
            expires = self.expires_at.replace(tzinfo=timezone.utc)
        else:
            expires = self.expires_at
        return now > expires

    @property
    def is_verified(self) -> bool:
        """檢查是否已驗證"""
        return self.verified_at is not None

    @property
    def is_used(self) -> bool:
        """檢查是否已使用"""
        return self.used_at is not None

    def verify(self, code: str) -> bool:
        """
        驗證 6 碼驗證碼

        Args:
            code: 用戶輸入的驗證碼

        Returns:
            bool: 是否驗證成功
        """
        if self.is_expired:
            return False
        if self.is_verified:
            return False
        if self.verification_code != code:
            return False

        self.verified_at = datetime.utcnow()
        return True

    def mark_temp_password_sent(self):
        """標記暫時密碼已寄出"""
        self.temp_password_sent = True

    def mark_used(self):
        """標記已使用"""
        self.used_at = datetime.utcnow()
