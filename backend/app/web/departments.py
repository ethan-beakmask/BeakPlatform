"""
BeakMask Department Settings Web Routes
部門設定網頁路由
"""
from flask import Blueprint, render_template
from flask_login import current_user

from ..security.decorators import admin_required

departments_bp = Blueprint('departments', __name__)


@departments_bp.route('/')
@admin_required
def department_settings():
    """部門設定主頁面"""
    org = current_user.organization
    conglomerate = org.conglomerate if org else None

    return render_template(
        'pages/admin/departments.html',
        organization=org,
        conglomerate=conglomerate
    )
