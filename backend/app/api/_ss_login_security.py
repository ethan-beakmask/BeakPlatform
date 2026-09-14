"""
System Settings - 登入安全欄位子模組

端點：
- GET    /api/system-settings/login-security             取得系統預設
- PUT    /api/system-settings/login-security             更新系統預設
"""
from flask import jsonify, request
from flask_babel import gettext as _
from flask_login import current_user

from ..security.decorators import system_admin_required
from ..models.system_setting import SystemSetting
from ..services.login_security_service import (
    LoginSecurityService, VALID_FIELDS, DEFAULT_CONFIG,
)


def register(bp):
    """將登入安全欄位路由掛載到 Blueprint"""

    def _get_defaults(context: str) -> dict:
        """取得系統層級預設（不含企業覆蓋）"""
        key = f'login_security_{context}'
        saved = SystemSetting.get(key, default=None)
        result = dict(DEFAULT_CONFIG)
        if isinstance(saved, dict):
            result.update({k: v for k, v in saved.items() if k in DEFAULT_CONFIG})
        return result

    def _save_config(context: str, data: dict) -> tuple:
        """驗證並儲存設定，回傳 (success, error_or_None)"""
        config = {}
        for k in ('password_field', 'mine_field', 'rescue_field'):
            val = data.get(k)
            if val is not None:
                if val not in VALID_FIELDS:
                    return False, _('%(field)s 無效，允許值: %(allowed)s', field=k, allowed=", ".join(VALID_FIELDS))
                config[k] = val

        if 'rescue_keyword' in data:
            config['rescue_keyword'] = str(data['rescue_keyword']).strip()

        # 合併現有設定再驗證
        merged = dict(DEFAULT_CONFIG)
        saved = SystemSetting.get(f'login_security_{context}', default=None)
        if isinstance(saved, dict):
            merged.update(saved)
        merged.update(config)

        is_valid, err = LoginSecurityService.validate_config(merged)
        if not is_valid:
            return False, err

        key = f'login_security_{context}'
        SystemSetting.set(
            key=key,
            value=merged,
            value_type='json',
            category='login_security',
            description=f'登入安全欄位預設（{context}）',
            updated_by=current_user.email,
        )
        return True, None

    # ==================== 員工登入預設 ====================

    @bp.route('/login-security/employee', methods=['GET'])
    @system_admin_required
    def get_login_security_employee():
        """取得員工登入安全欄位系統預設"""
        return jsonify({
            'success': True,
            'data': _get_defaults('employee'),
            'valid_fields': list(VALID_FIELDS),
        })

    @bp.route('/login-security/employee', methods=['PUT'])
    @system_admin_required
    def update_login_security_employee():
        """更新員工登入安全欄位系統預設"""
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': _('缺少 request body')}), 400

        ok, err = _save_config('employee', data)
        if not ok:
            return jsonify({'success': False, 'error': err}), 400

        return jsonify({
            'success': True,
            'message': _('員工登入安全欄位預設已更新'),
            'data': _get_defaults('employee'),
        })

    # ==================== 廠商登入預設 ====================

    @bp.route('/login-security/vendor', methods=['GET'])
    @system_admin_required
    def get_login_security_vendor():
        """取得廠商登入安全欄位系統預設"""
        return jsonify({
            'success': True,
            'data': _get_defaults('vendor'),
            'valid_fields': list(VALID_FIELDS),
        })

    @bp.route('/login-security/vendor', methods=['PUT'])
    @system_admin_required
    def update_login_security_vendor():
        """更新廠商登入安全欄位系統預設"""
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': _('缺少 request body')}), 400

        ok, err = _save_config('vendor', data)
        if not ok:
            return jsonify({'success': False, 'error': err}), 400

        return jsonify({
            'success': True,
            'message': _('廠商登入安全欄位預設已更新'),
            'data': _get_defaults('vendor'),
        })
