"""
BeakMask User Management Web Routes
用戶管理網頁路由

URL 安全設計：
1. 使用 secure_code 而非自增 ID
2. 所有頁面經過權限檢查
3. 不可透過 URL 參數猜測存取其他資源
"""
import csv
import io
from datetime import datetime
from flask import Blueprint, render_template, abort, request, flash, redirect, url_for, Response, jsonify
from flask_babel import gettext as _
from flask_login import current_user

from ..security.decorators import login_required
from ..security.resource_gateway import ResourceGateway
from ..models.organization import counts_toward_user_limit
from ..models.user import User, UserType
from ..models.organizational_unit import OrganizationalUnit
from ..models.user_numbering_rule import UsedUserNumber
from ..models.user_unit_membership import UserUnitMembership, MembershipType, MembershipRole
from ..models.work_schedule import WorkSchedule
from ..utils.timezone import get_timezone_choices
from ..services.password_policy_service import PasswordPolicyService
from .. import db

users_bp = Blueprint('users', __name__)


@users_bp.route('/check-username')
def check_username():
    """即時檢查帳號是否可用（排除已刪除，保留停用）"""
    username = request.args.get('username', '').strip().lower()
    if not username:
        return jsonify({'available': False})

    org = current_user.organization
    if not org:
        return jsonify({'available': False})

    email = f"{username}@{org.domain_name}"
    existing = User.query.filter(
        User.email == email,
        User.is_deleted == False
    ).first()

    return jsonify({'available': existing is None})


@users_bp.route('/')
def list_users():
    """一般用戶列表頁面

    此頁面只顯示一般用戶（EMPLOYEE），排除：
    - 系統管理員 → /portal/sys-accounts
    - 企業管理員 → /admin/org-admins
    - 外部廠商 → /external-users
    """
    page = request.args.get('page', 1, type=int)

    # 只顯示一般用戶（EMPLOYEE）
    base_query = User.query.filter(
        User.org_secure_code == current_user.org_secure_code,
        User.is_deleted == False,
        User.user_type == UserType.EMPLOYEE  # 只顯示一般用戶
    ).order_by(User.created_at.desc())

    pagination = base_query.paginate(page=page, per_page=20, error_out=False)

    return render_template(
        'pages/users/list.html',
        users=pagination.items,
        pagination={
            'items': pagination.items,
            'total': pagination.total,
            'page': pagination.page,
            'per_page': pagination.per_page,
            'pages': pagination.pages
        }
    )


@users_bp.route('/<secure_code>')
def view_user(secure_code: str):
    """查看用戶詳情"""
    try:
        user = ResourceGateway.get(User, secure_code)
    except Exception:
        abort(404)

    # 查詢用戶參加的社團 (membership_type='MEMBER' 且 unit_type='GROUP')
    group_memberships = UserUnitMembership.query.filter(
        UserUnitMembership.user_secure_code == user.secure_code,
        UserUnitMembership.membership_type == MembershipType.MEMBER,
        UserUnitMembership.is_deleted == False
    ).all()

    # 過濾出 unit_type='GROUP' 的社團，並整理資料
    groups = []
    for membership in group_memberships:
        if membership.unit and membership.unit.unit_type == 'GROUP':
            role_display = {
                MembershipRole.MANAGER: '團長',
                MembershipRole.DEPUTY: '副團長',
                MembershipRole.PROXY1: '代理人(一)',
                MembershipRole.PROXY2: '代理人(二)',
                MembershipRole.MEMBER: '團員',
            }.get(membership.role_type, '團員')

            groups.append({
                'name': membership.unit.name,
                'code': membership.unit.code,
                'role': role_display,
                'role_type': membership.role_type,
                'start_date': membership.start_date,
            })

    # 查詢跨部門支援清單 (membership_type='DOTTED' 且 unit_type='DEPARTMENT')
    cross_memberships = UserUnitMembership.query.filter(
        UserUnitMembership.user_secure_code == user.secure_code,
        UserUnitMembership.membership_type == MembershipType.DOTTED,
        UserUnitMembership.is_deleted == False
    ).all()

    # 整理跨部門支援資料
    cross_departments = []
    for membership in cross_memberships:
        if membership.unit and membership.unit.unit_type == 'DEPARTMENT':
            role_display = {
                MembershipRole.MANAGER: '跨部門主管',
                MembershipRole.DEPUTY: '跨部門副主管',
                MembershipRole.PROXY1: '代理人(一)',
                MembershipRole.PROXY2: '代理人(二)',
                MembershipRole.MEMBER: '支援人員',
            }.get(membership.role_type, '支援人員')

            cross_departments.append({
                'name': membership.unit.name,
                'code': membership.unit.code,
                'role': role_display,
                'role_type': membership.role_type,
                'start_date': membership.start_date,
            })

    # 判斷是否有權限重設密碼
    is_admin = current_user.is_org_admin or current_user.is_system_admin
    is_self = user.secure_code == current_user.secure_code
    # 企業管理員可重設非系統管理員的密碼；系統管理員可重設所有人的密碼
    can_reset_password = is_admin and not is_self and (
        current_user.is_system_admin or user.user_type != UserType.SYSTEM_ADMIN
    )

    from ..services import egress_service
    egress_service.meter_view('user', 'detail', [user.secure_code])

    return render_template(
        'pages/users/view.html',
        user=user,
        groups=groups,
        cross_departments=cross_departments,
        is_admin=is_admin,
        is_self=is_self,
        can_reset_password=can_reset_password
    )


def _assign_default_role(user, org):
    """
    自動指派預設角色（鑰匙2: 角色對齊用戶類型）

    EMPLOYEE 帳號 → EMPLOYEE 角色
    ORG_ADMIN 帳號 → ORG_ADMIN 角色
    EXTERNAL 帳號 → EXTERNAL_USERS 角色
    """
    from ..models.role import Role
    from ..models.associations import UserRoleAssignment

    type_to_code = {
        UserType.EMPLOYEE: 'EMPLOYEE',
        UserType.ORG_ADMIN: 'ORG_ADMIN',
        UserType.EXTERNAL: 'EXTERNAL_USERS',
    }

    role_code = type_to_code.get(str(user.user_type))
    if not role_code:
        return

    role = Role.query.filter(
        Role.org_secure_code == org.secure_code,
        Role.code == role_code,
        Role.is_deleted == False,
        Role.is_active == True,
    ).first()

    if not role:
        return

    # 避免重複指派
    existing = UserRoleAssignment.query.filter(
        UserRoleAssignment.user_secure_code == user.secure_code,
        UserRoleAssignment.role_secure_code == role.secure_code,
        UserRoleAssignment.is_deleted == False,
    ).first()
    if existing:
        return

    assignment = UserRoleAssignment(
        org_secure_code=org.secure_code,
        user_secure_code=user.secure_code,
        role_secure_code=role.secure_code,
        assigned_by=current_user.secure_code if current_user and current_user.is_authenticated else None,
    )
    db.session.add(assignment)


def _get_user_type_from_role(role: str, is_current_system_admin: bool) -> str:
    """根據角色字串返回 UserType"""
    if role == 'system_admin' and is_current_system_admin:
        return UserType.SYSTEM_ADMIN
    elif role == 'org_admin':
        return UserType.ORG_ADMIN
    elif role == 'external':
        return UserType.EXTERNAL
    else:
        return UserType.EMPLOYEE


def _find_department_by_code(org_secure_code: str, dept_code: str) -> OrganizationalUnit:
    """根據部門代碼查找部門"""
    if not dept_code:
        return None
    return OrganizationalUnit.query.filter_by(
        org_secure_code=org_secure_code,
        code=dept_code,
        is_deleted=False
    ).first()


def _check_employee_id_unique(org_secure_code: str, employee_id: str, exclude_user_id: int = None) -> bool:
    """檢查用戶編號在組織內是否唯一（同時檢查 users 和 used_user_numbers）"""
    if not employee_id:
        return True

    # 檢查 used_user_numbers 表
    if UsedUserNumber.is_number_used(org_secure_code, employee_id):
        # 如果是編輯現有用戶，檢查是否為該用戶自己的編號
        if exclude_user_id:
            user = User.query.get(exclude_user_id)
            if user and user.employee_id == employee_id:
                return True  # 是自己的編號，允許
        return False

    # 也檢查 users 表（雙重保險）
    query = User.query.filter_by(
        org_secure_code=org_secure_code,
        employee_id=employee_id,
        is_deleted=False
    )
    if exclude_user_id:
        query = query.filter(User.id != exclude_user_id)
    return query.first() is None


@users_bp.route('/create', methods=['GET', 'POST'])
def create_user():
    """建立企業成員帳號頁面"""
    # 表單資料（用於錯誤時保留）
    form_data = {}

    if request.method == 'POST':
        # 收集所有表單資料（用於錯誤時回填）
        form_data = {
            'username': request.form.get('username', '').strip(),
            'role': request.form.get('role', 'user'),
            'employee_id': request.form.get('employee_id', '').strip(),
            'department_code': request.form.get('department_code', '').strip(),
            'english_name': request.form.get('english_name', '').strip(),
            'native_name': request.form.get('native_name', '').strip(),
            'nickname': request.form.get('nickname', '').strip(),
            'backup_email_1': request.form.get('backup_email_1', '').strip(),
            'backup_email_2': request.form.get('backup_email_2', '').strip(),
            'mobile_phone_1': request.form.get('mobile_phone_1', '').strip(),
            'mobile_phone_2': request.form.get('mobile_phone_2', '').strip(),
            'interface_language': request.form.get('interface_language', '').strip(),
            'timezone': request.form.get('timezone', '').strip(),
        }

        # 必填欄位
        english_name = form_data['english_name']
        native_name = form_data['native_name']
        # 帳號正規化：移除所有空白、轉小寫
        username_raw = form_data['username']
        username = ''.join(username_raw.split()).lower()
        password = request.form.get('password', '').strip()
        role = form_data['role']

        # 選填欄位
        employee_id = form_data['employee_id'] or None
        department_code = form_data['department_code']
        nickname = form_data['nickname'] or None
        backup_email_1 = form_data['backup_email_1'] or None
        backup_email_2 = form_data['backup_email_2'] or None
        mobile_phone_1 = form_data['mobile_phone_1'] or None
        mobile_phone_2 = form_data['mobile_phone_2'] or None
        interface_language = form_data['interface_language'] or None
        user_timezone = form_data['timezone'] or None

        # 密碼政策驗證
        from ..services.password_policy_service import PasswordPolicyService
        pw_valid, pw_errors = (True, [])
        if password:
            pw_valid, pw_errors = PasswordPolicyService.validate_password(
                password, current_user.org_secure_code)

        if not english_name or not native_name or not username:
            flash(_('英文姓名、本國姓名、帳號為必填'), 'error')
        elif not employee_id:
            flash(_('用戶編號為必填'), 'error')
        elif password and not pw_valid:
            for err in pw_errors:
                flash(err, 'error')
        else:
            org = current_user.organization
            if not org:
                flash(_('找不到所屬企業'), 'error')
            else:
                email = f"{username}@{org.domain_name}"

                # 預設通知 Email：如果未填寫備用 Email 1，使用帳號 Email
                if not backup_email_1:
                    backup_email_1 = email

                # 檢查帳號是否已存在
                existing = User.query.filter_by(email=email, is_deleted=False).first()
                if existing:
                    flash(_('帳號 %(username)s 已存在', username=username), 'error')
                # 檢查用戶編號唯一性
                elif not _check_employee_id_unique(org.secure_code, employee_id):
                    flash(_('用戶編號 %(employee_id)s 已存在', employee_id=employee_id), 'error')
                elif not org.can_create_user(
                        _get_user_type_from_role(role, current_user.is_system_admin)):
                    flash(_('已達帳號上限（%(limit)s），目前已使用 %(used)s 個',
                            limit=org.user_limit, used=org.get_active_user_count()), 'error')
                else:
                    # 查找部門
                    primary_unit = None
                    if department_code:
                        primary_unit = _find_department_by_code(org.secure_code, department_code)
                        if not primary_unit:
                            flash(_('找不到部門代碼 %(code)s', code=department_code), 'error')
                            org_ctx = current_user.organization
                            return render_template(
                                'pages/users/create.html',
                                form_data=form_data,
                                org_settings=org_ctx.get_settings() if org_ctx else {},
                                timezone_choices=get_timezone_choices()
                            )

                    try:
                        # 密碼：空白時自動產生強化密碼
                        if not password:
                            from ..services.password_policy_service import PasswordPolicyService
                            password = PasswordPolicyService.generate_password(org.secure_code)

                        # display_name 依企業設定自動衍生
                        display_name_field = org.get_setting('display_name_field', 'native_name')
                        display_name_map = {
                            'native_name': native_name,
                            'english_name': english_name,
                            'nickname': nickname or native_name,
                            'username': username,
                            'employee_id': employee_id or username,
                        }
                        display_name = display_name_map.get(display_name_field, native_name)

                        user = User(
                            username=username,
                            email=email,
                            display_name=display_name,
                            org_secure_code=org.secure_code,
                            user_type=_get_user_type_from_role(role, current_user.is_system_admin),
                            is_active=True,
                            employee_id=employee_id,
                            primary_unit_secure_code=primary_unit.secure_code if primary_unit else None,
                            english_name=english_name,
                            native_name=native_name,
                            nickname=nickname,
                            backup_email_1=backup_email_1,
                            backup_email_2=backup_email_2,
                            mobile_phone_1=mobile_phone_1,
                            mobile_phone_2=mobile_phone_2,
                            interface_language=interface_language,
                            timezone=user_timezone,
                        )
                        user.set_password(password)
                        db.session.add(user)
                        db.session.flush()

                        # 自動指派對應角色 (鑰匙2: 角色)
                        _assign_default_role(user, org)

                        # 記錄用戶編號到 used_user_numbers（防止重複使用）
                        if employee_id:
                            UsedUserNumber.record_number(
                                org_secure_code=org.secure_code,
                                number=employee_id,
                                user_secure_code=user.secure_code
                            )

                        db.session.commit()

                        flash(_('已建立用戶 %(name)s', name=native_name), 'success')
                        return redirect(url_for('users.list_users'))
                    except Exception as e:
                        db.session.rollback()
                        flash(_('建立失敗: %(error)s', error=str(e)), 'error')

    org = current_user.organization
    return render_template(
        'pages/users/create.html',
        form_data=form_data,
        org_settings=org.get_settings() if org else {},
        timezone_choices=get_timezone_choices()
    )


def _get_edit_context(user, is_self: bool) -> dict:
    """計算編輯頁面的權限與欄位配置"""
    org = current_user.organization
    is_admin = current_user.is_org_admin or current_user.is_system_admin

    # 檢查是否允許用戶自己編輯
    allow_self_edit = org.get_setting('allow_user_self_edit', True) if org else True

    # 判斷是否可編輯
    if is_admin and not is_self:
        # 管理員編輯他人：完整權限
        can_edit = True
        can_edit_role = True
        can_edit_status = True
        can_edit_org_info = True
    elif is_self:
        # 編輯自己
        can_edit = allow_self_edit
        can_edit_role = False  # 不能改自己的角色
        can_edit_status = False  # 不能改自己的啟用狀態
        can_edit_org_info = False  # 不能改自己的企業成員編號、部門
    else:
        # 一般用戶試圖編輯他人 - 不允許
        can_edit = False
        can_edit_role = False
        can_edit_status = False
        can_edit_org_info = False

    return {
        'is_self': is_self,
        'is_admin': is_admin,
        'can_edit': can_edit,
        'can_edit_role': can_edit_role,
        'can_edit_status': can_edit_status,
        'can_edit_org_info': can_edit_org_info,
        'allow_self_edit': allow_self_edit
    }


@users_bp.route('/<secure_code>/edit', methods=['GET', 'POST'])
@login_required
def edit_user(secure_code: str):
    """
    編輯用戶頁面

    支援兩種模式：
    1. /users/me/edit - 編輯自己的資料
    2. /users/<secure_code>/edit - 管理員編輯他人（需 admin 權限）

    權限邏輯：
    - 管理員編輯他人：完整欄位，完整編輯權
    - 用戶編輯自己 + 開關開啟：部分欄位可編輯（帳號、角色、狀態除外）
    - 用戶編輯自己 + 開關關閉：唯讀模式
    """
    # 處理 /users/me/edit
    is_self = (secure_code == 'me' or secure_code == current_user.secure_code)

    if is_self:
        user = current_user
    else:
        # 非編輯自己，需要管理員權限
        if not (current_user.is_org_admin or current_user.is_system_admin):
            abort(403)
        try:
            user = ResourceGateway.get(User, secure_code)
        except Exception:
            abort(404)

    # 取得編輯權限配置
    ctx = _get_edit_context(user, is_self)

    if request.method == 'POST':
        # 如果不可編輯，拒絕 POST
        if not ctx['can_edit']:
            flash(_('您沒有編輯權限'), 'error')
            return render_template('pages/users/edit.html', user=user, **ctx)

        # 取得表單資料
        new_password = request.form.get('new_password', '').strip()

        # 只有管理員可以修改的欄位
        if ctx['can_edit_role']:
            role = request.form.get('role', 'user')
        if ctx['can_edit_status']:
            is_active = request.form.get('is_active') == 'true'
        if ctx['can_edit_org_info']:
            employee_id = request.form.get('employee_id', '').strip() or None
            department_code = request.form.get('department_code', '').strip()
            work_schedule_code = request.form.get('work_schedule_code', '').strip() or None

        # 個人資料（允許編輯）
        english_name = request.form.get('english_name', '').strip() or None
        native_name = request.form.get('native_name', '').strip() or None
        nickname = request.form.get('nickname', '').strip() or None

        # 個人偏好（允許編輯）
        interface_language = request.form.get('interface_language', '').strip() or None
        user_timezone = request.form.get('timezone', '').strip() or None
        navbar_display = request.form.get('navbar_display', '').strip() or None

        # 聯絡方式（允許編輯）
        backup_email_1 = request.form.get('backup_email_1', '').strip() or None
        backup_email_2 = request.form.get('backup_email_2', '').strip() or None
        mobile_phone_1 = request.form.get('mobile_phone_1', '').strip() or None
        mobile_phone_2 = request.form.get('mobile_phone_2', '').strip() or None

        # 密碼政策驗證
        pw_valid, pw_errors = (True, [])
        if new_password:
            pw_valid, pw_errors = PasswordPolicyService.validate_password(
                new_password, user.org_secure_code,
                user_secure_code=user.secure_code)

        # 帳號上限：重新啟用會增加使用中人數
        target_user_type = user.user_type
        if ctx['can_edit_role']:
            target_user_type = _get_user_type_from_role(role, current_user.is_system_admin)
        limit_org = user.organization
        user_limit_blocked = bool(
            ctx['can_edit_status'] and is_active and not user.is_active
            and limit_org is not None
            and not limit_org.can_create_user(target_user_type)
        )

        # 驗證
        if not native_name or not english_name:
            flash(_('本國姓名、英文姓名為必填'), 'error')
        elif new_password and not pw_valid:
            for err in pw_errors:
                flash(err, 'error')
        elif ctx['can_edit_org_info'] and not _check_employee_id_unique(user.org_secure_code, employee_id, exclude_user_id=user.id):
            flash(_('企業成員編號 %(employee_id)s 已存在', employee_id=employee_id), 'error')
        elif user_limit_blocked:
            flash(_('已達帳號上限（%(limit)s），目前已使用 %(used)s 個',
                    limit=limit_org.user_limit, used=limit_org.get_active_user_count()), 'error')
        else:
            # 查找部門（只有管理員可改）
            primary_unit = None
            if ctx['can_edit_org_info'] and department_code:
                primary_unit = _find_department_by_code(user.org_secure_code, department_code)
                if not primary_unit:
                    flash(_('找不到部門代碼 %(code)s', code=department_code), 'error')
                    return render_template('pages/users/edit.html', user=user, **ctx)

            try:
                # display_name 依企業設定自動衍生
                org = current_user.organization
                display_name_field = org.get_setting('display_name_field', 'native_name') if org else 'native_name'
                display_name_map = {
                    'native_name': native_name,
                    'english_name': english_name,
                    'nickname': nickname or native_name,
                    'username': user.username,
                    'employee_id': (employee_id if ctx['can_edit_org_info'] else user.employee_id) or user.username,
                }
                user.display_name = display_name_map.get(display_name_field, native_name)

                if ctx['can_edit_role']:
                    user.user_type = _get_user_type_from_role(role, current_user.is_system_admin)
                if ctx['can_edit_status']:
                    user.is_active = is_active
                if ctx['can_edit_org_info']:
                    user.employee_id = employee_id
                    user.primary_unit_secure_code = primary_unit.secure_code if primary_unit else None
                    user.work_schedule_secure_code = work_schedule_code

                if new_password:
                    user.set_password(new_password)

                # 個人資料
                user.english_name = english_name
                user.native_name = native_name
                user.nickname = nickname

                # 個人偏好
                user.interface_language = interface_language
                user.timezone = user_timezone
                user.navbar_display = navbar_display

                # 聯絡方式
                user.backup_email_1 = backup_email_1
                user.backup_email_2 = backup_email_2
                user.mobile_phone_1 = mobile_phone_1
                user.mobile_phone_2 = mobile_phone_2

                db.session.commit()
                flash(_('已更新用戶資料'), 'success')

                # 編輯自己導向 dashboard，編輯他人導向用戶列表
                if is_self:
                    return redirect(url_for('main.dashboard'))
                else:
                    return redirect(url_for('users.list_users'))
            except Exception as e:
                db.session.rollback()
                flash(_('更新失敗: %(error)s', error=str(e)), 'error')

    # 取得部門列表（給下拉選單用）
    departments = []
    work_schedules = []
    if ctx['can_edit_org_info']:
        departments = OrganizationalUnit.query.filter_by(
            org_secure_code=user.org_secure_code,
            unit_type='DEPARTMENT',
            is_deleted=False
        ).order_by(OrganizationalUnit.name).all()

        # 取得班表列表
        work_schedules = WorkSchedule.query.filter_by(
            org_secure_code=user.org_secure_code,
            is_deleted=False,
            is_active=True
        ).order_by(WorkSchedule.is_default.desc(), WorkSchedule.name).all()

    return render_template(
        'pages/users/edit.html',
        user=user,
        departments=departments,
        work_schedules=work_schedules,
        timezone_choices=get_timezone_choices(),
        org_settings=current_user.organization.get_settings() if current_user.organization else {},
        **ctx
    )


@users_bp.route('/<secure_code>/delete', methods=['POST'])
def delete_user(secure_code: str):
    """刪除用戶"""
    try:
        user = ResourceGateway.get(User, secure_code)
    except Exception:
        abort(404)

    # 不能刪除自己
    if user.secure_code == current_user.secure_code:
        flash(_('不能刪除自己的帳號'), 'error')
        return redirect(url_for('users.edit_user', secure_code=secure_code))

    # 不能刪除自己綁定的企業成員帳號 (刪除後管理員將無法登入)
    if current_user.bound_employee_secure_code == user.secure_code:
        flash(_('不能刪除自己綁定的企業成員帳號'), 'error')
        return redirect(url_for('users.edit_user', secure_code=secure_code))

    # 不能刪除企業原始管理員
    if user.is_original_admin:
        flash(_('不能刪除企業原始管理員'), 'error')
        return redirect(url_for('users.edit_user', secure_code=secure_code))

    try:
        user.is_deleted = True
        user.deleted_at = datetime.utcnow()
        db.session.commit()
        flash(_('已刪除用戶 %(name)s', name=user.display_name), 'success')
        return redirect(url_for('users.list_users'))
    except Exception as e:
        db.session.rollback()
        flash(_('刪除失敗: %(error)s', error=str(e)), 'error')
        return redirect(url_for('users.edit_user', secure_code=secure_code))


@users_bp.route('/<secure_code>/toggle-status', methods=['POST'])
def toggle_status(secure_code: str):
    """切換用戶啟用狀態"""
    try:
        user = ResourceGateway.get(User, secure_code)
    except Exception:
        abort(404)

    # 不能停用自己
    if user.secure_code == current_user.secure_code:
        flash(_('不能停用自己的帳號'), 'error')
        return redirect(url_for('users.list_users'))

    # 不能停用自己綁定的企業成員帳號 (停用後管理員將無法登入)
    if current_user.bound_employee_secure_code == user.secure_code and user.is_active:
        flash(_('不能停用自己綁定的企業成員帳號'), 'error')
        return redirect(url_for('users.list_users'))

    # 帳號上限：重新啟用會增加使用中人數
    if not user.is_active:
        limit_org = user.organization
        if limit_org and not limit_org.can_create_user(user.user_type):
            flash(_('已達帳號上限（%(limit)s），目前已使用 %(used)s 個',
                    limit=limit_org.user_limit, used=limit_org.get_active_user_count()), 'error')
            return redirect(url_for('users.list_users'))

    try:
        user.is_active = not user.is_active
        db.session.commit()
        if user.is_active:
            flash(_('已啟用用戶 %(name)s', name=user.display_name), 'success')
        else:
            flash(_('已停用用戶 %(name)s', name=user.display_name), 'success')
    except Exception as e:
        db.session.rollback()
        flash(_('操作失敗: %(error)s', error=str(e)), 'error')

    return redirect(url_for('users.list_users'))


@users_bp.route('/<secure_code>/reset-password', methods=['POST'])
def reset_password(secure_code: str):
    """
    管理員重設用戶密碼

    企業管理員可以重設同企業內其他企業管理員和一般帳號的密碼，
    無須知道原本的密碼。
    """
    try:
        user = ResourceGateway.get(User, secure_code)
    except Exception:
        flash(_('找不到該用戶'), 'error')
        return redirect(url_for('users.list_users'))

    # 不能重設自己的密碼（應使用個人密碼變更功能）
    if user.secure_code == current_user.secure_code:
        flash(_('請使用「變更密碼」功能修改自己的密碼'), 'error')
        return redirect(url_for('users.view_user', secure_code=secure_code))

    # 不能重設系統管理員的密碼（除非自己也是系統管理員）
    if user.user_type == UserType.SYSTEM_ADMIN and not current_user.is_system_admin:
        flash(_('無權重設系統管理員的密碼'), 'error')
        return redirect(url_for('users.view_user', secure_code=secure_code))

    new_password = request.form.get('new_password', '').strip()
    confirm_password = request.form.get('confirm_password', '').strip()

    # 密碼政策驗證
    pw_valid, pw_errors = (True, [])
    if new_password:
        pw_valid, pw_errors = PasswordPolicyService.validate_password(
            new_password, user.org_secure_code,
            user_secure_code=user.secure_code)

    # 驗證
    if not new_password:
        flash(_('請輸入新密碼'), 'error')
    elif not pw_valid:
        for err in pw_errors:
            flash(err, 'error')
    elif new_password != confirm_password:
        flash(_('兩次輸入的密碼不一致'), 'error')
    else:
        try:
            user.set_password(new_password)
            user.password_changed_at = datetime.utcnow()
            # 可選：強制用戶下次登入時變更密碼
            # user.must_change_password = True
            db.session.commit()
            flash(_('已重設 %(name)s 的密碼', name=user.display_name), 'success')
        except Exception as e:
            db.session.rollback()
            flash(_('重設密碼失敗: %(error)s', error=str(e)), 'error')

    return redirect(url_for('users.view_user', secure_code=secure_code))


# ============================================================
# CSV 匯入/匯出功能
# ============================================================

CSV_COLUMNS = [
    ('username', '帳號', True),           # (欄位名, 顯示名稱, 是否必填)
    ('password', '密碼', True),
    ('display_name', '姓名', True),
    ('role', '角色', False),              # user / org_admin
    ('employee_id', '企業成員編號', False),
    ('department_code', '部門代碼', False),
    ('english_name', '英文姓名', False),
    ('native_name', '本國姓名', False),
    ('nickname', '暱稱', False),
    ('backup_email_1', '備用Email1', False),
    ('backup_email_2', '備用Email2', False),
    ('mobile_phone_1', '手機號碼1', False),
    ('mobile_phone_2', '手機號碼2', False),
]


@users_bp.route('/csv-template')
def download_csv_template():
    """下載 CSV 匯入範本"""
    output = io.StringIO()
    writer = csv.writer(output)

    # 寫入標題列 (使用英文欄位名)
    headers = [col[0] for col in CSV_COLUMNS]
    writer.writerow(headers)

    # 寫入範例資料
    writer.writerow([
        'john.doe',           # username
        'password123',        # password
        'John Doe',           # display_name
        'user',               # role (user/org_admin)
        'EMP001',             # employee_id
        'IT',                 # department_code
        'John Doe',           # english_name
        '',                   # native_name
        'Johnny',             # nickname
        'john@gmail.com',     # backup_email_1
        '',                   # backup_email_2
        '+886-912-345-678',   # mobile_phone_1
        '',                   # mobile_phone_2
    ])

    output.seek(0)
    response = Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': 'attachment; filename=user_import_template.csv',
            'Content-Type': 'text/csv; charset=utf-8-sig'
        }
    )
    return response


@users_bp.route('/import', methods=['GET', 'POST'])
def import_users():
    """匯入用戶 CSV"""
    if request.method == 'POST':
        file = request.files.get('csv_file')
        if not file:
            flash(_('請選擇 CSV 檔案'), 'error')
            return render_template('pages/users/import.html')

        if not file.filename.endswith('.csv'):
            flash(_('請上傳 CSV 格式檔案'), 'error')
            return render_template('pages/users/import.html')

        org = current_user.organization
        if not org:
            flash(_('找不到所屬企業'), 'error')
            return render_template('pages/users/import.html')

        try:
            # 讀取 CSV (處理 UTF-8 BOM)
            content = file.read().decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(content))

            success_count = 0
            counted_new = 0
            error_messages = []
            existing_count = org.get_active_user_count()

            for row_num, row in enumerate(reader, start=2):  # 從第2列開始 (第1列是標題)
                try:
                    result = _import_single_user(row, org, row_num)
                    if result is True:
                        success_count += 1
                        row_user_type = _get_user_type_from_role(
                            row.get('role', '').strip() or 'user',
                            current_user.is_system_admin)
                        if counts_toward_user_limit(row_user_type):
                            counted_new += 1
                    else:
                        error_messages.append(result)
                except Exception as e:
                    error_messages.append(_('第 %(row)s 列: %(error)s', row=row_num, error=str(e)))

            # 帳號上限：整批拒絕，一筆都不建立
            if counted_new and existing_count + counted_new > org.user_limit:
                db.session.rollback()
                remain = max(0, org.user_limit - existing_count)
                flash(_('已達帳號上限（%(limit)s）：本次將新增 %(need)s 筆，剩餘名額 %(remain)s，未匯入任何資料',
                        limit=org.user_limit, need=counted_new, remain=remain), 'error')
                for msg in error_messages[:10]:
                    flash(msg, 'error')
                return render_template('pages/users/import.html')

            db.session.commit()

            if success_count > 0:
                flash(_('成功匯入 %(count)s 位用戶', count=success_count), 'success')
            if error_messages:
                for msg in error_messages[:10]:  # 只顯示前10個錯誤
                    flash(msg, 'error')
                if len(error_messages) > 10:
                    flash(_('... 還有 %(count)s 個錯誤', count=len(error_messages) - 10), 'error')

            return redirect(url_for('users.list_users'))

        except Exception as e:
            db.session.rollback()
            flash(_('匯入失敗: %(error)s', error=str(e)), 'error')

    return render_template('pages/users/import.html')


def _import_single_user(row: dict, org, row_num: int):
    """
    匯入單一用戶
    返回 True 表示成功，返回字串表示錯誤訊息
    """
    # 帳號正規化：移除所有空白、轉小寫
    username_raw = row.get('username', '').strip()
    username = ''.join(username_raw.split()).lower()
    password = row.get('password', '').strip()
    display_name = row.get('display_name', '').strip()

    # 必填欄位驗證
    if not username:
        return _('第 %(row)s 列: 帳號為必填', row=row_num)
    if not password:
        return _('第 %(row)s 列: 密碼為必填', row=row_num)
    if not display_name:
        return _('第 %(row)s 列: 姓名為必填', row=row_num)
    pw_valid, pw_errors = PasswordPolicyService.validate_password(
        password, org.secure_code)
    if not pw_valid:
        return _('第 %(row)s 列: ', row=row_num) + '、'.join(pw_errors)

    email = f"{username}@{org.domain_name}"

    # 檢查帳號是否已存在
    existing = User.query.filter_by(email=email, is_deleted=False).first()
    if existing:
        return _('第 %(row)s 列: 帳號 %(username)s 已存在', row=row_num, username=username)

    # 選填欄位
    role = row.get('role', '').strip() or 'user'
    # 預設通知 Email：如果未填寫備用 Email 1，使用帳號 Email
    backup_email_1 = row.get('backup_email_1', '').strip() or email
    employee_id = row.get('employee_id', '').strip() or None
    department_code = row.get('department_code', '').strip()

    # 檢查企業成員編號唯一性
    if employee_id and not _check_employee_id_unique(org.secure_code, employee_id):
        return _('第 %(row)s 列: 企業成員編號 %(employee_id)s 已存在', row=row_num, employee_id=employee_id)

    # 查找部門
    primary_unit = None
    if department_code:
        primary_unit = _find_department_by_code(org.secure_code, department_code)
        # 不報錯，只是不關聯部門 (因為部門可能尚未建立)

    # 建立用戶
    user = User(
        username=username,
        email=email,
        display_name=display_name,
        org_secure_code=org.secure_code,
        user_type=_get_user_type_from_role(role, current_user.is_system_admin),
        is_active=True,
        employee_id=employee_id,
        primary_unit_secure_code=primary_unit.secure_code if primary_unit else None,
        english_name=row.get('english_name', '').strip() or None,
        native_name=row.get('native_name', '').strip() or None,
        nickname=row.get('nickname', '').strip() or None,
        backup_email_1=backup_email_1,
        backup_email_2=row.get('backup_email_2', '').strip() or None,
        mobile_phone_1=row.get('mobile_phone_1', '').strip() or None,
        mobile_phone_2=row.get('mobile_phone_2', '').strip() or None,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.flush()  # 確保 user.secure_code 已產生

    # 自動指派對應角色 (鑰匙2: 角色)
    _assign_default_role(user, org)

    # 記錄用戶編號到 used_user_numbers（防止重複使用）
    if employee_id:
        UsedUserNumber.record_number(
            org_secure_code=org.secure_code,
            number=employee_id,
            user_secure_code=user.secure_code
        )

    return True
