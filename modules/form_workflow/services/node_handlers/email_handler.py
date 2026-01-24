"""
FormWorkflow Module - Email Handler
Email 通知節點處理器

支援透過 SMTP 發送郵件。
"""
import logging
import re
import smtplib
from typing import Dict, Any, List
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid

from .base import BaseNodeHandler

logger = logging.getLogger(__name__)


class EmailHandler(BaseNodeHandler):
    """Email 通知節點處理器"""

    # 郵件優先級對應 X-Priority 值
    PRIORITY_MAP = {
        'high': '1',
        'normal': '3',
        'low': '5'
    }

    def validate(self) -> bool:
        """驗證節點配置"""
        # 檢查主旨
        subject = self.get_config_value('subject')
        if not subject:
            raise ValueError('必須設定郵件主旨')

        # 檢查內容
        body = self.get_config_value('body')
        if not body:
            raise ValueError('必須設定郵件內容')

        # 檢查收件者設定
        recipients = self.get_config_value('recipients', '')
        if not recipients.strip():
            raise ValueError('必須設定至少一個收件者')

        return True

    def handle(self) -> Dict[str, Any]:
        """處理節點 - 發送郵件"""
        self.report_running()

        try:
            # 收集收件者
            to_emails = self._parse_recipients(self.get_config_value('recipients', ''))
            if not to_emails:
                raise ValueError('無法解析出有效的收件者')

            # 收集副本收件者
            cc_emails = self._parse_recipients(self.get_config_value('cc', ''))

            # 處理主旨和內容（變數替換）
            subject = self._process_template(self.get_config_value('subject', ''))
            body = self._process_template(self.get_config_value('body', ''))

            # 取得設定
            smtp_host = self.get_config_value('smtp_host', 'localhost')
            smtp_port = self.get_config_value('smtp_port', 25)
            smtp_user = self.get_config_value('smtp_user', '')
            smtp_password = self.get_config_value('smtp_password', '')
            smtp_use_tls = self.get_config_value('smtp_use_tls', False)

            from_email = self.get_config_value('from_email', 'formworkflow@localhost')
            from_name = self.get_config_value('from_name', 'FormWorkflow')
            body_type = self.get_config_value('body_type', 'plain')
            priority = self.get_config_value('priority', 'normal')

            # 組裝郵件
            msg = self._create_email(
                from_email=from_email,
                from_name=from_name,
                to_emails=to_emails,
                cc_emails=cc_emails,
                subject=subject,
                body=body,
                body_type=body_type,
                priority=priority
            )

            # 發送郵件
            result = self._send_email(
                msg=msg,
                smtp_host=smtp_host,
                smtp_port=smtp_port,
                smtp_user=smtp_user,
                smtp_password=smtp_password,
                smtp_use_tls=smtp_use_tls,
                from_email=from_email,
                to_emails=to_emails + cc_emails
            )

            if result['success']:
                self.log_info('郵件發送成功', {
                    'to': to_emails,
                    'cc': cc_emails,
                    'subject': subject[:50] + '...' if len(subject) > 50 else subject
                })

                return {
                    'status': 'success',
                    'message': '郵件發送成功',
                    'data': {
                        'to_count': len(to_emails),
                        'cc_count': len(cc_emails)
                    }
                }
            else:
                self.log_error('郵件發送失敗', {
                    'error': result.get('error')
                })
                return {
                    'status': 'error',
                    'message': f"郵件發送失敗: {result.get('error')}"
                }

        except Exception as e:
            self.log_error(f'Email 節點執行失敗: {str(e)}')
            return {
                'status': 'error',
                'message': str(e)
            }

    def _parse_recipients(self, recipients_str: str) -> List[str]:
        """
        解析收件者字串

        支援逗號、分號、換行分隔的多個 email。
        支援變數替換。

        Args:
            recipients_str: 收件者字串

        Returns:
            list: email 清單
        """
        if not recipients_str:
            return []

        # 變數替換
        recipients_str = self._process_template(recipients_str)

        emails = set()
        for email in re.split(r'[,;\n\r]+', recipients_str):
            email = email.strip()
            if email and '@' in email:
                emails.add(email)

        return list(emails)

    def _process_template(self, template: str) -> str:
        """
        處理變數替換

        Returns:
            str: 處理後的字串
        """
        return self.replace_variables(
            template,
            include_form=True,
            include_workflow=True,
            include_timestamp=True,
            include_node=True
        )

    def _create_email(
        self,
        from_email: str,
        from_name: str,
        to_emails: List[str],
        cc_emails: List[str],
        subject: str,
        body: str,
        body_type: str,
        priority: str
    ) -> MIMEMultipart:
        """
        建立 MIME 郵件

        Returns:
            MIMEMultipart: 郵件物件
        """
        # 建立郵件物件
        msg = MIMEMultipart('alternative')

        # 設定標頭
        msg['From'] = f'{from_name} <{from_email}>' if from_name else from_email
        msg['To'] = ', '.join(to_emails)
        if cc_emails:
            msg['Cc'] = ', '.join(cc_emails)
        msg['Subject'] = subject
        msg['Date'] = formatdate(localtime=True)
        msg['Message-ID'] = make_msgid(domain='formworkflow.local')

        # 優先級
        x_priority = self.PRIORITY_MAP.get(priority, '3')
        msg['X-Priority'] = x_priority

        # FormWorkflow 追蹤標頭
        if self.workflow_instance:
            msg['X-FormWorkflow-Instance'] = self.workflow_instance.secure_code
        msg['X-FormWorkflow-Node'] = self.queue_item.node_id
        msg['X-FormWorkflow-Queue'] = self.queue_item.secure_code

        # 添加內容
        if body_type == 'html':
            msg.attach(MIMEText(body, 'html', 'utf-8'))
        else:
            msg.attach(MIMEText(body, 'plain', 'utf-8'))

        return msg

    def _send_email(
        self,
        msg: MIMEMultipart,
        smtp_host: str,
        smtp_port: int,
        smtp_user: str,
        smtp_password: str,
        smtp_use_tls: bool,
        from_email: str,
        to_emails: List[str]
    ) -> Dict[str, Any]:
        """
        發送郵件

        Returns:
            dict: {'success': bool, 'error': str}
        """
        try:
            # 建立 SMTP 連線
            if smtp_use_tls:
                server = smtplib.SMTP(smtp_host, smtp_port)
                server.starttls()
            else:
                server = smtplib.SMTP(smtp_host, smtp_port)

            # 登入（如果有設定）
            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)

            # 發送郵件
            server.sendmail(from_email, to_emails, msg.as_string())
            server.quit()

            return {'success': True}

        except smtplib.SMTPAuthenticationError:
            return {
                'success': False,
                'error': 'SMTP 認證失敗'
            }
        except smtplib.SMTPConnectError:
            return {
                'success': False,
                'error': f'無法連線到 SMTP 伺服器 {smtp_host}:{smtp_port}'
            }
        except smtplib.SMTPException as e:
            return {
                'success': False,
                'error': f'SMTP 錯誤: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'發送失敗: {str(e)}'
            }

    @staticmethod
    def test_smtp_connection(
        smtp_host: str,
        smtp_port: int,
        smtp_user: str = None,
        smtp_password: str = None,
        smtp_use_tls: bool = False
    ) -> Dict[str, Any]:
        """
        測試 SMTP 連線

        Returns:
            dict: {'success': bool, 'message': str}
        """
        try:
            if smtp_use_tls:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
                server.starttls()
            else:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)

            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)

            server.quit()

            return {
                'success': True,
                'message': f'成功連線到 {smtp_host}:{smtp_port}'
            }

        except smtplib.SMTPAuthenticationError:
            return {
                'success': False,
                'message': 'SMTP 認證失敗'
            }
        except smtplib.SMTPConnectError:
            return {
                'success': False,
                'message': f'無法連線到 {smtp_host}:{smtp_port}'
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'測試失敗: {str(e)}'
            }
