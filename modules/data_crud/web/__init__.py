"""
Data CRUD Module - Web Routes
資料表工具頁面路由
"""
import logging

from flask import Blueprint, render_template, request, abort
from flask_login import current_user

from app.security.decorators import login_required as security_login_required

logger = logging.getLogger(__name__)

web_bp = Blueprint(
    'data_crud_web',
    __name__,
    url_prefix='/data-crud',
    template_folder='../templates'
)


@web_bp.route('/')
@security_login_required
def index():
    """視圖管理首頁"""
    return render_template('modules/data_crud/view_list.html')


@web_bp.route('/views/new')
@security_login_required
def view_new():
    """建立視圖"""
    return render_template('modules/data_crud/view_config.html', secure_code=None)


@web_bp.route('/views/<secure_code>/config')
@security_login_required
def view_config(secure_code):
    """編輯視圖配置"""
    return render_template('modules/data_crud/view_config.html', secure_code=secure_code)


@web_bp.route('/views/<secure_code>')
@security_login_required
def view_browse(secure_code):
    """資料瀏覽/操作"""
    return render_template('modules/data_crud/view_browse.html', secure_code=secure_code)


@web_bp.route('/lab')
@security_login_required
def lab():
    """Web Builder - 佈局設計器（新頁面）"""
    return render_template('modules/data_crud/lab.html')


@web_bp.route('/lab/<secure_code>')
@security_login_required
def lab_edit(secure_code):
    """Web Builder - 佈局設計器（編輯既有頁面）"""
    return render_template('modules/data_crud/lab.html')


@web_bp.route('/pages/<secure_code>')
@security_login_required
def page_view(secure_code):
    """Web Builder - 頁面檢視（用戶模式）"""
    # 子系統 context: ?sub=<sub_sc>&ssp=<ssp_sc>
    sub_sc = request.args.get('sub', '').strip()
    ssp_sc = request.args.get('ssp', '').strip()

    sub_system_context = None
    if sub_sc and ssp_sc:
        sub_system_context = _build_sub_system_context(sub_sc, ssp_sc)

    return render_template(
        'modules/data_crud/lab_view.html',
        secure_code=secure_code,
        page_name='',
        sub_system_context=sub_system_context,
    )


@web_bp.route('/sub-systems/<secure_code>/portal')
@security_login_required
def sub_system_portal(secure_code):
    """子系統入口導航頁"""
    from ..models import DcSubSystem
    from ..services.sub_system_service import SubSystemService
    from ..services.site_map_service import SiteMapService
    from app.security.resource_gateway import ResourceGateway

    ss = ResourceGateway.get(
        DcSubSystem, secure_code,
        raise_on_not_found=False,
        check_permission=False
    )
    if not ss or ss.is_deleted or not ss.is_active:
        abort(404)

    role_type = SubSystemService.get_user_role_type(current_user, ss)
    if role_type is None:
        abort(403)

    # 有 site map 時使用 V2 Portal (樹狀選單)
    if SiteMapService.has_site_map(ss.secure_code, ss.org_secure_code):
        return render_template(
            'modules/data_crud/sub_system_portal_v2.html',
            sub_system_sc=secure_code,
            sub_system_name=ss.name,
        )

    # 無 site map 時使用舊卡片 Portal
    return render_template(
        'modules/data_crud/sub_system_portal.html',
        sub_system_sc=secure_code,
        sub_system_name=ss.name,
    )


@web_bp.route('/views/<secure_code>/rows/new')
@security_login_required
def row_create(secure_code):
    """新增資料（全頁面）"""
    return render_template('modules/data_crud/row_form.html', secure_code=secure_code, row_id=None)


@web_bp.route('/views/<secure_code>/rows/<row_id>/edit')
@security_login_required
def row_edit(secure_code, row_id):
    """編輯資料（全頁面）"""
    return render_template('modules/data_crud/row_form.html', secure_code=secure_code, row_id=row_id)


# =============================================================================
# Lookup 管理頁面
# =============================================================================

@web_bp.route('/lookup')
@security_login_required
def lookup_manager():
    """選項清單管理"""
    return render_template('modules/data_crud/lookup_manager.html')


# =============================================================================
# 開發案管理頁面 (Web Builder Studio Phase 1)
# =============================================================================

@web_bp.route('/my-projects')
@security_login_required
def my_projects():
    """我的開發案列表"""
    return render_template('modules/data_crud/my_projects.html')


@web_bp.route('/studio/<secure_code>')
@security_login_required
def studio(secure_code):
    """統一設計器 (Phase 2)"""
    return render_template(
        'modules/data_crud/studio.html',
        sub_system_sc=secure_code,
    )


@web_bp.route('/studio-test/<secure_code>')
@security_login_required
def studio_grid_test(secure_code):
    """Grid 模式測試頁 (standalone, no base.html)"""
    return render_template(
        'modules/data_crud/studio_grid_test.html',
        sub_system_sc=secure_code,
    )


# =============================================================================
# 子系統管理頁面
# =============================================================================

@web_bp.route('/sub-systems')
@security_login_required
def sub_system_list():
    """子系統列表"""
    return render_template('modules/data_crud/sub_system_list.html')


@web_bp.route('/sub-systems/<secure_code>/config')
@security_login_required
def sub_system_config(secure_code):
    """子系統配置"""
    return render_template(
        'modules/data_crud/sub_system_config.html',
        secure_code=secure_code,
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
