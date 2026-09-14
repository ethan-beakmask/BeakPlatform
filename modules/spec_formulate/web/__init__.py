"""
Spec Formulate Module - Web Routes
規格制定模組頁面路由
"""
from flask import Blueprint, render_template

from app.security.decorators import module_access_required

web_bp = Blueprint(
    'spec_formulate_web',
    __name__,
    url_prefix='/spec-formulate',
    template_folder='../templates'
)


@web_bp.route('/')
@module_access_required('spec_formulate')
def spec_schema():
    """規格管理"""
    return render_template('modules/spec_formulate/spec_schema.html')


@web_bp.route('/<spec_sc>/edit')
@module_access_required('spec_formulate')
def spec_schema_edit(spec_sc):
    """規格編輯器"""
    return render_template(
        'modules/spec_formulate/spec_schema_editor.html',
        spec_sc=spec_sc,
    )
