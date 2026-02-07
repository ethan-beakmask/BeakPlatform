"""
BeakPlatform Telegram Config Model
Telegram Bot 設定
"""
import json
import requests
from typing import Dict, Any, Optional, List

from sqlalchemy import Column, String, Boolean, Text

from .base import TenantBaseModel


class TelegramConfig(TenantBaseModel):
    """
    Telegram Bot 設定

    支援多組設定，每組可設定多個頻道。
    org_secure_code 為必填（企業級設定）。
    """
    __tablename__ = 'telegram_configs'

    # 設定名稱
    name = Column(String(100), nullable=False, comment='設定名稱')

    # 描述
    description = Column(Text, nullable=True, comment='描述說明')

    # Bot Token
    bot_token = Column(String(255), nullable=False, comment='Telegram Bot Token')

    # 頻道設定 (JSON 格式: {"頻道名": "chat_id", ...})
    channels = Column(Text, nullable=True, comment='頻道設定 JSON')

    # 預設頻道名稱
    default_channel = Column(String(100), nullable=True, comment='預設頻道名稱')

    # 狀態
    is_active = Column(Boolean, default=True, nullable=False, comment='是否啟用')

    def to_dict(self, hide_token: bool = True) -> Dict[str, Any]:
        """
        轉換為字典

        Args:
            hide_token: 是否隱藏 token (只顯示前後各 4 碼)
        """
        base = super().to_dict()

        # 處理 token 顯示
        if hide_token and self.bot_token:
            if len(self.bot_token) > 12:
                token_display = f"{self.bot_token[:4]}...{self.bot_token[-4:]}"
            else:
                token_display = '****'
        else:
            token_display = self.bot_token

        base.update({
            'name': self.name,
            'description': self.description,
            'bot_token': token_display,
            'channels': self.get_channels(),
            'default_channel': self.default_channel,
            'is_active': self.is_active,
        })
        return base

    def get_channels(self) -> Dict[str, str]:
        """取得頻道設定"""
        if self.channels:
            try:
                return json.loads(self.channels)
            except json.JSONDecodeError:
                return {}
        return {}

    def set_channels(self, channels: Dict[str, str]) -> None:
        """設定頻道"""
        self.channels = json.dumps(channels, ensure_ascii=False)

    def get_channel_list(self) -> List[Dict[str, str]]:
        """取得頻道列表 (用於前端顯示)"""
        channels = self.get_channels()
        return [
            {'name': name, 'chat_id': chat_id}
            for name, chat_id in channels.items()
        ]

    def get_channel_id(self, channel_name: str) -> Optional[str]:
        """取得指定頻道的 chat_id"""
        channels = self.get_channels()
        return channels.get(channel_name)

    def get_default_channel_id(self) -> Optional[str]:
        """取得預設頻道的 chat_id"""
        if self.default_channel:
            return self.get_channel_id(self.default_channel)
        # 如果沒設定預設，返回第一個
        channels = self.get_channels()
        if channels:
            return list(channels.values())[0]
        return None

    def add_channel(self, name: str, chat_id: str) -> None:
        """新增頻道"""
        channels = self.get_channels()
        channels[name] = chat_id
        self.set_channels(channels)

    def remove_channel(self, name: str) -> bool:
        """移除頻道"""
        channels = self.get_channels()
        if name in channels:
            del channels[name]
            self.set_channels(channels)
            # 如果移除的是預設頻道，清除預設
            if self.default_channel == name:
                self.default_channel = None
            return True
        return False

    @classmethod
    def get_org_configs(cls, org_secure_code: str) -> List['TelegramConfig']:
        """取得企業所有設定"""
        return cls.query.filter_by(
            org_secure_code=org_secure_code,
            is_deleted=False
        ).order_by(cls.name).all()

    @classmethod
    def get_active_config(cls, org_secure_code: str) -> Optional['TelegramConfig']:
        """取得第一個啟用的設定"""
        return cls.query.filter_by(
            org_secure_code=org_secure_code,
            is_active=True,
            is_deleted=False
        ).first()

    @staticmethod
    def test_connection(
        bot_token: str,
        chat_id: Optional[str] = None,
        test_message: str = '[BeakPlatform] Telegram 連線測試'
    ) -> Dict[str, Any]:
        """
        測試 Telegram 連線

        Args:
            bot_token: Bot Token
            chat_id: 頻道 ID (提供則發送測試訊息)
            test_message: 測試訊息內容

        Returns:
            {'success': bool, 'message': str, 'bot_info': dict}
        """
        try:
            # 取得 Bot 資訊
            api_url = f'https://api.telegram.org/bot{bot_token}/getMe'
            response = requests.get(api_url, timeout=10)
            result = response.json()

            if not result.get('ok'):
                return {
                    'success': False,
                    'message': f"Bot Token 無效: {result.get('description', '未知錯誤')}"
                }

            bot_info = result.get('result', {})

            # 如果有 chat_id，發送測試訊息
            if chat_id:
                send_url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
                send_response = requests.post(send_url, json={
                    'chat_id': chat_id,
                    'text': test_message
                }, timeout=10)
                send_result = send_response.json()

                if not send_result.get('ok'):
                    return {
                        'success': False,
                        'message': f"發送測試訊息失敗: {send_result.get('description', '未知錯誤')}",
                        'bot_info': bot_info
                    }

                return {
                    'success': True,
                    'message': f"測試訊息已發送至頻道 {chat_id}",
                    'bot_info': bot_info
                }

            return {
                'success': True,
                'message': f"Bot 連線成功: @{bot_info.get('username', 'unknown')}",
                'bot_info': bot_info
            }

        except requests.Timeout:
            return {'success': False, 'message': '連線逾時'}
        except requests.RequestException as e:
            return {'success': False, 'message': f'網路錯誤: {str(e)}'}
        except Exception as e:
            return {'success': False, 'message': f'測試失敗: {str(e)}'}

    def __repr__(self):
        return f'<TelegramConfig {self.name}>'
