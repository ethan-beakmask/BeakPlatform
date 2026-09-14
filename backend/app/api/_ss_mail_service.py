"""
System Settings - 發信服務設定子模組

端點：
- GET    /api/system-settings/mail-service       取得發信服務設定
- PUT    /api/system-settings/mail-service       更新發信服務設定
"""
from flask import jsonify, request
from flask_babel import gettext as _
from flask_login import current_user

from ..models.system_setting import SystemSetting
from ..security.decorators import system_admin_required
from ..services.email_service import (
    MAIL_SERVICE_EMAILRELAY,
    MAIL_SERVICE_SMTP,
    MAIL_SERVICES,
    SETTING_CATEGORY,
    SETTING_PRIMARY_KEY,
    SETTING_SEND_BOTH_KEY,
    EmailService,
)


def _service_label(service: str) -> str:
    if service == MAIL_SERVICE_EMAILRELAY:
        return 'E-MailRelay'
    if service == MAIL_SERVICE_SMTP:
        return 'SMTP'
    return service or ''


def _service_message(service: str, status: dict) -> str:
    if status.get('ready'):
        if service == MAIL_SERVICE_SMTP:
            return _('就緒（使用設定組「%(name)s」）', name=status.get('detail') or '')
        return _('就緒')

    reason = status.get('reason')
    detail = status.get('detail')
    if reason == 'submit_missing':
        return _('找不到 emailrelay-submit：%(path)s', path=detail)
    if reason == 'spool_missing':
        return _('Spool 目錄不存在：%(path)s', path=detail)
    if reason == 'spool_not_writable':
        return _('Spool 目錄無寫入權限：%(path)s', path=detail)
    if reason == 'no_default_config':
        return _('沒有啟用中且勾選「設為預設」的系統級 SMTP 設定組')
    if reason == 'unknown_service':
        return _('未知發信服務：%(service)s', service=detail)
    return reason or ''


def _overall_message(readiness: dict) -> str:
    if readiness.get('ready'):
        if readiness.get('send_both'):
            return _('系統信將由 E-MailRelay 與 SMTP 同時寄出')
        return _('系統信將由 %(svc)s 寄出', svc=_service_label(readiness.get('primary')))

    reason = readiness.get('reason')
    if reason == 'not_selected':
        return _('尚未指定發信服務，系統信目前無法寄出')
    if reason == 'primary_not_ready':
        return _('指定的發信服務未就緒，系統信目前無法寄出')
    if reason == 'secondary_not_ready':
        return _('已勾選兩個服務都發，但另一個服務未就緒，系統信目前無法寄出')
    return ''


def _payload() -> dict:
    settings = EmailService.get_mail_settings()
    readiness = EmailService.get_readiness()
    messages = {
        MAIL_SERVICE_EMAILRELAY: _service_message(
            MAIL_SERVICE_EMAILRELAY,
            readiness['services'][MAIL_SERVICE_EMAILRELAY],
        ),
        MAIL_SERVICE_SMTP: _service_message(
            MAIL_SERVICE_SMTP,
            readiness['services'][MAIL_SERVICE_SMTP],
        ),
        'overall': _overall_message(readiness),
    }
    return {
        'primary': settings['primary'],
        'send_both': settings['send_both'],
        'readiness': readiness,
        'messages': messages,
    }


def register(bp):
    """將發信服務路由掛載到 Blueprint"""

    @bp.route('/mail-service', methods=['GET'])
    @system_admin_required
    def get_mail_service():
        """取得系統級發信服務設定與就緒狀態。"""
        return jsonify({'success': True, 'data': _payload()})

    @bp.route('/mail-service', methods=['PUT'])
    @system_admin_required
    def update_mail_service():
        """更新系統級發信服務設定。"""
        data = request.get_json() or {}
        primary = data.get('primary')
        send_both = bool(data.get('send_both', False))

        if primary not in MAIL_SERVICES:
            return jsonify({
                'success': False,
                'message': _('發信服務必須是 E-MailRelay 或 SMTP'),
            }), 400

        primary_status = EmailService.check_service(primary)
        if not primary_status['ready']:
            return jsonify({
                'success': False,
                'message': _(
                    '無法指定 %(svc)s 為發信服務：%(reason)s',
                    svc=_service_label(primary),
                    reason=_service_message(primary, primary_status),
                ),
            }), 400

        if send_both:
            secondary = (
                MAIL_SERVICE_SMTP
                if primary == MAIL_SERVICE_EMAILRELAY
                else MAIL_SERVICE_EMAILRELAY
            )
            secondary_status = EmailService.check_service(secondary)
            if not secondary_status['ready']:
                return jsonify({
                    'success': False,
                    'message': _(
                        '勾選「兩個服務都發」時另一個服務也必須就緒：%(reason)s',
                        reason=_service_message(secondary, secondary_status),
                    ),
                }), 400

        SystemSetting.set(
            SETTING_PRIMARY_KEY,
            primary,
            updated_by=current_user.username,
            value_type='string',
            description='系統級發信服務',
            category=SETTING_CATEGORY,
        )
        SystemSetting.set(
            SETTING_SEND_BOTH_KEY,
            send_both,
            updated_by=current_user.username,
            value_type='boolean',
            description='系統級發信是否同時使用兩個服務',
            category=SETTING_CATEGORY,
        )

        return jsonify({
            'success': True,
            'message': _('發信服務設定已儲存'),
            'data': _payload(),
        })
