"""
FormWorkflow Module - Web Routes
表單流程模組頁面路由

提供表單填寫、簽核等頁面。
"""
from flask import Blueprint, render_template, redirect, url_for, request

from app.security.decorators import login_required as security_login_required
from app.platform.auth import current_user, require_permission
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
@security_login_required
def index():
    """表單流程首頁 - 重導到表單中心"""
    return redirect(url_for('form_workflow_web.center'))


# =============================================================================
# 表單模板管理（需要管理權限）
# =============================================================================

@web_bp.route('/templates')
@web_bp.route('/templates/')
@require_permission('form_workflow.template.view')
def templates():
    """表單模板列表"""
    return render_template('modules/form_workflow/template_list.html')


@web_bp.route('/templates/new')
@require_permission('form_workflow.template.create')
def template_new():
    """建立表單模板（跳轉到列表頁，使用 Modal）"""
    return redirect(url_for('form_workflow_web.templates'))


@web_bp.route('/templates/<secure_code>')
@require_permission('form_workflow.template.view')
def template_detail(secure_code):
    """表單設計器（重定向到查詢參數格式）"""
    created = request.args.get('created', '')
    return redirect(f'/api/forms/designer/standalone?id={secure_code}{"&created=1" if created else ""}')


# =============================================================================
# 欄位規格編輯器（需要管理權限）
# =============================================================================

@web_bp.route('/templates/<secure_code>/spec')
@require_permission('form_workflow.template.view')
def template_spec(secure_code):
    """欄位規格編輯器"""
    return render_template(
        'modules/form_workflow/field_spec_editor.html',
        form_template_secure_code=secure_code
    )


# =============================================================================
# 工作流管理（需要管理權限）
# =============================================================================

@web_bp.route('/workflows')
@web_bp.route('/workflows/')
@require_permission('form_workflow.workflow.view')
def workflows():
    """工作流列表"""
    return render_template('modules/form_workflow/workflow_list.html')


@web_bp.route('/workflows/new')
@require_permission('form_workflow.workflow.create')
def workflow_new():
    """建立工作流（跳轉到列表頁，使用 Modal）"""
    return redirect(url_for('form_workflow_web.workflows'))


@web_bp.route('/workflows/<secure_code>')
@require_permission('form_workflow.workflow.view')
def workflow_detail(secure_code):
    """工作流設計器（重定向到查詢參數格式）"""
    created = request.args.get('created', '')
    return redirect(f'/api/workflows/designer/standalone?id={secure_code}&editable=1{"&created=1" if created else ""}')


@web_bp.route('/workflows/<secure_code>/tree')
@require_permission('form_workflow.workflow.view')
def workflow_tree(secure_code):
    """工作流樹系圖（獨立分頁）"""
    return render_template('modules/form_workflow/workflow_tree.html', secure_code=secure_code)


# =============================================================================
# 表單實例（我的表單）- 員工可用
# =============================================================================

@web_bp.route('/instances')
@web_bp.route('/my')
@web_bp.route('/my/')
@security_login_required
def instances():
    """我的表單列表"""
    return render_template('modules/form_workflow/instance_list.html')


@web_bp.route('/instances/<secure_code>')
@security_login_required
def instance_detail(secure_code):
    """表單實例詳情（跳轉到列表頁）"""
    return redirect(url_for('form_workflow_web.instances'))


# =============================================================================
# 配對管理（需要管理權限）
# =============================================================================

@web_bp.route('/mappings')
@require_permission('form_workflow.workflow.manage')
def mappings():
    """配對管理頁面"""
    return render_template('modules/form_workflow/mappings_list.html')


# =============================================================================
# 表單中心 - 員工可用
# =============================================================================

@web_bp.route('/center')
@security_login_required
def center():
    """表單中心頁面"""
    # 取得用戶有效時區：個人設定 > 企業設定 > Asia/Taipei
    user_tz = getattr(current_user, 'timezone', None)
    if not user_tz and hasattr(current_user, 'organization') and current_user.organization:
        user_tz = current_user.organization.get_setting('timezone', 'Asia/Taipei')
    user_tz = user_tz or 'Asia/Taipei'

    # 判斷是否為管理員（用於前端顯示管理功能）
    is_admin = (
        getattr(current_user, 'is_system_admin', False) or
        getattr(current_user, 'level', 0) >= 90
    )

    return render_template(
        'modules/form_workflow/form_center.html',
        user_timezone=user_tz,
        is_admin=is_admin
    )



# =============================================================================
# 待簽核任務 - 員工可用
# =============================================================================

@web_bp.route('/pending')
@web_bp.route('/pending/')
@security_login_required
def pending():
    """待簽核任務列表"""
    return render_template('modules/form_workflow/pending_list.html')


# =============================================================================
# 資料表規格管理（需要管理權限）
# =============================================================================

@web_bp.route('/data-specs')
@require_permission('form_workflow.template.manage')
def data_specs():
    """資料表規格管理"""
    return render_template('modules/form_workflow/data_spec_list.html')


@web_bp.route('/data-specs/new')
@require_permission('form_workflow.template.manage')
def data_spec_new():
    """獨立規格編輯器（新建）"""
    return render_template(
        'modules/form_workflow/field_spec_editor.html',
        mode='standalone',
        form_template_secure_code='',
    )


@web_bp.route('/data-specs/<spec_sc>/edit')
@require_permission('form_workflow.template.manage')
def data_spec_edit(spec_sc):
    """獨立規格編輯器（編輯）"""
    return render_template(
        'modules/form_workflow/field_spec_editor.html',
        mode='standalone',
        spec_sc=spec_sc,
        form_template_secure_code='',
    )


@web_bp.route('/data-specs/<form_template_sc>/sync')
@require_permission('form_workflow.template.manage')
def data_spec_sync(form_template_sc):
    """同步中控台"""
    return render_template(
        'modules/form_workflow/sync_control.html',
        form_template_secure_code=form_template_sc,
    )


# =============================================================================
# 表單風格管理（需要管理權限）
# =============================================================================

@web_bp.route('/form-themes')
@require_permission('form_workflow.admin')
def form_themes():
    """表單風格主題管理頁面"""
    return render_template('modules/form_workflow/form_theme_list.html')


# =============================================================================
# 分類管理（需要管理權限）
# =============================================================================

@web_bp.route('/categories')
@require_permission('form_workflow.admin')
def categories():
    """分類管理頁面"""
    return render_template('modules/form_workflow/category_list.html')
