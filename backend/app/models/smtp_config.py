"""
BeakPlatform SMTP Config Model
SMTP 郵件伺服器設定

密碼加密：使用 Fernet 對稱加密，密鑰從 Flask SECRET_KEY 派生
"""
import base64
import hashlib
import smtplib
from datetime import datetime
from typing import Dict, Any, Optional, List

from cryptography.fernet import Fernet
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text

from .base import TenantBaseModel


class SmtpConfig(TenantBaseModel):
    """
    SMTP 郵件伺服器設定

    支援多組設定，可設定優先順序作為備援機制。
    密碼使用 Fernet 加密存儲。
    """
    __tablename__ = 'smtp_configs'

    # 設定名稱
    name = Column(String(100), nullable=False, comment='設定名稱')

    # 描述
    description = Column(Text, nullable=True, comment='描述說明')

    # SMTP 伺服器
    smtp_host = Column(String(255), nullable=False, comment='SMTP 伺服器位址')
    smtp_port = Column(Integer, default=587, nullable=False, comment='SMTP 連接埠')

    # TLS/SSL 設定
    use_tls = Column(Boolean, default=True, nullable=False, comment='使用 STARTTLS')
    use_ssl = Column(Boolean, default=False, nullable=False, comment='使用 SSL/TLS')

    # 認證資訊
    username = Column(String(255), nullable=False, comment='SMTP 帳號')
    password_encrypted = Column(String(512), nullable=True, comment='Fernet 加密後的密碼')

    # Gmail 應用程式密碼
    use_app_password = Column(
        Boolean,
        default=False,
        nullable=False,
        comment='是否使用 Gmail 應用程式密碼'
    )

    # 寄件人資訊
    from_email = Column(String(255), nullable=False, comment='寄件人信箱')
    from_name = Column(String(100), nullable=True, comment='寄件人名稱')

    # 提供者類型 (用於預設值)
    provider_type = Column(
        String(20),
        default='generic',
        nullable=False,
        comment='提供者類型: generic, gmail, outlook'
    )

    # 優先順序 (數字越小越優先)
    priority = Column(Integer, default=100, nullable=False, comment='優先順序')

    # 狀態
    is_default = Column(Boolean, default=False, nullable=False, comment='是否為預設')
    is_active = Column(Boolean, default=True, nullable=False, comment='是否啟用')

    # 測試狀態
    last_test_at = Column(DateTime, nullable=True, comment='最後測試時間')
    last_test_success = Column(Boolean, nullable=True, comment='最後測試結果')
    last_test_message = Column(Text, nullable=True, comment='最後測試訊息')

    # 常用 SMTP 伺服器預設值
    PROVIDER_PRESETS = {
        'gmail': {
            'smtp_host': 'smtp.gmail.com',
            'smtp_port': 587,
            'use_tls': True,
            'use_ssl': False
        },
        'outlook': {
            'smtp_host': 'smtp.office365.com',
            'smtp_port': 587,
            'use_tls': True,
            'use_ssl': False
        },
        'yahoo': {
            'smtp_host': 'smtp.mail.yahoo.com',
            'smtp_port': 587,
            'use_tls': True,
            'use_ssl': False
        }
    }

    @staticmethod
    def _get_fernet() -> Fernet:
        """
        取得 Fernet 加密器

        使用 Flask SECRET_KEY 派生加密密鑰
        """
        from flask import current_app
        secret_key = current_app.config.get('SECRET_KEY', 'default-secret-key')
        # 使用 SHA256 將 SECRET_KEY 轉為 32 bytes，再 base64 編碼為 Fernet 密鑰
        key = hashlib.sha256(secret_key.encode()).digest()
        fernet_key = base64.urlsafe_b64encode(key)
        return Fernet(fernet_key)

    def set_password(self, password: str) -> None:
        """
        設定密碼 (Fernet 加密)

        使用 AES-128-CBC 加密，密鑰從 Flask SECRET_KEY 派生
        """
        if password:
            fernet = self._get_fernet()
            encrypted = fernet.encrypt(password.encode())
            self.password_encrypted = encrypted.decode()
        else:
            self.password_encrypted = None

    def get_password(self) -> Optional[str]:
        """取得密碼 (Fernet 解密)"""
        if self.password_encrypted:
            try:
                fernet = self._get_fernet()
                decrypted = fernet.decrypt(self.password_encrypted.encode())
                return decrypted.decode()
            except Exception:
                # 解密失敗（可能是舊的 Base64 格式），嘗試 Base64 解碼
                try:
                    return base64.b64decode(self.password_encrypted.encode()).decode()
                except Exception:
                    return None
        return None

    def to_dict(self, include_password: bool = False) -> Dict[str, Any]:
        """轉換為字典"""
        base = super().to_dict()
        base.update({
            'name': self.name,
            'description': self.description,
            'smtp_host': self.smtp_host,
            'smtp_port': self.smtp_port,
            'use_tls': self.use_tls,
            'use_ssl': self.use_ssl,
            'username': self.username,
            'use_app_password': self.use_app_password,
            'from_email': self.from_email,
            'from_name': self.from_name,
            'provider_type': self.provider_type,
            'priority': self.priority,
            'is_default': self.is_default,
            'is_active': self.is_active,
            'last_test_at': self.last_test_at.isoformat() if self.last_test_at else None,
            'last_test_success': self.last_test_success,
            'last_test_message': self.last_test_message,
        })
        if include_password and self.password_encrypted:
            base['password'] = self.get_password()
        return base

    @classmethod
    def get_default_config(cls, org_secure_code: str) -> Optional['SmtpConfig']:
        """
        取得預設設定

        優先順序：
        1. is_default = True
        2. priority 最小
        3. 第一個啟用的
        """
        # 先找 is_default
        config = cls.query.filter_by(
            org_secure_code=org_secure_code,
            is_default=True,
            is_active=True,
            is_deleted=False
        ).first()
        if config:
            return config

        # 找 priority 最小
        return cls.query.filter_by(
            org_secure_code=org_secure_code,
            is_active=True,
            is_deleted=False
        ).order_by(cls.priority).first()

    @classmethod
    def get_org_configs(cls, org_secure_code: str) -> List['SmtpConfig']:
        """取得企業所有設定"""
        return cls.query.filter_by(
            org_secure_code=org_secure_code,
            is_deleted=False
        ).order_by(cls.priority).all()

    @staticmethod
    def test_connection(
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        use_tls: bool = True,
        use_ssl: bool = False,
        from_email: Optional[str] = None,
        test_recipient: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        測試 SMTP 連線

        Args:
            smtp_host: SMTP 伺服器
            smtp_port: 連接埠
            username: 帳號
            password: 密碼
            use_tls: 使用 STARTTLS
            use_ssl: 使用 SSL
            from_email: 寄件人 (測試發信用)
            test_recipient: 測試收件人 (不提供則只測連線)

        Returns:
            {'success': bool, 'message': str}
        """
        try:
            # 建立連線
            if use_ssl:
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10)
            else:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)

            # STARTTLS
            if use_tls and not use_ssl:
                server.starttls()

            # 登入
            server.login(username, password)

            # 發送測試信
            if test_recipient and from_email:
                from email.mime.text import MIMEText
                msg = MIMEText('這是 BeakPlatform SMTP 測試郵件。\n\nThis is a test email from BeakPlatform.')
                msg['Subject'] = '[BeakPlatform] SMTP 連線測試'
                msg['From'] = from_email
                msg['To'] = test_recipient
                server.sendmail(from_email, [test_recipient], msg.as_string())
                server.quit()
                return {'success': True, 'message': f'測試郵件已發送至 {test_recipient}'}

            server.quit()
            return {'success': True, 'message': 'SMTP 連線成功'}

        except smtplib.SMTPAuthenticationError:
            return {'success': False, 'message': '認證失敗：帳號或密碼錯誤'}
        except smtplib.SMTPConnectError:
            return {'success': False, 'message': f'無法連線到 {smtp_host}:{smtp_port}'}
        except Exception as e:
            return {'success': False, 'message': f'連線失敗：{str(e)}'}

    def __repr__(self):
        return f'<SmtpConfig {self.name} ({self.smtp_host})>'
