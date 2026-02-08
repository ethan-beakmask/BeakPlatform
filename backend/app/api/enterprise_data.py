"""
企業資料查詢 API（供流程設計器等模組使用）

提供「可用設定」的唯讀查詢端點，與 enterprise_settings.py（管理用 CRUD）分離。
權限層級：@login_required（一般登入用戶即可查詢）

端點：
- GET /api/enterprise/data/settings/smtp/available        可用 SMTP 設定
- GET /api/enterprise/data/settings/email-groups/available 可用收件人群組
- GET /api/enterprise/data/settings/telegram/available     可用 Telegram 設定
"""
from flask import Blueprint, jsonify
from flask_login import current_user

from ..models import SmtpConfig, TelegramConfig, RecipientGroup
from ..security.decorators import login_required
from ..security.resource_gateway import ResourceGateway


SYSTEM_ORG_CODE = 'system.local'

api_enterprise_data = Blueprint(
    'api_enterprise_data',
    __name__,
    url_prefix='/api/enterprise/data/settings'
)


@api_enterprise_data.route('/smtp/available', methods=['GET'])
@login_required
def available_smtp_configs():
    """列出當前企業可用的 SMTP 設定（啟用中）"""
    configs = ResourceGateway.filter(
        SmtpConfig,
        is_deleted=False,
        is_active=True,
        order_by='priority'
    )

    default_config = None
    result = []
    for cfg in configs:
        item = {
            'id': cfg.secure_code,
            'name': cfg.name,
            'provider_type': cfg.provider_type or 'generic',
            'is_default': cfg.is_default or False,
        }
        result.append(item)
        if cfg.is_default:
            default_config = {
                'id': cfg.secure_code,
                'name': cfg.name,
            }

    return jsonify({
        'success': True,
        'data': {
            'configs': result,
            'default_config': default_config,
        }
    })


@api_enterprise_data.route('/email-groups/available', methods=['GET'])
@login_required
def available_email_groups():
    """列出可用的收件人群組（企業 + 系統級）"""
    org_code = current_user.org_secure_code

    # 企業級群組
    org_groups = ResourceGateway.filter(
        RecipientGroup,
        is_deleted=False,
        is_active=True,
        order_by='priority'
    )

    # 系統級群組
    system_groups = RecipientGroup.query.filter_by(
        org_secure_code=SYSTEM_ORG_CODE,
        is_deleted=False,
        is_active=True,
    ).order_by(RecipientGroup.priority).all()

    result = []
    seen = set()

    for group in org_groups:
        seen.add(group.secure_code)
        result.append({
            'id': group.secure_code,
            'name': group.name,
            'scope': 'organization',
            'recipient_count': group.get_recipient_count(),
        })

    for group in system_groups:
        if group.secure_code not in seen:
            result.append({
                'id': group.secure_code,
                'name': group.name,
                'scope': 'system',
                'recipient_count': group.get_recipient_count(),
            })

    return jsonify({
        'success': True,
        'data': {
            'groups': result,
        }
    })


@api_enterprise_data.route('/telegram/available', methods=['GET'])
@login_required
def available_telegram_configs():
    """列出當前企業可用的 Telegram 設定（啟用中）"""
    configs = ResourceGateway.filter(
        TelegramConfig,
        is_deleted=False,
        is_active=True,
        order_by='name'
    )

    # 也查系統級設定
    system_configs = TelegramConfig.query.filter_by(
        org_secure_code=SYSTEM_ORG_CODE,
        is_deleted=False,
        is_active=True,
    ).order_by(TelegramConfig.name).all()

    result = []
    seen = set()

    for cfg in configs:
        seen.add(cfg.secure_code)
        result.append({
            'id': cfg.secure_code,
            'name': cfg.name,
            'is_system': False,
            'channels': cfg.get_channels(),
            'default_channel': cfg.default_channel,
        })

    for cfg in system_configs:
        if cfg.secure_code not in seen:
            result.append({
                'id': cfg.secure_code,
                'name': cfg.name,
                'is_system': True,
                'channels': cfg.get_channels(),
                'default_channel': cfg.default_channel,
            })

    return jsonify({
        'success': True,
        'data': {
            'configs': result,
        }
    })
