"""
BeakPlatform Profile Web Routes
個人資料網頁路由

注意：個人資料編輯功能已整合到 /users/me/edit
此模組保留基本路由並重導到整合後的頁面
"""
from flask import Blueprint, redirect, url_for

from ..security.decorators import login_required

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
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not current_password or not new_password or not confirm_password:
            flash('所有欄位為必填', 'error')
        elif new_password != confirm_password:
            flash('新密碼與確認密碼不符', 'error')
        elif len(new_password) < 8:
            flash('新密碼至少需要 8 個字元', 'error')
        elif not current_user.check_password(current_password):
            flash('目前密碼錯誤', 'error')
        else:
            try:
                current_user.set_password(new_password)
                db.session.commit()
                flash('已變更密碼', 'success')
                return redirect(url_for('profile.view'))
            except Exception as e:
                db.session.rollback()
                flash(f'變更失敗: {str(e)}', 'error')

    return render_template('pages/profile/password.html')
