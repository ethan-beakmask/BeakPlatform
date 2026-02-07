"""
BeakPlatform Enterprise Admin Management Web Routes
企業管理員帳號管理網頁路由

功能：
1. 專門管理企業管理員帳號
2. 至少保留一個管理員
3. 可停用預設 admin 帳號
"""
from datetime import datetime
from flask import Blueprint, render_template, abort, request, flash, redirect, url_for
from flask_login import current_user

from ..security.decorators import admin_required
from ..security.resource_gateway import ResourceGateway
from ..models.user import User, UserType
from .. import db

org_admins_bp = Blueprint('org_admins', __name__)


def _count_active_admins(org_secure_code: str) -> int:
    """計算企業中啟用的管理員數量"""
    return User.query.filter(
        User.org_secure_code == org_secure_code,
        User.user_type == UserType.ORG_ADMIN,
        User.is_active == True,
        User.is_deleted == False
    ).count()


@org_admins_bp.route('/admin/org-admins')
@admin_required
def list_admins():
    """企業管理員列表"""
    admins = User.query.filter(
        User.org_secure_code == current_user.org_secure_code,
        User.user_type == UserType.ORG_ADMIN,
        User.is_deleted == False
    ).order_by(User.created_at).all()

    active_count = _count_active_admins(current_user.org_secure_code)

    return render_template(
        'pages/admin/org-admins/list.html',
        admins=admins,
        active_count=active_count
    )


@org_admins_bp.route('/admin/org-admins/create', methods=['GET', 'POST'])
@admin_required
def create_admin():
    """新增企業管理員"""
    form_data = {}

    # 先取得所有已被綁定的員工 secure_code
    bound_employee_codes = db.session.query(User.bound_employee_secure_code).filter(
        User.org_secure_code == current_user.org_secure_code,
        User.bound_employee_secure_code.isnot(None),
        User.is_deleted == False
    ).all()
    bound_codes = {code[0] for code in bound_employee_codes}

    # 取得可綁定的員工
    available_employees = User.query.filter(
        User.org_secure_code == current_user.org_secure_code,
        User.employee_id.isnot(None),
        User.employee_id != '',
        User.user_type == UserType.EMPLOYEE,
        User.is_active == True,
        User.is_deleted == False,
        ~User.secure_code.in_(bound_codes) if bound_codes else True
    ).order_by(User.display_name).all()

    if request.method == 'POST':
        bound_employee_code = request.form.get('bound_employee', '').strip()
        password = request.form.get('password', '').strip()

        # 驗證必填欄位
        if not bound_employee_code:
            flash('請選擇要綁定的員工帳號', 'error')
        elif not password:
            flash('請輸入密碼', 'error')
        elif len(password) < 8:
            flash('密碼至少需要 8 個字元', 'error')
        else:
            # 驗證綁定的員工
            bound_employee = User.query.filter(
                User.secure_code == bound_employee_code,
                User.org_secure_code == current_user.org_secure_code,
                User.employee_id.isnot(None),
                User.is_active == True,
                User.is_deleted == False
            ).first()

            if not bound_employee:
                flash('選擇的員工帳號無效', 'error')
            elif bound_employee.secure_code in bound_codes:
                flash('此員工已被其他管理員綁定', 'error')
            else:
                org = current_user.organization
                if not org:
                    flash('找不到所屬企業', 'error')
                else:
                    # 從綁定員工帶入資料
                    username = bound_employee.username
                    display_name = bound_employee.display_name
                    email = bound_employee.email
                    notify_email = bound_employee.backup_email_1 or email

                    # 檢查是否已存在同 email 的管理員帳號
                    # 注意：員工帳號和管理員帳號 email 相同是允許的嗎？
                    # 不行，email 是 unique 的，所以管理員帳號需要不同的 email
                    # 方案：使用 admin-{username}@domain 作為管理員帳號
                    admin_username = f"admin-{username}"
                    admin_email = f"{admin_username}@{org.domain_name}"

                    existing = User.query.filter_by(email=admin_email, is_deleted=False).first()
                    if existing:
                        flash(f'管理員帳號 {admin_username} 已存在', 'error')
                    else:
                        try:
                            user = User(
                                username=admin_username,
                                email=admin_email,
                                display_name=display_name,
                                org_secure_code=org.secure_code,
                                user_type=UserType.ORG_ADMIN,
                                is_active=True,
                                backup_email_1=notify_email,
                                bound_employee_secure_code=bound_employee_code,
                            )
                            user.set_password(password)
                            db.session.add(user)
                            db.session.commit()

                            flash(f'已建立管理員 {admin_username}（綁定員工：{bound_employee.display_name}）', 'success')
                            return redirect(url_for('org_admins.list_admins'))
                        except Exception as e:
                            db.session.rollback()
                            flash(f'建立失敗: {str(e)}', 'error')

        # 保留表單資料供錯誤時回填
        form_data = {'bound_employee': bound_employee_code}

    return render_template(
        'pages/admin/org-admins/create.html',
        form_data=form_data,
        available_employees=available_employees
    )


@org_admins_bp.route('/admin/org-admins/<secure_code>/toggle-status', methods=['POST'])
@admin_required
def toggle_status(secure_code: str):
    """切換管理員啟用狀態"""
    try:
        admin = ResourceGateway.get(User, secure_code)
    except Exception:
        abort(404)

    # 確認是企業管理員
    if admin.user_type != UserType.ORG_ADMIN:
        flash('此帳號不是企業管理員', 'error')
        return redirect(url_for('org_admins.list_admins'))

    # 不能停用自己
    if admin.secure_code == current_user.secure_code:
        flash('不能停用自己的帳號', 'error')
        return redirect(url_for('org_admins.list_admins'))

    # 如果要停用，檢查是否為最後一個啟用的管理員
    if admin.is_active:
        active_count = _count_active_admins(current_user.org_secure_code)
        if active_count <= 1:
            flash('必須至少保留一個啟用的管理員', 'error')
            return redirect(url_for('org_admins.list_admins'))

    try:
        admin.is_active = not admin.is_active
        db.session.commit()
        status = '啟用' if admin.is_active else '停用'
        flash(f'已{status}管理員 {admin.display_name}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'操作失敗: {str(e)}', 'error')

    return redirect(url_for('org_admins.list_admins'))


@org_admins_bp.route('/admin/org-admins/<secure_code>/delete', methods=['POST'])
@admin_required
def delete_admin(secure_code: str):
    """刪除管理員"""
    try:
        admin = ResourceGateway.get(User, secure_code)
    except Exception:
        abort(404)

    # 確認是企業管理員
    if admin.user_type != UserType.ORG_ADMIN:
        flash('此帳號不是企業管理員', 'error')
        return redirect(url_for('org_admins.list_admins'))

    # 不能刪除自己
    if admin.secure_code == current_user.secure_code:
        flash('不能刪除自己的帳號', 'error')
        return redirect(url_for('org_admins.list_admins'))

    # 檢查是否為最後一個啟用的管理員
    if admin.is_active:
        active_count = _count_active_admins(current_user.org_secure_code)
        if active_count <= 1:
            flash('必須至少保留一個啟用的管理員', 'error')
            return redirect(url_for('org_admins.list_admins'))

    try:
        admin.is_deleted = True
        admin.deleted_at = datetime.utcnow()
        db.session.commit()
        flash(f'已刪除管理員 {admin.display_name}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'刪除失敗: {str(e)}', 'error')

    return redirect(url_for('org_admins.list_admins'))


@org_admins_bp.route('/admin/org-admins/<secure_code>/reset-password', methods=['POST'])
@admin_required
def reset_password(secure_code: str):
    """重設企業管理員密碼"""
    from ..services.email_service import EmailService

    try:
        admin = ResourceGateway.get(User, secure_code)
    except Exception:
        flash('找不到該管理員', 'error')
        return redirect(url_for('org_admins.list_admins'))

    # 確認是企業管理員
    if admin.user_type != UserType.ORG_ADMIN:
        flash('此帳號不是企業管理員', 'error')
        return redirect(url_for('org_admins.list_admins'))

    # 不能重設自己的密碼（應使用個人密碼變更功能）
    if admin.secure_code == current_user.secure_code:
        flash('請使用「變更密碼」功能修改自己的密碼', 'error')
        return redirect(url_for('org_admins.list_admins'))

    new_password = request.form.get('new_password', '').strip()
    confirm_password = request.form.get('confirm_password', '').strip()

    # 驗證
    if not new_password:
        flash('請輸入新密碼', 'error')
    elif len(new_password) < 8:
        flash('密碼至少需要 8 個字元', 'error')
    elif new_password != confirm_password:
        flash('兩次輸入的密碼不一致', 'error')
    else:
        try:
            admin.set_password(new_password)
            admin.password_changed_at = datetime.utcnow()
            db.session.commit()

            # 通知所有企業管理員（包含停用中的帳號）
            all_admins = User.query.filter(
                User.org_secure_code == current_user.org_secure_code,
                User.user_type == UserType.ORG_ADMIN,
                User.is_deleted == False
            ).all()

            # 收集所有管理員的通知 email（優先使用 backup_email_1）
            notify_emails = []
            for a in all_admins:
                email = a.backup_email_1 or a.email
                if email and email not in notify_emails:
                    notify_emails.append(email)

            # 發送通知
            if notify_emails:
                org = current_user.organization
                org_name = org.name if org else '未知企業'
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

    return redirect(url_for('org_admins.list_admins'))
