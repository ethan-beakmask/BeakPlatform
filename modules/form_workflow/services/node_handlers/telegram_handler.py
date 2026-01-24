"""
FormWorkflow Module - Telegram Handler
Telegram 通知節點處理器

發送 Telegram 訊息到指定頻道。
"""
import logging
import requests
from typing import Dict, Any

from .base import BaseNodeHandler

logger = logging.getLogger(__name__)


class TelegramHandler(BaseNodeHandler):
    """Telegram 通知節點處理器"""

    # Telegram Bot API 基礎 URL
    TELEGRAM_API_BASE = "https://api.telegram.org/bot"

    def validate(self) -> bool:
        """驗證節點配置"""
        # 必須指定 bot_token 和 chat_id
        bot_token = self.get_config_value('bot_token')
        chat_id = self.get_config_value('chat_id')

        if not bot_token:
            raise ValueError('必須設定 Telegram Bot Token')

        if not chat_id:
            raise ValueError('必須設定 Telegram Chat ID')

        # 檢查訊息內容
        message = self.get_config_value('message')
        if not message:
            raise ValueError('必須設定訊息內容')

        return True

    def handle(self) -> Dict[str, Any]:
        """處理節點 - 發送 Telegram 訊息"""
        self.report_running()

        try:
            # 取得設定
            bot_token = self.get_config_value('bot_token')
            chat_id = self.get_config_value('chat_id')

            # 取得並處理訊息內容（支援變數替換）
            message = self._process_message()

            # 發送訊息
            result = self._send_message(bot_token, chat_id, message)

            if result['success']:
                self.log_info('Telegram 訊息發送成功', {
                    'chat_id': chat_id,
                    'message_id': result.get('message_id'),
                    'message_preview': message[:100] if len(message) > 100 else message
                })

                return {
                    'status': 'success',
                    'message': 'Telegram 訊息發送成功',
                    'data': {
                        'message_id': result.get('message_id'),
                        'chat_id': chat_id
                    }
                }
            else:
                self.log_error('Telegram 訊息發送失敗', {
                    'chat_id': chat_id,
                    'error': result.get('error')
                })

                return {
                    'status': 'error',
                    'message': f"Telegram 發送失敗: {result.get('error')}"
                }

        except Exception as e:
            self.log_error(f'Telegram 節點執行失敗: {str(e)}')
            return {
                'status': 'error',
                'message': str(e)
            }

    def _process_message(self) -> str:
        """
        處理訊息內容（使用統一的變數替換方法）

        Returns:
            str: 處理後的訊息
        """
        message = self.get_config_value('message', '')
        return self.replace_variables(
            message,
            include_form=True,
            include_workflow=True
        )

    def _send_message(self, bot_token: str, chat_id: str, message: str) -> Dict[str, Any]:
        """
        發送 Telegram 訊息

        Args:
            bot_token: Bot Token
            chat_id: 聊天室 ID
            message: 訊息內容

        Returns:
            dict: {'success': bool, 'message_id': int, 'error': str}
        """
        url = f"{self.TELEGRAM_API_BASE}{bot_token}/sendMessage"

        # 取得解析模式（支援 HTML、Markdown、MarkdownV2）
        parse_mode = self.get_config_value('parse_mode', 'HTML')

        # 是否禁用連結預覽
        disable_preview = self.get_config_value('disable_web_page_preview', False)

        # 是否靜音發送
        disable_notification = self.get_config_value('disable_notification', False)

        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': parse_mode,
            'disable_web_page_preview': disable_preview,
            'disable_notification': disable_notification
        }

        try:
            response = requests.post(url, json=payload, timeout=30)
            data = response.json()

            if data.get('ok'):
                return {
                    'success': True,
                    'message_id': data.get('result', {}).get('message_id')
                }
            else:
                error_desc = data.get('description', '未知錯誤')
                return {
                    'success': False,
                    'error': error_desc
                }

        except requests.exceptions.Timeout:
            return {
                'success': False,
                'error': 'Telegram API 請求逾時'
            }
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': f'網路錯誤: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'發送失敗: {str(e)}'
            }

    @staticmethod
    def test_connection(bot_token: str, chat_id: str = None) -> Dict[str, Any]:
        """
        測試 Telegram Bot 連線

        Args:
            bot_token: Bot Token
            chat_id: 聊天室 ID（可選，如果提供則發送測試訊息）

        Returns:
            dict: {'success': bool, 'message': str, 'bot_info': dict}
        """
        url = f"https://api.telegram.org/bot{bot_token}/getMe"

        try:
            response = requests.get(url, timeout=10)
            data = response.json()

            if not data.get('ok'):
                return {
                    'success': False,
                    'message': f"Bot Token 無效: {data.get('description', '未知錯誤')}"
                }

            bot_info = data.get('result', {})
            result = {
                'success': True,
                'message': f"連線成功，Bot: @{bot_info.get('username')}",
                'bot_info': {
                    'id': bot_info.get('id'),
                    'username': bot_info.get('username'),
                    'first_name': bot_info.get('first_name')
                }
            }

            # 如果有提供 chat_id，發送測試訊息
            if chat_id:
                test_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                test_payload = {
                    'chat_id': chat_id,
                    'text': 'FormWorkflow Telegram 連線測試成功！',
                    'parse_mode': 'HTML'
                }

                test_response = requests.post(test_url, json=test_payload, timeout=10)
                test_data = test_response.json()

                if test_data.get('ok'):
                    result['message'] += f"，測試訊息已發送至 chat_id: {chat_id}"
                    result['test_message_id'] = test_data.get('result', {}).get('message_id')
                else:
                    result['message'] += f"，但測試訊息發送失敗: {test_data.get('description')}"
                    result['chat_test_failed'] = True

            return result

        except requests.exceptions.Timeout:
            return {
                'success': False,
                'message': 'Telegram API 請求逾時'
            }
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'message': f'網路錯誤: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'測試失敗: {str(e)}'
            }
