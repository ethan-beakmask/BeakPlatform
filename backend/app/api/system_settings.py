"""
BeakPlatform System Settings API
系統設定 API - 僅系統管理員可用

[標準 AUTH-02] 使用 @system_admin_required 裝飾器

端點：
E-MailRelay:
- GET    /api/system-settings/emailrelay              取得設定
- PUT    /api/system-settings/emailrelay              更新設定
- GET    /api/system-settings/emailrelay/auth         取得認證
- PUT    /api/system-settings/emailrelay/auth         更新認證
- POST   /api/system-settings/emailrelay/test         測試發送
- POST   /api/system-settings/emailrelay/service/<action>  服務控制

SMTP 設定 (系統級):
- GET    /api/system-settings/smtp                    列出 SMTP 設定
- POST   /api/system-settings/smtp                    新增 SMTP 設定
- GET    /api/system-settings/smtp/<id>               取得設定詳情
- PUT    /api/system-settings/smtp/<id>               更新 SMTP 設定
- DELETE /api/system-settings/smtp/<id>               刪除 SMTP 設定
- POST   /api/system-settings/smtp/test               測試連線
- POST   /api/system-settings/smtp/<id>/test          測試已儲存設定

Telegram 設定 (系統級):
- GET    /api/system-settings/telegram                列出 Telegram 設定
- POST   /api/system-settings/telegram                新增 Telegram 設定
- GET    /api/system-settings/telegram/<id>           取得設定詳情
- PUT    /api/system-settings/telegram/<id>           更新 Telegram 設定
- DELETE /api/system-settings/telegram/<id>           刪除 Telegram 設定
- POST   /api/system-settings/telegram/test           測試連線
- POST   /api/system-settings/telegram/<id>/test      測試已儲存設定

收件人群組 (系統級):
- GET    /api/system-settings/recipient-groups        列出群組
- POST   /api/system-settings/recipient-groups        新增群組
- GET    /api/system-settings/recipient-groups/<id>   取得群組詳情
- PUT    /api/system-settings/recipient-groups/<id>   更新群組
- DELETE /api/system-settings/recipient-groups/<id>   刪除群組
- GET    /api/system-settings/recipient-groups/<id>/resolve  解析收件人

套件版本:
- GET    /api/system-settings/package-versions        查詢套件版本

稽核設定:
- GET    /api/system-settings/audit                   取得稽核設定
- PUT    /api/system-settings/audit                   更新稽核設定
"""
import os
import base64
import subprocess
from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_login import current_user

from ..security.decorators import system_admin_required
from ..models.system_setting import SystemSetting
from ..models import SmtpConfig, TelegramConfig, RecipientGroup
from ..constants import SYSTEM_ORG_CODE
from .. import db
from ..services.emailrelay_config import get_paths as _get_emailrelay_paths
from ..services.emailrelay_config import validate_install_dir as _validate_install_dir

api_system_settings = Blueprint('api_system_settings', __name__, url_prefix='/api/system-settings')


# =============================================================================
# E-MailRelay 設定
# =============================================================================


@api_system_settings.route('/emailrelay', methods=['GET'])
@system_admin_required
def get_emailrelay_settings():
    """
    取得 E-MailRelay 設定

    包含：
    - 基本設定（從 SystemSetting 讀取）
    - Auth 設定（從檔案讀取並解碼）
    - 服務狀態
    """
    paths = _get_emailrelay_paths()

    # 基本設定
    settings = {
        'enabled': SystemSetting.get('emailrelay_enabled', True),
        'install_dir': paths['install_dir'],
        'spool_dir': paths['spool_dir'],
        'from_email': SystemSetting.get('emailrelay_from_email', 'system@beakplatform.local'),
        'from_name': SystemSetting.get('emailrelay_from_name', 'BeakPlatform System'),
    }

    # Auth 設定（從檔案讀取）
    auth_config = _read_emailrelay_auth()
    settings['auth'] = auth_config

    # 服務狀態
    settings['service'] = _get_emailrelay_service_status()

    return jsonify({
        'success': True,
        'data': settings
    })


@api_system_settings.route('/emailrelay', methods=['PUT'])
@system_admin_required
def update_emailrelay_settings():
    """
    更新 E-MailRelay 基本設定

    Request JSON:
    {
        "enabled": true,
        "install_dir": "/opt/E-MailRelay",
        "from_email": "system@beakmask.local",
        "from_name": "BeakMask System"
    }
    """
    data = request.get_json()

    updated = []

    # 安裝路徑變更需要驗證
    if 'install_dir' in data:
        new_dir = data['install_dir'].strip().rstrip('/')
        if not new_dir:
            return jsonify({
                'success': False,
                'message': '安裝路徑不可為空'
            }), 400

        is_valid, errors = _validate_install_dir(new_dir)
        if not is_valid:
            return jsonify({
                'success': False,
                'message': '安裝路徑驗證失敗',
                'errors': errors
            }), 400

        SystemSetting.set(
            'emailrelay_install_dir',
            new_dir,
            updated_by=current_user.username,
            value_type='string',
            description='E-MailRelay 安裝目錄',
            category='emailrelay'
        )
        updated.append('install_dir')

        # 同步更新 systemd service 檔案
        svc_result = _update_systemd_service(new_dir)
        if not svc_result['success']:
            logger.warning(
                f"[EMAILRELAY] systemd service 更新失敗: {svc_result.get('error')}"
            )

    if 'enabled' in data:
        SystemSetting.set(
            'emailrelay_enabled',
            data['enabled'],
            updated_by=current_user.username,
            value_type='boolean',
            description='E-MailRelay 是否啟用',
            category='emailrelay'
        )
        updated.append('enabled')

    if 'from_email' in data:
        SystemSetting.set(
            'emailrelay_from_email',
            data['from_email'],
            updated_by=current_user.username,
            value_type='string',
            description='發件人 Email',
            category='emailrelay'
        )
        updated.append('from_email')

    if 'from_name' in data:
        SystemSetting.set(
            'emailrelay_from_name',
            data['from_name'],
            updated_by=current_user.username,
            value_type='string',
            description='發件人名稱',
            category='emailrelay'
        )
        updated.append('from_name')

    return jsonify({
        'success': True,
        'message': f'已更新 {len(updated)} 項設定',
        'updated': updated
    })


@api_system_settings.route('/emailrelay/auth', methods=['GET'])
@system_admin_required
def get_emailrelay_auth():
    """
    取得 E-MailRelay SMTP 認證設定

    讀取並解碼 emailrelay.auth 檔案
    """
    auth_config = _read_emailrelay_auth()

    return jsonify({
        'success': True,
        'data': auth_config
    })


@api_system_settings.route('/emailrelay/auth', methods=['PUT'])
@system_admin_required
def update_emailrelay_auth():
    """
    更新 E-MailRelay SMTP 認證設定

    接收 email 和原始密碼，自動 Base64 編碼並儲存

    Request JSON:
    {
        "email": "your.email@gmail.com",
        "password": "xxxx xxxx xxxx xxxx"
    }
    """
    data = request.get_json()

    email = data.get('email', '').strip()
    password = data.get('password', '').strip()

    if not email:
        return jsonify({'success': False, 'message': '請填寫 Email'}), 400

    if not password:
        return jsonify({'success': False, 'message': '請填寫應用程式密碼'}), 400

    auth_file = _get_emailrelay_paths()['auth_file']
    auth_dir = os.path.dirname(auth_file)

    try:
        # 確保目錄存在
        if not os.path.exists(auth_dir):
            return jsonify({
                'success': False,
                'message': f'E-MailRelay 目錄不存在: {auth_dir}'
            }), 400

        # Base64 編碼
        email_b64 = base64.b64encode(email.encode('utf-8')).decode('utf-8')
        password_b64 = base64.b64encode(password.encode('utf-8')).decode('utf-8')

        # 產生 auth 檔案內容
        auth_content = f'client plain:b {email_b64} {password_b64}\n'

        # 寫入檔案
        with open(auth_file, 'w') as f:
            f.write(auth_content)

        # 設定權限為 600
        os.chmod(auth_file, 0o600)

        return jsonify({
            'success': True,
            'message': 'SMTP 認證設定已儲存',
            'data': {
                'email': email,
                'file': auth_file,
                'format': 'plain:b (Base64 encoded)'
            }
        })

    except PermissionError:
        return jsonify({
            'success': False,
            'message': '無權限寫入 Auth 檔案，請檢查目錄權限'
        }), 403
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'儲存失敗: {str(e)}'
        }), 500


@api_system_settings.route('/emailrelay/test', methods=['POST'])
@system_admin_required
def test_emailrelay():
    """
    測試 E-MailRelay 並發送測試郵件

    Request JSON (可選):
    {
        "recipient": "test@example.com"
    }
    """
    import tempfile
    from datetime import datetime
    from email.mime.text import MIMEText
    from email.utils import formatdate, make_msgid

    data = request.get_json() or {}

    # 1. 檢查 spool 目錄
    spool_dir = _get_emailrelay_paths()['spool_dir']
    if not os.path.exists(spool_dir):
        return jsonify({
            'success': False,
            'message': f'Spool 目錄不存在: {spool_dir}',
            'data': {'step': 'directory_check'}
        }), 400

    if not os.access(spool_dir, os.W_OK):
        return jsonify({
            'success': False,
            'message': f'Spool 目錄無寫入權限: {spool_dir}',
            'data': {'step': 'directory_check'}
        }), 400

    # 2. 取得收件人
    recipient = data.get('recipient', '').strip()

    if not recipient:
        # 從 Auth 檔案讀取 email
        auth_config = _read_emailrelay_auth()
        if auth_config.get('configured'):
            recipient = auth_config.get('email', '')

    if not recipient:
        return jsonify({
            'success': False,
            'message': '請指定收件人或先設定 SMTP 認證',
            'data': {'step': 'get_recipient'}
        }), 400

    # 3. 取得發件人設定
    from_email = SystemSetting.get('emailrelay_from_email', 'system@beakplatform.local')
    from_name = SystemSetting.get('emailrelay_from_name', 'BeakPlatform System')

    # 4. 建立測試郵件
    now = datetime.now()
    subject = f'[BeakPlatform] E-MailRelay 測試郵件 - {now.strftime("%Y-%m-%d %H:%M:%S")}'
    body = f'''這是一封來自 BeakPlatform 系統的測試郵件。

發送時間：{now.strftime("%Y-%m-%d %H:%M:%S")}
發件人：{from_name} <{from_email}>
收件人：{recipient}
Spool 目錄：{spool_dir}

如果您收到此郵件，表示 E-MailRelay 設定正確運作中。

---
BeakPlatform System
'''

    msg = MIMEText(body, 'plain', 'utf-8')
    msg['From'] = f'{from_name} <{from_email}>' if from_name else from_email
    msg['To'] = recipient
    msg['Subject'] = subject
    msg['Date'] = formatdate(localtime=True)
    msg['Message-ID'] = make_msgid(domain='beakplatform.local')
    msg['X-BeakPlatform-Test'] = 'true'

    eml_content = msg.as_string()

    # 5. 使用 emailrelay-submit 提交郵件
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.eml', delete=False, encoding='utf-8'
        ) as tmp_file:
            tmp_file.write(eml_content)
            tmp_filepath = tmp_file.name

        cmd = [
            _get_emailrelay_paths()['submit_bin'],
            '--spool-dir', spool_dir,
            '--from', from_email,
            '--input-file', tmp_filepath,
            '--verbose',
            recipient
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        # 清理暫存檔
        if os.path.exists(tmp_filepath):
            os.unlink(tmp_filepath)

        if result.returncode != 0:
            return jsonify({
                'success': False,
                'message': f'emailrelay-submit 失敗: {result.stderr}',
                'data': {'step': 'submit', 'stderr': result.stderr}
            }), 400

        return jsonify({
            'success': True,
            'message': f'測試郵件已發送至 {recipient}',
            'data': {
                'recipient': recipient,
                'spool_dir': spool_dir,
                'submit_output': result.stdout
            }
        })

    except subprocess.TimeoutExpired:
        return jsonify({
            'success': False,
            'message': 'emailrelay-submit 執行逾時',
            'data': {'step': 'submit'}
        }), 400
    except FileNotFoundError:
        return jsonify({
            'success': False,
            'message': '找不到 emailrelay-submit 工具，請確認 E-MailRelay 已安裝',
            'data': {'step': 'submit'}
        }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'發送測試郵件失敗: {str(e)}',
            'data': {'step': 'submit'}
        }), 500


@api_system_settings.route('/emailrelay/service/<action>', methods=['POST'])
@system_admin_required
def control_emailrelay_service(action):
    """
    控制 E-MailRelay 服務

    Args:
        action: start, stop, restart, status
    """
    if action not in ('start', 'stop', 'restart', 'status'):
        return jsonify({
            'success': False,
            'message': f'不支援的操作: {action}'
        }), 400

    service_name = 'emailrelay'

    try:
        if action == 'status':
            status = _get_emailrelay_service_status()
            return jsonify({
                'success': True,
                'data': status
            })

        # 執行 systemctl 操作
        result = subprocess.run(
            ['sudo', 'systemctl', action, service_name],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            return jsonify({
                'success': False,
                'message': f'操作失敗: {result.stderr}'
            }), 400

        # 取得新狀態
        status = _get_emailrelay_service_status()

        return jsonify({
            'success': True,
            'message': f'服務已 {action}',
            'data': status
        })

    except subprocess.TimeoutExpired:
        return jsonify({
            'success': False,
            'message': '操作逾時'
        }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'操作失敗: {str(e)}'
        }), 500


# =============================================================================
# Helper Functions
# =============================================================================

def _update_systemd_service(install_dir: str) -> dict:
    """更新 systemd service 檔案以對應新的安裝路徑"""
    import getpass
    user = getpass.getuser()

    service_content = f"""[Unit]
Description=E-MailRelay
After=network-online.target
Wants=network-online.target

[Service]
Type=forking
Restart=on-failure
RestartSec=10
User={user}
Group={user}
WorkingDirectory={install_dir}
ExecStart={install_dir}/sbin/emailrelay --as-server --pid-file {install_dir}/emailrelay.pid {install_dir}/etc/emailrelay.conf
ExecStop=/bin/kill -15 $MAINPID
PIDFile={install_dir}/emailrelay.pid

[Install]
WantedBy=multi-user.target
"""

    try:
        result = subprocess.run(
            ['sudo', 'tee', '/etc/systemd/system/emailrelay.service'],
            input=service_content,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            return {'success': False, 'error': result.stderr}

        subprocess.run(
            ['sudo', 'systemctl', 'daemon-reload'],
            capture_output=True, text=True, timeout=10
        )

        return {'success': True}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def _read_emailrelay_auth() -> dict:
    """讀取並解碼 emailrelay.auth 檔案"""
    auth_file_path = _get_emailrelay_paths()['auth_file']
    if not os.path.exists(auth_file_path):
        return {
            'configured': False,
            'email': '',
            'password': '',
            'message': 'Auth 檔案尚未建立'
        }

    try:
        with open(auth_file_path, 'r') as f:
            content = f.read().strip()

        parts = content.split()

        if len(parts) < 4:
            return {
                'configured': False,
                'email': '',
                'password': '',
                'message': f'Auth 檔案格式不正確，欄位數: {len(parts)}'
            }

        auth_type = parts[1]  # plain 或 plain:b

        if auth_type == 'plain:b':
            # Base64 編碼格式
            try:
                email = base64.b64decode(parts[2]).decode('utf-8')
                password = base64.b64decode(parts[3]).decode('utf-8')
            except Exception:
                return {
                    'configured': False,
                    'email': '',
                    'password': '',
                    'message': 'Base64 解碼失敗'
                }
        elif auth_type == 'plain':
            # 純文字格式
            email = parts[2]
            password = parts[3]
        else:
            return {
                'configured': False,
                'email': '',
                'password': '',
                'message': f'不支援的認證類型: {auth_type}'
            }

        return {
            'configured': True,
            'email': email,
            'password': password,
            'format': auth_type
        }

    except PermissionError:
        return {
            'configured': False,
            'email': '',
            'password': '',
            'message': '無權限讀取 Auth 檔案'
        }
    except Exception as e:
        return {
            'configured': False,
            'email': '',
            'password': '',
            'message': f'讀取失敗: {str(e)}'
        }


def _get_emailrelay_service_status() -> dict:
    """取得 E-MailRelay 服務狀態"""
    service_name = 'emailrelay'

    result = {
        'name': service_name,
        'status': 'unknown',
        'running': False,
        'enabled': False
    }

    try:
        # 檢查是否啟動中
        active_result = subprocess.run(
            ['systemctl', 'is-active', service_name],
            capture_output=True,
            text=True,
            timeout=5
        )
        result['status'] = active_result.stdout.strip()
        result['running'] = active_result.returncode == 0

        # 檢查是否開機啟動
        enabled_result = subprocess.run(
            ['systemctl', 'is-enabled', service_name],
            capture_output=True,
            text=True,
            timeout=5
        )
        result['enabled'] = enabled_result.returncode == 0

    except Exception:
        pass

    # 取得版本
    try:
        version_result = subprocess.run(
            [_get_emailrelay_paths()['server_bin'], '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        for line in version_result.stdout.split('\n'):
            if 'E-MailRelay' in line and 'V' in line:
                parts = line.split('V')
                if len(parts) >= 2:
                    result['version'] = parts[1].strip().split()[0]
                    break
    except Exception:
        result['version'] = None

    return result


# =============================================================================
# SMTP 設定 (系統級)
# =============================================================================

@api_system_settings.route('/smtp', methods=['GET'])
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


@api_system_settings.route('/smtp', methods=['POST'])
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
        return jsonify({'success': False, 'message': '請提供資料'}), 400

    # 必填欄位驗證
    required_fields = ['name', 'smtp_host', 'username', 'password', 'from_email']
    for field in required_fields:
        if not data.get(field):
            return jsonify({'success': False, 'message': f'請填寫 {field}'}), 400

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
        'message': 'SMTP 設定已建立',
        'data': config.to_dict()
    }), 201


@api_system_settings.route('/smtp/<secure_code>', methods=['GET'])
@system_admin_required
def get_smtp_config(secure_code):
    """取得 SMTP 設定詳情（含密碼）"""
    config = SmtpConfig.query.filter_by(
        secure_code=secure_code,
        org_secure_code=SYSTEM_ORG_CODE,
        is_deleted=False
    ).first()

    if not config:
        return jsonify({'success': False, 'message': '設定不存在'}), 404

    return jsonify({
        'success': True,
        'data': config.to_dict(include_password=True)
    })


@api_system_settings.route('/smtp/<secure_code>', methods=['PUT'])
@system_admin_required
def update_smtp_config(secure_code):
    """更新 SMTP 設定"""
    config = SmtpConfig.query.filter_by(
        secure_code=secure_code,
        org_secure_code=SYSTEM_ORG_CODE,
        is_deleted=False
    ).first()

    if not config:
        return jsonify({'success': False, 'message': '設定不存在'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': '請提供資料'}), 400

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
        'message': 'SMTP 設定已更新',
        'data': config.to_dict()
    })


@api_system_settings.route('/smtp/<secure_code>', methods=['DELETE'])
@system_admin_required
def delete_smtp_config(secure_code):
    """刪除 SMTP 設定（軟刪除）"""
    config = SmtpConfig.query.filter_by(
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
        'message': 'SMTP 設定已刪除'
    })


@api_system_settings.route('/smtp/test', methods=['POST'])
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


@api_system_settings.route('/smtp/<secure_code>/test', methods=['POST'])
@system_admin_required
def test_saved_smtp_config(secure_code):
    """測試已儲存的 SMTP 設定"""
    config = SmtpConfig.query.filter_by(
        secure_code=secure_code,
        org_secure_code=SYSTEM_ORG_CODE,
        is_deleted=False
    ).first()

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


@api_system_settings.route('/smtp/presets', methods=['GET'])
@system_admin_required
def get_smtp_presets():
    """取得常用 SMTP 伺服器預設值"""
    return jsonify({
        'success': True,
        'data': SmtpConfig.PROVIDER_PRESETS
    })


# =============================================================================
# Telegram 設定 (系統級)
# =============================================================================

@api_system_settings.route('/telegram', methods=['GET'])
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


@api_system_settings.route('/telegram', methods=['POST'])
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


@api_system_settings.route('/telegram/<secure_code>', methods=['GET'])
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


@api_system_settings.route('/telegram/<secure_code>', methods=['PUT'])
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


@api_system_settings.route('/telegram/<secure_code>', methods=['DELETE'])
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


@api_system_settings.route('/telegram/test', methods=['POST'])
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


@api_system_settings.route('/telegram/<secure_code>/test', methods=['POST'])
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


# =============================================================================
# 收件人群組 (系統級)
# =============================================================================

@api_system_settings.route('/recipient-groups', methods=['GET'])
@system_admin_required
def list_recipient_groups():
    """列出所有系統級收件人群組"""
    groups = RecipientGroup.query.filter_by(
        org_secure_code=SYSTEM_ORG_CODE,
        is_deleted=False
    ).order_by(RecipientGroup.priority).all()

    return jsonify({
        'success': True,
        'data': [g.to_dict() for g in groups]
    })


@api_system_settings.route('/recipient-groups', methods=['POST'])
@system_admin_required
def create_recipient_group():
    """
    新增系統級收件人群組

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
        org_secure_code=SYSTEM_ORG_CODE,
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
        'data': group.to_dict()
    }), 201


@api_system_settings.route('/recipient-groups/<secure_code>', methods=['GET'])
@system_admin_required
def get_recipient_group(secure_code):
    """取得收件人群組詳情"""
    group = RecipientGroup.query.filter_by(
        secure_code=secure_code,
        org_secure_code=SYSTEM_ORG_CODE,
        is_deleted=False
    ).first()

    if not group:
        return jsonify({'success': False, 'message': '群組不存在'}), 404

    return jsonify({
        'success': True,
        'data': group.to_dict()
    })


@api_system_settings.route('/recipient-groups/<secure_code>', methods=['PUT'])
@system_admin_required
def update_recipient_group(secure_code):
    """更新收件人群組"""
    group = RecipientGroup.query.filter_by(
        secure_code=secure_code,
        org_secure_code=SYSTEM_ORG_CODE,
        is_deleted=False
    ).first()

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
        'data': group.to_dict()
    })


@api_system_settings.route('/recipient-groups/<secure_code>', methods=['DELETE'])
@system_admin_required
def delete_recipient_group(secure_code):
    """刪除收件人群組（軟刪除）"""
    group = RecipientGroup.query.filter_by(
        secure_code=secure_code,
        org_secure_code=SYSTEM_ORG_CODE,
        is_deleted=False
    ).first()

    if not group:
        return jsonify({'success': False, 'message': '群組不存在'}), 404

    group.is_deleted = True
    group.deleted_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'message': '收件人群組已刪除'
    })


@api_system_settings.route('/recipient-groups/<secure_code>/resolve', methods=['GET'])
@system_admin_required
def resolve_recipient_group(secure_code):
    """
    解析收件人群組，取得最終收件人列表

    注意：系統級群組的 resolve 會嘗試解析所有企業的用戶
    """
    group = RecipientGroup.query.filter_by(
        secure_code=secure_code,
        org_secure_code=SYSTEM_ORG_CODE,
        is_deleted=False
    ).first()

    if not group:
        return jsonify({'success': False, 'message': '群組不存在'}), 404

    # 系統級群組目前不支援自動解析（跨企業邏輯複雜）
    # 返回設定內容讓前端顯示
    return jsonify({
        'success': True,
        'data': {
            'group_id': group.secure_code,
            'group_name': group.name,
            'included_units': group.included_units,
            'included_users': group.included_users,
            'excluded_units': group.excluded_units,
            'excluded_users': group.excluded_users,
            'message': '系統級群組需手動指定收件人'
        }
    })


# =============================================================================
# 套件版本查詢
# =============================================================================

import re
import time
import importlib.metadata
from concurrent.futures import ThreadPoolExecutor, as_completed
from packaging.version import Version, InvalidVersion

# 記憶體快取
_package_versions_cache = {
    'data': None,
    'cached_at': None,
    'ttl': 1800  # 30 分鐘
}

# 前端 vendor 套件定義
# header_pattern: 在檔案前 2000 字元搜尋（header 註解）
# full_pattern: header 找不到時掃描全檔（minified 內嵌版本）
FRONTEND_VENDOR_REGISTRY = [
    {
        'name': 'Bootstrap',
        'file': 'vendor/bootstrap.bundle.min.js',
        'header_pattern': r'Bootstrap\s+v([\d.]+)',
        'npm_name': 'bootstrap',
    },
    {
        'name': 'Alpine.js',
        'file': 'vendor/alpine.min.js',
        'full_pattern': r'version["\s:=]*"(\d+\.\d+\.\d+)"',
        'npm_name': 'alpinejs',
    },
    {
        'name': 'jQuery',
        'file': 'vendor/jquery.min.js',
        'header_pattern': r'jQuery\s+v([\d.]+)',
        'npm_name': 'jquery',
    },
    {
        'name': 'jsTree',
        'file': 'vendor/jstree.min.js',
        'header_pattern': r'jsTree\s+-\s+v([\d.]+)',
        'npm_name': 'jstree',
    },
    {
        'name': 'Cytoscape.js',
        'file': 'vendor/cytoscape.min.js',
        'full_pattern': r'version["\s:=]*"(\d+\.\d+\.\d+)"',
        'npm_name': 'cytoscape',
    },
    {
        'name': 'Formio',
        'file': 'vendor/formio.full.min.js',
        'header_pattern': r'[Ff]ormio[^\d]*([\d]+\.[\d]+\.[\d]+)',
        'full_pattern': r'Formio\.version\s*=\s*"(\d+\.\d+\.\d+)"',
        'npm_name': '@formio/js',
    },
    {
        'name': 'Font Awesome',
        'file': 'vendor/fontawesome/css/all.min.css',
        'header_pattern': r'Font Awesome[^\d]*([\d.]+)',
        'npm_name': '@fortawesome/fontawesome-free',
    },
]


def _parse_requirements():
    """解析 requirements.txt"""
    req_path = os.path.join(os.path.dirname(__file__), '..', '..', 'requirements.txt')
    req_path = os.path.normpath(req_path)
    packages = []

    if not os.path.exists(req_path):
        return packages

    with open(req_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            # 解析 name==version 或 name>=version 等
            match = re.match(r'^([a-zA-Z0-9_-]+)\s*([>=<~!]+)\s*([\d.]+)', line)
            if match:
                packages.append({
                    'name': match.group(1),
                    'required_version': match.group(3),
                    'operator': match.group(2),
                })
    return packages


def _get_installed_version(package_name):
    """取得已安裝版本"""
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _fetch_pypi_latest(package_name):
    """從 PyPI 取得最新版本"""
    import requests as req_lib
    try:
        resp = req_lib.get(
            f'https://pypi.org/pypi/{package_name}/json',
            timeout=3
        )
        if resp.status_code == 200:
            return resp.json().get('info', {}).get('version')
    except Exception:
        pass
    return None


def _fetch_npm_latest(package_name):
    """從 npm registry 取得最新穩定版本"""
    import requests as req_lib
    try:
        resp = req_lib.get(
            f'https://registry.npmjs.org/{package_name}',
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json()
            # 優先取 dist-tags.latest
            latest = data.get('dist-tags', {}).get('latest', '')
            # 若 latest 是穩定版，直接回傳
            if latest and _is_stable_version(latest):
                return latest
            # 否則從所有版本中找最新穩定版
            versions = list(data.get('versions', {}).keys())
            stable = [v for v in versions if _is_stable_version(v)]
            if stable:
                stable.sort(key=lambda v: _parse_version_tuple(v))
                return stable[-1]
            # 全都是預發行版本，回傳 latest tag 原值
            return latest or None
    except Exception:
        pass
    return None


def _is_stable_version(version_str):
    """判斷是否為穩定版本（不含 rc/alpha/beta/dev）"""
    return not re.search(r'(rc|alpha|beta|dev|canary|next|pre)', version_str, re.IGNORECASE)


def _parse_version_tuple(version_str):
    """將版本字串解析為可排序的 tuple"""
    m = re.match(r'(\d+)\.(\d+)\.(\d+)', version_str)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return (0, 0, 0)


def _normalize_npm_version(version_str):
    """將 npm semver 預發行版本轉換為 PEP 440 格式"""
    if not version_str:
        return version_str
    # 提取主版本號部分 (x.y.z)
    m = re.match(r'(\d+\.\d+\.\d+)', version_str)
    return m.group(1) if m else version_str


def _compare_versions(installed, latest):
    """比較版本，回傳狀態"""
    if not installed or not latest:
        return 'check_failed'
    try:
        v_installed = Version(installed)
        v_latest = Version(latest)
    except InvalidVersion:
        # npm semver 格式與 PEP 440 不相容時，嘗試只取主版本號比較
        try:
            v_installed = Version(_normalize_npm_version(installed))
            v_latest = Version(_normalize_npm_version(latest))
        except InvalidVersion:
            return 'check_failed'

    if v_installed >= v_latest:
        return 'up_to_date'
    if v_installed.major < v_latest.major:
        return 'major_update'
    return 'minor_update'


def _detect_vendor_version(entry):
    """從 vendor 檔案偵測版本（先 header，再 full scan）"""
    static_dir = os.path.join(os.path.dirname(__file__), '..', 'static')
    file_path = os.path.join(static_dir, entry['file'])
    file_path = os.path.normpath(file_path)

    if not os.path.exists(file_path):
        return None

    try:
        # 階段 1: header pattern（前 2000 字元）
        if 'header_pattern' in entry:
            with open(file_path, 'r', errors='ignore') as f:
                header = f.read(2000)
            match = re.search(entry['header_pattern'], header, re.IGNORECASE)
            if match:
                return match.group(1)

        # 階段 2: full pattern（掃描全檔，用於 minified 檔案）
        if 'full_pattern' in entry:
            with open(file_path, 'r', errors='ignore') as f:
                content = f.read()
            match = re.search(entry['full_pattern'], content)
            if match:
                return match.group(1)
    except Exception:
        pass
    return None


def _check_package_versions():
    """執行完整套件版本檢查"""
    start_time = time.time()

    # === Python 套件 ===
    requirements = _parse_requirements()
    python_packages = []

    # 先取得已安裝版本
    for pkg in requirements:
        installed = _get_installed_version(pkg['name'])
        python_packages.append({
            'name': pkg['name'],
            'required_version': pkg['required_version'],
            'installed_version': installed or '未安裝',
            'latest_version': None,
            'status': 'check_failed' if not installed else 'checking',
        })

    # 並行查詢 PyPI 最新版本
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_map = {}
        for i, pkg in enumerate(python_packages):
            if pkg['installed_version'] != '未安裝':
                future = executor.submit(_fetch_pypi_latest, pkg['name'])
                future_map[future] = i

        for future in as_completed(future_map):
            idx = future_map[future]
            try:
                latest = future.result()
                python_packages[idx]['latest_version'] = latest or '無法檢查'
                if latest:
                    python_packages[idx]['status'] = _compare_versions(
                        python_packages[idx]['installed_version'], latest
                    )
                else:
                    python_packages[idx]['status'] = 'check_failed'
            except Exception:
                python_packages[idx]['latest_version'] = '無法檢查'
                python_packages[idx]['status'] = 'check_failed'

    # === 前端 vendor 套件 ===
    frontend_packages = []
    for entry in FRONTEND_VENDOR_REGISTRY:
        installed = _detect_vendor_version(entry)
        frontend_packages.append({
            'name': entry['name'],
            'installed_version': installed or '未偵測',
            'latest_version': None,
            'status': 'check_failed' if not installed else 'checking',
            'source': entry['file'],
        })

    # 並行查詢 npm 最新版本
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_map = {}
        for i, entry in enumerate(FRONTEND_VENDOR_REGISTRY):
            if frontend_packages[i]['installed_version'] != '未偵測':
                future = executor.submit(_fetch_npm_latest, entry['npm_name'])
                future_map[future] = i

        for future in as_completed(future_map):
            idx = future_map[future]
            try:
                latest = future.result()
                frontend_packages[idx]['latest_version'] = latest or '無法檢查'
                if latest:
                    frontend_packages[idx]['status'] = _compare_versions(
                        frontend_packages[idx]['installed_version'], latest
                    )
                else:
                    frontend_packages[idx]['status'] = 'check_failed'
            except Exception:
                frontend_packages[idx]['latest_version'] = '無法檢查'
                frontend_packages[idx]['status'] = 'check_failed'

    duration_ms = int((time.time() - start_time) * 1000)

    return {
        'python_packages': python_packages,
        'frontend_packages': frontend_packages,
        'check_duration_ms': duration_ms,
    }


@api_system_settings.route('/package-versions', methods=['GET'])
@system_admin_required
def get_package_versions():
    """
    查詢 Python 後端套件 + 前端 vendor 套件的版本資訊

    Query params:
        refresh: 'true' 強制重新查詢（忽略快取）
    """
    force_refresh = request.args.get('refresh', '').lower() == 'true'
    now = time.time()

    # 檢查快取
    cache = _package_versions_cache
    if (not force_refresh
            and cache['data'] is not None
            and cache['cached_at'] is not None
            and (now - cache['cached_at']) < cache['ttl']):
        result = cache['data'].copy()
        result['cached'] = True
        result['cached_at'] = datetime.fromtimestamp(cache['cached_at']).isoformat()
        return jsonify({'success': True, 'data': result})

    # 執行查詢
    data = _check_package_versions()

    # 更新快取
    cache['data'] = data
    cache['cached_at'] = now

    data_response = data.copy()
    data_response['cached'] = False
    data_response['cached_at'] = datetime.fromtimestamp(now).isoformat()

    return jsonify({'success': True, 'data': data_response})


# =============================================================================
# 稽核設定
# =============================================================================

@api_system_settings.route('/audit', methods=['GET'])
@system_admin_required
def get_audit_settings():
    """
    取得稽核設定

    Returns:
        audit_level: MINIMAL / STANDARD / VERBOSE
        audit_retention_days: 保留天數
    """
    return jsonify({
        'success': True,
        'data': {
            'audit_level': SystemSetting.get('audit_level', 'STANDARD'),
            'audit_retention_days': SystemSetting.get('audit_retention_days', 90),
            'levels': [
                {'value': 'MINIMAL', 'label': '最小 -- 僅登入/登出與失敗嘗試'},
                {'value': 'STANDARD', 'label': '標準 -- 登入/登出 + 所有寫入操作 (預設)'},
                {'value': 'VERBOSE', 'label': '詳細 -- 記錄所有請求 (含讀取，資料量大)'},
            ]
        }
    })


@api_system_settings.route('/audit', methods=['PUT'])
@system_admin_required
def update_audit_settings():
    """
    更新稽核設定

    Body: {
        "audit_level": "STANDARD",
        "audit_retention_days": 90
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': '缺少 request body'}), 400

    from ..services.audit_service import AuditService, VALID_AUDIT_LEVELS

    updated = []

    if 'audit_level' in data:
        level = data['audit_level'].upper()
        if level not in VALID_AUDIT_LEVELS:
            return jsonify({
                'success': False,
                'error': f'無效的稽核等級，允許值: {", ".join(sorted(VALID_AUDIT_LEVELS))}'
            }), 400
        AuditService.set_audit_level(level)
        updated.append(f'audit_level={level}')

    if 'audit_retention_days' in data:
        days = data['audit_retention_days']
        if not isinstance(days, int) or days < 7:
            return jsonify({'success': False, 'error': '保留天數至少 7 天'}), 400
        SystemSetting.set(
            key='audit_retention_days',
            value=days,
            value_type='integer',
            category='security',
            updated_by=current_user.email
        )
        updated.append(f'audit_retention_days={days}')

    return jsonify({
        'success': True,
        'message': f'稽核設定已更新: {", ".join(updated)}'
    })
