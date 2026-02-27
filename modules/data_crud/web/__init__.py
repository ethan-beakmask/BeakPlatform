"""
Data CRUD Module - Web Routes
資料表工具頁面路由
"""
from flask import Blueprint, render_template

from app.security.decorators import login_required as security_login_required

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
