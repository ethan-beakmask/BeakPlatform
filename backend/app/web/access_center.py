"""
BeakPlatform Access Center Web Routes
權限管理中心網頁路由
"""
from flask import Blueprint, render_template
from flask_login import current_user


access_center_bp = Blueprint('access_center', __name__)


@access_center_bp.route('/')
def index():
    """權限管理中心頁面"""
    is_system_admin = bool(getattr(current_user, 'is_system_admin', False))

    return render_template(
        'pages/access_center/index.html',
        is_system_admin=is_system_admin,
    )
