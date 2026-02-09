"""
FormWorkflow Module - EmailRelay Handler
系統郵件中繼節點處理器

透過本機 emailrelay-submit 將郵件寫入 spool，
由 emailrelay daemon 自動轉發至外部 SMTP（如 Gmail）。
不依賴外部 SMTP 設定組，屬於系統級節點。
"""
import logging
import os
import re
import subprocess
import tempfile
from typing import Dict, Any, List, Tuple
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid

from .base import BaseNodeHandler

logger = logging.getLogger(__name__)

# emailrelay-submit 路徑與 spool 目錄
EMAILRELAY_SUBMIT = '/opt/E-MailRelay/sbin/emailrelay-submit'
SPOOL_DIR = '/opt/E-MailRelay/spool'
DEFAULT_FROM = 'beakmask@beakplatform.local'

# 郵件優先級對應 X-Priority 值
PRIORITY_MAP = {
    'high': '1',
    'normal': '3',
    'low': '5',
}


class EmailRelayHandler(BaseNodeHandler):
    """系統郵件中繼節點處理器"""

    def validate(self) -> bool:
        """驗證節點配置"""
        # 檢查 emailrelay-submit 是否存在
        if not os.path.isfile(EMAILRELAY_SUBMIT):
            raise ValueError(
                f'emailrelay-submit 不存在: {EMAILRELAY_SUBMIT}'
            )

        # 檢查 spool 目錄
        if not os.path.isdir(SPOOL_DIR):
            raise ValueError(f'Spool 目錄不存在: {SPOOL_DIR}')

        subject = self.get_config_value('subject')
        if not subject:
            raise ValueError('必須設定郵件主旨')

        body = self.get_config_value('body')
        if not body:
            raise ValueError('必須設定郵件內容')

        to_emails, _ = self._collect_recipients()
        if not to_emails:
            raise ValueError('必須設定至少一個收件者')

        return True

    def handle(self) -> Dict[str, Any]:
        """處理節點 - 透過 emailrelay-submit 發送郵件"""
        self.report_running()

        try:
            # 收集收件者
            to_emails, cc_emails = self._collect_recipients()
            if not to_emails:
                raise ValueError('無法解析出有效的收件者')

            # 處理主旨和內容（變數替換）
            subject = self._process_template(
                self.get_config_value('subject', '')
            )
            body = self._process_template(
                self.get_config_value('body', '')
            )

            body_type = self.get_config_value('body_type', 'plain')
            priority = self.get_config_value('priority', 'normal')

            # 組裝 MIME 郵件
            msg = self._create_email(
                to_emails=to_emails,
                cc_emails=cc_emails,
                subject=subject,
                body=body,
                body_type=body_type,
                priority=priority,
            )

            # 透過 emailrelay-submit 寫入 spool
            all_recipients = to_emails + cc_emails
            result = self._submit_to_spool(msg, all_recipients)

            if result['success']:
                self.log_info('郵件已提交至 EmailRelay spool', {
                    'to': to_emails,
                    'cc': cc_emails,
                    'subject': (
                        subject[:50] + '...'
                        if len(subject) > 50
                        else subject
                    ),
                })

                return {
                    'status': 'success',
                    'message': '郵件已提交至 EmailRelay',
                    'data': {
                        'to_count': len(to_emails),
                        'cc_count': len(cc_emails),
                    },
                }
            else:
                self.log_error('EmailRelay 提交失敗', {
                    'error': result.get('error')
                })
                return {
                    'status': 'error',
                    'message': f"EmailRelay 提交失敗: {result.get('error')}",
                }

        except Exception as e:
            self.log_error(f'EmailRelay 節點執行失敗: {str(e)}')
            return {
                'status': 'error',
                'message': str(e),
            }

    # --------------------------------------------------
    # 收件者解析
    # --------------------------------------------------

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

        # 向下相容舊格式 'recipients' 欄位
        if not to_emails:
            legacy = self.get_config_value('recipients', '')
            if legacy:
                to_emails = self._parse_recipients(legacy)

        # CC
        cc_manual = (
            self.get_config_value('cc_manual', '')
            or self.get_config_value('cc', '')
        )
        cc_emails = self._parse_recipients(cc_manual)

        return to_emails, cc_emails

    def _resolve_group_recipients(self, group_ids: list) -> List[str]:
        """解析收件人群組為 email 列表"""
        if not group_ids:
            return []

        from app.models import RecipientGroup
        emails = set()

        for gid in group_ids:
            group = RecipientGroup.query.filter_by(
                secure_code=str(gid),
                is_deleted=False,
                is_active=True,
            ).first()

            # 向下相容整數 ID
            if not group:
                try:
                    int_id = int(gid)
                    group = RecipientGroup.query.filter_by(
                        id=int_id,
                        is_deleted=False,
                        is_active=True,
                    ).first()
                except (ValueError, TypeError):
                    pass

            if group:
                for r in group.resolve_recipients():
                    if r.get('email'):
                        emails.add(r['email'])

        return list(emails)

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
            include_node=True,
        )

    # --------------------------------------------------
    # 郵件組裝
    # --------------------------------------------------

    def _create_email(
        self,
        to_emails: List[str],
        cc_emails: List[str],
        subject: str,
        body: str,
        body_type: str,
        priority: str,
    ) -> MIMEMultipart:
        """建立 MIME 郵件"""
        msg = MIMEMultipart('alternative')

        msg['From'] = DEFAULT_FROM
        msg['To'] = ', '.join(to_emails)
        if cc_emails:
            msg['Cc'] = ', '.join(cc_emails)
        msg['Subject'] = subject
        msg['Date'] = formatdate(localtime=True)
        msg['Message-ID'] = make_msgid(domain='beakplatform.local')

        x_priority = PRIORITY_MAP.get(priority, '3')
        msg['X-Priority'] = x_priority

        if self.workflow_instance:
            msg['X-FormWorkflow-Instance'] = (
                self.workflow_instance.secure_code
            )
        msg['X-FormWorkflow-Node'] = self.queue_item.node_id
        msg['X-FormWorkflow-Queue'] = self.queue_item.secure_code

        if body_type == 'html':
            msg.attach(MIMEText(body, 'html', 'utf-8'))
        else:
            msg.attach(MIMEText(body, 'plain', 'utf-8'))

        return msg

    # --------------------------------------------------
    # Spool 提交
    # --------------------------------------------------

    def _submit_to_spool(
        self,
        msg: MIMEMultipart,
        recipients: List[str],
    ) -> Dict[str, Any]:
        """
        透過 emailrelay-submit 將郵件寫入 spool 目錄

        emailrelay-submit 從 stdin 讀取郵件內容，
        將其寫入 spool 目錄等待 daemon 轉發。
        """
        try:
            cmd = [
                EMAILRELAY_SUBMIT,
                '--from', DEFAULT_FROM,
                '-s', SPOOL_DIR,
            ] + recipients

            result = subprocess.run(
                cmd,
                input=msg.as_string(),
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                return {'success': True}
            else:
                stderr = result.stderr.strip() or result.stdout.strip()
                return {
                    'success': False,
                    'error': f'emailrelay-submit 返回碼 {result.returncode}: {stderr}',
                }

        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'error': 'emailrelay-submit 執行逾時 (30s)',
            }
        except FileNotFoundError:
            return {
                'success': False,
                'error': f'找不到 emailrelay-submit: {EMAILRELAY_SUBMIT}',
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'提交失敗: {str(e)}',
            }
