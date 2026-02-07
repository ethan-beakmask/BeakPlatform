"""
BeakPlatform Users API
用戶管理路由
"""
from flask import Blueprint, request, jsonify
from flask_login import current_user

from ..security.decorators import login_required, admin_required
from ..security.resource_gateway import ResourceGateway
from ..models.user import User, UserType

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

    # 排除系統管理員（他們不應該出現在企業用戶列表）
    users = [u for u in result['items'] if u.user_type != UserType.SYSTEM_ADMIN]

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
        "email": "user@example.com",
        "password": "password",
        "display_name": "User Name"
    }
    """
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Request body required'}), 400

    required_fields = ['email', 'password', 'display_name']
    for field in required_fields:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400

    # Check email uniqueness
    if ResourceGateway.exists(User, email=data['email'].lower()):
        return jsonify({'error': 'Email already exists'}), 409

    user = ResourceGateway.create(
        User,
        email=data['email'].lower(),
        display_name=data['display_name'],
    )
    user.set_password(data['password'])

    ResourceGateway.commit()

    return jsonify({
        'message': 'User created',
        'user': user.to_dict()
    }), 201


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

    ResourceGateway.delete(user, soft=True)
    ResourceGateway.commit()

    return jsonify({'message': 'User deleted'}), 200
