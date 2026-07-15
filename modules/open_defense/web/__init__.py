"""
OpenDefense Module - Web Routes

管理員介面:dashboard / decisions / intake-keys / service-accounts。
所有頁面以 @module_access_required 鎖在本模組合約 + admin_required 鎖管理員。
"""
from flask import Blueprint, render_template, redirect, url_for

from app.security.decorators import module_access_required, admin_required

web_bp = Blueprint(
    'open_defense_web',
    __name__,
    url_prefix='/open-defense',
    template_folder='../templates',
)


@web_bp.route('/')
@module_access_required('open_defense', False)
def index():
    return redirect(url_for('open_defense_web.dashboard'))


@web_bp.route('/dashboard')
@module_access_required('open_defense', False)
@admin_required
def dashboard():
    return render_template('modules/open_defense/dashboard.html')


@web_bp.route('/decisions')
@module_access_required('open_defense', False)
@admin_required
def decisions():
    return render_template('modules/open_defense/decisions.html')


@web_bp.route('/intake-keys')
@module_access_required('open_defense', False)
@admin_required
def intake_keys():
    return render_template('modules/open_defense/intake_keys.html')


@web_bp.route('/service-accounts')
@module_access_required('open_defense', False)
@admin_required
def service_accounts():
    return render_template('modules/open_defense/service_accounts.html')


@web_bp.route('/security-cases')
@module_access_required('open_defense', False)
def security_cases():
    """資安案件處置中心（SOC 值班介面）。

    不鎖 admin_required：SOC_L1 值班人員（一般員工）為主要使用者，
    案件與簽核權限由 form_workflow 既有機制把關。
    """
    return render_template('modules/open_defense/security_cases.html')
