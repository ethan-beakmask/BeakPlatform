"""
System Settings - Telegram 設定子模組

端點：
- GET    /api/system-settings/telegram                列出 Telegram 設定
- POST   /api/system-settings/telegram                新增 Telegram 設定
- GET    /api/system-settings/telegram/<id>           取得設定詳情
- PUT    /api/system-settings/telegram/<id>           更新 Telegram 設定
- DELETE /api/system-settings/telegram/<id>           刪除 Telegram 設定
- POST   /api/system-settings/telegram/test           測試連線
- POST   /api/system-settings/telegram/<id>/test      測試已儲存設定
"""
from datetime import datetime
from flask import jsonify, request

from ..security.decorators import system_admin_required
from ..models import TelegramConfig
from ..constants import SYSTEM_ORG_CODE
from .. import db


def register(bp):
    """將 Telegram 路由掛載到 Blueprint"""

    @bp.route('/telegram', methods=['GET'])
    @system_admin_required
    def list_telegram_configs():
        """列出所有系統級 Telegram 設定"""
        configs = TelegramConfig.query.filter_by(
            org_secure_code=SYSTEM_ORG_CODE,
            is_deleted=False
        ).order_by(TelegramConfig.name).all()

        return jsonify({
            'success': True,
            'data': [config.to_dict() for config in configs]
        })

    @bp.route('/telegram', methods=['POST'])
    @system_admin_required
    def create_telegram_config():
        """
        新增系統級 Telegram 設定

        Body:
            name: 設定名稱 (必填)
            bot_token: Bot Token (必填)
            description: 描述
            channels: 頻道設定 {"頻道名": "chat_id", ...}
            default_channel: 預設頻道名稱
            is_active: 是否啟用 (預設 true)
        """
        data = request.get_json()

        if not data:
            return jsonify({'success': False, 'message': '請提供資料'}), 400

        if not data.get('name'):
            return jsonify({'success': False, 'message': '請填寫設定名稱'}), 400

        if not data.get('bot_token'):
            return jsonify({'success': False, 'message': '請填寫 Bot Token'}), 400

        # 建立設定
        config = TelegramConfig(
            org_secure_code=SYSTEM_ORG_CODE,
            name=data['name'],
            description=data.get('description'),
            bot_token=data['bot_token'],
            default_channel=data.get('default_channel'),
            is_active=data.get('is_active', True)
        )

        # 設定頻道
        if data.get('channels'):
            config.set_channels(data['channels'])

        db.session.add(config)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Telegram 設定已建立',
            'data': config.to_dict()
        }), 201

    @bp.route('/telegram/<secure_code>', methods=['GET'])
    @system_admin_required
    def get_telegram_config(secure_code):
        """取得 Telegram 設定詳情（含完整 token）"""
        config = TelegramConfig.query.filter_by(
            secure_code=secure_code,
            org_secure_code=SYSTEM_ORG_CODE,
            is_deleted=False
        ).first()

        if not config:
            return jsonify({'success': False, 'message': '設定不存在'}), 404

        return jsonify({
            'success': True,
            'data': config.to_dict(hide_token=False)
        })

    @bp.route('/telegram/<secure_code>', methods=['PUT'])
    @system_admin_required
    def update_telegram_config(secure_code):
        """更新 Telegram 設定"""
        config = TelegramConfig.query.filter_by(
            secure_code=secure_code,
            org_secure_code=SYSTEM_ORG_CODE,
            is_deleted=False
        ).first()

        if not config:
            return jsonify({'success': False, 'message': '設定不存在'}), 404

        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '請提供資料'}), 400

        # 更新欄位
        if 'name' in data:
            config.name = data['name']

        if 'description' in data:
            config.description = data['description']

        if 'bot_token' in data:
            config.bot_token = data['bot_token']

        if 'channels' in data:
            config.set_channels(data['channels'])

        if 'default_channel' in data:
            config.default_channel = data['default_channel']

        if 'is_active' in data:
            config.is_active = data['is_active']

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Telegram 設定已更新',
            'data': config.to_dict()
        })

    @bp.route('/telegram/<secure_code>', methods=['DELETE'])
    @system_admin_required
    def delete_telegram_config(secure_code):
        """刪除 Telegram 設定（軟刪除）"""
        config = TelegramConfig.query.filter_by(
            secure_code=secure_code,
            org_secure_code=SYSTEM_ORG_CODE,
            is_deleted=False
        ).first()

        if not config:
            return jsonify({'success': False, 'message': '設定不存在'}), 404

        config.is_deleted = True
        config.deleted_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Telegram 設定已刪除'
        })

    @bp.route('/telegram/test', methods=['POST'])
    @system_admin_required
    def test_telegram_connection():
        """
        測試 Telegram 連線（使用傳入的設定）

        Body:
            bot_token: Bot Token (必填)
            chat_id: 頻道 ID (選填，提供則發送測試訊息)
        """
        data = request.get_json()

        if not data:
            return jsonify({'success': False, 'message': '請提供資料'}), 400

        if not data.get('bot_token'):
            return jsonify({'success': False, 'message': '請填寫 Bot Token'}), 400

        result = TelegramConfig.test_connection(
            bot_token=data['bot_token'],
            chat_id=data.get('chat_id'),
            test_message=data.get('test_message', '[BeakPlatform] Telegram 連線測試')
        )

        return jsonify({
            'success': result['success'],
            'message': result['message'],
            'bot_info': result.get('bot_info')
        })

    @bp.route('/telegram/<secure_code>/test', methods=['POST'])
    @system_admin_required
    def test_saved_telegram_config(secure_code):
        """測試已儲存的 Telegram 設定"""
        config = TelegramConfig.query.filter_by(
            secure_code=secure_code,
            org_secure_code=SYSTEM_ORG_CODE,
            is_deleted=False
        ).first()

        if not config:
            return jsonify({'success': False, 'message': '設定不存在'}), 404

        data = request.get_json() or {}

        # 決定要測試的頻道
        chat_id = data.get('chat_id')
        if not chat_id:
            # 使用預設頻道或第一個頻道
            chat_id = config.get_default_channel_id()

        result = TelegramConfig.test_connection(
            bot_token=config.bot_token,
            chat_id=chat_id,
            test_message=data.get('test_message', '[BeakPlatform] Telegram 連線測試')
        )

        return jsonify({
            'success': result['success'],
            'message': result['message'],
            'bot_info': result.get('bot_info')
        })
