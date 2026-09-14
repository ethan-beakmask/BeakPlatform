"""
企業行事曆頁面路由（PF-229 第一期：唯讀投影）

- /calendar/    企業視圖（企業事件 + 成員的「已排程」遮罩）
- /calendar/me  個人視圖

資料由 /api/calendar/<scope>/events 提供，頁面本身只負責版面。
守門走雙鑰匙（選單 code `calendar` / `calendar_me`），SYSTEM_ADMIN / ORG_ADMIN bypass。
"""
from flask import Blueprint, render_template
from flask_login import current_user

from ..security.decorators import page_keys_required

calendar_web = Blueprint('calendar_web', __name__)


def _render(scope: str):
    org = current_user.organization
    return render_template(
        'pages/calendar/calendar.html',
        scope=scope,
        timezone=org.get_setting('timezone', 'Asia/Taipei'),
        today=org.local_today().isoformat(),
        is_org_admin=current_user.is_org_admin,
        user_secure_code=current_user.secure_code,
        page_caps={},
    )


@calendar_web.route('/')
@page_keys_required('calendar')
def org_calendar():
    """企業行事曆"""
    return _render('org')


@calendar_web.route('/me')
@page_keys_required('calendar_me')
def my_calendar():
    """我的行事曆"""
    return _render('me')
