"""
BeakMask Main Web Routes
主要網頁路由
"""
import logging
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import current_user

from ..security.decorators import login_required, public_route
from ..utils.timezone import get_timezone_choices
from .. import db

logger = logging.getLogger(__name__)

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
@public_route
def index():
    """首頁 - 重導向到儀表板或登入頁"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))


@main_bp.route('/dashboard')
@login_required
def dashboard():
    """儀表板"""
    from ..models.user import User, UserType

    # 企業管理員相關提示
    show_default_admin_warning = False
    show_disable_default_admin_hint = False

    if current_user.user_type == UserType.ORG_ADMIN:
        if current_user.is_original_admin and current_user.username == 'admin':
            show_default_admin_warning = True
        else:
            default_admin = User.query.filter(
                User.org_secure_code == current_user.org_secure_code,
                User.username == 'admin',
                User.is_original_admin == True,
                User.is_active == True,
                User.is_deleted == False
            ).first()
            if default_admin:
                show_disable_default_admin_hint = True

    # 待簽核數量（直接查 DB，不經模組權限）
    pending_count = 0
    try:
        from modules.form_workflow.models import FwNodeExecutionQueue
        from sqlalchemy import and_

        user_code = current_user.secure_code
        org_code = current_user.org_secure_code

        if org_code:
            tasks = FwNodeExecutionQueue.query.filter(
                and_(
                    FwNodeExecutionQueue.org_secure_code == org_code,
                    FwNodeExecutionQueue.status == 'WAITING',
                    FwNodeExecutionQueue.node_type.in_(['Approve', 'FormAdapter'])
                )
            ).all()

            for task in tasks:
                task_data = (task.result or {}).get('data', {})
                assignee_type = task_data.get('assignee_type')
                assignees = task_data.get('assignees', [])
                if not assignee_type or user_code in assignees:
                    pending_count += 1
    except Exception as e:
        logger.warning('Dashboard pending count query failed: %s', e)

    return render_template(
        'pages/dashboard.html',
        show_default_admin_warning=show_default_admin_warning,
        show_disable_default_admin_hint=show_disable_default_admin_hint,
        pending_count=pending_count
    )


# 支援的介面語言
SUPPORTED_LANGUAGES = [
    ('', '使用企業預設'),
    ('zh-TW', '繁體中文'),
    ('zh-CN', '简体中文'),
    ('en', 'English'),
    ('ja', '日本語'),
]


@main_bp.route('/personal-settings', methods=['GET', 'POST'])
@login_required
def personal_settings():
    """個人設定頁面"""
    if request.method == 'POST':
        try:
            # 更新個人資料
            current_user.english_name = request.form.get('english_name', '').strip() or None
            current_user.native_name = request.form.get('native_name', '').strip() or None
            current_user.nickname = request.form.get('nickname', '').strip() or None

            # 備用 Email 1 (系統通知專用)：空白時自動使用主要 Email
            backup_email_1 = request.form.get('backup_email_1', '').strip()
            current_user.backup_email_1 = backup_email_1 if backup_email_1 else current_user.email

            current_user.backup_email_2 = request.form.get('backup_email_2', '').strip() or None
            current_user.mobile_phone_1 = request.form.get('mobile_phone_1', '').strip() or None
            current_user.mobile_phone_2 = request.form.get('mobile_phone_2', '').strip() or None
            current_user.interface_language = request.form.get('interface_language', '').strip() or None
            current_user.timezone = request.form.get('timezone', '').strip() or None
            current_user.navbar_display = request.form.get('navbar_display', '').strip() or None

            db.session.commit()
            flash('個人設定已儲存', 'success')
            return redirect(url_for('main.personal_settings'))

        except Exception as e:
            db.session.rollback()
            flash(f'儲存失敗: {str(e)}', 'error')

    return render_template(
        'pages/personal_settings.html',
        languages=SUPPORTED_LANGUAGES,
        timezone_choices=get_timezone_choices()
    )


@main_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """變更密碼頁面"""
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        # 驗證當前密碼
        if not current_user.check_password(current_password):
            flash('目前密碼不正確', 'error')
        elif not new_password:
            flash('請輸入新密碼', 'error')
        elif new_password != confirm_password:
            flash('新密碼與確認密碼不一致', 'error')
        else:
            try:
                current_user.set_password(new_password)
                current_user.password_changed_at = datetime.utcnow()
                current_user.must_change_password = False
                db.session.commit()

                flash('密碼已變更成功', 'success')
                return redirect(url_for('main.personal_settings'))

            except Exception as e:
                db.session.rollback()
                flash(f'變更失敗: {str(e)}', 'error')

    return render_template('pages/change_password.html')


@main_bp.route('/p/<secure_code>')
@login_required
def published_page(secure_code):
    """
    Web Builder 上線版頁面

    僅限 status='published' 的頁面。
    支援子系統 context query params: ?sub=<sub_sc>&ssp=<ssp_sc>
    """
    from app.security.resource_gateway import ResourceGateway

    try:
        # 動態 import 模組 Model（避免循環引用）
        from modules.data_crud.models import DcPageLayout

        page = ResourceGateway.get(
            DcPageLayout, secure_code,
            raise_on_not_found=False,
            check_permission=False
        )
    except Exception:
        abort(404)
        return

    if not page or page.is_deleted or page.status != 'published':
        abort(404)

    # 子系統 context
    sub_sc = request.args.get('sub', '').strip()
    ssp_sc = request.args.get('ssp', '').strip()

    sub_system_context = None
    if sub_sc and ssp_sc:
        try:
            from modules.data_crud.web import _build_sub_system_context
            sub_system_context = _build_sub_system_context(sub_sc, ssp_sc)
        except Exception as e:
            logger.warning('Failed to build sub system context for /p/: %s', e)

    return render_template(
        'modules/data_crud/lab_view.html',
        secure_code=secure_code,
        page_name=page.name or '',
        sub_system_context=sub_system_context,
    )
