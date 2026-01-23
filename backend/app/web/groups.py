"""
BeakMask Group Settings Web Routes
社群設定網頁路由
"""
from flask import Blueprint, render_template
from flask_login import current_user

from ..security.decorators import admin_required

groups_bp = Blueprint('groups', __name__)


@groups_bp.route('/')
@admin_required
def group_settings():
    """社群設定主頁面"""
    org = current_user.organization
    conglomerate = org.conglomerate if org else None

    return render_template(
        'pages/admin/groups.html',
        organization=org,
        conglomerate=conglomerate
    )
