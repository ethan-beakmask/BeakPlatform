"""
BeakPlatform Security Center Web Routes
本機安全 - 網頁路由
"""
from flask import Blueprint, render_template
from flask_login import current_user

from ..security.decorators import admin_required
from ..models.organization import Organization
from ..constants import SYSTEM_ORG_CODE

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
            'name': '系統 (system.local)',
        })
        orgs = Organization.query.filter(
            Organization.is_deleted == False,
            Organization.domain_name != 'system.local',
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
