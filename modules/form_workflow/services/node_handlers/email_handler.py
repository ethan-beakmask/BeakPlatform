"""
FormWorkflow Module - Email Handler
Email 通知節點處理器

支援透過 SMTP 發送郵件。
透過 smtp_config_id 引用 SmtpConfig 設定組取得 SMTP 連線資訊。
"""
import logging
import re
import smtplib
from typing import Dict, Any, List, Optional, Tuple
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid

from .base import BaseNodeHandler
from backend.app.constants import SYSTEM_ORG_CODE

logger = logging.getLogger(__name__)


class EmailHandler(BaseNodeHandler):
    """Email 通知節點處理器"""

    # 郵件優先級對應 X-Priority 值
    PRIORITY_MAP = {
        'high': '1',
        'normal': '3',
        'low': '5'
    }

    def _resolve_smtp_config(self) -> Dict[str, Any]:
        """
        從 smtp_config_id 解析出 SMTP 連線設定

        節點 config 格式：
            smtp_config_id: SmtpConfig 的 secure_code（或留空使用預設）

        Returns:
            dict: SMTP 設定 {smtp_host, smtp_port, use_tls, use_ssl,
                            username, password, from_email, from_name}
        """
        from app.models import SmtpConfig

        config_id = self.get_config_value('smtp_config_id')
        smtp_config = None
        org_code = self.workflow_instance.org_secure_code if self.workflow_instance else None
        allowed_orgs = [o for o in {org_code, SYSTEM_ORG_CODE} if o]

        if config_id:
            smtp_config = SmtpConfig.query.filter(
                SmtpConfig.secure_code == str(config_id),
                SmtpConfig.org_secure_code.in_(allowed_orgs),
                SmtpConfig.is_deleted.is_(False),
                SmtpConfig.is_active.is_(True),
            ).first()

            # 仍找不到時，降級為自動選擇（可能是 parseInt 造成的壞資料）
            if not smtp_config:
                logger.warning(
                    f'SMTP config_id={config_id} 無法匹配，降級為自動選擇'
                )

        # 自動選擇：企業級 → 系統級
        if not smtp_config and org_code:
            smtp_config = SmtpConfig.query.filter_by(
                org_secure_code=org_code,
                is_default=True,
                is_deleted=False,
                is_active=True,
            ).first()

            if not smtp_config:
                smtp_config = SmtpConfig.query.filter_by(
                    org_secure_code=org_code,
                    is_deleted=False,
                    is_active=True,
                ).order_by(SmtpConfig.priority).first()

        # 系統級 fallback
        if not smtp_config:
            smtp_config = SmtpConfig.query.filter_by(
                org_secure_code=SYSTEM_ORG_CODE,
                is_deleted=False,
                is_active=True,
            ).order_by(SmtpConfig.priority).first()

        if not smtp_config:
            raise ValueError('沒有可用的 SMTP 設定')

        return {
            'smtp_host': smtp_config.smtp_host,
            'smtp_port': smtp_config.smtp_port,
            'use_tls': smtp_config.use_tls,
            'use_ssl': smtp_config.use_ssl,
            'username': smtp_config.username,
            'password': smtp_config.get_password(),
            'from_email': smtp_config.from_email,
            'from_name': smtp_config.from_name or '',
        }

    def _collect_recipients(self) -> Tuple[List[str], List[str]]:
        """
        根據 recipient_type 收集收件者和副本收件者

        節點 config 格式：
            recipient_type: 'manual' | 'group'
            recipient_manual: 逗號/分號分隔的 email 字串
            recipient_groups: [group_secure_code, ...]
            cc_manual: 逗號/分號分隔的 CC email 字串

        Returns:
            tuple: (to_emails, cc_emails)
        """
        recipient_type = self.get_config_value('recipient_type', 'manual')
        to_emails = []

        if recipient_type == 'manual':
            manual = self.get_config_value('recipient_manual', '')
            to_emails = self._parse_recipients(manual)
        elif recipient_type == 'group':
            group_ids = self.get_config_value('recipient_groups', [])
            to_emails = self._resolve_group_recipients(group_ids)

        # 也支援舊格式 'recipients' 欄位（向下相容）
        if not to_emails:
            legacy = self.get_config_value('recipients', '')
            if legacy:
                to_emails = self._parse_recipients(legacy)

        # CC
        cc_manual = self.get_config_value('cc_manual', '') or self.get_config_value('cc', '')
        cc_emails = self._parse_recipients(cc_manual)

        return to_emails, cc_emails

    def _resolve_group_recipients(self, group_ids: list) -> List[str]:
        """解析收件人群組為 email 列表"""
        if not group_ids:
            return []

        from app.models import RecipientGroup
        emails = set()

        org_code = self.workflow_instance.org_secure_code if self.workflow_instance else None
        allowed_orgs = [o for o in {org_code, SYSTEM_ORG_CODE} if o]

        for gid in group_ids:
            group = RecipientGroup.query.filter(
                RecipientGroup.secure_code == str(gid),
                RecipientGroup.org_secure_code.in_(allowed_orgs),
                RecipientGroup.is_deleted.is_(False),
                RecipientGroup.is_active.is_(True),
            ).first()

            if group:
                for r in group.resolve_recipients():
                    if r.get('email'):
                        emails.add(r['email'])

        return list(emails)

    def validate(self) -> bool:
        """驗證節點配置"""
        subject = self.get_config_value('subject')
        if not subject:
            raise ValueError('必須設定郵件主旨')

        body = self.get_config_value('body')
        if not body:
            raise ValueError('必須設定郵件內容')

        # 檢查收件者
        to_emails, _ = self._collect_recipients()
        if not to_emails:
            raise ValueError('必須設定至少一個收件者')

        # 檢查 SMTP 設定可解析
        self._resolve_smtp_config()

        return True

    def handle(self) -> Dict[str, Any]:
        """處理節點 - 發送郵件"""
        self.report_running()

        try:
            # 解析 SMTP 設定
            smtp = self._resolve_smtp_config()

            # 收集收件者
            to_emails, cc_emails = self._collect_recipients()
            if not to_emails:
                raise ValueError('無法解析出有效的收件者')

            # 處理主旨和內容（變數替換）
            subject = self._process_template(self.get_config_value('subject', ''))
            body = self._process_template(self.get_config_value('body', ''))

            body_type = self.get_config_value('body_type', 'plain')
            priority = self.get_config_value('priority', 'normal')

            # 組裝郵件
            msg = self._create_email(
                from_email=smtp['from_email'],
                from_name=smtp['from_name'],
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
                smtp_host=smtp['smtp_host'],
                smtp_port=smtp['smtp_port'],
                smtp_user=smtp['username'],
                smtp_password=smtp['password'],
                smtp_use_tls=smtp['use_tls'],
                smtp_use_ssl=smtp['use_ssl'],
                from_email=smtp['from_email'],
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
        """解析收件者字串（逗號、分號、換行分隔）"""
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
        """處理變數替換"""
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
        """建立 MIME 郵件"""
        msg = MIMEMultipart('alternative')

        msg['From'] = f'{from_name} <{from_email}>' if from_name else from_email
        msg['To'] = ', '.join(to_emails)
        if cc_emails:
            msg['Cc'] = ', '.join(cc_emails)
        msg['Subject'] = subject
        msg['Date'] = formatdate(localtime=True)
        msg['Message-ID'] = make_msgid(domain='formworkflow.local')

        x_priority = self.PRIORITY_MAP.get(priority, '3')
        msg['X-Priority'] = x_priority

        if self.workflow_instance:
            msg['X-FormWorkflow-Instance'] = self.workflow_instance.secure_code
        msg['X-FormWorkflow-Node'] = self.queue_item.node_id
        msg['X-FormWorkflow-Queue'] = self.queue_item.secure_code

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
        smtp_use_ssl: bool,
        from_email: str,
        to_emails: List[str]
    ) -> Dict[str, Any]:
        """發送郵件"""
        try:
            if smtp_use_ssl:
                server = smtplib.SMTP_SSL(smtp_host, smtp_port)
            else:
                server = smtplib.SMTP(smtp_host, smtp_port)
                if smtp_use_tls:
                    server.starttls()

            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)

            server.sendmail(from_email, to_emails, msg.as_string())
            server.quit()

            return {'success': True}

        except smtplib.SMTPAuthenticationError:
            return {'success': False, 'error': 'SMTP 認證失敗'}
        except smtplib.SMTPConnectError:
            return {'success': False, 'error': f'無法連線到 SMTP 伺服器 {smtp_host}:{smtp_port}'}
        except smtplib.SMTPException as e:
            return {'success': False, 'error': f'SMTP 錯誤: {str(e)}'}
        except Exception as e:
            return {'success': False, 'error': f'發送失敗: {str(e)}'}

    @staticmethod
    def test_smtp_connection(
        smtp_host: str,
        smtp_port: int,
        smtp_user: str = None,
        smtp_password: str = None,
        smtp_use_tls: bool = False
    ) -> Dict[str, Any]:
        """測試 SMTP 連線"""
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
            return {'success': False, 'message': 'SMTP 認證失敗'}
        except smtplib.SMTPConnectError:
            return {'success': False, 'message': f'無法連線到 {smtp_host}:{smtp_port}'}
        except Exception as e:
            return {'success': False, 'message': f'測試失敗: {str(e)}'}
