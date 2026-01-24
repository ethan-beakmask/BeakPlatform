"""
FormWorkflow Module - Web Routes
表單流程模組頁面路由

提供表單填寫、簽核等頁面。
"""
from flask import Blueprint, render_template, redirect, url_for

from app.platform.auth import current_user, require_permission

# 建立 Web Blueprint
web_bp = Blueprint(
    'form_workflow_web',
    __name__,
    url_prefix='/forms',
    template_folder='../templates'
)


@web_bp.route('/')
def index():
    """表單流程首頁"""
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))

    # 暫時導向 API 資訊頁
    return redirect(url_for('form_workflow_api.module_info'))


# 更多頁面路由將在後續移轉中實作
