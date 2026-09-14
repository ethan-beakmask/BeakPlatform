"""
BeakPlatform Email Service
郵件發送服務

系統級郵件依主機設定選擇 E-MailRelay 或 SMTP 發送。
"""
import logging
import os
import smtplib
import subprocess
import tempfile
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from typing import List, Optional

from .emailrelay_config import get_paths as _get_emailrelay_paths

logger = logging.getLogger(__name__)

DEFAULT_FROM_EMAIL = 'system@beakplatform.local'
DEFAULT_FROM_NAME = 'BeakPlatform System'

MAIL_SERVICE_EMAILRELAY = 'emailrelay'
MAIL_SERVICE_SMTP = 'smtp'
MAIL_SERVICES = (MAIL_SERVICE_EMAILRELAY, MAIL_SERVICE_SMTP)
SETTING_PRIMARY_KEY = 'mail_primary_service'
SETTING_SEND_BOTH_KEY = 'mail_send_both'
SETTING_CATEGORY = 'mail_service'


class EmailService:
    """郵件發送服務"""

    @staticmethod
    def _get_from_settings() -> tuple:
        """取得 E-MailRelay 預設發件人設定"""
        try:
            from ..models.system_setting import SystemSetting
            from_email = SystemSetting.get('emailrelay_from_email', DEFAULT_FROM_EMAIL)
            from_name = SystemSetting.get('emailrelay_from_name', DEFAULT_FROM_NAME)
            return from_email, from_name
        except Exception:
            return DEFAULT_FROM_EMAIL, DEFAULT_FROM_NAME

    @staticmethod
    def get_mail_settings() -> dict:
        """取得系統級發信設定。"""
        from ..models.system_setting import SystemSetting

        primary = SystemSetting.get(SETTING_PRIMARY_KEY)
        if primary not in MAIL_SERVICES:
            primary = None
        return {
            'primary': primary,
            'send_both': bool(SystemSetting.get(SETTING_SEND_BOTH_KEY, False)),
        }

    @staticmethod
    def _get_default_system_smtp_config():
        from ..constants import SYSTEM_ORG_CODE
        from ..models.smtp_config import SmtpConfig

        return SmtpConfig.query.filter_by(
            org_secure_code=SYSTEM_ORG_CODE,
            is_default=True,
            is_active=True,
            is_deleted=False,
        ).first()

    @staticmethod
    def check_service(service: str) -> dict:
        """檢查指定發信服務是否就緒。"""
        if service == MAIL_SERVICE_EMAILRELAY:
            paths = _get_emailrelay_paths()
            submit_bin = paths['submit_bin']
            spool_dir = paths['spool_dir']

            if not os.path.exists(submit_bin):
                return {'ready': False, 'reason': 'submit_missing', 'detail': submit_bin}
            if not os.path.exists(spool_dir):
                return {'ready': False, 'reason': 'spool_missing', 'detail': spool_dir}
            if not os.access(spool_dir, os.W_OK):
                return {'ready': False, 'reason': 'spool_not_writable', 'detail': spool_dir}
            return {'ready': True, 'reason': None, 'detail': None}

        if service == MAIL_SERVICE_SMTP:
            config = EmailService._get_default_system_smtp_config()
            if not config:
                return {'ready': False, 'reason': 'no_default_config', 'detail': None}
            return {'ready': True, 'reason': None, 'detail': config.name}

        return {'ready': False, 'reason': 'unknown_service', 'detail': service}

    @staticmethod
    def get_readiness() -> dict:
        """取得系統級發信整體就緒狀態。"""
        settings = EmailService.get_mail_settings()
        primary = settings['primary']
        send_both = settings['send_both']
        services = {
            MAIL_SERVICE_EMAILRELAY: EmailService.check_service(MAIL_SERVICE_EMAILRELAY),
            MAIL_SERVICE_SMTP: EmailService.check_service(MAIL_SERVICE_SMTP),
        }

        ready = False
        reason = None
        if not primary:
            reason = 'not_selected'
        elif not services[primary]['ready']:
            reason = 'primary_not_ready'
        elif send_both:
            secondary = EmailService._secondary_service(primary)
            if not services[secondary]['ready']:
                reason = 'secondary_not_ready'
            else:
                ready = True
        else:
            ready = True

        return {
            'primary': primary,
            'send_both': send_both,
            'services': services,
            'ready': ready,
            'reason': reason,
        }

    @staticmethod
    def is_ready() -> bool:
        """系統級發信是否已可用。"""
        return EmailService.get_readiness()['ready']

    @staticmethod
    def _secondary_service(primary: str) -> str:
        return MAIL_SERVICE_SMTP if primary == MAIL_SERVICE_EMAILRELAY else MAIL_SERVICE_EMAILRELAY

    @staticmethod
    def _build_message(
        to_email: str,
        subject: str,
        body: str,
        from_email: str,
        from_name: Optional[str] = None,
        html_body: Optional[str] = None,
    ):
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
        return msg

    @staticmethod
    def _send_via_emailrelay(
        to_email: str,
        subject: str,
        body: str,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        html_body: Optional[str] = None,
    ) -> tuple:
        """透過 E-MailRelay 發信，回傳 (ok, error)。"""
        readiness = EmailService.check_service(MAIL_SERVICE_EMAILRELAY)
        if not readiness['ready']:
            return False, readiness['reason']

        if not from_email or not from_name:
            default_email, default_name = EmailService._get_from_settings()
            from_email = from_email or default_email
            from_name = from_name or default_name

        paths = _get_emailrelay_paths()
        submit_bin = paths['submit_bin']
        spool_dir = paths['spool_dir']
        msg = EmailService._build_message(
            to_email, subject, body, from_email, from_name, html_body
        )
        tmp_filepath = None

        try:
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.eml', delete=False, encoding='utf-8'
            ) as tmp_file:
                tmp_file.write(msg.as_string())
                tmp_filepath = tmp_file.name

            result = subprocess.run(
                [
                    submit_bin,
                    '--spool-dir', spool_dir,
                    '--from', from_email,
                    '--input-file', tmp_filepath,
                    to_email,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return False, result.stderr.strip() or f'exit_code_{result.returncode}'
            return True, None
        except subprocess.TimeoutExpired:
            return False, 'timeout'
        except FileNotFoundError:
            return False, f'emailrelay-submit not found: {submit_bin}'
        except Exception as e:
            return False, str(e)
        finally:
            if tmp_filepath and os.path.exists(tmp_filepath):
                try:
                    os.unlink(tmp_filepath)
                except OSError as e:
                    logger.warning("[EMAIL] temporary file cleanup failed: %s", e)

    @staticmethod
    def _send_via_smtp(
        to_email: str,
        subject: str,
        body: str,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        html_body: Optional[str] = None,
    ) -> tuple:
        """透過系統級 SMTP 預設設定發信，回傳 (ok, error)。"""
        config = EmailService._get_default_system_smtp_config()
        if not config:
            return False, 'no_default_config'

        from_email = from_email or config.from_email
        from_name = from_name or config.from_name
        msg = EmailService._build_message(
            to_email, subject, body, from_email, from_name, html_body
        )

        smtp = None
        try:
            if config.use_ssl:
                smtp = smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=30)
            else:
                smtp = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30)
                if config.use_tls:
                    smtp.starttls()

            password = config.get_password()
            if config.username and password:
                smtp.login(config.username, password)
            smtp.sendmail(from_email, [to_email], msg.as_string())
            smtp.quit()
            smtp = None
            return True, None
        except Exception as e:
            return False, str(e)
        finally:
            if smtp is not None:
                try:
                    smtp.quit()
                except Exception:
                    pass

    @staticmethod
    def send_email_detailed(
        to_email: str,
        subject: str,
        body: str,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        html_body: Optional[str] = None,
    ) -> dict:
        """發送郵件，回傳每個已嘗試服務的詳細結果。"""
        settings = EmailService.get_mail_settings()
        primary = settings['primary']
        if not primary:
            logger.error('[EMAIL] mail_primary_service not configured; mail to %s dropped', to_email)
            return {
                'success': False,
                'any_success': False,
                'attempted': [],
                'results': {},
            }

        services = [primary]
        if settings['send_both']:
            services.append(EmailService._secondary_service(primary))

        results = {}
        for service in services:
            if service == MAIL_SERVICE_EMAILRELAY:
                ok, error = EmailService._send_via_emailrelay(
                    to_email, subject, body, from_email, from_name, html_body
                )
            elif service == MAIL_SERVICE_SMTP:
                ok, error = EmailService._send_via_smtp(
                    to_email, subject, body, from_email, from_name, html_body
                )
            else:
                ok, error = False, 'unknown_service'

            results[service] = {'success': ok, 'error': error}
            if ok:
                logger.info('[EMAIL] sent via %s: to=%s, subject=%s', service, to_email, subject)
            else:
                logger.error('[EMAIL] send via %s failed: to=%s, error=%s', service, to_email, error)

        attempted = list(results.keys())
        return {
            'success': all(item['success'] for item in results.values()),
            'any_success': any(item['success'] for item in results.values()),
            'attempted': attempted,
            'results': results,
        }

    @staticmethod
    def send_email(
        to_email: str,
        subject: str,
        body: str,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        html_body: Optional[str] = None,
    ) -> bool:
        """發送郵件，回傳所有指定服務是否全部成功。"""
        return EmailService.send_email_detailed(
            to_email=to_email,
            subject=subject,
            body=body,
            from_email=from_email,
            from_name=from_name,
            html_body=html_body,
        )['success']

    @staticmethod
    def send_password_reset_verification(
        to_email: str,
        verification_url: str,
        verification_code: str,
        org_name: str,
    ) -> dict:
        """發送密碼重設驗證信，回傳 send_email_detailed 的 dict。"""
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
        return EmailService.send_email_detailed(to_email, subject, body)

    @staticmethod
    def send_temp_password(
        to_email: str,
        temp_password: str,
        org_name: str,
    ) -> dict:
        """發送暫時密碼，回傳 send_email_detailed 的 dict。"""
        subject = f'[{org_name}] 暫時密碼'
        body = f'''您好，

您的 {org_name} 系統暫時密碼如下：

暫時密碼：{temp_password}

請使用此暫時密碼登入，登入後系統將要求您立即變更密碼。
此暫時密碼僅供一次性使用。

---
{org_name} 系統
'''
        return EmailService.send_email_detailed(to_email, subject, body)

    @staticmethod
    def send_new_account_password(
        to_email: str,
        org_name: str,
        account: str,
        temp_password: str,
        login_url: Optional[str] = None,
    ) -> bool:
        """發送新帳號自動產生密碼通知，回傳 bool。"""
        subject = f'[{org_name}] 新帳號密碼通知'
        login_line = f'登入網址：{login_url}' if login_url else ''
        body = f'''您好，

您的 {org_name} 系統新帳號已建立，登入資訊如下：

帳號：{account}
暫時密碼：{temp_password}
{login_line}

首次登入後系統將要求您立即變更密碼。

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
        reset_time: str,
    ) -> bool:
        """發送企業管理員密碼被重設的通知，回傳 bool。"""
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
        org_name: Optional[str] = None,
    ) -> bool:
        """發送一般通知郵件，回傳 bool。"""
        if org_name:
            subject = f'[{org_name}] {title}'
            footer = f'\n---\n{org_name} 系統'
        else:
            subject = f'[BeakPlatform] {title}'
            footer = '\n---\nBeakPlatform System'

        return EmailService.send_email(to_email, subject, f'{content}{footer}')
