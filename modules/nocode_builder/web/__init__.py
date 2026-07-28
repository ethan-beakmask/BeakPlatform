"""
Data CRUD Module - Web Routes
資料表工具頁面路由
"""
import logging

from flask import Blueprint, render_template, request, abort, redirect, url_for
from flask_babel import get_locale
from flask_login import current_user

from app.security.decorators import module_access_required
from app.platform.data import get_current_org

logger = logging.getLogger(__name__)

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
    return render_template(
        'modules/nocode_builder/ir_designer.html',
        secure_code=secure_code,
    )


@web_bp.route('/workspace/<sub_system_sc>')
@nocode_short_bp.route('/workspace/<sub_system_sc>')
@module_access_required('nocode_builder')
def workspace(sub_system_sc):
    """NoCode 統一工作區。"""
    return render_template(
        'modules/nocode_builder/workspace.html',
        sub_system_sc=sub_system_sc,
    )


@web_bp.route('/ir-designer/<secure_code>/preview')
@nocode_short_bp.route('/ir-designer/<secure_code>/preview')
@module_access_required('nocode_builder')
def ir_designer_preview(secure_code):
    """Page IR v3 草稿預覽。"""
    from app.pageir import PageIrRenderError, render_page_ir_full
    from app.security.resource_gateway import ResourceGateway
    from ..models import DcPageLayout

    page = ResourceGateway.get(
        DcPageLayout,
        secure_code,
        raise_on_not_found=False,
        check_permission=False,
    )
    if not page or page.is_deleted:
        abort(404)

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
    )


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
    from ..services.crud_service import resolve_filter_variables
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
