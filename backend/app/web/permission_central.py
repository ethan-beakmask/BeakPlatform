"""
BeakPlatform Permission Central Web Routes
權限中央管理網頁路由
"""
from flask import Blueprint, render_template
from flask_login import current_user

from ..security.decorators import admin_required
from ..models.organization import Organization
from ..models.user import UserType
from ..constants import SYSTEM_ORG_CODE

permission_central_bp = Blueprint('permission_central', __name__)


@permission_central_bp.route('/')
@admin_required
def index():
    """權限中央管理頁面"""
    is_system_admin = str(current_user.user_type) == 'SYSTEM_ADMIN'

    organizations = []
    user_org_label = ''

    if is_system_admin:
        # 系統企業放最前面
        organizations.append({
            'secure_code': SYSTEM_ORG_CODE,
            'name': f'系統 ({SYSTEM_ORG_CODE})',
        })
        # 其他企業
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
        # ORG_ADMIN: 取得自己企業的顯示名稱
        org = Organization.query.filter_by(
            secure_code=current_user.org_secure_code,
            is_deleted=False
        ).first()
        user_org_label = (org.display_name or org.name) if org else current_user.org_secure_code

    return render_template(
        'pages/permissions/index.html',
        is_system_admin=is_system_admin,
        organizations=organizations,
        user_org_secure_code=current_user.org_secure_code,
        user_org_label=user_org_label,
    )
