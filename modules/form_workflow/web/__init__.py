"""
FormWorkflow Module - Web Routes
表單流程模組頁面路由

提供表單填寫、簽核等頁面。
"""
from flask import Blueprint, render_template, redirect, url_for, request

from app.security.decorators import login_required as security_login_required
from app.platform.auth import current_user
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
    """表單流程首頁（儀表板）"""
    return render_template('modules/form_workflow/dashboard.html')


@web_bp.route('/dashboard')
@security_login_required
def dashboard():
    """表單流程儀表板"""
    return render_template('modules/form_workflow/dashboard.html')


# =============================================================================
# 表單模板管理
# =============================================================================

@web_bp.route('/templates')
@web_bp.route('/templates/')
@security_login_required
def templates():
    """表單模板列表"""
    return render_template('modules/form_workflow/template_list.html')


@web_bp.route('/templates/new')
@security_login_required
def template_new():
    """建立表單模板（跳轉到列表頁，使用 Modal）"""
    return redirect(url_for('form_workflow_web.templates'))


@web_bp.route('/templates/<secure_code>')
@security_login_required
def template_detail(secure_code):
    """表單設計器（重定向到查詢參數格式）"""
    created = request.args.get('created', '')
    return redirect(f'/api/forms/designer/standalone?id={secure_code}{"&created=1" if created else ""}')


# =============================================================================
# 欄位規格編輯器
# =============================================================================

@web_bp.route('/templates/<secure_code>/spec')
@security_login_required
def template_spec(secure_code):
    """欄位規格編輯器"""
    return render_template(
        'modules/form_workflow/field_spec_editor.html',
        form_template_secure_code=secure_code
    )


# =============================================================================
# 工作流管理
# =============================================================================

@web_bp.route('/workflows')
@web_bp.route('/workflows/')
@security_login_required
def workflows():
    """工作流列表"""
    return render_template('modules/form_workflow/workflow_list.html')


@web_bp.route('/workflows/new')
@security_login_required
def workflow_new():
    """建立工作流（跳轉到列表頁，使用 Modal）"""
    return redirect(url_for('form_workflow_web.workflows'))


@web_bp.route('/workflows/<secure_code>')
@security_login_required
def workflow_detail(secure_code):
    """工作流設計器（重定向到查詢參數格式）"""
    created = request.args.get('created', '')
    return redirect(f'/api/workflows/designer/standalone?id={secure_code}&editable=1{"&created=1" if created else ""}')


@web_bp.route('/workflows/<secure_code>/tree')
@security_login_required
def workflow_tree(secure_code):
    """工作流樹系圖（獨立分頁）"""
    return render_template('modules/form_workflow/workflow_tree.html', secure_code=secure_code)


# =============================================================================
# 表單實例（我的表單）
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
# 配對管理
# =============================================================================

@web_bp.route('/mappings')
@security_login_required
def mappings():
    """配對管理頁面"""
    return render_template('modules/form_workflow/mappings_list.html')


# =============================================================================
# 表單中心
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
# 待簽核任務
# =============================================================================

@web_bp.route('/pending')
@web_bp.route('/pending/')
@security_login_required
def pending():
    """待簽核任務列表"""
    return render_template('modules/form_workflow/pending_list.html')


# =============================================================================
# 資料表規格管理
# =============================================================================

@web_bp.route('/data-specs')
@security_login_required
def data_specs():
    """資料表規格管理"""
    return render_template('modules/form_workflow/data_spec_list.html')


# =============================================================================
# 分類管理
# =============================================================================

@web_bp.route('/categories')
@security_login_required
def categories():
    """分類管理頁面"""
    return render_template('modules/form_workflow/category_list.html')
