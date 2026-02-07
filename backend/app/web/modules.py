"""
BeakMask Modules Management Web Routes
模組管理頁面路由 (No-Code Builder)
"""
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user

from ..security.decorators import admin_required
from ..services.module_builder_service import ModuleBuilderService
from ..models.module import Module
from .. import db

modules_web_bp = Blueprint('modules', __name__)


@modules_web_bp.route('/')
@admin_required
def list_modules():
    """模組列表頁面"""
    modules = Module.query.filter(
        Module.is_deleted == False
    ).order_by(Module.display_order, Module.name).all()

    return render_template('pages/modules/list.html', modules=modules)


@modules_web_bp.route('/create', methods=['GET', 'POST'])
@admin_required
def create_module():
    """新增模組頁面"""
    if request.method == 'POST':
        code = request.form.get('code', '').strip().lower()
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip() or None
        icon = request.form.get('icon', '').strip() or None
        create_menu = request.form.get('create_menu') == 'on'
        required_level = int(request.form.get('required_level', 2))

        if not code or not name:
            flash('模組代碼和名稱為必填', 'error')
        else:
            # 檢查代碼是否已存在
            existing = Module.query.filter_by(code=code, is_deleted=False).first()
            if existing:
                flash(f'模組代碼 {code} 已存在', 'error')
            else:
                try:
                    module = ModuleBuilderService.create_module(
                        org_secure_code=current_user.org_secure_code,
                        code=code,
                        name=name,
                        description=description,
                        icon=icon,
                        create_menu=create_menu,
                        required_level=required_level,
                    )
                    db.session.commit()
                    flash(f'已建立模組 {name}', 'success')
                    return redirect(url_for('modules.view_module', secure_code=module.secure_code))
                except Exception as e:
                    db.session.rollback()
                    flash(f'建立失敗: {str(e)}', 'error')

    return render_template('pages/modules/create.html')


@modules_web_bp.route('/<secure_code>')
@admin_required
def view_module(secure_code: str):
    """模組詳情頁面"""
    structure = ModuleBuilderService.get_module_structure(secure_code)
    if not structure:
        abort(404)

    return render_template(
        'pages/modules/view.html',
        secure_code=secure_code,
        module=structure.get('module'),
        pages=structure.get('pages', []),
        menu_items=structure.get('menu_items', [])
    )


@modules_web_bp.route('/<secure_code>/edit', methods=['GET', 'POST'])
@admin_required
def edit_module(secure_code: str):
    """編輯模組頁面"""
    module = Module.query.filter_by(
        secure_code=secure_code,
        is_deleted=False
    ).first()

    if not module:
        abort(404)

    if module.is_system_module:
        flash('系統模組不可編輯', 'error')
        return redirect(url_for('modules.view_module', secure_code=secure_code))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip() or None
        icon = request.form.get('icon', '').strip() or None
        display_order = int(request.form.get('display_order', 0))
        is_active = request.form.get('is_active') == 'on'

        if not name:
            flash('模組名稱為必填', 'error')
        else:
            try:
                module.name = name
                module.description = description
                module.icon = icon
                module.display_order = display_order
                module.is_active = is_active

                db.session.commit()
                flash('已更新模組', 'success')
                return redirect(url_for('modules.view_module', secure_code=secure_code))
            except Exception as e:
                db.session.rollback()
                flash(f'更新失敗: {str(e)}', 'error')

    return render_template('pages/modules/edit.html', module=module)


@modules_web_bp.route('/<secure_code>/delete', methods=['POST'])
@admin_required
def delete_module(secure_code: str):
    """刪除模組"""
    module = Module.query.filter_by(
        secure_code=secure_code,
        is_deleted=False
    ).first()

    if not module:
        abort(404)

    if module.is_system_module:
        flash('系統模組不可刪除', 'error')
        return redirect(url_for('modules.view_module', secure_code=secure_code))

    try:
        module.is_deleted = True
        module.deleted_at = datetime.utcnow()
        db.session.commit()
        flash(f'已刪除模組 {module.name}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'刪除失敗: {str(e)}', 'error')

    return redirect(url_for('modules.list_modules'))
