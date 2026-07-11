"""
BeakMask Profile Web Routes
個人資料網頁路由

注意：個人資料編輯功能已整合到 /users/me/edit
此模組保留基本路由並重導到整合後的頁面
"""
from flask import Blueprint, redirect, url_for, request, flash, render_template
from flask_babel import gettext as _
from flask_login import current_user

from ..security.decorators import login_required
from ..services.password_policy_service import PasswordPolicyService
from .. import db

profile_bp = Blueprint('profile', __name__)


@profile_bp.route('/')
@login_required
def view():
    """個人資料頁面 - 重導到整合後的編輯頁面"""
    return redirect(url_for('users.edit_user', secure_code='me'))


@profile_bp.route('/edit', methods=['GET', 'POST'])
@login_required
def edit():
    """編輯個人資料頁面 - 重導到整合後的編輯頁面"""
    return redirect(url_for('users.edit_user', secure_code='me'))


@profile_bp.route('/password', methods=['GET', 'POST'])
@login_required
def change_password():
    """變更密碼頁面"""
    if request.method == 'POST':
        current_password = request.form.get('current_password', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        # 密碼政策驗證
        pw_valid, pw_errors = (True, [])
        if new_password:
            pw_valid, pw_errors = PasswordPolicyService.validate_password(
                new_password, current_user.org_secure_code,
                user_secure_code=current_user.secure_code)

        if not current_password or not new_password or not confirm_password:
            flash(_('所有欄位為必填'), 'error')
        elif new_password != confirm_password:
            flash(_('新密碼與確認密碼不符'), 'error')
        elif not pw_valid:
            for err in pw_errors:
                flash(err, 'error')
        elif not current_user.check_password(current_password):
            flash(_('目前密碼錯誤'), 'error')
        else:
            try:
                current_user.set_password(new_password)
                db.session.commit()
                flash(_('已變更密碼'), 'success')
                return redirect(url_for('profile.view'))
            except Exception as e:
                db.session.rollback()
                flash(_('變更失敗: %(error)s', error=str(e)), 'error')

    return render_template('pages/profile/password.html')
