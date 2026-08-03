"""
Data CRUD Module - Web Routes
資料表工具頁面路由
"""
import logging
import re

from flask import Blueprint, render_template, request, abort, redirect, url_for
from flask_babel import get_locale
from flask_login import current_user

from app.security.decorators import module_access_required
from app.platform.data import get_current_org

logger = logging.getLogger(__name__)
_PORTAL_PREVIEW_CODE_RE = re.compile(r'^[A-Z][A-Z0-9_]{0,31}$')

web_bp = Blueprint(
    'nocode_builder_web',
    __name__,
    url_prefix='/nocode-builder',
    template_folder='../templates'
)

nocode_short_bp = Blueprint(
    'nocode_builder_short_web',
    __name__,
    url_prefix='/nocode',
    template_folder='../templates'
)

additional_blueprints = [nocode_short_bp]


@web_bp.route('/')
@module_access_required('nocode_builder')
def index():
    """模組首頁 → 導向子系統列表"""
    return redirect(url_for('nocode_builder_web.sub_system_list'))


@web_bp.route('/ir-designer/<secure_code>')
@nocode_short_bp.route('/ir-designer/<secure_code>')
@module_access_required('nocode_builder')
def ir_designer(secure_code):
    """Page IR v3 設計器。"""
    from app.security.resource_gateway import ResourceGateway
    from ..models import DcPageLayout
    from ..services.page_ownership_service import is_page_reachable

    page = ResourceGateway.get(
        DcPageLayout,
        secure_code,
        raise_on_not_found=False,
        check_permission=False,
    )
    if not page or page.is_deleted:
        abort(404)

    if not is_page_reachable(secure_code):
        logger.info(
            'IR designer blocked: owner sub system deleted page=%s', secure_code
        )
        abort(404)

    return render_template(
        'modules/nocode_builder/ir_designer.html',
        secure_code=secure_code,
    )


@web_bp.route('/workspace/<sub_system_sc>')
@nocode_short_bp.route('/workspace/<sub_system_sc>')
@module_access_required('nocode_builder')
def workspace(sub_system_sc):
    """NoCode 統一工作區。"""
    from app.services.capability_service import build_caps
    from app.security.resource_gateway import ResourceGateway
    from ..models import DcSubSystem

    ss = ResourceGateway.get(
        DcSubSystem,
        sub_system_sc,
        raise_on_not_found=False,
        check_permission=False,
    )
    if not ss or ss.is_deleted:
        logger.info('Workspace blocked: sub system deleted sub_system=%s', sub_system_sc)
        abort(404)

    return render_template(
        'modules/nocode_builder/workspace.html',
        sub_system_sc=sub_system_sc,
        page_caps=build_caps(['nocode_builder.manage']),
    )


@web_bp.route('/ir-designer/<secure_code>/preview')
@nocode_short_bp.route('/ir-designer/<secure_code>/preview')
@module_access_required('nocode_builder')
def ir_designer_preview(secure_code):
    """Page IR v3 草稿預覽。"""
    from app.pageir import PageIrRenderError, render_page_ir_full
    from app.pageir.context import clear_render_context, set_render_context
    from app.security.resource_gateway import ResourceGateway
    from ..models import DcPageLayout, DcSubSystem
    from ..services import portal_access_service, portal_auth_service
    from ..services.page_ownership_service import (
        get_owner_sub_system_codes,
        is_page_reachable,
    )

    page = ResourceGateway.get(
        DcPageLayout,
        secure_code,
        raise_on_not_found=False,
        check_permission=False,
    )
    if not page or page.is_deleted:
        abort(404)

    if not is_page_reachable(secure_code):
        logger.info(
            'IR designer preview blocked: owner sub system deleted page=%s',
            secure_code,
        )
        abort(404)

    preview_banner = None
    sub_system_sc = (request.args.get('sub') or '').strip()
    if sub_system_sc:
        ss = ResourceGateway.get(
            DcSubSystem,
            sub_system_sc,
            raise_on_not_found=False,
            check_permission=False,
        )
        if not ss or ss.is_deleted:
            abort(404)

        if ss.secure_code not in get_owner_sub_system_codes(secure_code):
            abort(404)

        group_code = (request.args.get('group') or '').strip()
        level_code = (request.args.get('level') or '').strip()
        if group_code and not _PORTAL_PREVIEW_CODE_RE.fullmatch(group_code):
            abort(400)
        if level_code and not _PORTAL_PREVIEW_CODE_RE.fullmatch(level_code):
            abort(400)

        try:
            groups = portal_auth_service.list_groups(ss.secure_code)
            levels = portal_auth_service.list_levels(ss.secure_code)
        except FileNotFoundError:
            abort(400)

        def _portal_unit_active(item):
            return item.get('is_active') in (True, 1, '1')

        active_groups = {
            group.get('code'): group
            for group in groups
            if group.get('code') and _portal_unit_active(group)
        }
        active_levels = [
            level for level in levels
            if level.get('code') and _portal_unit_active(level)
        ]
        if group_code and group_code not in active_groups:
            abort(400)
        if not level_code:
            first_level = next(iter(active_levels), None)
            if not first_level:
                abort(400)
            level_code = first_level.get('code')

        level = next((item for item in active_levels if item.get('code') == level_code), None)
        if not level:
            abort(400)
        try:
            level_rank = int(level.get('rank'))
        except (TypeError, ValueError):
            abort(400)

        preview_user = {
            'sub_system_sc': ss.secure_code,
            'user_id': None,
            'user_type': 'PREVIEW',
            'group_code': group_code or None,
            'level_code': level_code,
            'level_rank': level_rank,
            'roles': [],
            'display_name': 'PREVIEW',
        }
        page_allowed, page_access_reason = portal_access_service.check_page_access(
            ss.secure_code,
            secure_code,
            preview_user,
        )
        if not page_allowed:
            logger.info(
                'Page IR portal preview denied: user=%s page=%s sub_system=%s group=%s level=%s reason=%s',
                getattr(current_user, 'secure_code', None),
                secure_code,
                ss.secure_code,
                group_code or None,
                level_code,
                page_access_reason,
            )
            abort(403)
        preview_banner = {
            'group': active_groups[group_code].get('name') if group_code else None,
            'level': level.get('name') or level_code,
        }
        user_sc = getattr(current_user, 'secure_code', None)
        username = getattr(current_user, 'username', None)
        logger.info(
            'Page IR portal preview: user=%s username=%s page=%s sub_system=%s group=%s level=%s',
            user_sc,
            username,
            secure_code,
            ss.secure_code,
            group_code or None,
            level_code,
        )
        set_render_context('portal', sub_system_sc=ss.secure_code, portal_user=preview_user)
        try:
            rendered = render_page_ir_full(page.layout_json or {})
        except PageIrRenderError:
            logger.exception(
                'Page IR preview render failed: page=%s sub_system=%s',
                secure_code,
                ss.secure_code,
            )
            # portal 語境的錯誤頁不得繼承 layouts/base.html（會帶平台選單等平台物件）
            return render_template(
                'modules/nocode_builder/portal_page_error.html',
                sub_system_name=ss.name,
                sub_system_icon=ss.icon or '',
            ), 422
        finally:
            clear_render_context()

        return render_template(
            'modules/nocode_builder/portal_page_v3.html',
            page=page,
            page_title=_page_ir_title(page),
            body_html=rendered['html'],
            has_form=rendered['has_form'],
            preview_banner=preview_banner,
            is_preview=True,
            sub_system_name=ss.name,
            sub_system_icon=ss.icon or '',
            portal_user=preview_user,
            path_id=None,
        )

    try:
        rendered = render_page_ir_full(page.layout_json or {})
    except PageIrRenderError:
        logger.exception('Page IR preview render failed: page=%s', secure_code)
        return render_template('pageir/page_error.html'), 422

    return render_template(
        'pageir/page_v3.html',
        page=page,
        page_title=_page_ir_title(page),
        body_html=rendered['html'],
        has_form=rendered['has_form'],
        preview_banner=None,
    )


@web_bp.route('/sub-systems/<secure_code>/preview')
@nocode_short_bp.route('/sub-systems/<secure_code>/preview')
@module_access_required('nocode_builder')
def sub_system_preview(secure_code):
    """子系統預覽：導向 site map 根頁面（welcome）的 portal 預覽。"""
    from app.security.resource_gateway import ResourceGateway
    from ..models import DcSubSystem
    from ..services.site_map_service import SiteMapService

    ss = ResourceGateway.get(
        DcSubSystem,
        secure_code,
        raise_on_not_found=False,
        check_permission=False,
    )
    if not ss or ss.is_deleted or not ss.is_active:
        abort(404)

    root_node = SiteMapService.get_root_node(ss.secure_code, ss.org_secure_code)
    if not root_node or not root_node.page_layout_secure_code:
        abort(404)

    return redirect(url_for(
        'nocode_builder_web.ir_designer_preview',
        secure_code=root_node.page_layout_secure_code,
        sub=ss.secure_code,
    ))


@web_bp.route('/sub-systems/<secure_code>/portal')
@module_access_required('nocode_builder', False)
def sub_system_portal(secure_code):
    """子系統入口導航頁（含 GUEST 支援）"""
    from ..models import DcSubSystem
    from ..services.site_map_service import SiteMapService
    from app.security.resource_gateway import ResourceGateway

    ss = ResourceGateway.get(
        DcSubSystem, secure_code,
        raise_on_not_found=False,
        check_permission=False
    )
    if not ss or ss.is_deleted or not ss.is_active:
        abort(404)

    # 有 site map 時使用 V2 Portal (樹狀選單)
    # 非成員也可進入，user-tree API 會回傳 GUEST 可見節點
    if SiteMapService.has_site_map(ss.secure_code, ss.org_secure_code):
        return render_template(
            'modules/nocode_builder/sub_system_portal_v2.html',
            sub_system_sc=secure_code,
            sub_system_name=ss.name,
        )

    # 無 site map 時使用舊卡片 Portal
    return render_template(
        'modules/nocode_builder/sub_system_portal.html',
        sub_system_sc=secure_code,
        sub_system_name=ss.name,
    )


# =============================================================================
# Lookup 管理頁面
# =============================================================================

@web_bp.route('/lookup')
@module_access_required('nocode_builder')
def lookup_manager():
    """選項-清單-資料樹"""
    return render_template('modules/nocode_builder/lookup_manager.html')


# =============================================================================
# 開發案管理頁面 (Web Builder Studio Phase 1)
# =============================================================================

@web_bp.route('/my-projects')
@module_access_required('nocode_builder')
def my_projects():
    """我的開發案列表"""
    return render_template('modules/nocode_builder/my_projects.html')


# =============================================================================
# 子系統管理頁面
# =============================================================================

@web_bp.route('/sub-systems')
@module_access_required('nocode_builder')
def sub_system_list():
    """子系統列表"""
    return render_template('modules/nocode_builder/sub_system_list.html')


@web_bp.route('/sub-systems/<secure_code>/config')
@module_access_required('nocode_builder')
def sub_system_config(secure_code):
    """子系統配置"""
    org = get_current_org()
    org_name = org.name if org else ''
    return render_template(
        'modules/nocode_builder/sub_system_config.html',
        secure_code=secure_code,
        org_name=org_name,
    )


# =============================================================================
# 內部輔助
# =============================================================================

def _build_sub_system_context(sub_sc, ssp_sc):
    """
    建立子系統權限 context (server-side)

    回傳 dict 或 None (驗證失敗)
    """
    from ..models import DcSubSystem, DcSubSystemPage
    from ..services.sub_system_service import SubSystemService
    from ..services.crud_service import FilterVariableNotSupported, resolve_filter_variables
    from app.security.resource_gateway import ResourceGateway

    try:
        ss = ResourceGateway.get(
            DcSubSystem, sub_sc,
            raise_on_not_found=False,
            check_permission=False
        )
        if not ss or ss.is_deleted or not ss.is_active:
            return None

        role_type = SubSystemService.get_user_role_type(current_user, ss)
        if role_type is None:
            return None

        ssp = ResourceGateway.get(
            DcSubSystemPage, ssp_sc,
            raise_on_not_found=False,
            check_permission=False
        )
        if not ssp or ssp.is_deleted:
            return None

        ctx = SubSystemService.get_page_context(role_type, ssp)
        ctx['data_filters'] = resolve_filter_variables(
            ctx['data_filters'], current_user
        )

        return {
            'sub_sc': sub_sc,
            'ssp_sc': ssp_sc,
            'role_type': role_type,
            'is_admin': SubSystemService.is_admin_role(role_type),
            'crud': ctx['crud'],
            'data_filters': ctx['data_filters'],
            'sub_system_name': ss.name,
        }
    except FilterVariableNotSupported:
        logger.warning('Failed to build sub system context: filter variable not supported')
        return None
    except Exception as e:
        logger.warning('Failed to build sub system context: %s', e)
        return None


def _deny_and_logout(resource_type, resource_id, sub_sc=''):
    """
    [SEC-01] 無權存取時：寫稽核日誌 + 強制登出

    Args:
        resource_type: 資源類型標識
        resource_id: 資源識別碼
        sub_sc: 子系統 secure_code (日誌用)
    """
    from flask_login import logout_user
    from app.services.audit_service import AuditService
    from app import db

    details = (
        f"User {current_user.username} (sc={current_user.secure_code}) "
        f"denied access to {resource_type}/{resource_id} "
        f"sub_system={sub_sc} path={request.path}"
    )
    logger.warning('NoCode page role guard DENIED: %s', details)

    try:
        AuditService.log(
            action='ACCESS_DENIED',
            resource_type=resource_type.upper(),
            org_secure_code=current_user.org_secure_code,
            user_secure_code=current_user.secure_code,
            details=details,
            request_method=request.method,
            request_path=request.path,
            status_code=403,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', '')[:500],
        )
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error('Failed to write NoCode access denied audit log: %s', e)

    try:
        logout_user()
    except Exception as e:
        logger.error('Failed to logout user: %s', e)


def _check_site_map_node_access(sub_system_sc, page_layout_sc, user):
    """
    [SEC-01] 檢查用戶是否有權存取 SiteMap 中對應的頁面

    透過 page_layout_secure_code 找到對應的 SiteMapNode，
    再用 access_roles 做准入檢查。

    無對應 node 時放行（向下相容）。
    拒絕時回傳 redirect_to 路徑，允許時回傳 True。
    """
    from ..models.site_map_node import DcSiteMapNode
    from ..models import DcSubSystem
    from ..services.site_map_service import SiteMapService
    from ..services.sub_system_service import SubSystemService
    from app.security.resource_gateway import ResourceGateway

    try:
        nodes = ResourceGateway.filter(
            DcSiteMapNode,
            sub_system_secure_code=sub_system_sc,
            page_layout_secure_code=page_layout_sc,
            is_deleted=False,
            is_active=True,
        )
        node = nodes[0] if nodes else None

        if not node:
            return True  # 無對應節點 → 放行

        ss = ResourceGateway.get(
            DcSubSystem, sub_system_sc,
            raise_on_not_found=False,
            check_permission=False
        )
        if not ss:
            return True

        role_type = SubSystemService.get_user_role_type(user, ss)
        if SubSystemService.is_admin_role(role_type or ''):
            return True  # 管理層全通
        return SiteMapService.check_page_access(role_type, node, user=user)

    except Exception as e:
        logger.warning('SiteMap node access check failed: %s', e)
        return True  # 異常時放行，避免鎖死


def _page_ir_title(page):
    """依使用者語系選 Page IR 標題。"""
    title_i18n = (page.layout_json or {}).get('page', {}).get('title_i18n', {})
    locale = str(get_locale() or 'zh-TW')
    return title_i18n.get(locale) or title_i18n.get('zh-TW') or page.name or ''
