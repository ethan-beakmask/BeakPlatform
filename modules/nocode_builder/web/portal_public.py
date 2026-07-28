"""
NoCode Builder - Public Portal Route
公開子系統入口路由

路由一覽:
  /public/portal/<path_id>                 -- 入口 (檢查匿名/session/導向登入)
  /public/portal/<path_id>/login           -- 登入頁 (GET/POST)
  /public/portal/<path_id>/register        -- 註冊頁 (GET/POST，需子系統開放)
  /public/portal/<path_id>/logout          -- 登出 (POST)

不需登入主系統，全部使用 @public_route 標記。
CSRF 在登入/註冊 POST 端點豁免 (無已登入 session 可被攻擊)。
"""
import logging
from datetime import date, datetime
from decimal import Decimal
from math import ceil

from flask import Blueprint, render_template, abort, redirect, url_for, request, flash, jsonify

from app import csrf
from app.security.decorators import public_route

logger = logging.getLogger(__name__)

public_portal_bp = Blueprint(
    'nocode_public_portal',
    __name__,
    url_prefix='/public/portal',
    template_folder='../templates',
)


# ── 共用: 驗證 path_id 並取子系統資訊 ────────────────────────

def _resolve_sub_system(path_id: str):
    """
    透過 path_id 查 lookup → 子系統

    Returns:
        (sub_system, path_id) or abort(404)
    """
    from ..services.portal_path_service import get_by_path_id
    from ..models.sub_system import DcSubSystem

    item = get_by_path_id(path_id)
    if not item or not item.is_active:
        abort(404)

    sub_system_sc = item.value_str
    if not sub_system_sc:
        abort(404)

    ss = DcSubSystem.query.filter_by(
        secure_code=sub_system_sc,
        is_deleted=False,
    ).first()
    if not ss or ss.status != 'published':
        abort(404)

    return ss


def _find_table_widget(doc: dict, widget_id: str) -> dict | None:
    """Find a table widget by id in Page IR v3, including nested layout children."""
    if not isinstance(doc, dict) or not widget_id:
        return None

    def walk(widgets):
        if not isinstance(widgets, list):
            return None
        for widget in widgets:
            if not isinstance(widget, dict):
                continue
            if widget.get('id') == widget_id:
                return widget if widget.get('type') == 'table' else None
            if widget.get('type') == 'layout':
                found = walk(widget.get('children', []))
                if found is not None:
                    return found
        return None

    page = doc.get('page') or {}
    return walk(page.get('widgets', []))


def _resolve_sort(widget: dict, binding: dict, requested_sort: str | None, requested_dir: str | None):
    """Resolve API sort params against binding fields and sortable table columns."""
    binding_fields = set(binding.get('fields') or [])
    sortable = {
        column.get('field')
        for column in widget.get('columns') or []
        if column.get('sortable') is True
    }
    if requested_sort in binding_fields and requested_sort in sortable:
        return requested_sort, requested_dir if requested_dir in {'asc', 'desc'} else 'asc'

    default_sort = widget.get('default_sort') or {}
    default_field = default_sort.get('field')
    if not default_field:
        return None, None
    default_dir = default_sort.get('dir')
    if default_dir not in {'asc', 'desc'}:
        default_dir = 'asc'
    return default_field, default_dir


def _positive_int(value, default: int, max_value: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < 1:
        return default
    if max_value is not None and parsed > max_value:
        return max_value
    return parsed


def _json_safe_value(value):
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _sanitize_rows(rows: list[dict], fields: list[str]) -> list[dict]:
    allowed = set(fields) | {'_sc'}
    sanitized = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        sanitized.append({
            key: _json_safe_value(value)
            for key, value in row.items()
            if key in allowed
        })
    return sanitized


# ── 入口 ──────────────────────────────────────────────────────

@public_portal_bp.route('/<path_id>')
@public_route
def portal_entry(path_id):
    """
    公開 Portal 入口

    1. path_id → 子系統
    2. 已有 session → 進入 portal
    3. allow_anonymous → 自動建立 GUEST session → 進入 portal
    4. 否則 → 導向登入頁
    """
    from ..services.portal_auth_service import (
        get_current_portal_user,
        create_guest_session,
        is_anonymous_allowed,
    )

    ss = _resolve_sub_system(path_id)

    # 已有 session
    portal_user = get_current_portal_user(ss.secure_code)
    if portal_user:
        return _render_portal(ss, portal_user, path_id)

    # 允許匿名 → 自動 GUEST session
    if is_anonymous_allowed(ss.secure_code):
        portal_user = create_guest_session(ss.secure_code)
        return _render_portal(ss, portal_user, path_id)

    # 需要登入
    return redirect(url_for('nocode_public_portal.portal_login', path_id=path_id))


@public_portal_bp.route('/<path_id>/p/<page_sc>', endpoint='portal_page')
@public_route
def portal_page(path_id, page_sc):
    """Public Page IR v3 portal page."""
    from app.pageir import PageIrRenderError, render_page_ir_full
    from app.pageir.context import clear_render_context, set_render_context
    from app.security.resource_gateway import ResourceGateway
    from ..models import DcPageLayout, DcSubSystemPage
    from ..services.portal_auth_service import (
        create_guest_session,
        get_current_portal_user,
        is_anonymous_allowed,
    )
    from ..services import portal_access_service
    from . import _page_ir_title

    ss = _resolve_sub_system(path_id)

    portal_user = get_current_portal_user(ss.secure_code)
    if not portal_user:
        if is_anonymous_allowed(ss.secure_code):
            portal_user = create_guest_session(ss.secure_code)
        else:
            return redirect(url_for('nocode_public_portal.portal_login', path_id=path_id))

    page = ResourceGateway.get(
        DcPageLayout,
        page_sc,
        raise_on_not_found=False,
        check_permission=False,
    )
    if (
        not page
        or page.is_deleted
        or page.status != 'published'
        or not isinstance(page.layout_json, dict)
        or page.layout_json.get('ir_version') != 3
    ):
        abort(404)

    mount = DcSubSystemPage.query.filter_by(
        sub_system_secure_code=ss.secure_code,
        page_layout_secure_code=page_sc,
        is_deleted=False,
        is_active=True,
    ).first()
    if not mount or not _portal_role_allowed(mount.visible_roles, portal_user):
        abort(404)

    allowed, reason = portal_access_service.check_page_access(
        ss.secure_code,
        page_sc,
        portal_user,
    )
    if not allowed:
        logger.warning(
            'Portal page access denied: page=%s sub_system=%s user=%s reason=%s',
            page_sc,
            ss.secure_code,
            portal_user.get('user_id'),
            reason,
        )
        abort(404)

    try:
        set_render_context('portal', sub_system_sc=ss.secure_code, portal_user=portal_user)
        rendered = render_page_ir_full(page.layout_json)
    except PageIrRenderError:
        logger.exception('Portal Page IR v3 render failed: page=%s sub_system=%s', page_sc, ss.secure_code)
        return render_template('pageir/page_error.html'), 422
    finally:
        clear_render_context()

    return render_template(
        'modules/nocode_builder/portal_page_v3.html',
        page=page,
        page_title=_page_ir_title(page),
        body_html=rendered['html'],
        has_form=rendered['has_form'],
        sub_system_name=ss.name,
        sub_system_icon=ss.icon or '',
        path_id=path_id,
        portal_user=portal_user,
    )


@public_portal_bp.route('/<path_id>/api/pages/<page_sc>/widgets/<widget_id>/rows')
@public_route
def portal_widget_rows(path_id, page_sc, widget_id):
    """Public portal Page IR table rows API for scroll loading."""
    from app.pageir.context import clear_render_context, set_render_context
    from app.pageir.registry import get_resource
    from app.security.resource_gateway import ResourceGateway
    from ..models import DcPageLayout, DcSubSystemPage
    from ..services.portal_auth_service import (
        create_guest_session,
        get_current_portal_user,
        is_anonymous_allowed,
    )
    from ..services import portal_access_service

    ss = _resolve_sub_system(path_id)

    portal_user = get_current_portal_user(ss.secure_code)
    if not portal_user:
        if is_anonymous_allowed(ss.secure_code):
            portal_user = create_guest_session(ss.secure_code)
        else:
            abort(404)

    page = ResourceGateway.get(
        DcPageLayout,
        page_sc,
        raise_on_not_found=False,
        check_permission=False,
    )
    if (
        not page
        or page.is_deleted
        or page.status != 'published'
        or not isinstance(page.layout_json, dict)
        or page.layout_json.get('ir_version') != 3
    ):
        abort(404)

    mount = DcSubSystemPage.query.filter_by(
        sub_system_secure_code=ss.secure_code,
        page_layout_secure_code=page_sc,
        is_deleted=False,
        is_active=True,
    ).first()
    if not mount or not _portal_role_allowed(mount.visible_roles, portal_user):
        abort(404)

    allowed, reason = portal_access_service.check_page_access(
        ss.secure_code,
        page_sc,
        portal_user,
    )
    if not allowed:
        logger.warning(
            'Portal rows access denied: page=%s widget=%s sub_system=%s user=%s reason=%s',
            page_sc,
            widget_id,
            ss.secure_code,
            portal_user.get('user_id'),
            reason,
        )
        abort(404)

    widget = _find_table_widget(page.layout_json, widget_id)
    if widget is None:
        abort(404)

    try:
        set_render_context('portal', sub_system_sc=ss.secure_code, portal_user=portal_user)
        ctx = {'world': 'portal', 'sub_system_sc': ss.secure_code, 'portal_user': portal_user}
        access_matrix = widget.get('access_matrix')
        if access_matrix is not None and not portal_access_service.check_widget_access(
            access_matrix,
            'read',
            ctx,
        ):
            logger.warning(
                'Portal rows widget denied: page=%s widget=%s sub_system=%s user=%s',
                page_sc,
                widget_id,
                ss.secure_code,
                portal_user.get('user_id'),
            )
            abort(404)

        binding = widget.get('binding') or {}
        resource = get_resource(binding.get('resource'))
        if resource is None:
            abort(404)

        binding_view = binding.get('view')
        binding_fields = binding.get('fields') or []
        if binding_view not in set(resource.get('views', [])):
            abort(404)
        allowed_fields = set(resource.get('fields', []))
        if any(field not in allowed_fields for field in binding_fields):
            abort(404)

        page_num = _positive_int(request.args.get('page'), 1, 10000)
        page_size = _positive_int(widget.get('page_size'), 20)
        sort_field, sort_dir = _resolve_sort(
            widget,
            binding,
            request.args.get('sort'),
            request.args.get('dir'),
        )
        rows, total = resource['fetch_list'](
            binding_fields,
            page_num,
            page_size,
            sort_field,
            sort_dir,
        )
    finally:
        clear_render_context()

    pages = max(1, ceil(total / page_size)) if page_size else 1
    return jsonify({
        'success': True,
        'rows': _sanitize_rows(rows, binding_fields),
        'page': page_num,
        'pages': pages,
        'total': total,
        'has_more': page_num < pages,
    })


def _portal_role_allowed(visible_roles, portal_user: dict) -> bool:
    roles = visible_roles or []
    if '*' in roles:
        return True
    user_roles = portal_user.get('roles') or ['GUEST']
    return bool(user_roles and user_roles[0] in roles)


def _render_portal(ss, portal_user: dict, path_id: str):
    """渲染 portal 主頁"""
    return render_template(
        'modules/nocode_builder/portal_public.html',
        sub_system_name=ss.name,
        sub_system_description=ss.description or '',
        sub_system_icon=ss.icon or '',
        path_id=path_id,
        portal_user=portal_user,
    )


# ── 登入 ──────────────────────────────────────────────────────

@public_portal_bp.route('/<path_id>/login', methods=['GET'])
@public_route
def portal_login(path_id):
    """登入頁面"""
    from ..services.portal_auth_service import (
        get_current_portal_user,
        is_registration_allowed,
    )

    ss = _resolve_sub_system(path_id)

    # 已登入 → 回入口
    if get_current_portal_user(ss.secure_code):
        return redirect(url_for('nocode_public_portal.portal_entry', path_id=path_id))

    return render_template(
        'modules/nocode_builder/portal_login.html',
        sub_system_name=ss.name,
        sub_system_icon=ss.icon or '',
        path_id=path_id,
        allow_registration=is_registration_allowed(ss.secure_code),
    )


@public_portal_bp.route('/<path_id>/login', methods=['POST'])
@public_route
@csrf.exempt
def portal_login_post(path_id):
    """登入處理"""
    from ..services.portal_auth_service import login, is_registration_allowed

    ss = _resolve_sub_system(path_id)

    username = request.form.get('username', '')
    password = request.form.get('password', '')

    user_data, error = login(ss.secure_code, username, password)
    if error:
        flash(error, 'error')
        return render_template(
            'modules/nocode_builder/portal_login.html',
            sub_system_name=ss.name,
            sub_system_icon=ss.icon or '',
            path_id=path_id,
            allow_registration=is_registration_allowed(ss.secure_code),
            form_username=username,
        ), 200

    return redirect(url_for('nocode_public_portal.portal_entry', path_id=path_id))


# ── 註冊 ──────────────────────────────────────────────────────

@public_portal_bp.route('/<path_id>/register', methods=['GET'])
@public_route
def portal_register(path_id):
    """註冊頁面 (子系統允許註冊時才開放)"""
    from ..services.portal_auth_service import (
        get_current_portal_user,
        is_registration_allowed,
    )

    ss = _resolve_sub_system(path_id)

    if not is_registration_allowed(ss.secure_code):
        abort(404)

    # 已登入 → 回入口
    if get_current_portal_user(ss.secure_code):
        return redirect(url_for('nocode_public_portal.portal_entry', path_id=path_id))

    return render_template(
        'modules/nocode_builder/portal_register.html',
        sub_system_name=ss.name,
        sub_system_icon=ss.icon or '',
        path_id=path_id,
    )


@public_portal_bp.route('/<path_id>/register', methods=['POST'])
@public_route
@csrf.exempt
def portal_register_post(path_id):
    """註冊處理"""
    from ..services.portal_auth_service import register, is_registration_allowed

    ss = _resolve_sub_system(path_id)

    if not is_registration_allowed(ss.secure_code):
        abort(404)

    username = request.form.get('username', '')
    password = request.form.get('password', '')
    password_confirm = request.form.get('password_confirm', '')
    display_name = request.form.get('display_name', '')
    email = request.form.get('email', '')

    # 密碼確認
    if password != password_confirm:
        flash('兩次輸入的密碼不一致', 'error')
        return render_template(
            'modules/nocode_builder/portal_register.html',
            sub_system_name=ss.name,
            sub_system_icon=ss.icon or '',
            path_id=path_id,
            form_username=username,
            form_display_name=display_name,
            form_email=email,
        ), 200

    user_data, error = register(
        sub_system_sc=ss.secure_code,
        username=username,
        password=password,
        display_name=display_name,
        email=email,
    )
    if error:
        flash(error, 'error')
        return render_template(
            'modules/nocode_builder/portal_register.html',
            sub_system_name=ss.name,
            sub_system_icon=ss.icon or '',
            path_id=path_id,
            form_username=username,
            form_display_name=display_name,
            form_email=email,
        ), 200

    flash('註冊成功，已自動登入', 'success')
    return redirect(url_for('nocode_public_portal.portal_entry', path_id=path_id))


# ── 登出 ──────────────────────────────────────────────────────

@public_portal_bp.route('/<path_id>/logout', methods=['POST'])
@public_route
@csrf.exempt
def portal_logout(path_id):
    """登出"""
    from ..services.portal_auth_service import logout

    ss = _resolve_sub_system(path_id)
    logout(ss.secure_code)
    return redirect(url_for('nocode_public_portal.portal_login', path_id=path_id))
