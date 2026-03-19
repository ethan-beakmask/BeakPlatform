"""
BeakPlatform Help Pages
平台說明文件
"""
from flask import Blueprint, render_template
from flask_login import current_user

from ..security.decorators import login_required

platform_help_bp = Blueprint('platform_help', __name__)


@platform_help_bp.route('/')
@login_required
def index():
    """依用戶類型導向對應說明頁"""
    user_type = str(current_user.user_type)
    template_map = {
        'SYSTEM_ADMIN': 'pages/platform_help/system_admin.html',
        'ORG_ADMIN': 'pages/platform_help/org_admin.html',
        'EMPLOYEE': 'pages/platform_help/employee.html',
        'EXTERNAL': 'pages/platform_help/external.html',
    }
    template = template_map.get(user_type, 'pages/platform_help/org_admin.html')
    return render_template(template)
