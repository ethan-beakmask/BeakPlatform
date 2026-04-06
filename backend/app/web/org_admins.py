"""
BeakMask Enterprise Admin Management Web Routes
企業管理員帳號管理網頁路由

功能：
1. 專門管理企業管理員帳號
2. 至少保留一個管理員
3. 可停用預設 admin 帳號
4. 原始管理員初始設定（建立企業成員帳號並自動產生綁定管理員）
"""
import logging
from datetime import datetime
from flask import Blueprint, render_template, abort, request, flash, redirect, url_for
from flask_login import current_user, logout_user

from ..security.decorators import admin_required, login_required
from ..security.resource_gateway import ResourceGateway
from ..models.user import User, UserType
from ..models.user_numbering_rule import UsedUserNumber
from ..services.numbering_service import NumberingService
from ..services.password_policy_service import PasswordPolicyService
from .. import db

logger = logging.getLogger(__name__)

org_admins_bp = Blueprint('org_admins', __name__)


def _count_active_admins(org_secure_code: str) -> int:
    """計算企業中啟用的管理員數量"""
    return User.query.filter(
        User.org_secure_code == org_secure_code,
        User.user_type == UserType.ORG_ADMIN,
        User.is_active == True,
        User.is_deleted == False
    ).count()


@org_admins_bp.route('/admin/initial-setup', methods=['GET', 'POST'])
@login_required
def initial_setup():
    """
    原始管理員初始設定頁面

    原始管理員 (admin@domain) 首次登入後，強制在此頁建立企業成員帳號。
    建立完成後自動產生綁定的管理員帳號 (admin-{username})，
    並停用原始管理員帳號。

    此頁面無選單，為獨立的初始化精靈。
    不可被誤刪：由 auth_interceptor [AUTH-03] 強制導向。
    """
    # 只有原始管理員才能存取
    if not current_user.is_original_admin:
        return redirect(url_for('main.dashboard'))

    # 如果已有綁定管理員，不需要再設定
    has_bound_admin = User.query.filter(
        User.org_secure_code == current_user.org_secure_code,
        User.user_type == UserType.ORG_ADMIN,
        User.bound_employee_secure_code.isnot(None),
        User.is_active == True,
        User.is_deleted == False
    ).first() is not None
    if has_bound_admin:
        return redirect(url_for('main.dashboard'))

    org = current_user.organization
    if not org:
        flash('找不到所屬企業', 'error')
        return redirect(url_for('auth.login'))

    form_data = {}

    if request.method == 'POST':
        # 收集表單資料
        form_data = {
            'native_name': request.form.get('native_name', '').strip(),
            'english_name': request.form.get('english_name', '').strip(),
            'username': request.form.get('username', '').strip(),
            'employee_id': request.form.get('employee_id', '').strip(),
            'nickname': request.form.get('nickname', '').strip(),
            'backup_email_1': request.form.get('backup_email_1', '').strip(),
            'mobile_phone_1': request.form.get('mobile_phone_1', '').strip(),
        }

        native_name = form_data['native_name']
        english_name = form_data['english_name']
        username_raw = form_data['username']
        username = ''.join(username_raw.split()).lower()
        employee_id = form_data['employee_id'] or None
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        nickname = form_data['nickname'] or None
        backup_email_1 = form_data['backup_email_1'] or None
        mobile_phone_1 = form_data['mobile_phone_1'] or None

        # 用戶編號: 留空時自動從預設編號規則產生
        auto_generated_id = False
        if not employee_id:
            default_rule = NumberingService.get_default_rule(
                org.secure_code, 'EMPLOYEE'
            )
            if default_rule:
                try:
                    employee_id = NumberingService.get_next_number(
                        default_rule, consume=False
                    )
                    auto_generated_id = True
                except ValueError:
                    pass

        # 密碼政策驗證（先計算，後面 elif 使用）
        pw_valid, pw_errors = (True, [])
        if password:
            pw_valid, pw_errors = PasswordPolicyService.validate_password(
                password, org.secure_code)

        # 驗證必填欄位
        if not native_name or not english_name or not username:
            flash('本國姓名、英文姓名、帳號為必填', 'error')
        elif not employee_id:
            flash('用戶編號為必填，且無可用的預設編號規則', 'error')
        elif not password:
            flash('密碼為必填', 'error')
        elif not pw_valid:
            for err in pw_errors:
                flash(err, 'error')
        elif password != confirm_password:
            flash('兩次輸入的密碼不一致', 'error')
        else:
            employee_email = f"{username}@{org.domain_name}"
            admin_username = f"admin-{username}"
            admin_email = f"{admin_username}@{org.domain_name}"

            # 檢查帳號衝突
            existing_emp = User.query.filter_by(email=employee_email, is_deleted=False).first()
            existing_adm = User.query.filter_by(email=admin_email, is_deleted=False).first()

            if existing_emp:
                flash(f'帳號 {username} 已存在', 'error')
            elif existing_adm:
                flash(f'管理員帳號 {admin_username} 已存在', 'error')
            else:
                # 檢查企業成員編號唯一性
                emp_id_exists = User.query.filter_by(
                    org_secure_code=org.secure_code,
                    employee_id=employee_id,
                    is_deleted=False
                ).first()
                if emp_id_exists:
                    flash(f'用戶編號 {employee_id} 已存在', 'error')
                else:
                    try:
                        # display_name 依企業設定
                        display_name_field = org.get_setting('display_name_field', 'native_name')
                        display_name_map = {
                            'native_name': native_name,
                            'english_name': english_name,
                            'nickname': nickname or native_name,
                            'username': username,
                            'employee_id': employee_id,
                        }
                        display_name = display_name_map.get(display_name_field, native_name)

                        if not backup_email_1:
                            backup_email_1 = employee_email

                        # 1. 建立企業成員帳號
                        employee = User(
                            username=username,
                            email=employee_email,
                            display_name=display_name,
                            org_secure_code=org.secure_code,
                            user_type=UserType.EMPLOYEE,
                            is_active=True,
                            employee_id=employee_id,
                            english_name=english_name,
                            native_name=native_name,
                            nickname=nickname,
                            backup_email_1=backup_email_1,
                            mobile_phone_1=mobile_phone_1,
                        )
                        employee.set_password(password)
                        db.session.add(employee)
                        db.session.flush()  # 取得 secure_code

                        # 記錄用戶編號
                        if employee_id:
                            if auto_generated_id:
                                # 自動產生的編號: consume 並記錄
                                default_rule = NumberingService.get_default_rule(
                                    org.secure_code, 'EMPLOYEE'
                                )
                                if default_rule:
                                    NumberingService.get_next_number(
                                        default_rule, consume=True
                                    )
                                    # consume 已經記錄了 UsedUserNumber，
                                    # 但 user_secure_code 尚未關聯，補上
                                    used = UsedUserNumber.query.filter_by(
                                        org_secure_code=org.secure_code,
                                        number=employee_id
                                    ).first()
                                    if used:
                                        used.user_secure_code = employee.secure_code
                            else:
                                UsedUserNumber.record_number(
                                    org_secure_code=org.secure_code,
                                    number=employee_id,
                                    user_secure_code=employee.secure_code
                                )

                        # 2. 自動建立管理員帳號並綁定
                        admin_user = User(
                            username=admin_username,
                            email=admin_email,
                            display_name=display_name,
                            org_secure_code=org.secure_code,
                            user_type=UserType.ORG_ADMIN,
                            is_active=True,
                            backup_email_1=backup_email_1,
                            bound_employee_secure_code=employee.secure_code,
                        )
                        admin_user.set_password(password)
                        db.session.add(admin_user)

                        # 3. 指派角色（雙鑰匙 Key2 必要）
                        from ..models.role import Role
                        from ..models.associations import UserRoleAssignment
                        org_admin_role = Role.query.filter(
                            Role.org_secure_code == org.secure_code,
                            Role.code == 'ORG_ADMIN',
                            Role.is_deleted == False,
                        ).first()
                        if org_admin_role:
                            role_assignment = UserRoleAssignment(
                                org_secure_code=org.secure_code,
                                user_secure_code=admin_user.secure_code,
                                role_secure_code=org_admin_role.secure_code,
                                assigned_by='system:initial-setup',
                            )
                            db.session.add(role_assignment)

                        # 企業成員帳號指派 EMPLOYEE 角色
                        employee_role = Role.query.filter(
                            Role.org_secure_code == org.secure_code,
                            Role.code == 'EMPLOYEE',
                            Role.is_deleted == False,
                        ).first()
                        if employee_role:
                            emp_role_assignment = UserRoleAssignment(
                                org_secure_code=org.secure_code,
                                user_secure_code=employee.secure_code,
                                role_secure_code=employee_role.secure_code,
                                assigned_by='system:initial-setup',
                            )
                            db.session.add(emp_role_assignment)

                        # 4. 停用原始管理員
                        current_user.is_active = False
                        logger.info(
                            f"[INITIAL-SETUP] org={org.domain_name} "
                            f"employee={username} admin={admin_username} "
                            f"original_admin={current_user.username} deactivated"
                        )

                        db.session.commit()

                        # 4. 登出，導向登入頁
                        logout_user()

                        flash(
                            f'初始設定完成。已建立企業成員帳號 {username} 與管理員帳號 {admin_username}。'
                            f'原始管理員已停用。請使用新的管理員帳號登入。',
                            'success'
                        )
                        return redirect(url_for('auth.org_login', domain_name=org.domain_name))

                    except Exception as e:
                        db.session.rollback()
                        logger.error(f"[INITIAL-SETUP] Failed: {e}")
                        flash(f'建立失敗: {str(e)}', 'error')

    # 取得預設編號規則的下一個建議值
    suggested_employee_id = None
    default_rule = NumberingService.get_default_rule(org.secure_code, 'EMPLOYEE')
    if default_rule:
        try:
            suggested_employee_id = NumberingService.get_next_number(
                default_rule, consume=False
            )
        except ValueError:
            pass

    return render_template(
        'pages/admin/initial_setup.html',
        form_data=form_data,
        org=org,
        suggested_employee_id=suggested_employee_id
    )


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

    # 先取得所有已被綁定的企業成員 secure_code
    bound_employee_codes = db.session.query(User.bound_employee_secure_code).filter(
        User.org_secure_code == current_user.org_secure_code,
        User.bound_employee_secure_code.isnot(None),
        User.is_deleted == False
    ).all()
    bound_codes = {code[0] for code in bound_employee_codes}

    # 取得可綁定的企業成員
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

        # 密碼政策驗證
        pw_valid, pw_errors = (True, [])
        if password:
            pw_valid, pw_errors = PasswordPolicyService.validate_password(
                password, current_user.org_secure_code)

        # 驗證必填欄位
        if not bound_employee_code:
            flash('請選擇要綁定的企業成員帳號', 'error')
        elif not password:
            flash('請輸入密碼', 'error')
        elif not pw_valid:
            for err in pw_errors:
                flash(err, 'error')
        else:
            # 驗證綁定的企業成員
            bound_employee = User.query.filter(
                User.secure_code == bound_employee_code,
                User.org_secure_code == current_user.org_secure_code,
                User.employee_id.isnot(None),
                User.is_active == True,
                User.is_deleted == False
            ).first()

            if not bound_employee:
                flash('選擇的企業成員帳號無效', 'error')
            elif bound_employee.secure_code in bound_codes:
                flash('此企業成員已被其他管理員綁定', 'error')
            else:
                org = current_user.organization
                if not org:
                    flash('找不到所屬企業', 'error')
                else:
                    # 從綁定企業成員帶入資料
                    username = bound_employee.username
                    display_name = bound_employee.display_name
                    email = bound_employee.email
                    notify_email = bound_employee.backup_email_1 or email

                    # 檢查是否已存在同 email 的管理員帳號
                    # 注意：企業成員帳號和管理員帳號 email 相同是允許的嗎？
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

                            # 指派 ORG_ADMIN 角色
                            from ..models.associations import UserRoleAssignment
                            org_admin_role = Role.query.filter(
                                Role.org_secure_code == org.secure_code,
                                Role.code == 'ORG_ADMIN',
                                Role.is_deleted == False,
                            ).first()
                            if org_admin_role:
                                role_assignment = UserRoleAssignment(
                                    org_secure_code=org.secure_code,
                                    user_secure_code=user.secure_code,
                                    role_secure_code=org_admin_role.secure_code,
                                    assigned_by=current_user.email,
                                )
                                db.session.add(role_assignment)

                            # 自動停用預設管理員帳號（名稱易被猜測，安全考量）
                            original_admin = User.query.filter(
                                User.org_secure_code == current_user.org_secure_code,
                                User.is_original_admin == True,
                                User.is_active == True,
                                User.is_deleted == False
                            ).first()
                            disabled_msg = ''
                            if original_admin:
                                original_admin.is_active = False
                                disabled_msg = f'，預設管理員 {original_admin.username} 已自動停用'

                            db.session.commit()

                            flash(f'已建立管理員 {admin_username}（綁定企業成員：{bound_employee.display_name}）{disabled_msg}', 'success')
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

    # 預設管理員帳號僅能由系統管理員啟用
    if not admin.is_active and admin.is_original_admin:
        flash('預設管理員帳號僅能由系統管理員啟用，請聯繫系統管理員', 'error')
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

    # 密碼政策驗證
    pw_valid, pw_errors = (True, [])
    if new_password:
        pw_valid, pw_errors = PasswordPolicyService.validate_password(
            new_password, current_user.org_secure_code,
            user_secure_code=admin.secure_code)

    # 驗證
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
