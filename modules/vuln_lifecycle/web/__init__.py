"""
VulnLifecycle Module - Web Routes
弱點生命週期模組頁面路由
"""
from flask import Blueprint, render_template

from app.security.decorators import module_access_required
from app.platform.auth import require_permission

# 建立 Web Blueprint
web_bp = Blueprint(
    'vuln_lifecycle_web',
    __name__,
    url_prefix='/vuln',
    template_folder='../templates'
)


@web_bp.route('/')
@module_access_required('vuln_lifecycle', False)
def index():
    """模組首頁 - 導向 Dashboard"""
    from flask import redirect, url_for
    return redirect(url_for('vuln_lifecycle_web.dashboard'))


@web_bp.route('/dashboard')
@module_access_required('vuln_lifecycle', False)
@require_permission('vuln_lifecycle.dashboard.view')
def dashboard():
    """弱點儀表板"""
    return render_template('modules/vuln_lifecycle/dashboard.html')


@web_bp.route('/assets')
@module_access_required('vuln_lifecycle', False)
@require_permission('vuln_lifecycle.asset.view')
def assets():
    """資產清冊"""
    return render_template('modules/vuln_lifecycle/assets.html')


@web_bp.route('/assets/<int:asset_id>')
@module_access_required('vuln_lifecycle', False)
@require_permission('vuln_lifecycle.finding.view')
def asset_detail(asset_id):
    """資產弱點詳情"""
    return render_template('modules/vuln_lifecycle/asset_detail.html',
                           asset_id=asset_id)


@web_bp.route('/risk')
@module_access_required('vuln_lifecycle', False)
@require_permission('vuln_lifecycle.risk.view')
def risk_list():
    """風險調整紀錄"""
    return render_template('modules/vuln_lifecycle/risk_list.html')


@web_bp.route('/kynd')
@module_access_required('vuln_lifecycle', False)
@require_permission('vuln_lifecycle.kynd.view')
def kynd():
    """KYND 外部風險監控"""
    return render_template('modules/vuln_lifecycle/kynd.html')
