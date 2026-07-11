"""
System Settings - 稽核 / 檔案儲存 / 速率限制 / 選單配色 子模組

端點：
稽核設定:
- GET    /api/system-settings/audit                   取得稽核設定
- PUT    /api/system-settings/audit                   更新稽核設定

檔案儲存:
- GET    /api/system-settings/file-storage            取得檔案儲存設定
- PUT    /api/system-settings/file-storage            更新檔案儲存設定

速率限制:
- GET    /api/system-settings/rate-limits             取得速率限制設定
- PUT    /api/system-settings/rate-limits             更新速率限制設定

選單配色:
- GET    /api/system-settings/menu-colors             取得選單配色
- PUT    /api/system-settings/menu-colors             更新選單配色
- POST   /api/system-settings/menu-colors/reset       重置為預設值
"""
import re
from flask import jsonify, request
from flask_babel import gettext as _
from flask_login import current_user

from ..security.decorators import system_admin_required
from ..models.system_setting import SystemSetting
from .. import db


# 檔案儲存預設值
DEFAULT_DIR_FILE_LIMIT = 100000

# 選單配色預設值
MENU_COLOR_DEFAULTS = {
    'menu-sys-bg': '#b91c1c',
    'menu-sys-text': '#ffffff',
    'menu-org-bg': '#1d4ed8',
    'menu-org-text': '#ffffff',
    'menu-user-bg': '#111827',
    'menu-user-text': '#ffffff',
    'menu-ext-bg': '#f59e0b',
    'menu-ext-text': '#111827',
    'menu-cross-text': '#fde047',
    'menu-common-bg': '#374151',
    'menu-common-text': '#e5e7eb',
    'menu-fixed-bg': '#111827',
    'menu-fixed-text': '#ffffff',
    'menu-module-bg': '#7c3aed',
    'menu-module-text': '#ffffff',
    'menu-header-bg': '#1e3a5f',
    'menu-header-text': '#ffffff',
    'menubar-bg': '#333333',
}


def register(bp):
    """將稽核/檔案儲存/速率限制/選單配色路由掛載到 Blueprint"""

    # ==================== 稽核設定 ====================

    @bp.route('/audit', methods=['GET'])
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
                    {'value': 'MINIMAL', 'label': _('最小 -- 僅登入/登出與失敗嘗試')},
                    {'value': 'STANDARD', 'label': _('標準 -- 登入/登出 + 所有寫入操作 (預設)')},
                    {'value': 'VERBOSE', 'label': _('詳細 -- 記錄所有請求 (含讀取，資料量大)')},
                ]
            }
        })

    @bp.route('/audit', methods=['PUT'])
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
            return jsonify({'success': False, 'error': _('缺少 request body')}), 400

        from ..services.audit_service import AuditService, VALID_AUDIT_LEVELS

        updated = []

        if 'audit_level' in data:
            level = data['audit_level'].upper()
            if level not in VALID_AUDIT_LEVELS:
                return jsonify({
                    'success': False,
                    'error': _('無效的稽核等級，允許值: %(values)s',
                               values=', '.join(sorted(VALID_AUDIT_LEVELS)))
                }), 400
            AuditService.set_audit_level(level)
            updated.append(f'audit_level={level}')

        if 'audit_retention_days' in data:
            days = data['audit_retention_days']
            if not isinstance(days, int) or days < 7:
                return jsonify({'success': False, 'error': _('保留天數至少 7 天')}), 400
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
            'message': _('稽核設定已更新: %(items)s', items=', '.join(updated))
        })

    # ==================== 檔案儲存 ====================

    @bp.route('/file-storage', methods=['GET'])
    @system_admin_required
    def get_file_storage_settings():
        """
        取得檔案儲存設定

        Returns:
            encrypted_storage_dir: 加密檔案儲存路徑（唯讀，來自環境變數）
            dir_file_limit: 單一目錄檔案數上限
        """
        from ..services.file_service import ENCRYPTED_STORAGE_DIR

        return jsonify({
            'success': True,
            'data': {
                'encrypted_storage_dir': ENCRYPTED_STORAGE_DIR,
                'dir_file_limit': int(SystemSetting.get(
                    'encrypted_dir_file_limit', DEFAULT_DIR_FILE_LIMIT
                )),
            }
        })

    @bp.route('/file-storage', methods=['PUT'])
    @system_admin_required
    def update_file_storage_settings():
        """
        更新檔案儲存設定

        Body: {
            "dir_file_limit": 100000
        }
        """
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': _('缺少 request body')}), 400

        updated = []

        if 'dir_file_limit' in data:
            limit = data['dir_file_limit']
            if not isinstance(limit, int) or limit < 1000:
                return jsonify({
                    'success': False,
                    'error': _('目錄檔案上限至少 1,000')
                }), 400
            if limit > 1000000:
                return jsonify({
                    'success': False,
                    'error': _('目錄檔案上限不可超過 1,000,000')
                }), 400
            SystemSetting.set(
                key='encrypted_dir_file_limit',
                value=limit,
                value_type='integer',
                category='file_storage',
                description='加密儲存單一目錄檔案數上限',
                updated_by=current_user.email
            )
            updated.append(f'dir_file_limit={limit}')

        return jsonify({
            'success': True,
            'message': _('檔案儲存設定已更新: %(items)s', items=', '.join(updated))
        })

    # ==================== 速率限制 ====================

    @bp.route('/rate-limits', methods=['GET'])
    @system_admin_required
    def get_rate_limit_settings():
        """
        取得認證速率限制設定

        Returns:
            categories: 五個分類的設定值、來源、預設值
        """
        from ..services.rate_limit_service import RateLimitService

        return jsonify({
            'success': True,
            'data': {
                'categories': RateLimitService.get_all_settings()
            }
        })

    @bp.route('/rate-limits', methods=['PUT'])
    @system_admin_required
    def update_rate_limit_settings():
        """
        更新認證速率限制設定

        Body: {
            "shared_login": "20 per 10 minutes",
            "org_login": "20 per 10 minutes",
            ...
        }
        """
        from ..services.rate_limit_service import (
            RateLimitService, RATE_LIMIT_CATEGORIES, validate_rate_limit_string
        )

        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': _('缺少 request body')}), 400

        updated = []
        errors = []

        for category in RATE_LIMIT_CATEGORIES:
            if category in data:
                value = str(data[category]).strip()
                if not validate_rate_limit_string(value):
                    errors.append(
                        _('%(category)s: 格式無效 "%(value)s" (正確格式如: 20 per 10 minutes, 5 per hour)',
                          category=category, value=value)
                    )
                    continue

                RateLimitService.set_limit(
                    category=category,
                    value=value,
                    updated_by=current_user.email,
                )
                updated.append(f'{category}={value}')

        if errors:
            return jsonify({
                'success': False,
                'error': _('部分設定格式無效'),
                'details': errors,
                'updated': updated,
            }), 400

        if not updated:
            return jsonify({'success': False, 'error': _('未提供任何有效設定')}), 400

        return jsonify({
            'success': True,
            'message': _('速率限制已更新: %(items)s', items=', '.join(updated))
        })

    # ==================== 選單配色 ====================

    @bp.route('/menu-colors', methods=['GET'])
    @system_admin_required
    def get_menu_colors():
        """取得選單配色設定"""
        saved = SystemSetting.get('menu_colors', default=None)
        colors = dict(MENU_COLOR_DEFAULTS)
        if saved and isinstance(saved, dict):
            colors.update(saved)
        return jsonify({
            'success': True,
            'data': {
                'colors': colors,
                'defaults': MENU_COLOR_DEFAULTS
            }
        })

    @bp.route('/menu-colors', methods=['PUT'])
    @system_admin_required
    def update_menu_colors():
        """更新選單配色設定"""
        data = request.get_json()
        if not data or 'colors' not in data:
            return jsonify({'success': False, 'error': _('缺少 colors 欄位')}), 400

        colors = data['colors']
        if not isinstance(colors, dict):
            return jsonify({'success': False, 'error': _('colors 必須是物件')}), 400

        hex_pattern = re.compile(r'^#[0-9a-fA-F]{6}$')
        cleaned = {}
        for key, value in colors.items():
            if key not in MENU_COLOR_DEFAULTS:
                continue
            if not hex_pattern.match(value):
                return jsonify({
                    'success': False,
                    'error': _('%(key)s 的值 "%(value)s" 不是有效的 hex 色碼（格式: #RRGGBB）',
                               key=key, value=value)
                }), 400
            cleaned[key] = value.lower()

        SystemSetting.set(
            key='menu_colors',
            value=cleaned,
            value_type='json',
            category='appearance',
            description='選單配色設定',
            updated_by=current_user.email
        )

        return jsonify({
            'success': True,
            'message': _('選單配色已更新，重新整理頁面後生效')
        })

    @bp.route('/menu-colors/reset', methods=['POST'])
    @system_admin_required
    def reset_menu_colors():
        """重置選單配色為預設值"""
        setting = SystemSetting.query.filter_by(key='menu_colors').first()
        if setting:
            db.session.delete(setting)
            db.session.commit()

        return jsonify({
            'success': True,
            'message': _('選單配色已重置為預設值，重新整理頁面後生效')
        })
