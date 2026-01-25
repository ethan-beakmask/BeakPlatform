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
    return redirect(f'/api/forms/designer/standalone?id={secure_code}')


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
    return redirect(f'/api/workflows/designer/standalone?id={secure_code}')


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
    return render_template('modules/form_workflow/form_center.html')


# =============================================================================
# 待簽核任務
# =============================================================================

@web_bp.route('/pending')
@web_bp.route('/pending/')
@security_login_required
def pending():
    """待簽核任務列表"""
    return render_template('modules/form_workflow/pending_list.html')
