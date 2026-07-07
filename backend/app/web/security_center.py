"""
BeakPlatform Security Center Web Routes
本機安全 - 網頁路由
"""
from flask import Blueprint, render_template
from flask_login import current_user

from ..security.decorators import admin_required
from ..models.organization import Organization
from ..models.lookup_item import LookupItem
from ..models.broadcast_acknowledgment import BroadcastAcknowledgment
from ..constants import SYSTEM_ORG_CODE
from .. import db

security_center_bp = Blueprint('security_center', __name__)


@security_center_bp.route('/login-failures/')
@admin_required
def login_failures():
    """登入錯誤監看頁面"""
    is_system_admin = str(current_user.user_type) == 'SYSTEM_ADMIN'

    organizations = []
    user_org_label = ''

    if is_system_admin:
        organizations.append({
            'secure_code': SYSTEM_ORG_CODE,
            'name': f'系統 ({SYSTEM_ORG_CODE})',
        })
        orgs = Organization.query.filter(
            Organization.is_deleted == False,
            Organization.domain_name != SYSTEM_ORG_CODE,
        ).order_by(Organization.name).all()
        for org in orgs:
            organizations.append({
                'secure_code': org.secure_code,
                'name': org.display_name or org.name,
            })
    else:
        org = Organization.query.filter_by(
            secure_code=current_user.org_secure_code,
            is_deleted=False
        ).first()
        user_org_label = (org.display_name or org.name) if org else current_user.org_secure_code

    return render_template(
        'pages/security/login_failures.html',
        is_system_admin=is_system_admin,
        organizations=organizations,
        user_org_secure_code=current_user.org_secure_code,
        user_org_label=user_org_label,
    )


@security_center_bp.route('/rate-limits/')
@admin_required
def rate_limits():
    """企業速率限制設定頁面"""
    return render_template('pages/security/org_rate_limits.html')


@security_center_bp.route('/api-keys/')
@admin_required
def api_keys():
    """API Key 管理頁面(外部系統 HMAC 金鑰)"""
    return render_template('pages/security/api_keys.html')


@security_center_bp.route('/alert-broadcasts/')
@admin_required
def alert_broadcasts():
    """緊急廣播管理頁面"""
    org_code = current_user.org_secure_code

    # 設定 RLS context
    db.session.execute(
        db.text("SELECT set_config('app.current_org', :org, true)"),
        {'org': org_code}
    )

    # 取得該企業所有 alert 類型廣播
    items = LookupItem.query.filter_by(
        org_secure_code=org_code,
        category_code='broadcast',
        is_deleted=False,
    ).order_by(LookupItem.created_at.desc()).all()

    broadcasts = []
    for item in items:
        value = item.value or {}
        if value.get('type') != 'alert':
            continue

        # 計算已確認數
        ack_count = BroadcastAcknowledgment.query.filter_by(
            broadcast_secure_code=item.secure_code,
            is_deleted=False,
        ).count()

        broadcasts.append({
            'secure_code': item.secure_code,
            'code': item.code,
            'title': value.get('title', ''),
            'message': value.get('message', ''),
            'target': value.get('target', {}),
            'require_ack': value.get('require_ack', True),
            'is_active': item.is_active,
            'created_at': item.created_at,
            'ack_count': ack_count,
        })

    return render_template(
        'pages/security/alert_broadcasts.html',
        broadcasts=broadcasts,
    )
