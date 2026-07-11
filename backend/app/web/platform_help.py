"""
BeakPlatform Help Pages
平台說明文件 + 頁內 [?] 按鈕對應的 per-page 說明
"""
from flask import Blueprint, abort, jsonify, render_template, request
from flask_babel import gettext as _
from flask_login import current_user

from ..security.decorators import login_required
from ..services import help_service

platform_help_bp = Blueprint('platform_help', __name__)


@platform_help_bp.route('/')
@login_required
def index():
    """依用戶類型導向對應總覽頁"""
    user_type = str(current_user.user_type)
    template_map = {
        'SYSTEM_ADMIN': 'pages/platform_help/system_admin.html',
        'ORG_ADMIN': 'pages/platform_help/org_admin.html',
        'EMPLOYEE': 'pages/platform_help/employee.html',
        'EXTERNAL': 'pages/platform_help/external.html',
    }
    template = template_map.get(user_type, 'pages/platform_help/org_admin.html')
    docs = help_service.list_all_docs()
    return render_template(template, help_docs=docs)


@platform_help_bp.route('/page/<menu_code>')
@login_required
def page_doc(menu_code: str):
    """整頁顯示某個 menu_code 對應的 help 文件"""
    doc = help_service.load_doc(menu_code)
    user_type = str(current_user.user_type)
    rendered = help_service.render_for_audience(doc, user_type) if doc else None
    return render_template(
        'pages/platform_help/page_doc.html',
        menu_code=menu_code,
        doc=rendered,
        user_type=user_type,
    )


@platform_help_bp.route('/api/page')
@login_required
def api_page_doc():
    """
    Modal 用 API：依 endpoint / path 反查 menu_code 並回傳 HTML
    Query params:
      - endpoint: Flask endpoint 名（如 'users.list_users'）
      - path: URL path（如 '/permissions/'，已去掉 APP_PREFIX）
    """
    endpoint = request.args.get('endpoint') or None
    path = request.args.get('path') or None

    menu_code = help_service.menu_code_for_endpoint(endpoint, path)
    if not menu_code:
        return jsonify({
            'found': False,
            'menu_code': None,
            'message': _('此頁面尚未提供說明文件'),
        })

    doc = help_service.load_doc(menu_code)
    if not doc:
        return jsonify({
            'found': False,
            'menu_code': menu_code,
            'message': _('此頁面尚未提供說明文件'),
        })

    user_type = str(current_user.user_type)
    rendered = help_service.render_for_audience(doc, user_type)
    return jsonify({
        'found': True,
        'menu_code': menu_code,
        'title': rendered['title'],
        'sections': rendered['sections'],
    })
