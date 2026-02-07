"""
企業級設定 API

[標準 AUTH-02] 所有路由使用統一認證 decorator
[標準 URL-01] 使用 secure_code 取代自增 ID
[標準 TENANT-02] 透過 ResourceGateway 存取資源

端點：
SMTP 設定:
- GET    /api/admin/settings/smtp              列出 SMTP 設定
- POST   /api/admin/settings/smtp              新增 SMTP 設定
- GET    /api/admin/settings/smtp/<id>         取得設定詳情
- PUT    /api/admin/settings/smtp/<id>         更新 SMTP 設定
- DELETE /api/admin/settings/smtp/<id>         刪除 SMTP 設定
- POST   /api/admin/settings/smtp/test         測試 SMTP 連線
- POST   /api/admin/settings/smtp/<id>/test    測試已儲存設定
- GET    /api/admin/settings/smtp/presets      取得預設值

Telegram 設定:
- GET    /api/admin/settings/telegram          列出 Telegram 設定
- POST   /api/admin/settings/telegram          新增 Telegram 設定
- GET    /api/admin/settings/telegram/<id>     取得設定詳情
- PUT    /api/admin/settings/telegram/<id>     更新 Telegram 設定
- DELETE /api/admin/settings/telegram/<id>     刪除 Telegram 設定
- POST   /api/admin/settings/telegram/test     測試 Telegram 連線
- POST   /api/admin/settings/telegram/<id>/test 測試已儲存設定
"""
from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_login import current_user

from .. import db
from ..models import SmtpConfig, TelegramConfig, RecipientGroup, OrganizationalUnit, User
from ..security.decorators import admin_required
from ..security.resource_gateway import ResourceGateway


api_enterprise_settings = Blueprint(
    'api_enterprise_settings',
    __name__,
    url_prefix='/api/admin/settings'
)


# ==================== 一般設定 ====================

@api_enterprise_settings.route('/general', methods=['GET'])
@admin_required
def get_general_settings():
    """取得一般設定"""
    org = current_user.organization
    if not org:
        return jsonify({'success': False, 'message': '找不到企業'}), 404

    return jsonify({
        'success': True,
        'data': org.get_settings()
    })


@api_enterprise_settings.route('/general', methods=['PUT'])
@admin_required
def update_general_settings():
    """更新一般設定"""
    org = current_user.organization
    if not org:
        return jsonify({'success': False, 'message': '找不到企業'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': '請提供資料'}), 400

    # 更新設定
    org.set_settings(data)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': '設定已儲存',
        'data': org.get_settings()
    })


# ==================== 密碼政策設定 ====================

@api_enterprise_settings.route('/password-policy', methods=['GET'])
@admin_required
def get_password_policy():
    """取得密碼政策設定"""
    from ..services.password_policy_service import PasswordPolicyService

    org = current_user.organization
    if not org:
        return jsonify({'success': False, 'message': '找不到企業'}), 404

    policy = PasswordPolicyService.get_policy(org.secure_code)
    has_smtp = PasswordPolicyService.has_smtp_configured(org.secure_code)

    return jsonify({
        'success': True,
        'data': {
            'policy': policy,
            'has_smtp': has_smtp
        }
    })


@api_enterprise_settings.route('/password-policy', methods=['PUT'])
@admin_required
def update_password_policy():
    """更新密碼政策設定"""
    from ..services.password_policy_service import PasswordPolicyService

    org = current_user.organization
    if not org:
        return jsonify({'success': False, 'message': '找不到企業'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': '請提供資料'}), 400

    # 更新密碼政策
    PasswordPolicyService.set_policy(org.secure_code, data)
    has_smtp = PasswordPolicyService.has_smtp_configured(org.secure_code)

    return jsonify({
        'success': True,
        'message': '密碼政策已儲存',
        'data': {
            'policy': data,
            'has_smtp': has_smtp
        }
    })


@api_enterprise_settings.route('/password-policy/generate', methods=['POST'])
@admin_required
def generate_password():
    """生成符合政策的密碼"""
    from ..services.password_policy_service import PasswordPolicyService

    org = current_user.organization
    if not org:
        return jsonify({'success': False, 'message': '找不到企業'}), 404

    password = PasswordPolicyService.generate_password(org.secure_code)

    return jsonify({
        'success': True,
        'data': {
            'password': password
        }
    })


@api_enterprise_settings.route('/password-policy/validate', methods=['POST'])
@admin_required
def validate_password():
    """驗證密碼是否符合政策"""
    from ..services.password_policy_service import PasswordPolicyService

    org = current_user.organization
    if not org:
        return jsonify({'success': False, 'message': '找不到企業'}), 404

    data = request.get_json()
    if not data or 'password' not in data:
        return jsonify({'success': False, 'message': '請提供密碼'}), 400

    password = data['password']
    user_secure_code = data.get('user_secure_code')  # 檢查歷史時需要

    is_valid, errors = PasswordPolicyService.validate_password(
        password,
        org.secure_code,
        user_secure_code=user_secure_code,
        check_history=bool(user_secure_code)
    )

    requirements = PasswordPolicyService.get_password_requirements_text(org.secure_code)

    return jsonify({
        'success': True,
        'data': {
            'valid': is_valid,
            'errors': errors,
            'requirements': requirements
        }
    })


# ==================== 企業 Logo 設定 ====================

import os
from werkzeug.utils import secure_filename
from flask import current_app

ALLOWED_LOGO_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'}
MAX_LOGO_SIZE = 2 * 1024 * 1024  # 2MB


def allowed_logo_file(filename):
    """檢查檔案副檔名是否允許"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_LOGO_EXTENSIONS


@api_enterprise_settings.route('/logo', methods=['GET'])
@admin_required
def get_logo_info():
    """取得企業 Logo 資訊"""
    org = current_user.organization
    if not org:
        return jsonify({'success': False, 'message': '找不到企業'}), 404

    logo_path = org.get_setting('logo_path')
    logo_url = None

    if logo_path:
        # 檢查檔案是否存在
        full_path = os.path.join(current_app.static_folder, logo_path)
        if os.path.exists(full_path):
            logo_url = f'/static/{logo_path}'
        else:
            # 檔案不存在，清除設定
            org.set_setting('logo_path', None)
            db.session.commit()
            logo_path = None

    return jsonify({
        'success': True,
        'data': {
            'has_logo': logo_path is not None,
            'logo_url': logo_url
        }
    })


@api_enterprise_settings.route('/logo', methods=['POST'])
@admin_required
def upload_logo():
    """
    上傳企業 Logo

    Form Data:
        logo: 圖片檔案 (png, jpg, jpeg, gif, svg, webp)
    """
    org = current_user.organization
    if not org:
        return jsonify({'success': False, 'message': '找不到企業'}), 404

    if 'logo' not in request.files:
        return jsonify({'success': False, 'message': '請選擇圖片檔案'}), 400

    file = request.files['logo']
    if file.filename == '':
        return jsonify({'success': False, 'message': '請選擇圖片檔案'}), 400

    if not allowed_logo_file(file.filename):
        return jsonify({
            'success': False,
            'message': f'不支援的檔案格式，允許: {", ".join(ALLOWED_LOGO_EXTENSIONS)}'
        }), 400

    # 檢查檔案大小
    file.seek(0, 2)  # 移到檔案結尾
    size = file.tell()
    file.seek(0)  # 移回開頭

    if size > MAX_LOGO_SIZE:
        return jsonify({
            'success': False,
            'message': f'檔案過大，上限 {MAX_LOGO_SIZE // 1024 // 1024}MB'
        }), 400

    # 刪除舊 Logo（如果有）
    old_logo_path = org.get_setting('logo_path')
    if old_logo_path:
        old_full_path = os.path.join(current_app.static_folder, old_logo_path)
        if os.path.exists(old_full_path):
            try:
                os.remove(old_full_path)
            except OSError:
                pass

    # 儲存新 Logo
    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = f'{org.secure_code}.{ext}'
    relative_path = f'uploads/logos/{filename}'
    full_path = os.path.join(current_app.static_folder, relative_path)

    try:
        file.save(full_path)
        org.set_setting('logo_path', relative_path)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Logo 上傳成功',
            'data': {
                'logo_url': f'/static/{relative_path}'
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'上傳失敗: {str(e)}'}), 500


@api_enterprise_settings.route('/logo', methods=['DELETE'])
@admin_required
def delete_logo():
    """刪除企業 Logo"""
    org = current_user.organization
    if not org:
        return jsonify({'success': False, 'message': '找不到企業'}), 404

    logo_path = org.get_setting('logo_path')
    if not logo_path:
        return jsonify({'success': False, 'message': '尚未上傳 Logo'}), 400

    # 刪除檔案
    full_path = os.path.join(current_app.static_folder, logo_path)
    if os.path.exists(full_path):
        try:
            os.remove(full_path)
        except OSError:
            pass

    # 清除設定
    org.set_setting('logo_path', None)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Logo 已刪除'
    })


# ==================== SMTP 設定 ====================

@api_enterprise_settings.route('/smtp', methods=['GET'])
@admin_required
def list_smtp_configs():
    """列出所有 SMTP 設定"""
    configs = ResourceGateway.filter(
        SmtpConfig,
        is_deleted=False,
        order_by='priority'
    )

    return jsonify({
        'success': True,
        'data': [config.to_dict() for config in configs]
    })


@api_enterprise_settings.route('/smtp', methods=['POST'])
@admin_required
def create_smtp_config():
    """
    新增 SMTP 設定

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
        provider_type: 提供者類型
        priority: 優先順序 (預設 100)
        is_default: 是否為預設
        is_active: 是否啟用 (預設 true)
    """
    data = request.get_json()

    if not data:
        return jsonify({'success': False, 'message': '請提供資料'}), 400

    # 必填欄位驗證
    required_fields = ['name', 'smtp_host', 'username', 'password', 'from_email']
    for field in required_fields:
        if not data.get(field):
            return jsonify({'success': False, 'message': f'請填寫 {field}'}), 400

    # 如果設為預設，取消其他預設
    if data.get('is_default'):
        existing_defaults = ResourceGateway.filter(
            SmtpConfig,
            is_default=True,
            is_deleted=False
        )
        for config in existing_defaults:
            config.is_default = False

    # 建立設定
    config = SmtpConfig(
        org_secure_code=current_user.org_secure_code,
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
        'message': 'SMTP 設定已建立',
        'data': config.to_dict()
    }), 201


@api_enterprise_settings.route('/smtp/<secure_code>', methods=['GET'])
@admin_required
def get_smtp_config(secure_code):
    """取得 SMTP 設定詳情（含密碼）"""
    config = ResourceGateway.get_by(
        SmtpConfig,
        secure_code=secure_code,
        is_deleted=False
    )

    if not config:
        return jsonify({'success': False, 'message': '設定不存在'}), 404

    return jsonify({
        'success': True,
        'data': config.to_dict(include_password=True)
    })


@api_enterprise_settings.route('/smtp/<secure_code>', methods=['PUT'])
@admin_required
def update_smtp_config(secure_code):
    """更新 SMTP 設定"""
    config = ResourceGateway.get_by(
        SmtpConfig,
        secure_code=secure_code,
        is_deleted=False
    )

    if not config:
        return jsonify({'success': False, 'message': '設定不存在'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': '請提供資料'}), 400

    # 如果設為預設，取消其他預設
    if data.get('is_default') and not config.is_default:
        existing_defaults = ResourceGateway.filter(
            SmtpConfig,
            is_default=True,
            is_deleted=False
        )
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
        'message': 'SMTP 設定已更新',
        'data': config.to_dict()
    })


@api_enterprise_settings.route('/smtp/<secure_code>', methods=['DELETE'])
@admin_required
def delete_smtp_config(secure_code):
    """刪除 SMTP 設定（軟刪除）"""
    config = ResourceGateway.get_by(
        SmtpConfig,
        secure_code=secure_code,
        is_deleted=False
    )

    if not config:
        return jsonify({'success': False, 'message': '設定不存在'}), 404

    config.is_deleted = True
    config.deleted_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'SMTP 設定已刪除'
    })


@api_enterprise_settings.route('/smtp/test', methods=['POST'])
@admin_required
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
        return jsonify({'success': False, 'message': '請提供資料'}), 400

    required_fields = ['smtp_host', 'smtp_port', 'username', 'password']
    for field in required_fields:
        if not data.get(field):
            return jsonify({'success': False, 'message': f'請填寫 {field}'}), 400

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


@api_enterprise_settings.route('/smtp/<secure_code>/test', methods=['POST'])
@admin_required
def test_saved_smtp_config(secure_code):
    """測試已儲存的 SMTP 設定"""
    config = ResourceGateway.get_by(
        SmtpConfig,
        secure_code=secure_code,
        is_deleted=False
    )

    if not config:
        return jsonify({'success': False, 'message': '設定不存在'}), 404

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


@api_enterprise_settings.route('/smtp/presets', methods=['GET'])
@admin_required
def get_smtp_presets():
    """取得常用 SMTP 伺服器預設值"""
    return jsonify({
        'success': True,
        'data': SmtpConfig.PROVIDER_PRESETS
    })


# ==================== Telegram 設定 ====================

@api_enterprise_settings.route('/telegram', methods=['GET'])
@admin_required
def list_telegram_configs():
    """列出所有 Telegram 設定"""
    configs = ResourceGateway.filter(
        TelegramConfig,
        is_deleted=False,
        order_by='name'
    )

    return jsonify({
        'success': True,
        'data': [config.to_dict() for config in configs]
    })


@api_enterprise_settings.route('/telegram', methods=['POST'])
@admin_required
def create_telegram_config():
    """
    新增 Telegram 設定

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
        org_secure_code=current_user.org_secure_code,
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


@api_enterprise_settings.route('/telegram/<secure_code>', methods=['GET'])
@admin_required
def get_telegram_config(secure_code):
    """取得 Telegram 設定詳情（含完整 token）"""
    config = ResourceGateway.get_by(
        TelegramConfig,
        secure_code=secure_code,
        is_deleted=False
    )

    if not config:
        return jsonify({'success': False, 'message': '設定不存在'}), 404

    return jsonify({
        'success': True,
        'data': config.to_dict(hide_token=False)
    })


@api_enterprise_settings.route('/telegram/<secure_code>', methods=['PUT'])
@admin_required
def update_telegram_config(secure_code):
    """更新 Telegram 設定"""
    config = ResourceGateway.get_by(
        TelegramConfig,
        secure_code=secure_code,
        is_deleted=False
    )

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


@api_enterprise_settings.route('/telegram/<secure_code>', methods=['DELETE'])
@admin_required
def delete_telegram_config(secure_code):
    """刪除 Telegram 設定（軟刪除）"""
    config = ResourceGateway.get_by(
        TelegramConfig,
        secure_code=secure_code,
        is_deleted=False
    )

    if not config:
        return jsonify({'success': False, 'message': '設定不存在'}), 404

    config.is_deleted = True
    config.deleted_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Telegram 設定已刪除'
    })


@api_enterprise_settings.route('/telegram/test', methods=['POST'])
@admin_required
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
        test_message=data.get('test_message', '[BeakMask] Telegram 連線測試')
    )

    return jsonify({
        'success': result['success'],
        'message': result['message'],
        'bot_info': result.get('bot_info')
    })


@api_enterprise_settings.route('/telegram/<secure_code>/test', methods=['POST'])
@admin_required
def test_saved_telegram_config(secure_code):
    """測試已儲存的 Telegram 設定"""
    config = ResourceGateway.get_by(
        TelegramConfig,
        secure_code=secure_code,
        is_deleted=False
    )

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
        test_message=data.get('test_message', '[BeakMask] Telegram 連線測試')
    )

    return jsonify({
        'success': result['success'],
        'message': result['message'],
        'bot_info': result.get('bot_info')
    })


# ==================== 收件人群組設定 ====================

@api_enterprise_settings.route('/recipient-groups', methods=['GET'])
@admin_required
def list_recipient_groups():
    """列出所有收件人群組"""
    groups = ResourceGateway.filter(
        RecipientGroup,
        is_deleted=False,
        order_by='priority'
    )

    return jsonify({
        'success': True,
        'data': [g.to_dict(include_recipient_count=True) for g in groups]
    })


@api_enterprise_settings.route('/recipient-groups', methods=['POST'])
@admin_required
def create_recipient_group():
    """
    新增收件人群組

    Body:
        name: 群組名稱 (必填)
        description: 描述
        priority: 優先順序 (預設 100)
        is_active: 是否啟用 (預設 true)
        included_units: [{"id": "xxx", "include_children": bool}, ...]
        included_users: ["user_id", ...]
        excluded_units: ["unit_id", ...]
        excluded_users: ["user_id", ...]
    """
    data = request.get_json()

    if not data:
        return jsonify({'success': False, 'message': '請提供資料'}), 400

    if not data.get('name'):
        return jsonify({'success': False, 'message': '請填寫群組名稱'}), 400

    # 建立群組
    group = RecipientGroup(
        org_secure_code=current_user.org_secure_code,
        name=data['name'],
        description=data.get('description'),
        priority=data.get('priority', 100),
        is_active=data.get('is_active', True)
    )

    # 設定收件人
    group.included_units = data.get('included_units', [])
    group.included_users = data.get('included_users', [])
    group.excluded_units = data.get('excluded_units', [])
    group.excluded_users = data.get('excluded_users', [])

    db.session.add(group)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': '收件人群組已建立',
        'data': group.to_dict(include_recipient_count=True)
    }), 201


@api_enterprise_settings.route('/recipient-groups/<secure_code>', methods=['GET'])
@admin_required
def get_recipient_group(secure_code):
    """取得收件人群組詳情"""
    group = ResourceGateway.get_by(
        RecipientGroup,
        secure_code=secure_code,
        is_deleted=False
    )

    if not group:
        return jsonify({'success': False, 'message': '群組不存在'}), 404

    return jsonify({
        'success': True,
        'data': group.to_dict(include_recipient_count=True)
    })


@api_enterprise_settings.route('/recipient-groups/<secure_code>', methods=['PUT'])
@admin_required
def update_recipient_group(secure_code):
    """更新收件人群組"""
    group = ResourceGateway.get_by(
        RecipientGroup,
        secure_code=secure_code,
        is_deleted=False
    )

    if not group:
        return jsonify({'success': False, 'message': '群組不存在'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': '請提供資料'}), 400

    # 更新基本欄位
    if 'name' in data:
        group.name = data['name']
    if 'description' in data:
        group.description = data['description']
    if 'priority' in data:
        group.priority = data['priority']
    if 'is_active' in data:
        group.is_active = data['is_active']

    # 更新收件人設定
    if 'included_units' in data:
        group.included_units = data['included_units']
    if 'included_users' in data:
        group.included_users = data['included_users']
    if 'excluded_units' in data:
        group.excluded_units = data['excluded_units']
    if 'excluded_users' in data:
        group.excluded_users = data['excluded_users']

    db.session.commit()

    return jsonify({
        'success': True,
        'message': '收件人群組已更新',
        'data': group.to_dict(include_recipient_count=True)
    })


@api_enterprise_settings.route('/recipient-groups/<secure_code>', methods=['DELETE'])
@admin_required
def delete_recipient_group(secure_code):
    """刪除收件人群組（軟刪除）"""
    group = ResourceGateway.get_by(
        RecipientGroup,
        secure_code=secure_code,
        is_deleted=False
    )

    if not group:
        return jsonify({'success': False, 'message': '群組不存在'}), 404

    group.is_deleted = True
    group.deleted_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'message': '收件人群組已刪除'
    })


@api_enterprise_settings.route('/recipient-groups/<secure_code>/resolve', methods=['GET'])
@admin_required
def resolve_recipient_group(secure_code):
    """
    解析收件人群組，取得最終收件人列表

    Returns:
        recipients: [{"user_id": "xxx", "email": "xxx", "name": "xxx"}, ...]
    """
    group = ResourceGateway.get_by(
        RecipientGroup,
        secure_code=secure_code,
        is_deleted=False
    )

    if not group:
        return jsonify({'success': False, 'message': '群組不存在'}), 404

    recipients = group.resolve_recipients()

    return jsonify({
        'success': True,
        'data': {
            'group_id': group.secure_code,
            'group_name': group.name,
            'recipients': recipients,
            'count': len(recipients)
        }
    })


# ==================== 組織樹與用戶查詢（供收件人設定使用）====================

@api_enterprise_settings.route('/org-tree', methods=['GET'])
@admin_required
def get_org_tree():
    """
    取得組織樹結構（用於收件人設定的拖拉選擇）

    Returns:
        units: 扁平化的部門列表，包含層級資訊
    """
    units = ResourceGateway.filter(
        OrganizationalUnit,
        is_deleted=False,
        is_active=True,
        order_by='level,sort_order,name'
    )

    # 計算每個部門的成員數
    result = []
    for unit in units:
        member_count = User.query.filter(
            User.primary_unit_secure_code == unit.secure_code,
            User.org_secure_code == current_user.org_secure_code,
            User.is_active == True,
            User.is_deleted == False
        ).count()

        result.append({
            'id': unit.secure_code,
            'code': unit.code,
            'name': unit.name,
            'full_path': unit.full_path,
            'level': unit.level,
            'parent_id': unit.parent_secure_code,
            'unit_type': unit.unit_type,
            'member_count': member_count
        })

    return jsonify({
        'success': True,
        'data': result
    })


@api_enterprise_settings.route('/org-users', methods=['GET'])
@admin_required
def get_org_users():
    """
    取得企業所有用戶列表（用於收件人設定）

    Query params:
        unit_id: 篩選特定部門的用戶
        search: 搜尋關鍵字（姓名、email）

    Returns:
        users: [{"id": "xxx", "name": "xxx", "email": "xxx", "unit_name": "xxx"}, ...]
    """
    query = User.query.filter(
        User.org_secure_code == current_user.org_secure_code,
        User.is_active == True,
        User.is_deleted == False
    )

    # 篩選部門
    unit_id = request.args.get('unit_id')
    if unit_id:
        query = query.filter(User.primary_unit_secure_code == unit_id)

    # 搜尋
    search = request.args.get('search', '').strip()
    if search:
        search_pattern = f'%{search}%'
        query = query.filter(
            db.or_(
                User.display_name.ilike(search_pattern),
                User.native_name.ilike(search_pattern),
                User.english_name.ilike(search_pattern),
                User.email.ilike(search_pattern)
            )
        )

    users = query.order_by(User.display_name).limit(100).all()

    result = []
    for user in users:
        # 取得用戶所屬部門名稱
        unit_name = None
        if user.primary_unit_secure_code:
            unit = OrganizationalUnit.query.filter_by(
                secure_code=user.primary_unit_secure_code,
                is_deleted=False
            ).first()
            if unit:
                unit_name = unit.name

        result.append({
            'id': user.secure_code,
            'name': user.display_name or user.username,
            'email': user.backup_email_1 or user.email,  # 系統通知專用信箱
            'primary_email': user.email,
            'unit_id': user.primary_unit_secure_code,
            'unit_name': unit_name
        })

    return jsonify({
        'success': True,
        'data': result
    })
