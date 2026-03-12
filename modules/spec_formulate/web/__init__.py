"""
Spec Formulate Module - Web Routes
規格制定模組頁面路由
"""
from flask import Blueprint, render_template

from app.security.decorators import login_required as security_login_required

web_bp = Blueprint(
    'spec_formulate_web',
    __name__,
    url_prefix='/spec-formulate',
    template_folder='../templates'
)


@web_bp.route('/')
@security_login_required
def data_specs():
    """資料表規格管理"""
    return render_template('modules/spec_formulate/data_spec_list.html')


@web_bp.route('/new')
@security_login_required
def data_spec_new():
    """獨立規格編輯器（新建）"""
    return render_template(
        'modules/spec_formulate/field_spec_editor.html',
        mode='standalone',
        form_template_secure_code='',
    )


@web_bp.route('/<spec_sc>/edit')
@security_login_required
def data_spec_edit(spec_sc):
    """獨立規格編輯器（編輯）"""
    return render_template(
        'modules/spec_formulate/field_spec_editor.html',
        mode='standalone',
        spec_sc=spec_sc,
        form_template_secure_code='',
    )


@web_bp.route('/<form_template_sc>/sync')
@security_login_required
def data_spec_sync(form_template_sc):
    """同步中控台"""
    return render_template(
        'modules/spec_formulate/sync_control.html',
        form_template_secure_code=form_template_sc,
    )
