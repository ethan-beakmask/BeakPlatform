"""
OpenDefense Module - Web Routes

管理員介面:dashboard / decisions / service-accounts。
所有頁面以 @module_access_required 鎖在本模組合約 + admin_required 鎖管理員。
"""
from flask import Blueprint, render_template, redirect, url_for

from app.security.decorators import module_access_required
from app.services.capability_service import build_caps

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
def dashboard():
    """PERM-01 試點：不鎖 admin_required，存取交給 PageRoleGuard 雙鑰匙。

    企業可自行決定是否透過角色開放給員工（如資安人員）；
    stats API 掛 @page_keys_required 與本頁共用同一組鑰匙。
    """
    return render_template('modules/open_defense/dashboard.html')


@web_bp.route('/decisions')
@module_access_required('open_defense', False)
def decisions():
    caps = build_caps(['open_defense.decision.write'])
    return render_template('modules/open_defense/decisions.html', page_caps=caps)


@web_bp.route('/event-routing')
@module_access_required('open_defense', False)
def event_routing():
    caps = build_caps(['open_defense.admin'])
    return render_template('modules/open_defense/event_routing.html', page_caps=caps)


@web_bp.route('/protected-targets')
@module_access_required('open_defense', False)
def protected_targets():
    caps = build_caps(['open_defense.admin'])
    return render_template('modules/open_defense/protected_targets.html', page_caps=caps)


@web_bp.route('/intake-keys')
@module_access_required('open_defense', False)
def intake_keys():
    return redirect(url_for('security_center.api_keys'))


@web_bp.route('/service-accounts')
@module_access_required('open_defense', False)
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
