"""
BeakMask Admin Routes
企業管理員專區 + 系統管理員模組概覽

路徑：/admin/*
權限：admin_required / system_admin_required
"""
import json
from datetime import date

from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_babel import gettext as _
from flask_login import current_user

from ..security.decorators import admin_required, system_admin_required, login_required
from ..utils.timezone import get_timezone_choices, local_today
from ..services.lookup_service import LookupService
from .. import db

admin_bp = Blueprint('admin', __name__)


def _format_remaining(total_days: int) -> str:
    """將剩餘天數格式化為 X年Y月Z日"""
    if total_days < 0:
        return _('已過期')
    years = total_days // 365
    remainder = total_days % 365
    months = remainder // 30
    days = remainder % 30
    parts = []
    if years > 0:
        parts.append(_('%(n)s 年', n=years))
    if months > 0:
        parts.append(_('%(n)s 月', n=months))
    parts.append(_('%(n)s 日', n=days))
    return ' '.join(parts)


@admin_bp.route('/')
@admin_required
def index():
    """企業管理首頁"""
    return render_template('pages/admin/index.html')


@admin_bp.route('/settings')
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


@admin_bp.route('/module-permissions')
def module_permissions():
    """
    模組權限管理頁面

    列出企業已授權的模組清單（根據有效合約的 modules_config）。

    NOTE: 此頁面內容與 /modules/ 同步。修改時請同步檢查:
          - backend/app/web/modules.py list_modules()
          - templates/pages/modules/list.html
    """
    from ..models.contract import Contract, ContractStatus
    from ..models.organization import Organization

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

    # 聯集所有已授權的模組代碼 + 各模組最晚終止日
    authorized_codes = set()
    module_end_dates = {}  # module_code -> latest end_date
    for contract in contracts:
        if contract.modules_config:
            try:
                modules = json.loads(contract.modules_config)
                if isinstance(modules, list):
                    authorized_codes.update(modules)
                    for mc in modules:
                        if contract.end_date:
                            prev = module_end_dates.get(mc)
                            if not prev or contract.end_date > prev:
                                module_end_dates[mc] = contract.end_date
            except (json.JSONDecodeError, TypeError):
                pass

    # 取得已安裝模組的詳細資訊
    installed_modules = LookupService.get_items('INSTALLED_MODULES')

    # 合併：標記哪些已授權 + 計算剩餘時間
    module_list = []
    for mod in installed_modules:
        end_date = module_end_dates.get(mod['code'])
        remaining = None
        if end_date:
            delta = end_date - today
            remaining = _format_remaining(delta.days)
        module_list.append({
            'code': mod['code'],
            'label': mod['label'],
            'authorized': mod['code'] in authorized_codes,
            'end_date': end_date,
            'remaining': remaining,
        })

    return render_template(
        'pages/admin/module_permissions.html',
        module_list=module_list,
        authorized_count=len(authorized_codes),
        total_count=len(installed_modules),
    )


@admin_bp.route('/module-list')
@system_admin_required
def module_list():
    """
    模組清單頁面（系統管理員）

    展示已安裝模組及各企業授權狀態。
    """
    from ..models.contract import Contract, ContractStatus
    from ..models.organization import Organization

    installed_modules = LookupService.get_items('INSTALLED_MODULES')
    today = date.today()

    # 跨租戶查所有 ACTIVE 合約
    contracts = Contract.query.filter(
        Contract.status == ContractStatus.ACTIVE,
        Contract.is_deleted == False
    ).all()

    # 組織名稱快取
    org_names = {}
    org_scs = {c.org_secure_code for c in contracts}
    if org_scs:
        orgs = Organization.query.filter(
            Organization.secure_code.in_(org_scs),
            Organization.is_deleted == False
        ).all()
        org_names = {o.secure_code: o.name for o in orgs}

    # 整理: module_code -> [{org_name, contract_number, end_date, days_remaining}]
    module_orgs = {}
    for c in contracts:
        if not c.modules_config:
            continue
        try:
            modules = json.loads(c.modules_config)
            if not isinstance(modules, list):
                continue
        except (json.JSONDecodeError, TypeError):
            continue

        days_remaining = (c.end_date - today).days if c.end_date else None
        org_name = org_names.get(c.org_secure_code, c.org_secure_code)

        for mc in modules:
            module_orgs.setdefault(mc, []).append({
                'org_name': org_name,
                'contract_number': c.contract_number,
                'end_date': c.end_date.strftime('%Y-%m-%d') if c.end_date else '-',
                'days_remaining': days_remaining,
                'is_expired': c.end_date < today if c.end_date else False,
            })

    # 組合模組列表
    result = []
    for mod in installed_modules:
        orgs_info = module_orgs.get(mod['code'], [])
        active_orgs = [o for o in orgs_info if not o.get('is_expired')]
        result.append({
            'code': mod['code'],
            'label': mod['label'],
            'org_count': len(active_orgs),
            'orgs': orgs_info,
        })

    return render_template(
        'pages/admin/module_list.html',
        modules=result,
    )


@admin_bp.route('/test-treegrid')
@admin_required
def test_treegrid():
    """TreeGrid 元件測試頁（jstree 替代方案評估）"""
    return render_template('pages/admin/test_treegrid.html')
