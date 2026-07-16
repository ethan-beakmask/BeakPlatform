"""
BeakMask Group Settings Web Routes
社群設定網頁路由

Admin: 完整社群管理 (CRUD + 成員管理)
Team leader (MANAGER/DEPUTY): 只能管理自己社群的成員
"""
from flask import Blueprint, render_template, abort
from flask_babel import gettext as _
from flask_login import current_user

from ..security.decorators import login_required
from ..models.user_unit_membership import UserUnitMembership, MembershipRole

groups_bp = Blueprint('groups', __name__)


def _user_is_admin():
    return (
        getattr(current_user, 'is_system_admin', False)
        or getattr(current_user, 'is_org_admin', False)
    )


def _user_has_managed_groups():
    """Check if user is MANAGER or DEPUTY of at least one group"""
    return UserUnitMembership.query.filter(
        UserUnitMembership.user_secure_code == current_user.secure_code,
        UserUnitMembership.org_secure_code == current_user.org_secure_code,
        UserUnitMembership.role_type.in_([MembershipRole.MANAGER, MembershipRole.DEPUTY]),
        UserUnitMembership.is_deleted == False
    ).first() is not None


@groups_bp.route('/')
def group_settings():
    """社群設定主頁面 (Admin + Team Leader)"""
    is_admin = _user_is_admin()

    if not is_admin and not _user_has_managed_groups():
        abort(403, description=_('無權限存取社群管理'))

    org = current_user.organization
    conglomerate = org.conglomerate if org else None

    return render_template(
        'pages/admin/groups.html',
        organization=org,
        conglomerate=conglomerate,
        is_admin=is_admin,
    )


# 團長專用入口 (別名): /my-groups/
my_groups_bp = Blueprint('my_groups', __name__)


@my_groups_bp.route('/')
@login_required
def my_groups():
    """我的社群 (團長入口)"""
    is_admin = _user_is_admin()

    if not is_admin and not _user_has_managed_groups():
        abort(403, description=_('無權限存取社群管理'))

    org = current_user.organization
    conglomerate = org.conglomerate if org else None

    return render_template(
        'pages/admin/groups.html',
        organization=org,
        conglomerate=conglomerate,
        is_admin=is_admin,
    )
