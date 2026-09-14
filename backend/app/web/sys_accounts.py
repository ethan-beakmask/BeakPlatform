"""
BeakMask System Accounts Management
系統級帳號管理（僅限系統管理員）

功能：
- 系統管理員帳號的增刪改
- Email 不受 blocked_email_domains 限制
- 左表格 + 右編輯面板布局，新增使用 Modal
"""
import logging
from datetime import datetime
from flask import Blueprint, render_template, abort, request, flash, redirect, url_for, jsonify
from flask_babel import gettext as _
from flask_login import current_user

from ..security.decorators import system_admin_required
from ..models import User, UserType, Organization
from ..constants import SYSTEM_ORG_CODE
from .. import db

logger = logging.getLogger(__name__)

sys_accounts_bp = Blueprint('sys_accounts', __name__)

# 密碼長度限制
MIN_PASSWORD_LENGTH = 12


def _wants_json():
    """判斷是否為 AJAX 請求"""
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json


def _get_system_org():
    """取得系統企業 (SYSTEM_ORG_CODE)"""
    return Organization.query.filter(
        Organization.domain_name == SYSTEM_ORG_CODE,
        Organization.is_deleted == False
    ).first()


def _serialize_account(account, current_user_id):
    """序列化帳號為 JSON 物件"""
    return {
        'secure_code': account.secure_code,
        'username': account.username,
        'email': account.email,
        'display_name': account.display_name,
        'is_active': account.is_active,
        'last_login_at': account.last_login_at.strftime('%Y-%m-%d %H:%M') if account.last_login_at else '',
        'created_at': account.created_at.strftime('%Y-%m-%d %H:%M') if account.created_at else '',
        'password_changed_at': account.password_changed_at.strftime('%Y-%m-%d %H:%M') if account.password_changed_at else '',
        'is_self': account.id == current_user_id
    }


@sys_accounts_bp.route('/')
@system_admin_required
def list_accounts():
    """系統管理員列表（左右分欄布局）"""
    sys_org = _get_system_org()
    if not sys_org:
        flash(_('系統企業不存在'), 'error')
        return redirect(url_for('main.dashboard'))

    accounts = User.query.filter(
        User.org_secure_code == sys_org.secure_code,
        User.user_type == UserType.SYSTEM_ADMIN,
        User.is_deleted == False
    ).order_by(User.created_at.desc()).all()

    accounts_json = [_serialize_account(a, current_user.id) for a in accounts]

    return render_template(
        'pages/sys_accounts/list.html',
        accounts=accounts,
        accounts_json=accounts_json
    )


@sys_accounts_bp.route('/create', methods=['POST'])
@system_admin_required
def create_account():
    """新增系統管理員（僅接受 POST）"""
    sys_org = _get_system_org()
    if not sys_org:
        if _wants_json():
            return jsonify({'success': False, 'errors': [_('系統企業不存在')]}), 400
        flash(_('系統企業不存在'), 'error')
        return redirect(url_for('main.dashboard'))

    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip().lower()
    display_name = request.form.get('display_name', '').strip()
    password = request.form.get('password', '').strip()
    confirm_password = request.form.get('confirm_password', '').strip()

    # 驗證
    errors = []
    if not username:
        errors.append(_('帳號為必填'))
    elif not username.replace('_', '').isalnum():
        errors.append(_('帳號只能包含英數字和底線'))

    if not email:
        errors.append(_('Email 為必填'))
    elif '@' not in email:
        errors.append(_('Email 格式不正確'))

    if not display_name:
        errors.append(_('顯示名稱為必填'))

    if not password:
        errors.append(_('密碼為必填'))
    elif len(password) < MIN_PASSWORD_LENGTH:
        errors.append(_('密碼長度至少 %(min)s 碼', min=MIN_PASSWORD_LENGTH))
    elif password != confirm_password:
        errors.append(_('兩次輸入的密碼不一致'))

    # 檢查帳號/Email 是否重複
    if username:
        existing = User.query.filter(
            User.org_secure_code == sys_org.secure_code,
            User.username == username,
            User.is_deleted == False
        ).first()
        if existing:
            errors.append(_('帳號 %(username)s 已存在', username=username))

    if email:
        existing = User.query.filter(
            User.email == email,
            User.is_deleted == False
        ).first()
        if existing:
            errors.append(_('Email %(email)s 已被使用', email=email))

    if errors:
        if _wants_json():
            return jsonify({'success': False, 'errors': errors}), 400
        for error in errors:
            flash(error, 'error')
        return redirect(url_for('sys_accounts.list_accounts'))

    try:
        user = User(
            org_secure_code=sys_org.secure_code,
            username=username,
            email=email,
            display_name=display_name,
            user_type=UserType.SYSTEM_ADMIN,
            is_active=True,
            must_change_password=False
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        logger.info(f"System admin created: {email} by {current_user.email}")

        if _wants_json():
            return jsonify({'success': True, 'message': _('已建立系統管理員 %(username)s', username=username)})

        flash(_('已建立系統管理員 %(username)s', username=username), 'success')
        return redirect(url_for('sys_accounts.list_accounts'))

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to create system admin: {e}")
        if _wants_json():
            return jsonify({'success': False, 'errors': [_('建立失敗: %(error)s', error=str(e))]}), 500
        flash(_('建立失敗: %(error)s', error=str(e)), 'error')
        return redirect(url_for('sys_accounts.list_accounts'))


@sys_accounts_bp.route('/<secure_code>/edit', methods=['POST'])
@system_admin_required
def edit_account(secure_code: str):
    """編輯系統管理員（僅接受 POST）"""
    sys_org = _get_system_org()
    if not sys_org:
        if _wants_json():
            return jsonify({'success': False, 'errors': [_('系統企業不存在')]}), 400
        flash(_('系統企業不存在'), 'error')
        return redirect(url_for('main.dashboard'))

    user = User.query.filter(
        User.secure_code == secure_code,
        User.org_secure_code == sys_org.secure_code,
        User.user_type == UserType.SYSTEM_ADMIN,
        User.is_deleted == False
    ).first()

    if not user:
        if _wants_json():
            return jsonify({'success': False, 'errors': [_('帳號不存在')]}), 404
        abort(404)

    display_name = request.form.get('display_name', '').strip()
    new_password = request.form.get('new_password', '').strip()
    confirm_password = request.form.get('confirm_password', '').strip()
    is_active = request.form.get('is_active') == '1'

    errors = []
    if not display_name:
        errors.append(_('顯示名稱為必填'))

    # 只有輸入新密碼時才驗證
    if new_password:
        if len(new_password) < MIN_PASSWORD_LENGTH:
            errors.append(_('密碼長度至少 %(min)s 碼', min=MIN_PASSWORD_LENGTH))
        elif new_password != confirm_password:
            errors.append(_('兩次輸入的密碼不一致'))

    # 不能停用自己
    if user.id == current_user.id and not is_active:
        errors.append(_('不能停用自己的帳號'))

    if errors:
        if _wants_json():
            return jsonify({'success': False, 'errors': errors}), 400
        for error in errors:
            flash(error, 'error')
        return redirect(url_for('sys_accounts.list_accounts'))

    try:
        user.display_name = display_name
        user.is_active = is_active

        if new_password:
            user.set_password(new_password)
            user.password_changed_at = datetime.utcnow()
            logger.info(f"Password changed for system admin: {user.email} by {current_user.email}")

        db.session.commit()

        if _wants_json():
            return jsonify({'success': True, 'message': _('已更新帳號資料')})

        flash(_('已更新帳號資料'), 'success')
        return redirect(url_for('sys_accounts.list_accounts'))

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update system admin: {e}")
        if _wants_json():
            return jsonify({'success': False, 'errors': [_('更新失敗: %(error)s', error=str(e))]}), 500
        flash(_('更新失敗: %(error)s', error=str(e)), 'error')
        return redirect(url_for('sys_accounts.list_accounts'))


@sys_accounts_bp.route('/<secure_code>/delete', methods=['POST'])
@system_admin_required
def delete_account(secure_code: str):
    """刪除系統管理員"""
    sys_org = _get_system_org()
    if not sys_org:
        if _wants_json():
            return jsonify({'success': False, 'errors': [_('系統企業不存在')]}), 400
        flash(_('系統企業不存在'), 'error')
        return redirect(url_for('main.dashboard'))

    user = User.query.filter(
        User.secure_code == secure_code,
        User.org_secure_code == sys_org.secure_code,
        User.user_type == UserType.SYSTEM_ADMIN,
        User.is_deleted == False
    ).first()

    if not user:
        if _wants_json():
            return jsonify({'success': False, 'errors': [_('帳號不存在')]}), 404
        abort(404)

    # 不能刪除自己
    if user.id == current_user.id:
        msg = _('不能刪除自己的帳號')
        if _wants_json():
            return jsonify({'success': False, 'errors': [msg]}), 400
        flash(msg, 'error')
        return redirect(url_for('sys_accounts.list_accounts'))

    # 確保至少保留一個系統管理員
    count = User.query.filter(
        User.org_secure_code == sys_org.secure_code,
        User.user_type == UserType.SYSTEM_ADMIN,
        User.is_deleted == False,
        User.is_active == True
    ).count()

    if count <= 1:
        msg = _('至少需要保留一個啟用的系統管理員')
        if _wants_json():
            return jsonify({'success': False, 'errors': [msg]}), 400
        flash(msg, 'error')
        return redirect(url_for('sys_accounts.list_accounts'))

    try:
        user.is_deleted = True
        user.deleted_at = datetime.utcnow()
        db.session.commit()

        logger.info(f"System admin deleted: {user.email} by {current_user.email}")

        if _wants_json():
            return jsonify({'success': True, 'message': _('已刪除系統管理員 %(username)s', username=user.username)})

        flash(_('已刪除系統管理員 %(username)s', username=user.username), 'success')
        return redirect(url_for('sys_accounts.list_accounts'))

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete system admin: {e}")
        if _wants_json():
            return jsonify({'success': False, 'errors': [_('刪除失敗: %(error)s', error=str(e))]}), 500
        flash(_('刪除失敗: %(error)s', error=str(e)), 'error')
        return redirect(url_for('sys_accounts.list_accounts'))
