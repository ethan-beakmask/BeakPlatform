"""
BeakPlatform Permission Central Web Routes
權限中央管理網頁路由
"""
from flask import Blueprint, render_template
from flask_login import current_user

from ..security.decorators import admin_required

permission_central_bp = Blueprint('permission_central', __name__)


@permission_central_bp.route('/')
@admin_required
def index():
    """權限中央管理頁面"""
    return render_template('pages/permissions/index.html')
