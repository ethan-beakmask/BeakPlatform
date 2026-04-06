"""
BeakMask Organization Admin Rescue Web Routes
系統管理員管理企業管理員（救援功能）

功能：
1. 查看特定企業的管理員列表
2. 啟用/停用企業管理員
3. 重設企業管理員密碼
"""
from datetime import datetime
from flask import Blueprint, render_template, abort, request, flash, redirect, url_for
from flask_login import current_user

from ..security.decorators import system_admin_required
from ..security.resource_gateway import ResourceGateway
from ..models.organization import Organization
from ..models.user import User, UserType
from .. import db

org_admin_rescue_bp = Blueprint('org_admin_rescue', __name__)


def _count_active_admins(org_secure_code: str) -> int:
    """計算企業中啟用的管理員數量"""
    return User.query.filter(
        User.org_secure_code == org_secure_code,
        User.user_type == UserType.ORG_ADMIN,
        User.is_active == True,
        User.is_deleted == False
    ).count()


def _get_org_or_404(org_code: str) -> Organization:
    """取得企業，不存在則 404"""
    org = ResourceGateway.get_by(
        Organization,
        secure_code=org_code,
        is_deleted=False,
        check_permission=False
    )
    if not org:
        abort(404)
    return org


@org_admin_rescue_bp.route('/organizations/<org_code>/admins')
@system_admin_required
def list_admins(org_code: str):
    """該企業的管理員列表"""
    org = _get_org_or_404(org_code)

    admins = User.query.filter(
        User.org_secure_code == org.secure_code,
        User.user_type == UserType.ORG_ADMIN,
        User.is_deleted == False
    ).order_by(User.created_at).all()

    active_count = _count_active_admins(org.secure_code)

    return render_template(
        'pages/organizations/admins.html',
        org=org,
        admins=admins,
        active_count=active_count
    )


@org_admin_rescue_bp.route('/organizations/<org_code>/admins/<admin_code>/toggle-status', methods=['POST'])
@system_admin_required
def toggle_status(org_code: str, admin_code: str):
    """切換管理員啟用狀態"""
    org = _get_org_or_404(org_code)

    admin = User.query.filter(
        User.secure_code == admin_code,
        User.org_secure_code == org.secure_code,
        User.user_type == UserType.ORG_ADMIN,
        User.is_deleted == False
    ).first()

    if not admin:
        flash('找不到該管理員', 'error')
        return redirect(url_for('org_admin_rescue.list_admins', org_code=org_code))

    # 如果要停用，檢查是否為最後一個啟用的管理員
    if admin.is_active:
        active_count = _count_active_admins(org.secure_code)
        if active_count <= 1:
            flash('必須至少保留一個啟用的管理員', 'error')
            return redirect(url_for('org_admin_rescue.list_admins', org_code=org_code))

    try:
        admin.is_active = not admin.is_active
        db.session.commit()
        status = '啟用' if admin.is_active else '停用'
        flash(f'已{status}管理員 {admin.display_name}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'操作失敗: {str(e)}', 'error')

    return redirect(url_for('org_admin_rescue.list_admins', org_code=org_code))


@org_admin_rescue_bp.route('/organizations/<org_code>/admins/<admin_code>/reset-password', methods=['POST'])
@system_admin_required
def reset_password(org_code: str, admin_code: str):
    """重設企業管理員密碼"""
    from ..services.email_service import EmailService

    org = _get_org_or_404(org_code)

    admin = User.query.filter(
        User.secure_code == admin_code,
        User.org_secure_code == org.secure_code,
        User.user_type == UserType.ORG_ADMIN,
        User.is_deleted == False
    ).first()

    if not admin:
        flash('找不到該管理員', 'error')
        return redirect(url_for('org_admin_rescue.list_admins', org_code=org_code))

    new_password = request.form.get('new_password', '').strip()
    confirm_password = request.form.get('confirm_password', '').strip()

    # 密碼政策驗證（用目標企業的政策）
    from ..services.password_policy_service import PasswordPolicyService
    pw_valid, pw_errors = (True, [])
    if new_password:
        pw_valid, pw_errors = PasswordPolicyService.validate_password(
            new_password, org.secure_code,
            user_secure_code=admin.secure_code)

    if not new_password:
        flash('請輸入新密碼', 'error')
    elif not pw_valid:
        for err in pw_errors:
            flash(err, 'error')
    elif new_password != confirm_password:
        flash('兩次輸入的密碼不一致', 'error')
    else:
        try:
            admin.set_password(new_password)
            admin.password_changed_at = datetime.utcnow()
            db.session.commit()

            # 通知該企業所有管理員（包含停用中的帳號，作為防弊措施）
            all_admins = User.query.filter(
                User.org_secure_code == org.secure_code,
                User.user_type == UserType.ORG_ADMIN,
                User.is_deleted == False
            ).all()

            notify_emails = []
            for a in all_admins:
                email = a.backup_email_1 or a.email
                if email and email not in notify_emails:
                    notify_emails.append(email)

            if notify_emails:
                org_name = org.name or '未知企業'
                reset_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')

                EmailService.send_admin_password_reset_notification(
                    to_emails=notify_emails,
                    target_admin_name=admin.display_name,
                    target_admin_email=admin.email,
                    operator_name=current_user.display_name,
                    operator_email=current_user.email,
                    org_name=org_name,
                    reset_time=reset_time
                )

            flash(f'已重設 {admin.display_name} 的密碼，並通知所有企業管理員', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'重設密碼失敗: {str(e)}', 'error')

    return redirect(url_for('org_admin_rescue.list_admins', org_code=org_code))
