"""
BeakPlatform Email Service
郵件發送服務

透過 E-MailRelay 發送系統郵件
"""
import os
import logging
import tempfile
import subprocess
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid
from typing import Optional, List

logger = logging.getLogger(__name__)

# E-MailRelay 設定
EMAILRELAY_SPOOL_DIR = '/opt/BeakPlatform/E-MailRelay/spool'
EMAILRELAY_SUBMIT = '/usr/sbin/emailrelay-submit'

# 預設發件人設定
DEFAULT_FROM_EMAIL = 'system@beakplatform.local'
DEFAULT_FROM_NAME = 'BeakPlatform System'


class EmailService:
    """郵件發送服務"""

    @staticmethod
    def _get_from_settings() -> tuple:
        """取得發件人設定"""
        try:
            from ..models.system_setting import SystemSetting
            from_email = SystemSetting.get('emailrelay_from_email', DEFAULT_FROM_EMAIL)
            from_name = SystemSetting.get('emailrelay_from_name', DEFAULT_FROM_NAME)
            return from_email, from_name
        except Exception:
            return DEFAULT_FROM_EMAIL, DEFAULT_FROM_NAME

    @staticmethod
    def _get_spool_dir() -> str:
        """取得 spool 目錄"""
        try:
            from ..models.system_setting import SystemSetting
            return SystemSetting.get('emailrelay_spool_dir', EMAILRELAY_SPOOL_DIR)
        except Exception:
            return EMAILRELAY_SPOOL_DIR

    @staticmethod
    def _is_emailrelay_available() -> bool:
        """檢查 E-MailRelay 是否可用"""
        spool_dir = EmailService._get_spool_dir()

        # 檢查 emailrelay-submit 是否存在
        if not os.path.exists(EMAILRELAY_SUBMIT):
            logger.warning(f"[EMAIL] emailrelay-submit not found: {EMAILRELAY_SUBMIT}")
            return False

        # 檢查 spool 目錄是否存在且可寫入
        if not os.path.exists(spool_dir):
            logger.warning(f"[EMAIL] Spool directory not found: {spool_dir}")
            return False

        if not os.access(spool_dir, os.W_OK):
            logger.warning(f"[EMAIL] Spool directory not writable: {spool_dir}")
            return False

        return True

    @staticmethod
    def _submit_email(
        to_email: str,
        subject: str,
        body: str,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        html_body: Optional[str] = None
    ) -> bool:
        """
        透過 emailrelay-submit 提交郵件

        Args:
            to_email: 收件人 email
            subject: 主旨
            body: 純文字內容
            from_email: 寄件人 email
            from_name: 寄件人名稱
            html_body: HTML 內容（選填）

        Returns:
            bool: 是否成功提交
        """
        # 取得發件人設定
        if not from_email or not from_name:
            default_email, default_name = EmailService._get_from_settings()
            from_email = from_email or default_email
            from_name = from_name or default_name

        spool_dir = EmailService._get_spool_dir()

        # 建立郵件
        if html_body:
            msg = MIMEMultipart('alternative')
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        else:
            msg = MIMEText(body, 'plain', 'utf-8')

        msg['From'] = f'{from_name} <{from_email}>' if from_name else from_email
        msg['To'] = to_email
        msg['Subject'] = subject
        msg['Date'] = formatdate(localtime=True)
        msg['Message-ID'] = make_msgid(domain='beakplatform.local')
        msg['X-BeakPlatform-Auto'] = 'true'

        eml_content = msg.as_string()

        # 使用 emailrelay-submit 提交
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.eml', delete=False, encoding='utf-8'
            ) as tmp_file:
                tmp_file.write(eml_content)
                tmp_filepath = tmp_file.name

            cmd = [
                EMAILRELAY_SUBMIT,
                '--spool-dir', spool_dir,
                '--from', from_email,
                '--input-file', tmp_filepath,
                to_email
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            # 清理暫存檔
            if os.path.exists(tmp_filepath):
                os.unlink(tmp_filepath)

            if result.returncode != 0:
                logger.error(f"[EMAIL] emailrelay-submit failed: {result.stderr}")
                return False

            logger.info(f"[EMAIL] Email submitted: to={to_email}, subject={subject}")
            return True

        except subprocess.TimeoutExpired:
            logger.error("[EMAIL] emailrelay-submit timeout")
            return False
        except FileNotFoundError:
            logger.error(f"[EMAIL] emailrelay-submit not found: {EMAILRELAY_SUBMIT}")
            return False
        except Exception as e:
            logger.error(f"[EMAIL] Submit failed: {str(e)}")
            return False

    @staticmethod
    def _log_email(
        to_email: str,
        subject: str,
        body: str,
        reason: str = "E-MailRelay unavailable"
    ):
        """當無法發送時，記錄郵件內容到日誌"""
        logger.info(f"[EMAIL] {reason}, logging email instead:")
        logger.info(f"  To: {to_email}")
        logger.info(f"  Subject: {subject}")
        logger.info(f"  ------ Email Content ------")
        for line in body.split('\n'):
            logger.info(f"  {line}")
        logger.info(f"  ------ End of Email ------")

    @staticmethod
    def send_email(
        to_email: str,
        subject: str,
        body: str,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        html_body: Optional[str] = None
    ) -> bool:
        """
        發送郵件（通用方法）

        Args:
            to_email: 收件人 email
            subject: 主旨
            body: 純文字內容
            from_email: 寄件人 email（選填）
            from_name: 寄件人名稱（選填）
            html_body: HTML 內容（選填）

        Returns:
            bool: 是否成功發送
        """
        if EmailService._is_emailrelay_available():
            return EmailService._submit_email(
                to_email=to_email,
                subject=subject,
                body=body,
                from_email=from_email,
                from_name=from_name,
                html_body=html_body
            )
        else:
            EmailService._log_email(to_email, subject, body)
            return True  # 返回 True 避免業務邏輯中斷

    @staticmethod
    def send_password_reset_verification(
        to_email: str,
        verification_url: str,
        verification_code: str,
        org_name: str
    ) -> bool:
        """
        發送密碼重設驗證信

        郵件內容包含:
        - 驗證 URL
        - 6 碼驗證碼
        - 10 分鐘有效期限提醒

        Args:
            to_email: 收件人 email
            verification_url: 驗證 URL
            verification_code: 6 碼驗證碼
            org_name: 企業名稱

        Returns:
            bool: 是否成功發送
        """
        subject = f'[{org_name}] 密碼重設驗證'

        body = f'''您好，

您已申請 {org_name} 系統的密碼重設。
請點擊以下連結並輸入 6 碼驗證碼完成驗證：

驗證連結：{verification_url}
驗證碼：{verification_code}

此驗證碼將於 10 分鐘後失效。
如果您沒有申請密碼重設，請忽略此郵件。

---
{org_name} 系統
'''

        return EmailService.send_email(to_email, subject, body)

    @staticmethod
    def send_temp_password(
        to_email: str,
        temp_password: str,
        org_name: str
    ) -> bool:
        """
        發送暫時密碼

        Args:
            to_email: 收件人 email
            temp_password: 暫時密碼
            org_name: 企業名稱

        Returns:
            bool: 是否成功發送
        """
        subject = f'[{org_name}] 暫時密碼'

        body = f'''您好，

您的 {org_name} 系統暫時密碼如下：

暫時密碼：{temp_password}

請使用此暫時密碼登入，登入後系統將要求您立即變更密碼。
此暫時密碼僅供一次性使用。

---
{org_name} 系統
'''

        return EmailService.send_email(to_email, subject, body)

    @staticmethod
    def send_welcome_email(
        to_email: str,
        username: str,
        org_name: str,
        login_url: str
    ) -> bool:
        """
        發送歡迎郵件 (新用戶建立時)

        Args:
            to_email: 收件人 email
            username: 用戶名
            org_name: 企業名稱
            login_url: 登入 URL

        Returns:
            bool: 是否成功發送
        """
        subject = f'[{org_name}] 歡迎加入'

        body = f'''您好 {username}，

歡迎加入 {org_name} 系統！

您的帳號已建立，請使用以下連結登入：
{login_url}

如有任何問題，請聯繫系統管理員。

---
{org_name} 系統
'''

        return EmailService.send_email(to_email, subject, body)

    @staticmethod
    def send_admin_password_reset_notification(
        to_emails: List[str],
        target_admin_name: str,
        target_admin_email: str,
        operator_name: str,
        operator_email: str,
        org_name: str,
        reset_time: str
    ) -> bool:
        """
        發送企業管理員密碼被重設的通知

        當企業管理員的密碼被其他管理員重設時，通知該企業所有企業管理員
        （包含停用中的帳號，作為防弊措施）

        Args:
            to_emails: 收件人 email 列表
            target_admin_name: 被重設密碼的管理員姓名
            target_admin_email: 被重設密碼的管理員 email
            operator_name: 操作者姓名
            operator_email: 操作者 email
            org_name: 企業名稱
            reset_time: 重設時間

        Returns:
            bool: 是否成功發送
        """
        subject = f'[{org_name}] 企業管理員密碼重設通知'

        body = f'''企業管理員密碼重設通知

您好，

這是一封自動發送的安全通知郵件。

以下企業管理員的密碼已被重設：

被重設帳號：{target_admin_name} ({target_admin_email})
操作者：{operator_name} ({operator_email})
重設時間：{reset_time}

如果這不是您或授權人員的操作，請立即聯繫系統管理員。

此郵件發送給 {org_name} 的所有企業管理員（包含停用帳號）。

---
{org_name} 系統
'''

        # 發送給所有收件人
        success = True
        for email in to_emails:
            if not EmailService.send_email(email, subject, body):
                success = False

        return success

    @staticmethod
    def send_notification(
        to_email: str,
        title: str,
        content: str,
        org_name: Optional[str] = None
    ) -> bool:
        """
        發送一般通知郵件

        Args:
            to_email: 收件人 email
            title: 通知標題
            content: 通知內容
            org_name: 企業名稱（選填）

        Returns:
            bool: 是否成功發送
        """
        if org_name:
            subject = f'[{org_name}] {title}'
            footer = f'\n---\n{org_name} 系統'
        else:
            subject = f'[BeakPlatform] {title}'
            footer = '\n---\nBeakPlatform System'

        body = f'{content}{footer}'

        return EmailService.send_email(to_email, subject, body)
