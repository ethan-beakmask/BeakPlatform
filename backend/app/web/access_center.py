"""
BeakPlatform Access Center Web Routes
權限管理中心網頁路由
"""
from flask import Blueprint, render_template
from flask_babel import gettext as _
from flask_login import current_user

from ..constants import SYSTEM_ORG_CODE
from ..models.organization import Organization


access_center_bp = Blueprint('access_center', __name__)


@access_center_bp.route('/')
def index():
    """權限管理中心頁面"""
    is_system_admin = bool(getattr(current_user, 'is_system_admin', False))
    organizations = []
    user_org_label = ''

    if is_system_admin:
        organizations.append({
            'secure_code': SYSTEM_ORG_CODE,
            'name': _('系統 (%(code)s)', code=SYSTEM_ORG_CODE),
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
        'pages/access_center/index.html',
        is_system_admin=is_system_admin,
        organizations=organizations,
        user_org_secure_code=current_user.org_secure_code,
        user_org_label=user_org_label,
        form_templates=[] if is_system_admin else _form_template_options(current_user.org_secure_code),
    )


def _form_template_options(org_sc):
    """代理／候補指派的「限定表單」多選來源（PF-251 第 3a 期）。
    模組 model 一律函式內 import：`modules` 套件在 app 啟動後才進 sys.path（PF-71 踩過）。"""
    from modules.form_workflow.models import FwFormTemplate

    templates = FwFormTemplate.query.filter(
        FwFormTemplate.org_secure_code == org_sc,
        FwFormTemplate.is_deleted == False,  # noqa: E712
    ).order_by(FwFormTemplate.name).all()
    return [{'secure_code': t.secure_code, 'name': t.name, 'code': t.code} for t in templates]
