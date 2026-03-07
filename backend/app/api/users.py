"""
BeakMask Users API
用戶管理路由
"""
from flask import Blueprint, request, jsonify
from flask_login import current_user

from ..security.decorators import login_required, admin_required
from ..security.resource_gateway import ResourceGateway
from ..models.user import User, UserType
from ..models.organizational_unit import OrganizationalUnit
from ..models.user_numbering_rule import UsedUserNumber
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
        is_deleted=False,
        is_active=True
    )

    # 只保留員工帳號（排除系統管理員、企業管理員、外部人員）
    users = [u for u in result['items'] if u.user_type == UserType.EMPLOYEE]

    return jsonify({
        'users': [u.to_dict() for u in users],
        'pagination': {
            'total': len(users),
            'page': result['page'],
            'per_page': result['per_page'],
            'pages': result['pages']
        }
    }), 200


@users_bp.route('/<secure_code>', methods=['GET'])
@login_required
def get_user(secure_code: str):
    """
    取得單一用戶資訊。

    GET /api/users/<secure_code>
    """
    user = ResourceGateway.get(User, secure_code)

    return jsonify({'user': user.to_dict()}), 200


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
        "role": "user",
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

    if not native_name or not english_name or not username:
        return jsonify({'error': '本國姓名、英文姓名、帳號為必填'}), 400

    org = current_user.organization
    if not org:
        return jsonify({'error': '找不到所屬企業'}), 400

    email = f"{username}@{org.domain_name}"

    # 檢查帳號唯一性
    existing = User.query.filter_by(email=email, is_deleted=False).first()
    if existing:
        return jsonify({'error': f'帳號 {username} 已存在'}), 409

    # 檢查用戶編號唯一性
    employee_id = (data.get('employee_id') or '').strip() or None
    if employee_id:
        from ..web.users import _check_employee_id_unique
        if not _check_employee_id_unique(org.secure_code, employee_id):
            return jsonify({'error': f'用戶編號 {employee_id} 已存在'}), 409

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
            return jsonify({'error': f'找不到部門代碼 {department_code}'}), 400

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

    # 角色
    role = data.get('role', 'user')
    from ..web.users import _get_user_type_from_role
    user_type = _get_user_type_from_role(role, current_user.is_system_admin)

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
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        # 記錄用戶編號
        if employee_id:
            UsedUserNumber.record_number(
                org_secure_code=org.secure_code,
                number=employee_id,
                user_secure_code=user.secure_code
            )
            db.session.commit()

        return jsonify({
            'message': f'已建立用戶 {native_name}',
            'user': user.to_dict()
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'建立失敗: {str(e)}'}), 500


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
        return jsonify({'error': '不能刪除自己的帳號'}), 403

    # 不能刪除自己綁定的員工帳號
    if current_user.bound_employee_secure_code == user.secure_code:
        return jsonify({'error': '不能刪除自己綁定的員工帳號'}), 403

    # 不能刪除企業原始管理員
    if user.is_original_admin:
        return jsonify({'error': '不能刪除企業原始管理員'}), 403

    ResourceGateway.delete(user, soft=True)
    ResourceGateway.commit()

    return jsonify({'message': 'User deleted'}), 200
