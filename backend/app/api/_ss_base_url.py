"""
System Settings - 系統對外網址 子模組

端點：
- GET  /api/system-settings/base-url   取得系統對外網址
- PUT  /api/system-settings/base-url   更新系統對外網址
"""
from urllib.parse import urlparse

from flask import jsonify, request
from flask_babel import gettext as _
from flask_login import current_user

from ..models.system_setting import SystemSetting
from ..security.decorators import system_admin_required


SETTING_KEY = 'system_base_url'


def _normalize_base_url(value: str) -> str:
    raw = (value or '').strip()
    if not raw:
        return ''

    parsed = urlparse(raw)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise ValueError(_('系統對外網址必須是 http 或 https 的完整 base URL'))

    if parsed.path.rstrip('/'):
        raise ValueError(_('系統對外網址不要含 /beakplatform 之類的路徑前綴'))

    if parsed.query or parsed.fragment:
        raise ValueError(_('系統對外網址不可包含 query 或 fragment'))

    return raw.rstrip('/')


def register(bp):
    """將系統對外網址路由掛載到 Blueprint"""

    @bp.route('/base-url', methods=['GET'])
    @system_admin_required
    def get_base_url():
        return jsonify({
            'success': True,
            'data': {
                'system_base_url': SystemSetting.get(SETTING_KEY, '') or ''
            }
        })

    @bp.route('/base-url', methods=['PUT'])
    @system_admin_required
    def update_base_url():
        data = request.get_json()
        if not data or 'system_base_url' not in data:
            return jsonify({'success': False, 'error': _('缺少 system_base_url')}), 400

        try:
            system_base_url = _normalize_base_url(data.get('system_base_url', ''))
        except ValueError as exc:
            return jsonify({'success': False, 'error': str(exc)}), 400

        SystemSetting.set(
            key=SETTING_KEY,
            value=system_base_url,
            value_type='string',
            category='general',
            updated_by=current_user.email
        )

        return jsonify({
            'success': True,
            'message': _('系統對外網址已更新'),
            'data': {'system_base_url': system_base_url}
        })
