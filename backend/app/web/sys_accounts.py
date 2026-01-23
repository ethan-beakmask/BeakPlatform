"""
BeakMask System Accounts Management
系統級帳號管理（僅限系統管理員）

功能：
- 系統管理員帳號的增刪改
- Email 不受 blocked_email_domains 限制
"""
import logging
from datetime import datetime
from flask import Blueprint, render_template, abort, request, flash, redirect, url_for
from flask_login import current_user

from ..security.decorators import system_admin_required
from ..models import User, UserType, Organization
from .. import db

logger = logging.getLogger(__name__)

sys_accounts_bp = Blueprint('sys_accounts', __name__)

# 密碼長度限制
MIN_PASSWORD_LENGTH = 12


def _get_system_org():
    """取得系統企業 (system.local)"""
    return Organization.query.filter(
        Organization.domain_name == 'system.local',
        Organization.is_deleted == False
    ).first()


@sys_accounts_bp.route('/')
@system_admin_required
def list_accounts():
    """系統管理員列表"""
    sys_org = _get_system_org()
    if not sys_org:
        flash('系統企業不存在', 'error')
        return redirect(url_for('main.dashboard'))

    accounts = User.query.filter(
        User.org_secure_code == sys_org.secure_code,
        User.user_type == UserType.SYSTEM_ADMIN,
        User.is_deleted == False
    ).order_by(User.created_at.desc()).all()

    return render_template(
        'pages/sys_accounts/list.html',
        accounts=accounts
    )


@sys_accounts_bp.route('/create', methods=['GET', 'POST'])
@system_admin_required
def create_account():
    """新增系統管理員"""
    sys_org = _get_system_org()
    if not sys_org:
        flash('系統企業不存在', 'error')
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        display_name = request.form.get('display_name', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        # 驗證
        errors = []
        if not username:
            errors.append('帳號為必填')
        elif not username.replace('_', '').isalnum():
            errors.append('帳號只能包含英數字和底線')

        if not email:
            errors.append('Email 為必填')
        elif '@' not in email:
            errors.append('Email 格式不正確')

        if not display_name:
            errors.append('顯示名稱為必填')

        if not password:
            errors.append('密碼為必填')
        elif len(password) < MIN_PASSWORD_LENGTH:
            errors.append(f'密碼長度至少 {MIN_PASSWORD_LENGTH} 碼')
        elif password != confirm_password:
            errors.append('兩次輸入的密碼不一致')

        # 檢查帳號/Email 是否重複
        if username:
            existing = User.query.filter(
                User.org_secure_code == sys_org.secure_code,
                User.username == username,
                User.is_deleted == False
            ).first()
            if existing:
                errors.append(f'帳號 {username} 已存在')

        if email:
            existing = User.query.filter(
                User.email == email,
                User.is_deleted == False
            ).first()
            if existing:
                errors.append(f'Email {email} 已被使用')

        if errors:
            for error in errors:
                flash(error, 'error')
        else:
            try:
                user = User(
                    org_secure_code=sys_org.secure_code,
                    username=username,
                    email=email,
                    display_name=display_name,
                    user_type=UserType.SYSTEM_ADMIN,
                    is_active=True,
                    must_change_password=False  # 系統管理員不強制變更密碼
                )
                user.set_password(password)
                db.session.add(user)
                db.session.commit()

                logger.info(f"System admin created: {email} by {current_user.email}")
                flash(f'已建立系統管理員 {username}', 'success')
                return redirect(url_for('sys_accounts.list_accounts'))

            except Exception as e:
                db.session.rollback()
                logger.error(f"Failed to create system admin: {e}")
                flash(f'建立失敗: {str(e)}', 'error')

    return render_template('pages/sys_accounts/create.html')


@sys_accounts_bp.route('/<secure_code>/edit', methods=['GET', 'POST'])
@system_admin_required
def edit_account(secure_code: str):
    """編輯系統管理員（修改密碼）"""
    sys_org = _get_system_org()
    if not sys_org:
        flash('系統企業不存在', 'error')
        return redirect(url_for('main.dashboard'))

    user = User.query.filter(
        User.secure_code == secure_code,
        User.org_secure_code == sys_org.secure_code,
        User.user_type == UserType.SYSTEM_ADMIN,
        User.is_deleted == False
    ).first()

    if not user:
        abort(404)

    if request.method == 'POST':
        display_name = request.form.get('display_name', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        is_active = request.form.get('is_active') == '1'

        errors = []
        if not display_name:
            errors.append('顯示名稱為必填')

        # 只有輸入新密碼時才驗證
        if new_password:
            if len(new_password) < MIN_PASSWORD_LENGTH:
                errors.append(f'密碼長度至少 {MIN_PASSWORD_LENGTH} 碼')
            elif new_password != confirm_password:
                errors.append('兩次輸入的密碼不一致')

        # 不能停用自己
        if user.id == current_user.id and not is_active:
            errors.append('不能停用自己的帳號')

        if errors:
            for error in errors:
                flash(error, 'error')
        else:
            try:
                user.display_name = display_name
                user.is_active = is_active

                if new_password:
                    user.set_password(new_password)
                    user.password_changed_at = datetime.utcnow()
                    logger.info(f"Password changed for system admin: {user.email} by {current_user.email}")

                db.session.commit()
                flash('已更新帳號資料', 'success')
                return redirect(url_for('sys_accounts.list_accounts'))

            except Exception as e:
                db.session.rollback()
                logger.error(f"Failed to update system admin: {e}")
                flash(f'更新失敗: {str(e)}', 'error')

    return render_template(
        'pages/sys_accounts/edit.html',
        account=user,
        is_self=(user.id == current_user.id)
    )


@sys_accounts_bp.route('/<secure_code>/delete', methods=['POST'])
@system_admin_required
def delete_account(secure_code: str):
    """刪除系統管理員"""
    sys_org = _get_system_org()
    if not sys_org:
        flash('系統企業不存在', 'error')
        return redirect(url_for('main.dashboard'))

    user = User.query.filter(
        User.secure_code == secure_code,
        User.org_secure_code == sys_org.secure_code,
        User.user_type == UserType.SYSTEM_ADMIN,
        User.is_deleted == False
    ).first()

    if not user:
        abort(404)

    # 不能刪除自己
    if user.id == current_user.id:
        flash('不能刪除自己的帳號', 'error')
        return redirect(url_for('sys_accounts.edit_account', secure_code=secure_code))

    # 確保至少保留一個系統管理員
    count = User.query.filter(
        User.org_secure_code == sys_org.secure_code,
        User.user_type == UserType.SYSTEM_ADMIN,
        User.is_deleted == False,
        User.is_active == True
    ).count()

    if count <= 1:
        flash('至少需要保留一個啟用的系統管理員', 'error')
        return redirect(url_for('sys_accounts.edit_account', secure_code=secure_code))

    try:
        user.is_deleted = True
        user.deleted_at = datetime.utcnow()
        db.session.commit()

        logger.info(f"System admin deleted: {user.email} by {current_user.email}")
        flash(f'已刪除系統管理員 {user.username}', 'success')
        return redirect(url_for('sys_accounts.list_accounts'))

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete system admin: {e}")
        flash(f'刪除失敗: {str(e)}', 'error')
        return redirect(url_for('sys_accounts.edit_account', secure_code=secure_code))
