"""
System Settings - SMTP 設定子模組

端點：
- GET    /api/system-settings/smtp                    列出 SMTP 設定
- POST   /api/system-settings/smtp                    新增 SMTP 設定
- GET    /api/system-settings/smtp/<id>               取得設定詳情
- PUT    /api/system-settings/smtp/<id>               更新 SMTP 設定
- DELETE /api/system-settings/smtp/<id>               刪除 SMTP 設定
- POST   /api/system-settings/smtp/test               測試連線
- POST   /api/system-settings/smtp/<id>/test          測試已儲存設定
- GET    /api/system-settings/smtp/presets             取得預設值
"""
from datetime import datetime
from flask import jsonify, request
from flask_babel import gettext as _

from ..security.decorators import system_admin_required
from ..models import SmtpConfig
from ..constants import SYSTEM_ORG_CODE
from .. import db


def register(bp):
    """將 SMTP 路由掛載到 Blueprint"""

    @bp.route('/smtp', methods=['GET'])
    @system_admin_required
    def list_smtp_configs():
        """列出所有系統級 SMTP 設定"""
        configs = SmtpConfig.query.filter_by(
            org_secure_code=SYSTEM_ORG_CODE,
            is_deleted=False
        ).order_by(SmtpConfig.priority).all()

        return jsonify({
            'success': True,
            'data': [config.to_dict() for config in configs]
        })

    @bp.route('/smtp', methods=['POST'])
    @system_admin_required
    def create_smtp_config():
        """
        新增系統級 SMTP 設定

        Body:
            name: 設定名稱 (必填)
            smtp_host: SMTP 伺服器 (必填)
            smtp_port: 連接埠 (預設 587)
            username: 帳號 (必填)
            password: 密碼 (必填)
            from_email: 寄件人信箱 (必填)
            from_name: 寄件人名稱
            use_tls: 使用 STARTTLS (預設 true)
            use_ssl: 使用 SSL (預設 false)
            provider_type: 提供者類型 (generic, gmail, outlook)
            priority: 優先順序 (預設 100)
            is_default: 是否為預設
            is_active: 是否啟用 (預設 true)
        """
        data = request.get_json()

        if not data:
            return jsonify({'success': False, 'message': _('請提供資料')}), 400

        # 必填欄位驗證
        required_fields = ['name', 'smtp_host', 'username', 'password', 'from_email']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'message': _('請填寫 %(field)s', field=field)}), 400

        # 如果設為預設，取消其他預設
        if data.get('is_default'):
            existing_defaults = SmtpConfig.query.filter_by(
                org_secure_code=SYSTEM_ORG_CODE,
                is_default=True,
                is_deleted=False
            ).all()
            for config in existing_defaults:
                config.is_default = False

        # 建立設定
        config = SmtpConfig(
            org_secure_code=SYSTEM_ORG_CODE,
            name=data['name'],
            description=data.get('description'),
            smtp_host=data['smtp_host'],
            smtp_port=data.get('smtp_port', 587),
            use_tls=data.get('use_tls', True),
            use_ssl=data.get('use_ssl', False),
            username=data['username'],
            from_email=data['from_email'],
            from_name=data.get('from_name'),
            provider_type=data.get('provider_type', 'generic'),
            use_app_password=data.get('use_app_password', False),
            priority=data.get('priority', 100),
            is_default=data.get('is_default', False),
            is_active=data.get('is_active', True)
        )
        config.set_password(data['password'])

        db.session.add(config)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': _('SMTP 設定已建立'),
            'data': config.to_dict()
        }), 201

    @bp.route('/smtp/<secure_code>', methods=['GET'])
    @system_admin_required
    def get_smtp_config(secure_code):
        """取得 SMTP 設定詳情（含密碼）"""
        config = SmtpConfig.query.filter_by(
            secure_code=secure_code,
            org_secure_code=SYSTEM_ORG_CODE,
            is_deleted=False
        ).first()

        if not config:
            return jsonify({'success': False, 'message': _('設定不存在')}), 404

        return jsonify({
            'success': True,
            'data': config.to_dict(include_password=True)
        })

    @bp.route('/smtp/<secure_code>', methods=['PUT'])
    @system_admin_required
    def update_smtp_config(secure_code):
        """更新 SMTP 設定"""
        config = SmtpConfig.query.filter_by(
            secure_code=secure_code,
            org_secure_code=SYSTEM_ORG_CODE,
            is_deleted=False
        ).first()

        if not config:
            return jsonify({'success': False, 'message': _('設定不存在')}), 404

        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': _('請提供資料')}), 400

        # 如果設為預設，取消其他預設
        if data.get('is_default') and not config.is_default:
            existing_defaults = SmtpConfig.query.filter_by(
                org_secure_code=SYSTEM_ORG_CODE,
                is_default=True,
                is_deleted=False
            ).all()
            for other_config in existing_defaults:
                if other_config.secure_code != secure_code:
                    other_config.is_default = False

        # 更新欄位
        updatable_fields = [
            'name', 'description', 'smtp_host', 'smtp_port',
            'use_tls', 'use_ssl', 'username', 'from_email', 'from_name',
            'provider_type', 'use_app_password', 'priority', 'is_default', 'is_active'
        ]
        for field in updatable_fields:
            if field in data:
                setattr(config, field, data[field])

        # 密碼特別處理
        if 'password' in data and data['password']:
            config.set_password(data['password'])

        db.session.commit()

        return jsonify({
            'success': True,
            'message': _('SMTP 設定已更新'),
            'data': config.to_dict()
        })

    @bp.route('/smtp/<secure_code>', methods=['DELETE'])
    @system_admin_required
    def delete_smtp_config(secure_code):
        """刪除 SMTP 設定（軟刪除）"""
        config = SmtpConfig.query.filter_by(
            secure_code=secure_code,
            org_secure_code=SYSTEM_ORG_CODE,
            is_deleted=False
        ).first()

        if not config:
            return jsonify({'success': False, 'message': _('設定不存在')}), 404

        config.is_deleted = True
        config.deleted_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            'success': True,
            'message': _('SMTP 設定已刪除')
        })

    @bp.route('/smtp/test', methods=['POST'])
    @system_admin_required
    def test_smtp_connection():
        """
        測試 SMTP 連線（使用傳入的設定）

        Body:
            smtp_host: SMTP 伺服器 (必填)
            smtp_port: 連接埠 (必填)
            username: 帳號 (必填)
            password: 密碼 (必填)
            use_tls: 使用 STARTTLS
            use_ssl: 使用 SSL
            from_email: 寄件人信箱
            test_recipient: 測試收件人 (提供則發送測試信)
        """
        data = request.get_json()

        if not data:
            return jsonify({'success': False, 'message': _('請提供資料')}), 400

        required_fields = ['smtp_host', 'smtp_port', 'username', 'password']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'message': _('請填寫 %(field)s', field=field)}), 400

        result = SmtpConfig.test_connection(
            smtp_host=data['smtp_host'],
            smtp_port=data['smtp_port'],
            username=data['username'],
            password=data['password'],
            use_tls=data.get('use_tls', True),
            use_ssl=data.get('use_ssl', False),
            from_email=data.get('from_email'),
            test_recipient=data.get('test_recipient')
        )

        return jsonify({
            'success': result['success'],
            'message': result['message']
        })

    @bp.route('/smtp/<secure_code>/test', methods=['POST'])
    @system_admin_required
    def test_saved_smtp_config(secure_code):
        """測試已儲存的 SMTP 設定"""
        config = SmtpConfig.query.filter_by(
            secure_code=secure_code,
            org_secure_code=SYSTEM_ORG_CODE,
            is_deleted=False
        ).first()

        if not config:
            return jsonify({'success': False, 'message': _('設定不存在')}), 404

        data = request.get_json() or {}

        result = SmtpConfig.test_connection(
            smtp_host=config.smtp_host,
            smtp_port=config.smtp_port,
            username=config.username,
            password=config.get_password(),
            use_tls=config.use_tls,
            use_ssl=config.use_ssl,
            from_email=config.from_email,
            test_recipient=data.get('test_recipient')
        )

        # 更新測試狀態
        config.last_test_at = datetime.utcnow()
        config.last_test_success = result['success']
        config.last_test_message = result['message']
        db.session.commit()

        return jsonify({
            'success': result['success'],
            'message': result['message']
        })

    @bp.route('/smtp/presets', methods=['GET'])
    @system_admin_required
    def get_smtp_presets():
        """取得常用 SMTP 伺服器預設值"""
        return jsonify({
            'success': True,
            'data': SmtpConfig.PROVIDER_PRESETS
        })
