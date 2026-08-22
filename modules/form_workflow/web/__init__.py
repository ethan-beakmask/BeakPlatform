"""
FormWorkflow Module - Web Routes
表單流程模組頁面路由

提供表單填寫、簽核等頁面。
"""
from flask import Blueprint, render_template, redirect, url_for, request

from app.security.decorators import module_access_required
from app.platform.auth import current_user, has_permission, require_any_permission, require_permission
from app.platform.data import get_current_org

# 建立 Web Blueprint
web_bp = Blueprint(
    'form_workflow_web',
    __name__,
    url_prefix='/forms',
    template_folder='../templates'
)


# =============================================================================
# 主要頁面
# =============================================================================

@web_bp.route('/')
@module_access_required('form_workflow', False)
def index():
    """表單流程首頁 - 重導到表單中心"""
    return redirect(url_for('form_workflow_web.center'))


# =============================================================================
# 表單模板管理（需要管理權限）
# =============================================================================

@web_bp.route('/templates')
@web_bp.route('/templates/')
@module_access_required('form_workflow', False)
@require_permission('form_workflow.template.view')
def templates():
    """表單模板列表"""
    return render_template('modules/form_workflow/template_list.html')


@web_bp.route('/templates/new')
@module_access_required('form_workflow', False)
@require_permission('form_workflow.template.create')
def template_new():
    """建立表單模板（跳轉到列表頁，使用 Modal）"""
    return redirect(url_for('form_workflow_web.templates'))


@web_bp.route('/templates/<secure_code>')
@module_access_required('form_workflow', False)
@require_permission('form_workflow.template.view')
def template_detail(secure_code):
    """表單設計器"""
    from ..models import FwFormTemplate

    org = get_current_org()
    if not org:
        return redirect(url_for('form_workflow_web.templates'))

    template = FwFormTemplate.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    return render_template(
        'modules/form_workflow/form_designer.html',
        org_secure_code=org.secure_code,
        form_secure_code=secure_code,
        form=template.to_dict(include_schema=True) if template else None,
        user_type=current_user.user_type
    )


# =============================================================================
# 工作流管理（需要管理權限）
# =============================================================================

@web_bp.route('/workflows')
@web_bp.route('/workflows/')
@module_access_required('form_workflow', False)
@require_permission('form_workflow.workflow.view')
def workflows():
    """工作流列表"""
    return render_template('modules/form_workflow/workflow_list.html')


@web_bp.route('/workflows/new')
@module_access_required('form_workflow', False)
@require_permission('form_workflow.workflow.create')
def workflow_new():
    """建立工作流（跳轉到列表頁，使用 Modal）"""
    return redirect(url_for('form_workflow_web.workflows'))


@web_bp.route('/workflows/<secure_code>')
@module_access_required('form_workflow', False)
@require_permission('form_workflow.workflow.view')
def workflow_detail(secure_code):
    """工作流設計器"""
    from ..models import FwWorkflowTemplate

    org = get_current_org()
    if not org:
        return redirect(url_for('form_workflow_web.workflows'))

    template = FwWorkflowTemplate.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    return render_template(
        'modules/form_workflow/workflow_designer.html',
        org_secure_code=org.secure_code,
        workflow_secure_code=secure_code,
        workflow=template.to_dict(include_graph=True) if template else None
    )


@web_bp.route('/workflows/<secure_code>/tree')
@module_access_required('form_workflow', False)
@require_permission('form_workflow.workflow.view')
def workflow_tree(secure_code):
    """工作流樹系圖（獨立分頁）"""
    return render_template('modules/form_workflow/workflow_tree.html', secure_code=secure_code)


# =============================================================================
# 表單實例（我的表單）- 企業成員可用
# =============================================================================

@web_bp.route('/instances')
@web_bp.route('/my')
@web_bp.route('/my/')
@module_access_required('form_workflow', False)
def instances():
    """我的表單列表"""
    return render_template('modules/form_workflow/instance_list.html')


@web_bp.route('/instances/<secure_code>')
@module_access_required('form_workflow', False)
def instance_detail(secure_code):
    """表單實例詳情（跳轉到列表頁）"""
    return redirect(url_for('form_workflow_web.instances'))


# =============================================================================
# 配對管理（需要管理權限）
# =============================================================================

@web_bp.route('/mappings')
@module_access_required('form_workflow', False)
@require_any_permission('form_workflow.workflow.manage', 'form_workflow.template.manage')
def mappings():
    """配對管理頁面"""
    org = get_current_org()
    org_name = org.name if org else ''
    return render_template('modules/form_workflow/mappings_list.html', org_name=org_name)


# =============================================================================
# 表單中心 - 企業成員可用
# =============================================================================

@web_bp.route('/center')
@module_access_required('form_workflow', False)
def center():
    """表單中心頁面"""
    # 取得用戶有效時區：個人設定 > 企業設定 > Asia/Taipei
    user_tz = getattr(current_user, 'timezone', None)
    if not user_tz and hasattr(current_user, 'organization') and current_user.organization:
        user_tz = current_user.organization.get_setting('timezone', 'Asia/Taipei')
    user_tz = user_tz or 'Asia/Taipei'

    # 判斷是否為企業管理員（用於前端顯示管理功能，SYSTEM_ADMIN 不適用模組管理）
    is_admin = getattr(current_user, 'is_org_admin', False)

    # 判斷是否為系統管理員
    is_system_admin = str(getattr(current_user, 'user_type', '')) == 'SYSTEM_ADMIN'

    # 判斷是否可試行設計稿
    can_tryout = has_permission('form_workflow.design.tryout')

    # 取得用戶角色碼列表（用於前端按鈕權限控制）
    from app.platform.auth import get_user_roles
    user_role_codes = [r['code'] for r in get_user_roles(current_user)]

    # 用戶語系
    from flask import g
    user_locale = getattr(g, 'locale', 'zh-TW') or 'zh-TW'

    return render_template(
        'modules/form_workflow/form_center.html',
        user_timezone=user_tz,
        is_admin=is_admin,
        is_system_admin=is_system_admin,
        can_tryout=can_tryout,
        user_role_codes=user_role_codes,
        user_locale=user_locale,
        user_secure_code=current_user.secure_code,
    )



# =============================================================================
# 流程大圖 - 企業成員可用（展開子流程 + 簡化視角）
# =============================================================================

@web_bp.route('/flow-overview/<instance_id>')
@module_access_required('form_workflow', False)
def flow_overview(instance_id):
    """流程大圖頁面（全螢幕）"""
    return render_template(
        'modules/form_workflow/flow_overview.html',
        instance_id=instance_id
    )


# =============================================================================
# 待簽核任務 - 企業成員可用
# =============================================================================

@web_bp.route('/pending')
@web_bp.route('/pending/')
@module_access_required('form_workflow', False)
def pending():
    """待簽核任務列表"""
    return render_template('modules/form_workflow/pending_list.html')


# =============================================================================
# 表單風格管理（需要管理權限）
# =============================================================================

@web_bp.route('/form-themes')
@module_access_required('form_workflow', False)
@require_permission('form_workflow.admin')
def form_themes():
    """表單風格主題管理頁面"""
    return render_template('modules/form_workflow/form_theme_list.html')


# =============================================================================
# AI 用量與配額（需要管理權限）
# =============================================================================

@web_bp.route('/ai-usage')
@module_access_required('form_workflow', False)
@require_permission('form_workflow.admin')
def ai_usage():
    """AiAgent 用量與配額管理頁面"""
    from app.services.capability_service import build_caps
    return render_template(
        'modules/form_workflow/ai_usage.html',
        page_caps=build_caps(['form_workflow.admin'])
    )


# =============================================================================
# 分類管理（需要管理權限）
# =============================================================================

@web_bp.route('/categories')
@module_access_required('form_workflow', False)
@require_permission('form_workflow.admin')
def categories():
    """分類管理頁面"""
    return render_template('modules/form_workflow/category_list.html')
