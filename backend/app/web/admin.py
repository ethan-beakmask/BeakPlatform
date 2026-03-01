"""
BeakMask Admin Routes
企業管理員專區 - 各企業的管理功能

路徑：/admin/*
權限：admin_required (企業管理員)
"""
import json
from datetime import date

from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import current_user

from ..security.decorators import admin_required, login_required
from ..utils.timezone import get_timezone_choices
from ..services.lookup_service import LookupService
from .. import db

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/')
@admin_required
def index():
    """企業管理首頁"""
    return render_template('pages/admin/index.html')


@admin_bp.route('/settings')
@admin_required
def settings():
    """
    系統設定頁面 (企業級)

    企業管理員可設定：
    - 企業基本資訊
    - 選單配置
    - 通知設定
    - 整合設定
    """
    return render_template(
        'pages/admin/settings.html',
        timezone_choices=get_timezone_choices()
    )


@admin_bp.route('/settings/general', methods=['GET', 'POST'])
@admin_required
def settings_general():
    """
    一般設定頁面

    包含：
    - 允許用戶修改自己的資料
    """
    org = current_user.organization

    if request.method == 'POST':
        # 取得表單值
        allow_user_self_edit = request.form.get('allow_user_self_edit') == '1'

        # 儲存設定
        org.set_setting('allow_user_self_edit', allow_user_self_edit)
        db.session.commit()

        flash('設定已儲存', 'success')
        return redirect(url_for('admin.settings_general'))

    # 取得目前設定
    settings = org.get_settings()

    return render_template(
        'pages/admin/settings_general.html',
        settings=settings
    )


@admin_bp.route('/module-permissions')
@admin_required
def module_permissions():
    """
    模組權限管理頁面

    列出企業已授權的模組清單（根據有效合約的 modules_config）。
    """
    from ..models.contract import Contract, ContractStatus

    org_sc = current_user.org_secure_code
    today = date.today()

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
        'pages/admin/module_permissions.html',
        module_list=module_list,
        contracts=contract_module_map,
        authorized_count=len(authorized_codes),
        total_count=len(installed_modules),
    )
