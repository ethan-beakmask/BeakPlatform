"""
FormWorkflow Module - Notify Handler
通知節點處理器

發送通知（Email、Telegram 等）。
"""
from typing import Dict, Any, List
from .base import BaseNodeHandler


class NotifyHandler(BaseNodeHandler):
    """
    通知處理器

    配置參數：
    - type: 通知類型 (email/telegram/webhook)
    - recipients: 收件人列表
    - subject: 主旨（email 用）
    - message: 訊息內容
    - template: 模板名稱（可選）
    """

    def validate(self) -> bool:
        """驗證節點配置"""
        notify_type = self.get_config_value('type')
        if not notify_type:
            self.node_config['type'] = 'email'

        message = self.get_config_value('message')
        template = self.get_config_value('template')

        if not message and not template:
            raise ValueError('必須設定 message 或 template')

        return True

    def handle(self) -> Dict[str, Any]:
        """處理通知節點"""
        notify_type = self.get_config_value('type', 'email')
        recipients = self.get_config_value('recipients', [])
        subject = self.get_config_value('subject', '')
        message = self.get_config_value('message', '')
        template = self.get_config_value('template')

        # 替換變數
        if subject:
            subject = self.replace_variables(subject)
        if message:
            message = self.replace_variables(message)

        self.log_info('發送通知', {
            'type': notify_type,
            'recipients_count': len(recipients),
            'subject': subject[:50] if subject else None
        })

        # 根據類型發送通知
        if notify_type == 'email':
            result = self._send_email(recipients, subject, message)
        elif notify_type == 'telegram':
            result = self._send_telegram(recipients, message)
        elif notify_type == 'webhook':
            result = self._send_webhook(recipients, message)
        else:
            return {
                'status': 'error',
                'message': f'不支援的通知類型: {notify_type}'
            }

        return result

    def _send_email(self, recipients: List[str], subject: str, message: str) -> Dict[str, Any]:
        """發送 Email"""
        # TODO: 實作 Email 發送
        self.log_info(f'Email 通知（模擬）: {len(recipients)} 位收件人')
        return {
            'status': 'success',
            'message': f'Email 已發送至 {len(recipients)} 位收件人',
            'data': {
                'type': 'email',
                'recipients': recipients,
                'sent': True
            }
        }

    def _send_telegram(self, recipients: List[str], message: str) -> Dict[str, Any]:
        """發送 Telegram"""
        # TODO: 實作 Telegram 發送
        self.log_info(f'Telegram 通知（模擬）: {len(recipients)} 位收件人')
        return {
            'status': 'success',
            'message': f'Telegram 已發送至 {len(recipients)} 位收件人',
            'data': {
                'type': 'telegram',
                'recipients': recipients,
                'sent': True
            }
        }

    def _send_webhook(self, endpoints: List[str], payload: str) -> Dict[str, Any]:
        """發送 Webhook"""
        # TODO: 實作 Webhook 發送
        self.log_info(f'Webhook 通知（模擬）: {len(endpoints)} 個端點')
        return {
            'status': 'success',
            'message': f'Webhook 已發送至 {len(endpoints)} 個端點',
            'data': {
                'type': 'webhook',
                'endpoints': endpoints,
                'sent': True
            }
        }
