"""
BeakMask Modules Management Web Routes
模組管理頁面路由

NOTE: /modules/ 頁面內容與 /admin/module-permissions 同步顯示模組權限資訊。
      修改模組清單顯示邏輯時，請同步檢查 backend/app/web/admin.py module_permissions()
      以及 templates/pages/admin/module_permissions.html
"""
import json
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user
from flask_babel import gettext as _

from ..security.decorators import system_admin_required
from ..services.module_builder_service import ModuleBuilderService
from ..services.lookup_service import LookupService
from ..models.module import Module
from ..models.organization import Organization
from ..utils.timezone import local_today
from .. import db

modules_web_bp = Blueprint('modules', __name__)


@modules_web_bp.route('/')
@system_admin_required
def list_modules():
    """
    模組列表頁面

    顯示內容與 /admin/module-permissions 一致（模組授權狀態 + 合約資訊）。
    參考: backend/app/web/admin.py module_permissions()
    """
    from ..models.contract import Contract, ContractStatus

    org_sc = current_user.org_secure_code
    org = Organization.query.filter_by(secure_code=org_sc).first()
    today = org.local_today() if org else local_today('Asia/Taipei')

    # 查詢企業的有效合約
    contracts = Contract.query.filter(
        Contract.org_secure_code == org_sc,
        Contract.status == ContractStatus.ACTIVE,
        Contract.start_date <= today,
        Contract.end_date >= today,
        Contract.is_deleted == False
    ).order_by(Contract.end_date.desc()).all()

    # 聯集所有已授權的模組代碼
    authorized_codes = set()
    contract_module_map = []
    for contract in contracts:
        modules = []
        if contract.modules_config:
            try:
                modules = json.loads(contract.modules_config)
                if isinstance(modules, list):
                    authorized_codes.update(modules)
            except (json.JSONDecodeError, TypeError):
                pass
        contract_module_map.append({
            'contract': contract,
            'modules': modules,
        })

    # 取得已安裝模組的詳細資訊
    installed_modules = LookupService.get_items('INSTALLED_MODULES')

    # 合併：標記哪些已授權
    module_list = []
    for mod in installed_modules:
        module_list.append({
            'code': mod['code'],
            'label': mod['label'],
            'authorized': mod['code'] in authorized_codes,
        })

    return render_template(
        'pages/modules/list.html',
        module_list=module_list,
        contracts=contract_module_map,
        authorized_count=len(authorized_codes),
        total_count=len(installed_modules),
    )


@modules_web_bp.route('/create', methods=['GET', 'POST'])
@system_admin_required
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
            flash(_('模組代碼和名稱為必填'), 'error')
        else:
            # 檢查代碼是否已存在
            existing = Module.query.filter_by(code=code, is_deleted=False).first()
            if existing:
                flash(_('模組代碼 %(code)s 已存在', code=code), 'error')
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
                    flash(_('已建立模組 %(name)s', name=name), 'success')
                    return redirect(url_for('modules.view_module', secure_code=module.secure_code))
                except Exception as e:
                    db.session.rollback()
                    flash(_('建立失敗: %(error)s', error=str(e)), 'error')

    return render_template('pages/modules/create.html')


@modules_web_bp.route('/<secure_code>')
@system_admin_required
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
@system_admin_required
def edit_module(secure_code: str):
    """編輯模組頁面"""
    module = Module.query.filter_by(
        secure_code=secure_code,
        is_deleted=False
    ).first()

    if not module:
        abort(404)

    if module.is_system_module:
        flash(_('系統模組不可編輯'), 'error')
        return redirect(url_for('modules.view_module', secure_code=secure_code))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip() or None
        icon = request.form.get('icon', '').strip() or None
        display_order = int(request.form.get('display_order', 0))
        is_active = request.form.get('is_active') == 'on'

        if not name:
            flash(_('模組名稱為必填'), 'error')
        else:
            try:
                module.name = name
                module.description = description
                module.icon = icon
                module.display_order = display_order
                module.is_active = is_active

                db.session.commit()
                flash(_('已更新模組'), 'success')
                return redirect(url_for('modules.view_module', secure_code=secure_code))
            except Exception as e:
                db.session.rollback()
                flash(_('更新失敗: %(error)s', error=str(e)), 'error')

    return render_template('pages/modules/edit.html', module=module)


@modules_web_bp.route('/<secure_code>/delete', methods=['POST'])
@system_admin_required
def delete_module(secure_code: str):
    """刪除模組"""
    module = Module.query.filter_by(
        secure_code=secure_code,
        is_deleted=False
    ).first()

    if not module:
        abort(404)

    if module.is_system_module:
        flash(_('系統模組不可刪除'), 'error')
        return redirect(url_for('modules.view_module', secure_code=secure_code))

    try:
        module.is_deleted = True
        module.deleted_at = datetime.utcnow()
        db.session.commit()
        flash(_('已刪除模組 %(name)s', name=module.name), 'success')
    except Exception as e:
        db.session.rollback()
        flash(_('刪除失敗: %(error)s', error=str(e)), 'error')

    return redirect(url_for('modules.list_modules'))
