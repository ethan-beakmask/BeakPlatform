"""
System Settings - E-MailRelay 設定子模組

端點：
- GET    /api/system-settings/emailrelay              取得設定
- PUT    /api/system-settings/emailrelay              更新設定
- GET    /api/system-settings/emailrelay/auth          取得認證
- PUT    /api/system-settings/emailrelay/auth          更新認證
- POST   /api/system-settings/emailrelay/test          測試發送
- POST   /api/system-settings/emailrelay/service/<action>  服務控制
"""
import os
import base64
import subprocess
from flask import jsonify, request
from flask_babel import gettext as _
from flask_login import current_user

from ..security.decorators import system_admin_required
from ..models.system_setting import SystemSetting
from ..services.emailrelay_config import get_paths as _get_emailrelay_paths
from ..services.emailrelay_config import validate_install_dir as _validate_install_dir


def register(bp):
    """將 E-MailRelay 路由掛載到 Blueprint"""

    @bp.route('/emailrelay', methods=['GET'])
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

    @bp.route('/emailrelay', methods=['PUT'])
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
                    'message': _('安裝路徑不可為空')
                }), 400

            is_valid, errors = _validate_install_dir(new_dir)
            if not is_valid:
                return jsonify({
                    'success': False,
                    'message': _('安裝路徑驗證失敗'),
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
            'message': _('已更新 %(count)s 項設定', count=len(updated)),
            'updated': updated
        })

    @bp.route('/emailrelay/auth', methods=['GET'])
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

    @bp.route('/emailrelay/auth', methods=['PUT'])
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
            return jsonify({'success': False, 'message': _('請填寫 Email')}), 400

        if not password:
            return jsonify({'success': False, 'message': _('請填寫應用程式密碼')}), 400

        auth_file = _get_emailrelay_paths()['auth_file']
        auth_dir = os.path.dirname(auth_file)

        try:
            # 確保目錄存在
            if not os.path.exists(auth_dir):
                return jsonify({
                    'success': False,
                    'message': _('E-MailRelay 目錄不存在: %(dir)s', dir=auth_dir)
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
                'message': _('SMTP 認證設定已儲存'),
                'data': {
                    'email': email,
                    'file': auth_file,
                    'format': 'plain:b (Base64 encoded)'
                }
            })

        except PermissionError:
            return jsonify({
                'success': False,
                'message': _('無權限寫入 Auth 檔案，請檢查目錄權限')
            }), 403
        except Exception as e:
            return jsonify({
                'success': False,
                'message': _('儲存失敗: %(error)s', error=str(e))
            }), 500

    @bp.route('/emailrelay/test', methods=['POST'])
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
                'message': _('Spool 目錄不存在: %(dir)s', dir=spool_dir),
                'data': {'step': 'directory_check'}
            }), 400

        if not os.access(spool_dir, os.W_OK):
            return jsonify({
                'success': False,
                'message': _('Spool 目錄無寫入權限: %(dir)s', dir=spool_dir),
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
                'message': _('請指定收件人或先設定 SMTP 認證'),
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
                    'message': _('emailrelay-submit 失敗: %(error)s', error=result.stderr),
                    'data': {'step': 'submit', 'stderr': result.stderr}
                }), 400

            return jsonify({
                'success': True,
                'message': _('測試郵件已發送至 %(recipient)s', recipient=recipient),
                'data': {
                    'recipient': recipient,
                    'spool_dir': spool_dir,
                    'submit_output': result.stdout
                }
            })

        except subprocess.TimeoutExpired:
            return jsonify({
                'success': False,
                'message': _('emailrelay-submit 執行逾時'),
                'data': {'step': 'submit'}
            }), 400
        except FileNotFoundError:
            return jsonify({
                'success': False,
                'message': _('找不到 emailrelay-submit 工具，請確認 E-MailRelay 已安裝'),
                'data': {'step': 'submit'}
            }), 400
        except Exception as e:
            return jsonify({
                'success': False,
                'message': _('發送測試郵件失敗: %(error)s', error=str(e)),
                'data': {'step': 'submit'}
            }), 500

    @bp.route('/emailrelay/service/<action>', methods=['POST'])
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
                'message': _('不支援的操作: %(action)s', action=action)
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
                    'message': _('操作失敗: %(error)s', error=result.stderr)
                }), 400

            # 取得新狀態
            status = _get_emailrelay_service_status()

            return jsonify({
                'success': True,
                'message': _('服務已 %(action)s', action=action),
                'data': status
            })

        except subprocess.TimeoutExpired:
            return jsonify({
                'success': False,
                'message': _('操作逾時')
            }), 400
        except Exception as e:
            return jsonify({
                'success': False,
                'message': _('操作失敗: %(error)s', error=str(e))
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
            'message': _('Auth 檔案尚未建立')
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
                'message': _('Auth 檔案格式不正確，欄位數: %(count)s', count=len(parts))
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
                    'message': _('Base64 解碼失敗')
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
                'message': _('不支援的認證類型: %(auth_type)s', auth_type=auth_type)
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
            'message': _('無權限讀取 Auth 檔案')
        }
    except Exception as e:
        return {
            'configured': False,
            'email': '',
            'password': '',
            'message': _('讀取失敗: %(error)s', error=str(e))
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
