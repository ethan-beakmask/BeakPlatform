"""
BeakMask Users API
用戶管理路由
"""
from flask import Blueprint, request, jsonify, url_for, current_app
from flask_babel import gettext as _
from flask_login import current_user

from ..security.decorators import login_required, admin_required
from ..security.resource_gateway import ResourceGateway
from ..models.user import User, UserType
from ..models.organizational_unit import OrganizationalUnit
from ..models.user_numbering_rule import UsedUserNumber
from ..services.email_service import EmailService
from app.utils.external_url import build_external_url
from .. import db

users_bp = Blueprint('api_users', __name__)


@users_bp.route('/', methods=['GET'])
@admin_required
def list_users():
    """
    取得用戶列表（僅限管理員）。

    GET /api/users?page=1&per_page=20

    [TENANT-02] 強制使用 org_secure_code 過濾
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    # [CRITICAL] 明確過濾 org_secure_code，不依賴 ResourceGateway 自動過濾
    result = ResourceGateway.list(
        User,
        page=page,
        per_page=min(per_page, 100),  # Max 100 per page
        order_by='-created_at',
        org_secure_code=current_user.org_secure_code,  # 強制租戶隔離
        require_permission='user:read',
        is_deleted=False,
        is_active=True
    )

    # 只保留企業成員帳號（排除系統管理員、企業管理員、外部廠商）
    users = [u for u in result['items'] if u.user_type == UserType.EMPLOYEE]

    from ..services import egress_service
    items = egress_service.apply('user', 'list', [u.to_dict() for u in users])

    return jsonify({
        'users': items,
        'pagination': {
            'total': len(users),
            'page': result['page'],
            'per_page': result['per_page'],
            'pages': result['pages']
        }
    }), 200


@users_bp.route('/<secure_code>', methods=['GET'])
@admin_required
def get_user(secure_code: str):
    """
    取得單一用戶資訊。

    GET /api/users/<secure_code>
    限管理員（to_dict 含手機/備用信箱等 PII，不開放一般登入用戶）。
    原為 @permission_required('user','read')，實際僅 SYSTEM_ADMIN 角色持有
    user:read、ORG_ADMIN 自動通過 -- 與 @admin_required 行為等價，隨軌 C 選單/
    頁面層退役改用 user_type 檢查。
    """
    user = ResourceGateway.get(User, secure_code)

    from ..services import egress_service
    data = egress_service.apply('user', 'detail', [user.to_dict()])[0]

    return jsonify({'user': data}), 200


@users_bp.route('/', methods=['POST'])
@admin_required
def create_user():
    """
    建立新用戶（僅限管理員）。

    POST /api/users
    Body: {
        "native_name": "王大明",
        "english_name": "Da-Ming Wang",
        "username": "daming.wang",
        "password": "optional",
        "role": "user",                      # user / org_admin / external
        "email": "vendor@example.com",       # role=external 時必填（完整 Email，username 可省略）
        "employee_id": "EMP001",
        "department_code": "DEPT_CODE",
        "nickname": "王○明",
        "interface_language": "zh-TW",
        "timezone": "Asia/Taipei",
        "backup_email_1": "...",
        "backup_email_2": "...",
        "mobile_phone_1": "...",
        "mobile_phone_2": "..."
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    native_name = (data.get('native_name') or '').strip()
    english_name = (data.get('english_name') or '').strip()
    username = (data.get('username') or '').replace(' ', '').lower()
    password = (data.get('password') or '').strip()
    auto_generated = not password
    role = (data.get('role') or 'user').strip()
    is_external = role == 'external'

    employee_id_raw = (data.get('employee_id') or '').strip()
    if not native_name or not english_name or (not username and not is_external):
        return jsonify({'error': _('本國姓名、英文姓名、帳號為必填')}), 400
    if not employee_id_raw:
        return jsonify({'error': _('用戶編號為必填')}), 400

    org = current_user.organization
    if not org:
        return jsonify({'error': _('找不到所屬企業')}), 400

    if is_external:
        # 外部廠商的 Email 不屬企業網域，身分識別就是完整 Email，username 直接等於它
        # （與 web/external_users.py 的建立路徑一致，2026-09-02 起）
        email = (data.get('email') or '').strip().lower()
        if not email or '@' not in email:
            return jsonify({'error': _('外部廠商帳號需提供完整 Email')}), 400
        username = email
        existing = User.query.filter_by(
            email=email, org_secure_code=org.secure_code, is_deleted=False).first()
        if existing:
            return jsonify({'error': _('Email %(email)s 已存在', email=email)}), 409
    else:
        email = f"{username}@{org.domain_name}"

        # 檢查帳號唯一性
        existing = User.query.filter_by(email=email, is_deleted=False).first()
        if existing:
            return jsonify({'error': _('帳號 %(username)s 已存在', username=username)}), 409

    # 檢查用戶編號唯一性
    employee_id = employee_id_raw
    if employee_id:
        from ..web.users import _check_employee_id_unique
        if not _check_employee_id_unique(org.secure_code, employee_id):
            return jsonify({'error': _('用戶編號 %(employee_id)s 已存在', employee_id=employee_id)}), 409

    # 查找部門
    department_code = (data.get('department_code') or '').strip()
    primary_unit = None
    if department_code:
        primary_unit = OrganizationalUnit.query.filter_by(
            org_secure_code=org.secure_code,
            code=department_code,
            is_deleted=False
        ).first()
        if not primary_unit:
            return jsonify({'error': _('找不到部門代碼 %(department_code)s', department_code=department_code)}), 400

    # 密碼：空白時自動產生
    if not password:
        from ..services.password_policy_service import PasswordPolicyService
        password = PasswordPolicyService.generate_password(org.secure_code)

    # display_name 依企業設定
    nickname = (data.get('nickname') or '').strip() or None
    display_name_field = org.get_setting('display_name_field', 'native_name')
    display_name_map = {
        'native_name': native_name,
        'english_name': english_name,
        'nickname': nickname or native_name,
        'username': username,
        'employee_id': employee_id or username,
    }
    display_name = display_name_map.get(display_name_field, native_name)

    # 角色（role 已在上方讀取）
    from ..web.users import _get_user_type_from_role
    user_type = _get_user_type_from_role(role, current_user.is_system_admin)

    if not org.can_create_user(user_type):
        return jsonify({'error': _('已達帳號上限（%(limit)s），目前已使用 %(used)s 個',
                                   limit=org.user_limit, used=org.get_active_user_count())}), 400

    try:
        backup_email_1 = (data.get('backup_email_1') or '').strip() or email
        user = User(
            username=username,
            email=email,
            display_name=display_name,
            org_secure_code=org.secure_code,
            user_type=user_type,
            is_active=True,
            employee_id=employee_id,
            primary_unit_secure_code=primary_unit.secure_code if primary_unit else None,
            english_name=english_name,
            native_name=native_name,
            nickname=nickname,
            backup_email_1=backup_email_1,
            backup_email_2=(data.get('backup_email_2') or '').strip() or None,
            mobile_phone_1=(data.get('mobile_phone_1') or '').strip() or None,
            mobile_phone_2=(data.get('mobile_phone_2') or '').strip() or None,
            interface_language=(data.get('interface_language') or '').strip() or None,
            timezone=(data.get('timezone') or '').strip() or None,
        )
        if auto_generated:
            user.must_change_password = True
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        # 自動指派 user_type 對應的預設角色（雙鑰匙 Key2）
        from ..web.users import _assign_default_role
        _assign_default_role(user, org)

        # 記錄用戶編號並更新計數器
        if employee_id:
            numbering_rule_code = (data.get('numbering_rule') or '').strip()
            UsedUserNumber.record_number(
                org_secure_code=org.secure_code,
                number=employee_id,
                user_secure_code=user.secure_code,
                rule_secure_code=numbering_rule_code or None
            )
            # 自動編號：同步更新 counter
            if numbering_rule_code:
                from ..services.numbering_service import NumberingService
                from ..models.user_numbering_rule import UserNumberingRule as NRule
                rule_obj = NRule.query.filter_by(
                    secure_code=numbering_rule_code,
                    org_secure_code=org.secure_code
                ).first()
                if rule_obj:
                    NumberingService.sync_counter_to_used(rule_obj)

        db.session.commit()

        password_notification = None
        if auto_generated:
            notification_email = user.backup_email_1 or user.email
            mail_sent = False
            try:
                login_url = build_external_url(
                    url_for('auth.org_login', domain_name=org.domain_name)
                )
                mail_sent = EmailService.send_new_account_password(
                    to_email=notification_email,
                    org_name=org.name,
                    account=f"{user.username}@{org.domain_name}",
                    temp_password=password,
                    login_url=login_url
                )
            except Exception as exc:  # 只記例外型別，不記密碼與內文
                current_app.logger.warning('new account password mail failed: %s', type(exc).__name__)
                mail_sent = False
            password_notification = {
                'sent': mail_sent,
                'to': notification_email,
            }
            if mail_sent:
                message = _('已建立用戶 %(name)s，密碼通知信已寄至 %(email)s',
                            name=native_name, email=notification_email)
            else:
                message = _('已建立用戶 %(name)s，但密碼通知信寄送失敗（%(email)s），請到編輯頁重設密碼交給對方',
                            name=native_name, email=notification_email)
        else:
            message = _('已建立用戶 %(name)s', name=native_name)

        return jsonify({
            'message': message,
            'user': user.to_dict(),
            'password_notification': password_notification
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': _('建立失敗: %(error)s', error=str(e))}), 500


@users_bp.route('/<secure_code>', methods=['PUT'])
@admin_required
def update_user(secure_code: str):
    """
    更新用戶資訊（僅限管理員）。

    PUT /api/users/<secure_code>
    """
    user = ResourceGateway.get(User, secure_code)
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Request body required'}), 400

    # Allowed update fields
    allowed_fields = ['display_name', 'is_active']
    update_data = {k: v for k, v in data.items() if k in allowed_fields}

    # 帳號上限：重新啟用會增加使用中人數
    if update_data.get('is_active') and not user.is_active:
        limit_org = user.organization
        if limit_org and not limit_org.can_create_user(user.user_type):
            return jsonify({'error': _('已達帳號上限（%(limit)s），目前已使用 %(used)s 個',
                                       limit=limit_org.user_limit,
                                       used=limit_org.get_active_user_count())}), 400

    ResourceGateway.update(user, **update_data)
    ResourceGateway.commit()

    return jsonify({
        'message': 'User updated',
        'user': user.to_dict()
    }), 200


@users_bp.route('/<secure_code>', methods=['DELETE'])
@admin_required
def delete_user(secure_code: str):
    """
    刪除用戶（僅限管理員，軟刪除）。

    DELETE /api/users/<secure_code>
    """
    user = ResourceGateway.get(User, secure_code)

    # 不能刪除自己
    if user.secure_code == current_user.secure_code:
        return jsonify({'error': _('不能刪除自己的帳號')}), 403

    # 不能刪除自己綁定的企業成員帳號
    if current_user.bound_employee_secure_code == user.secure_code:
        return jsonify({'error': _('不能刪除自己綁定的企業成員帳號')}), 403

    # 不能刪除企業原始管理員
    if user.is_original_admin:
        return jsonify({'error': _('不能刪除企業原始管理員')}), 403

    ResourceGateway.delete(user, soft=True)
    ResourceGateway.commit()

    return jsonify({'message': 'User deleted'}), 200
