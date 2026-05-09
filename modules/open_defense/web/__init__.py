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
