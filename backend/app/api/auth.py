"""
BeakMask Authentication API
認證相關路由

登入方式:
1. 共用登入頁: /auth/login
   - 格式: username@domain_name 或 email
2. 企業專屬登入頁: /auth/org/<domain_name>/login
   - 格式: username (自動帶入 domain_name)
"""
import logging
import os
from datetime import datetime
from flask import Blueprint, request, jsonify, redirect, url_for, render_template, session, current_app, flash

from flask_login import login_user, logout_user, current_user

from ..security.decorators import public_route, login_required
from ..security.resource_gateway import ResourceGateway
from ..services.auth_service import AuthService
from ..services.password_policy_service import PasswordPolicyService
from ..models import Organization, User
from .. import limiter, csrf, db

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)


# Rate limit helpers (從 config 讀取)
def _get_login_limit():
    return current_app.config.get('RATELIMIT_LOGIN', '5 per minute')


def _get_forgot_password_limit():
    return current_app.config.get('RATELIMIT_FORGOT_PASSWORD', '3 per hour')


def _get_reset_password_limit():
    return current_app.config.get('RATELIMIT_RESET_PASSWORD', '5 per hour')


def _parse_account(account: str, domain_name: str = None) -> tuple:
    """
    解析帳號格式

    Args:
        account: 帳號輸入 (username@domain 或 username)
        domain_name: 企業專屬登入時的 domain

    Returns:
        tuple: (username, domain_name) 或 (None, None) 如果無法解析
    """
    if not account:
        return None, None

    account = account.strip()

    # 如果包含 @ 且不是專屬登入，則解析 username@domain
    if '@' in account and domain_name is None:
        parts = account.rsplit('@', 1)
        if len(parts) == 2:
            return parts[0], parts[1].lower()

    # 企業專屬登入或不含 @ 的情況
    if domain_name:
        return account, domain_name.lower()

    # 無法解析
    return None, None


def _do_login(username: str, domain_name: str, password: str, is_json: bool, login_type: str = 'shared', org_for_template=None):
    """
    執行登入邏輯

    Args:
        username: 用戶名
        domain_name: 企業 domain
        password: 密碼
        is_json: 是否為 JSON 請求
        login_type: 登入類型 ('shared' 或 'org')
        org_for_template: 企業專屬登入時的 Organization 物件

    Returns:
        Response tuple
    """
    # 錯誤回應處理函數
    def error_response(message, status_code):
        if is_json:
            return jsonify({'error': message}), status_code
        else:
            flash(message, 'error')
            if login_type == 'org' and org_for_template:
                return render_template(
                    'auth/login.html',
                    error=message,
                    login_type='org',
                    org=org_for_template,
                    domain_name=domain_name,
                    show_logo=org_for_template.get_setting('login_employee_show_logo', True),
                    show_org_name=org_for_template.get_setting('login_employee_show_name', True)
                ), status_code
            else:
                return render_template(
                    'auth/login.html',
                    error=message,
                    login_type='shared'
                ), status_code

    # 查詢企業
    org = Organization.query.filter(
        Organization.domain_name == domain_name,
        Organization.is_deleted == False
    ).first()

    if org is None:
        logger.warning(f"Login attempt for unknown domain: {domain_name} from {request.remote_addr}")
        return error_response('帳號或密碼錯誤', 401)

    # 查詢用戶 (支援 username 和 email 登入)
    user = User.query.filter(
        User.org_secure_code == org.secure_code,
        User.is_deleted == False,
        db.or_(
            User.username == username,
            User.email == f'{username}@{domain_name}'
        )
    ).first()

    if user is None:
        logger.warning(f"Login attempt for unknown user: {username}@{domain_name} from {request.remote_addr}")
        # 稽核記錄: 未知用戶登入嘗試
        from ..services.audit_service import AuditService
        AuditService.log_auth_event(
            action='LOGIN_FAILED',
            org_secure_code=org.secure_code,
            details=f'未知用戶: {username}@{domain_name}',
            status_code=401,
        )
        return error_response('帳號或密碼錯誤', 401)

    # 驗證密碼
    if not user.check_password(password):
        logger.warning(f"Failed login attempt for: {username}@{domain_name} from {request.remote_addr}")
        # 稽核記錄: 密碼錯誤
        from ..services.audit_service import AuditService
        AuditService.log_auth_event(
            action='LOGIN_FAILED',
            org_secure_code=org.secure_code,
            user_secure_code=user.secure_code,
            details=f'密碼錯誤: {username}@{domain_name}',
            status_code=401,
        )
        return error_response('帳號或密碼錯誤', 401)

    # 檢查是否可登入
    can_login, error_msg = user.can_login()
    if not can_login:
        logger.warning(f"Login denied for {username}@{domain_name}: {error_msg}")
        # 稽核記錄: 登入被拒
        from ..services.audit_service import AuditService
        AuditService.log_auth_event(
            action='LOGIN_DENIED',
            org_secure_code=org.secure_code,
            user_secure_code=user.secure_code,
            details=f'{error_msg}: {username}@{domain_name}',
            status_code=403,
        )
        return error_response(error_msg, 403)

    # 登入成功
    login_user(user, remember=False)
    user.update_last_login()
    db.session.commit()

    # 設定 session
    session['org_secure_code'] = org.secure_code
    session['org_domain'] = org.domain_name

    logger.info(f"User logged in: {username}@{domain_name} from {request.remote_addr}")

    # 稽核記錄: 登入成功
    from ..services.audit_service import AuditService
    AuditService.log_auth_event(
        action='LOGIN',
        org_secure_code=org.secure_code,
        user_secure_code=user.secure_code,
        details=f'{username}@{domain_name} ({login_type})',
        status_code=200,
    )

    # 檢查是否需要強制變更密碼
    if user.must_change_password:
        session['must_change_password'] = True
        if is_json:
            return jsonify({
                'message': 'Password change required',
                'must_change_password': True,
                'redirect': url_for('auth.change_password')
            }), 200
        else:
            return redirect(url_for('auth.change_password'))

    # JSON 或表單回應
    if is_json:
        return jsonify({
            'message': 'Login successful',
            'user': {
                'id': user.secure_code,
                'username': user.username,
                'email': user.email,
                'name': user.display_name,
                'user_type': user.user_type,
            }
        }), 200
    else:
        return redirect(url_for('main.dashboard'))


@auth_bp.route('/login', methods=['GET', 'POST'])
@public_route
@csrf.exempt  # 登入不需要 CSRF（沒有已登入 session 可被攻擊）
@limiter.limit(_get_login_limit)
def login():
    """
    共用登入端點。

    GET /auth/login - 顯示登入頁面
    POST /auth/login - 處理登入請求

    帳號格式: username@domain_name
    例如: admin@acme.com.tw
    """
    if request.method == 'GET':
        if current_user.is_authenticated:
            return redirect(url_for('main.dashboard'))
        return render_template('auth/login.html', login_type='shared')

    # POST - Handle login
    is_json = request.is_json

    if is_json:
        data = request.get_json()
        account = data.get('account', '').strip() if data else ''
        password = data.get('password', '') if data else ''
    else:
        account = request.form.get('account', '').strip()
        # 偽裝欄位: 真正的密碼從 OTP1 讀取
        password = request.form.get('OTP1', '')
        # Honeypot 偵測: decoy 欄位被填寫 → 可能是自動化攻擊
        _decoy_credential = request.form.get('auth_token', '')
        _decoy_otp2 = request.form.get('OTP2', '')
        if _decoy_credential or _decoy_otp2:
            logger.warning(f"[HONEYPOT] Decoy fields filled on shared login: "
                           f"credential={'Y' if _decoy_credential else 'N'}, "
                           f"OTP2={'Y' if _decoy_otp2 else 'N'} "
                           f"ip={request.remote_addr}")

    # 錯誤回應
    def error_response(message, status_code):
        if is_json:
            return jsonify({'error': message}), status_code
        else:
            from flask import flash
            flash(message, 'error')
            return render_template('auth/login.html', error=message, login_type='shared'), status_code

    if not account or not password:
        return error_response('請輸入帳號和密碼', 400)

    # 解析帳號
    username, domain_name = _parse_account(account)

    if not username or not domain_name:
        return error_response('請輸入正確的帳號格式 (username@domain)', 400)

    return _do_login(username, domain_name, password, is_json)


@auth_bp.route('/org/<domain_name>/login', methods=['GET', 'POST'])
@public_route
@csrf.exempt
@limiter.limit(_get_login_limit)
def org_login(domain_name: str):
    """
    企業專屬登入端點。

    GET /auth/org/<domain_name>/login - 顯示企業登入頁面
    POST /auth/org/<domain_name>/login - 處理登入請求

    帳號格式: username (自動帶入 domain_name)
    """
    domain_name = domain_name.lower().strip()

    # 查詢企業資訊（用於顯示 Logo 和名稱）
    org = ResourceGateway.get_by(
        Organization,
        domain_name=domain_name,
        is_deleted=False,
        is_active=True,
        check_permission=False
    )

    if request.method == 'GET':
        if current_user.is_authenticated:
            return redirect(url_for('main.dashboard'))

        if org is None:
            # 企業不存在或已停用，重導向到共用登入頁
            return redirect(url_for('auth.login'))

        # 取得企業 Logo URL
        logo_url = None
        logo_path = org.get_setting('logo_path')
        if logo_path:
            full_path = os.path.join(current_app.static_folder, logo_path)
            if os.path.exists(full_path):
                logo_url = f'/static/{logo_path}'

        # 登入頁面品牌設定
        show_logo = org.get_setting('login_employee_show_logo', True)
        show_org_name = org.get_setting('login_employee_show_name', True)

        return render_template(
            'auth/login.html',
            login_type='org',
            org=org,
            domain_name=domain_name,
            logo_url=logo_url,
            show_logo=show_logo,
            show_org_name=show_org_name
        )

    # POST - Handle login
    is_json = request.is_json

    if org is None:
        if is_json:
            return jsonify({'error': '企業不存在或已停用'}), 404
        return redirect(url_for('auth.login'))

    if is_json:
        data = request.get_json()
        username = data.get('username', '').strip() if data else ''
        password = data.get('password', '') if data else ''
    else:
        username = request.form.get('username', '').strip()
        # 偽裝欄位: 真正的密碼從 OTP1 讀取
        password = request.form.get('OTP1', '')
        # Honeypot 偵測: decoy 欄位被填寫 → 可能是自動化攻擊
        _decoy_credential = request.form.get('auth_token', '')
        _decoy_otp2 = request.form.get('OTP2', '')
        if _decoy_credential or _decoy_otp2:
            logger.warning(f"[HONEYPOT] Decoy fields filled on org login: "
                           f"credential={'Y' if _decoy_credential else 'N'}, "
                           f"OTP2={'Y' if _decoy_otp2 else 'N'} "
                           f"domain={domain_name} ip={request.remote_addr}")

    # 錯誤回應
    def error_response(message, status_code):
        if is_json:
            return jsonify({'error': message}), status_code
        else:
            from flask import flash
            flash(message, 'error')
            return render_template(
                'auth/login.html',
                error=message,
                login_type='org',
                org=org,
                domain_name=domain_name,
                show_logo=org.get_setting('login_employee_show_logo', True) if org else True,
                show_org_name=org.get_setting('login_employee_show_name', True) if org else True
            ), status_code

    if not username or not password:
        return error_response('請輸入帳號和密碼', 400)

    return _do_login(username, domain_name, password, is_json, login_type='org', org_for_template=org)


@auth_bp.route('/org/<domain_name>/public', methods=['GET'])
@public_route
def org_public(domain_name: str):
    """
    企業專屬公開區入口。

    GET /auth/org/<domain_name>/public - 顯示企業公開區頁面
    """
    domain_name = domain_name.lower().strip()

    # 查詢企業資訊
    org = ResourceGateway.get_by(
        Organization,
        domain_name=domain_name,
        is_deleted=False,
        is_active=True,
        check_permission=False
    )

    if org is None:
        return redirect(url_for('auth.login'))

    # 取得企業 Logo URL
    logo_url = None
    logo_path = org.get_setting('logo_path')
    if logo_path:
        full_path = os.path.join(current_app.static_folder, logo_path)
        if os.path.exists(full_path):
            logo_url = f'/static/{logo_path}'

    # 公開區入口：同時傳入員工和外部的品牌設定（頁面有兩個入口連結）
    show_logo = org.get_setting('login_external_show_logo', True)
    show_org_name = org.get_setting('login_external_show_name', True)

    return render_template(
        'auth/org_public.html',
        org=org,
        domain_name=domain_name,
        logo_url=logo_url,
        show_logo=show_logo,
        show_org_name=show_org_name
    )


@auth_bp.route('/org/<domain_name>/public/login', methods=['GET', 'POST'])
@public_route
@csrf.exempt  # 登入端點不需要 CSRF
@limiter.limit(_get_login_limit)
def org_public_login(domain_name: str):
    """
    非員工（外部人員）專屬登入端點。

    GET /auth/org/<domain_name>/public/login - 顯示非員工登入頁面
    POST /auth/org/<domain_name>/public/login - 處理登入請求

    帳號格式: 完整 Email (如 guest@gmail.com)
    限制: 只允許 user_type = 'EXTERNAL' 的用戶登入
    """
    domain_name = domain_name.lower().strip()

    # 查詢企業資訊
    org = ResourceGateway.get_by(
        Organization,
        domain_name=domain_name,
        is_deleted=False,
        is_active=True,
        check_permission=False
    )

    if request.method == 'GET':
        if current_user.is_authenticated:
            return redirect(url_for('main.dashboard'))

        if org is None:
            return redirect(url_for('auth.login'))

        # 取得企業 Logo URL
        logo_url = None
        logo_path = org.get_setting('logo_path')
        if logo_path:
            full_path = os.path.join(current_app.static_folder, logo_path)
            if os.path.exists(full_path):
                logo_url = f'/static/{logo_path}'

        # 登入頁面品牌設定
        show_logo = org.get_setting('login_external_show_logo', True)
        show_org_name = org.get_setting('login_external_show_name', True)

        return render_template(
            'auth/org_public_login.html',
            org=org,
            domain_name=domain_name,
            logo_url=logo_url,
            show_logo=show_logo,
            show_org_name=show_org_name
        )

    # POST - Handle login
    is_json = request.is_json

    if org is None:
        if is_json:
            return jsonify({'error': '企業不存在或已停用'}), 404
        return redirect(url_for('auth.login'))

    if is_json:
        data = request.get_json()
        email = data.get('email', '').strip().lower() if data else ''
        password = data.get('password', '') if data else ''
    else:
        email = request.form.get('email', '').strip().lower()
        # 偽裝欄位: 真正的密碼從 OTP1 讀取
        password = request.form.get('OTP1', '')
        # Honeypot 偵測: decoy 欄位被填寫 → 可能是自動化攻擊
        _decoy_credential = request.form.get('auth_token', '')
        _decoy_otp2 = request.form.get('OTP2', '')
        if _decoy_credential or _decoy_otp2:
            logger.warning(f"[HONEYPOT] Decoy fields filled on external login: "
                           f"credential={'Y' if _decoy_credential else 'N'}, "
                           f"OTP2={'Y' if _decoy_otp2 else 'N'} "
                           f"domain={domain_name} ip={request.remote_addr}")

    def error_response(msg: str, status_code: int = 400):
        if is_json:
            return jsonify({'error': msg}), status_code
        flash(msg, 'error')
        logo_url = None
        logo_path = org.get_setting('logo_path')
        if logo_path:
            full_path = os.path.join(current_app.static_folder, logo_path)
            if os.path.exists(full_path):
                logo_url = f'/static/{logo_path}'
        return render_template(
            'auth/org_public_login.html',
            org=org,
            domain_name=domain_name,
            logo_url=logo_url,
            show_logo=org.get_setting('login_external_show_logo', True),
            show_org_name=org.get_setting('login_external_show_name', True)
        ), status_code

    if not email or not password:
        return error_response('請輸入 Email 和密碼', 400)

    # 查詢外部人員帳號
    user = ResourceGateway.get_by(
        User,
        email=email,
        org_secure_code=org.secure_code,
        user_type='EXTERNAL',
        is_deleted=False,
        check_permission=False
    )

    if user is None:
        logger.warning(f"[AUTH] 外部人員登入失敗 - 帳號不存在或非外部人員: {email}")
        return error_response('帳號或密碼錯誤', 401)

    if not user.is_active:
        logger.warning(f"[AUTH] 外部人員登入失敗 - 帳號已停用: {email}")
        return error_response('此帳號已停用', 403)

    if not user.check_password(password):
        logger.warning(f"[AUTH] 外部人員登入失敗 - 密碼錯誤: {email}")
        return error_response('帳號或密碼錯誤', 401)

    # 登入成功
    login_user(user, remember=False)
    session['org_domain'] = domain_name
    session['login_type'] = 'external'
    user.last_login_at = datetime.now()
    db.session.commit()

    logger.info(f"[AUTH] 外部人員登入成功: {email} ({org.name})")

    # 稽核記錄: 外部人員登入成功
    from ..services.audit_service import AuditService
    AuditService.log_auth_event(
        action='LOGIN',
        org_secure_code=org.secure_code,
        user_secure_code=user.secure_code,
        details=f'外部人員: {email} ({org.name})',
        status_code=200,
    )

    if is_json:
        return jsonify({
            'success': True,
            'message': '登入成功',
            'redirect': url_for('main.dashboard')
        })

    return redirect(url_for('main.dashboard'))


@auth_bp.route('/logout', methods=['POST'])
@public_route  # 任何人都可以登出（包括未登入狀態）
@csrf.exempt  # 登出不需要 CSRF
def logout():
    """
    安全登出端點。

    完全清除 session、cookie 和相關記憶體。
    POST /auth/logout

    不要求已登入狀態，確保任何情況下都能正常登出。
    登出後導向企業專屬登入頁 (如果有 org_domain)。
    """
    from flask import session, make_response

    # 記錄登出（若已登入）
    user_email = current_user.email if current_user.is_authenticated else 'anonymous'
    logout_user_sc = current_user.secure_code if current_user.is_authenticated else None
    logout_org_sc = current_user.org_secure_code if current_user.is_authenticated else None

    # 稽核記錄: 登出
    if logout_org_sc:
        from ..services.audit_service import AuditService
        AuditService.log_auth_event(
            action='LOGOUT',
            org_secure_code=logout_org_sc,
            user_secure_code=logout_user_sc,
            details=user_email,
            status_code=200,
        )

    # 保存 org_domain 用於登出後導向
    org_domain = session.get('org_domain')

    # 1. Flask-Login 登出
    logout_user()

    # 2. 完全清除 session 資料
    session.clear()

    # 3. 標記 session 為修改過（強制重新生成）
    session.modified = True

    if user_email != 'anonymous':
        logger.info(f"User logged out (secure): {user_email}")

    # 支援表單和 API 兩種回應
    if request.is_json:
        response = jsonify({'message': 'Logout successful'})
    else:
        # 導向企業專屬登入頁或共用登入頁
        if org_domain:
            response = make_response(redirect(url_for('auth.org_login', domain_name=org_domain)))
        else:
            response = make_response(redirect(url_for('auth.login')))

    # 清除所有登入相關 cookie
    response.delete_cookie('remember_token')  # Flask-Login remember me
    response.delete_cookie('beakmask_session')  # Flask session (自定義名稱)
    response.delete_cookie('session')  # 備用：預設 session 名稱

    return response


@auth_bp.route('/me', methods=['GET'])
@login_required
def get_current_user():
    """
    取得當前登入用戶資訊。

    GET /auth/me
    """
    return jsonify({
        'user': {
            'id': current_user.secure_code,
            'email': current_user.email,
            'name': current_user.display_name,
            'org_id': current_user.org_secure_code,
            'is_org_admin': current_user.is_org_admin,
            'is_system_admin': current_user.is_system_admin,
        }
    }), 200


# 密碼長度限制
MIN_PASSWORD_LENGTH = 12


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """
    變更密碼頁面。

    GET /auth/change-password - 顯示變更密碼頁面
    POST /auth/change-password - 處理密碼變更

    密碼規則:
    - 最少 12 碼
    - 無大小寫/數字/符號要求
    """
    is_forced = session.get('must_change_password', False)

    if request.method == 'GET':
        return render_template(
            'auth/change_password.html',
            is_forced=is_forced,
            min_length=MIN_PASSWORD_LENGTH
        )

    # POST - 處理密碼變更
    is_json = request.is_json

    if is_json:
        data = request.get_json()
        current_password = data.get('current_password', '') if data else ''
        new_password = data.get('new_password', '') if data else ''
        confirm_password = data.get('confirm_password', '') if data else ''
    else:
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

    def error_response(message, status_code=400):
        if is_json:
            return jsonify({'error': message}), status_code
        else:
            flash(message, 'error')
            return render_template(
                'auth/change_password.html',
                is_forced=is_forced,
                min_length=MIN_PASSWORD_LENGTH,
                error=message
            ), status_code

    # 驗證當前密碼
    if not current_user.check_password(current_password):
        return error_response('目前密碼錯誤')

    # 驗證新密碼長度
    if len(new_password) < MIN_PASSWORD_LENGTH:
        return error_response(f'新密碼長度至少 {MIN_PASSWORD_LENGTH} 碼')

    # 驗證兩次輸入一致
    if new_password != confirm_password:
        return error_response('兩次輸入的新密碼不一致')

    # 驗證不能與原密碼相同
    if current_password == new_password:
        return error_response('新密碼不能與目前密碼相同')

    # 更新密碼
    current_user.set_password(new_password)
    current_user.must_change_password = False
    current_user.password_changed_at = datetime.utcnow()
    db.session.commit()

    # 清除 session flag
    session.pop('must_change_password', None)

    logger.info(f"Password changed for user: {current_user.email}")

    # 稽核記錄: 密碼變更
    from ..services.audit_service import AuditService
    AuditService.log_auth_event(
        action='CHANGE_PASSWORD',
        org_secure_code=current_user.org_secure_code,
        user_secure_code=current_user.secure_code,
        details=f'密碼變更: {current_user.email}',
        status_code=200,
    )

    if is_json:
        return jsonify({'message': '密碼變更成功'}), 200
    else:
        flash('密碼變更成功', 'success')
        return redirect(url_for('main.dashboard'))


# ==================== 忘記密碼功能 (二階段驗證) ====================

def _process_forgot_password(username: str, domain_name: str, login_type: str, org=None):
    """
    處理忘記密碼請求 (共用邏輯)

    安全設計:
    - 無論帳號是否存在，都顯示相同訊息 (防止帳號列舉)
    - 使用 username@domain 組成 email
    - 二階段驗證: 先寄驗證碼 URL，驗證後才寄暫時密碼
    """
    from ..models import PasswordResetToken
    from ..services.email_service import EmailService

    email = f'{username}@{domain_name}'

    # 查詢企業
    target_org = Organization.query.filter(
        Organization.domain_name == domain_name,
        Organization.is_deleted == False,
        Organization.is_active == True
    ).first()

    # 查詢用戶 (僅用於判斷是否真的發送郵件)
    user = None
    if target_org:
        user = User.query.filter(
            User.org_secure_code == target_org.secure_code,
            User.is_deleted == False,
            db.or_(
                User.username == username,
                User.email == email
            )
        ).first()

    # 建立 Token (即使用戶不存在也建立，防止 timing attack)
    if target_org:
        token = PasswordResetToken.create_for_user(
            org_secure_code=target_org.secure_code,
            email=email
        )
        db.session.add(token)
        db.session.commit()

        # 只有用戶存在時才真的寄信
        if user:
            verification_url = url_for(
                'auth.verify_reset',
                token=token.verification_url_token,
                _external=True
            )
            EmailService.send_password_reset_verification(
                to_email=email,
                verification_url=verification_url,
                verification_code=token.verification_code,
                org_name=target_org.name
            )
            logger.info(f"Password reset requested for: {email}")

    # 一律顯示成功訊息 (防止帳號列舉)
    flash('已寄送密碼重設驗證信到您的信箱，請在 10 分鐘內完成驗證', 'success')

    if login_type == 'org' and org:
        return redirect(url_for('auth.org_login', domain_name=domain_name))
    else:
        return redirect(url_for('auth.login'))


@auth_bp.route('/org/<domain_name>/forgot-password', methods=['GET', 'POST'])
@public_route
@csrf.exempt
@limiter.limit(_get_forgot_password_limit)
def org_forgot_password(domain_name: str):
    """
    企業專屬忘記密碼頁面

    GET: 顯示忘記密碼表單 (只需輸入 username)
    POST: 處理忘記密碼請求
    """
    domain_name = domain_name.lower().strip()

    # 查詢企業資訊
    org = ResourceGateway.get_by(
        Organization,
        domain_name=domain_name,
        is_deleted=False,
        is_active=True,
        check_permission=False
    )

    if org is None:
        return redirect(url_for('auth.login'))

    if request.method == 'GET':
        return render_template(
            'auth/forgot_password.html',
            login_type='org',
            org=org,
            domain_name=domain_name
        )

    # POST - 處理忘記密碼
    username = request.form.get('username', '').strip()

    if not username:
        flash('請輸入帳號', 'error')
        return render_template(
            'auth/forgot_password.html',
            login_type='org',
            org=org,
            domain_name=domain_name
        ), 400

    return _process_forgot_password(username, domain_name, 'org', org)


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@public_route
@csrf.exempt
@limiter.limit(_get_forgot_password_limit)
def forgot_password():
    """
    共用忘記密碼頁面

    GET: 顯示忘記密碼表單 (需輸入 username@domain)
    POST: 處理忘記密碼請求
    """
    if request.method == 'GET':
        return render_template(
            'auth/forgot_password.html',
            login_type='shared'
        )

    # POST - 處理忘記密碼
    account = request.form.get('account', '').strip()

    if not account:
        flash('請輸入帳號', 'error')
        return render_template(
            'auth/forgot_password.html',
            login_type='shared'
        ), 400

    # 解析帳號
    username, domain_name = _parse_account(account)

    if not username or not domain_name:
        # 一律顯示成功訊息 (防止帳號列舉)
        flash('已寄送密碼重設驗證信到您的信箱，請在 10 分鐘內完成驗證', 'success')
        return redirect(url_for('auth.login'))

    return _process_forgot_password(username, domain_name, 'shared')


@auth_bp.route('/verify-reset/<token>', methods=['GET', 'POST'])
@public_route
@csrf.exempt
@limiter.limit(_get_reset_password_limit)
def verify_reset(token: str):
    """
    驗證密碼重設 - 輸入 6 碼驗證碼

    GET: 顯示驗證碼輸入表單
    POST: 驗證 6 碼驗證碼，成功後寄送暫時密碼
    """
    from ..models import PasswordResetToken
    from ..services.email_service import EmailService

    # 查詢 Token
    reset_token = PasswordResetToken.query.filter(
        PasswordResetToken.verification_url_token == token,
        PasswordResetToken.is_deleted == False
    ).first()

    if reset_token is None:
        flash('無效的驗證連結', 'error')
        return redirect(url_for('auth.login'))

    if reset_token.is_expired:
        flash('驗證連結已過期，請重新申請', 'error')
        return redirect(url_for('auth.login'))

    if reset_token.temp_password_sent:
        flash('此驗證連結已使用過', 'error')
        return redirect(url_for('auth.login'))

    # 查詢企業
    org = Organization.query.filter(
        Organization.secure_code == reset_token.org_secure_code,
        Organization.is_deleted == False
    ).first()

    if request.method == 'GET':
        return render_template(
            'auth/verify_reset.html',
            token=token,
            email=reset_token.email,
            org=org
        )

    # POST - 驗證 6 碼驗證碼
    code = request.form.get('code', '').strip()

    if not code:
        flash('請輸入驗證碼', 'error')
        return render_template(
            'auth/verify_reset.html',
            token=token,
            email=reset_token.email,
            org=org
        ), 400

    if not reset_token.verify(code):
        flash('驗證碼錯誤或已過期', 'error')
        return render_template(
            'auth/verify_reset.html',
            token=token,
            email=reset_token.email,
            org=org
        ), 400

    # 驗證成功，產生暫時密碼並寄送
    # 使用高強度密碼生成（忽略企業設定，確保臨時密碼安全）
    temp_password = PasswordPolicyService.generate_strong_password()

    # 查詢並更新用戶密碼
    user = User.query.filter(
        User.org_secure_code == reset_token.org_secure_code,
        User.email == reset_token.email,
        User.is_deleted == False
    ).first()

    if user:
        user.set_password(temp_password)
        user.must_change_password = True
        reset_token.mark_temp_password_sent()
        db.session.commit()

        # 寄送暫時密碼
        EmailService.send_temp_password(
            to_email=reset_token.email,
            temp_password=temp_password,
            org_name=org.name if org else 'BeakMask'
        )
        logger.info(f"Temp password sent for: {reset_token.email}")
    else:
        # 用戶不存在但仍標記為已使用 (防止重複嘗試)
        reset_token.mark_temp_password_sent()
        db.session.commit()

    flash('已寄送暫時密碼到您的信箱，請使用暫時密碼登入後變更密碼', 'success')

    # 導向對應的登入頁
    if org:
        return redirect(url_for('auth.org_login', domain_name=org.domain_name))
    else:
        return redirect(url_for('auth.login'))


# ==================== 密碼政策 API（一般用戶可存取）====================

@auth_bp.route('/password-policy', methods=['GET'])
@login_required
def get_user_password_policy():
    """
    取得當前用戶企業的密碼政策（供前端顯示）

    GET /auth/password-policy

    Returns:
        密碼要求資訊（不含敏感設定如鎖定時間）
    """
    org = current_user.organization
    if not org:
        return jsonify({'success': False, 'message': '找不到企業'}), 404

    policy = PasswordPolicyService.get_policy(org.secure_code)

    # 只回傳前端需要的資訊
    return jsonify({
        'success': True,
        'data': {
            'policy': {
                'enabled': policy.get('enabled', False),
                'min_length': policy.get('min_length', 8),
                'require_uppercase': policy.get('require_uppercase', False),
                'require_lowercase': policy.get('require_lowercase', False),
                'require_digit': policy.get('require_digit', False),
                'require_special': policy.get('require_special', False),
            }
        }
    })


@auth_bp.route('/password-policy/generate', methods=['POST'])
@login_required
def generate_user_password():
    """
    生成符合政策的密碼

    POST /auth/password-policy/generate
    """
    org = current_user.organization
    if not org:
        return jsonify({'success': False, 'message': '找不到企業'}), 404

    password = PasswordPolicyService.generate_password(org.secure_code)

    return jsonify({
        'success': True,
        'data': {
            'password': password
        }
    })


@auth_bp.route('/password-policy/validate', methods=['POST'])
@login_required
def validate_user_password():
    """
    驗證密碼是否符合政策

    POST /auth/password-policy/validate
    Body: {"password": "..."}
    """
    org = current_user.organization
    if not org:
        return jsonify({'success': False, 'message': '找不到企業'}), 404

    data = request.get_json()
    if not data or 'password' not in data:
        return jsonify({'success': False, 'message': '請提供密碼'}), 400

    password = data['password']

    is_valid, errors = PasswordPolicyService.validate_password(
        password,
        org.secure_code,
        check_history=False  # 一般用戶驗證不檢查歷史
    )

    return jsonify({
        'success': True,
        'data': {
            'valid': is_valid,
            'errors': errors
        }
    })
