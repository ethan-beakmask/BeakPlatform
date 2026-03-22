"""
BeakMask Modules API
模組管理 API (No-Code Builder)
"""
from flask import Blueprint, jsonify, request
from flask_login import current_user

from ..security.decorators import login_required, system_admin_required
from ..security.resource_gateway import ResourceGateway
from ..services.module_builder_service import ModuleBuilderService
from ..models.module import Module
from .. import db

modules_bp = Blueprint('api_modules', __name__)


@modules_bp.route('', methods=['GET'])
@login_required
def list_modules():
    """
    列出所有模組

    Query params:
        include_inactive: bool (default: false)

    Returns:
        {items: [...], total: int}
    """
    include_inactive = request.args.get('include_inactive', 'false') == 'true'

    filters = {'is_deleted': False}
    if not include_inactive:
        filters['is_active'] = True

    modules = ResourceGateway.filter(Module, order_by='display_order', **filters)

    return jsonify({
        'items': [m.to_dict() for m in modules],
        'total': len(modules)
    })


@modules_bp.route('/<secure_code>', methods=['GET'])
@login_required
def get_module(secure_code: str):
    """
    取得模組詳情

    Query params:
        include_structure: bool - 是否包含頁面和選單結構

    Returns:
        Module dict (可能含 pages 和 menu_items)
    """
    include_structure = request.args.get('include_structure', 'false') == 'true'

    if include_structure:
        structure = ModuleBuilderService.get_module_structure(secure_code)
        if not structure:
            return jsonify({'error': 'Module not found'}), 404
        return jsonify(structure)
    else:
        module = ResourceGateway.get(Module, secure_code)
        return jsonify(module.to_dict())


@modules_bp.route('', methods=['POST'])
@system_admin_required
def create_module():
    """
    建立新模組 (No-Code Builder 入口)

    Body:
        code: str (required)
        name: str (required)
        description: str
        icon: str
        page_structure: dict (自訂頁面結構)
        create_menu: bool (default: true)
        required_level: int (0-2, default: 2)

    page_structure 範例:
    {
        'main': {
            'title': '會員總覽',
            'type': 'dashboard',
            'children': ['list', 'stats']
        },
        'list': {
            'title': '會員列表',
            'type': 'list',
            'url': '/list',
            'children': ['create']
        },
        'create': {
            'title': '新增會員',
            'type': 'form',
            'url': '/create'
        },
        'stats': {
            'title': '統計報表',
            'type': 'dashboard',
            'url': '/stats'
        }
    }

    Returns:
        Module dict with structure
    """
    data = request.get_json()

    # 驗證必要欄位
    if not data.get('code') or not data.get('name'):
        return jsonify({'error': 'code and name are required'}), 400

    # 檢查代碼是否已存在
    if ResourceGateway.exists(Module, code=data['code'], is_deleted=False):
        return jsonify({'error': f'模組代碼「{data["code"]}」已存在，請使用其他代碼'}), 400

    # 建立模組
    module = ModuleBuilderService.create_module(
        org_secure_code=current_user.org_secure_code,
        code=data['code'],
        name=data['name'],
        description=data.get('description'),
        icon=data.get('icon'),
        page_structure=data.get('page_structure'),
        create_menu=data.get('create_menu', True),
        required_level=data.get('required_level', 2),
    )

    db.session.commit()

    # 返回完整結構
    structure = ModuleBuilderService.get_module_structure(module.secure_code)

    return jsonify(structure), 201


@modules_bp.route('/<secure_code>', methods=['PUT'])
@system_admin_required
def update_module(secure_code: str):
    """
    更新模組基本資訊

    Body:
        name: str
        description: str
        icon: str
        display_order: int
        is_active: bool

    Returns:
        Updated Module dict
    """
    module = ResourceGateway.get(Module, secure_code)
    data = request.get_json()

    # 系統模組只能更新部分欄位
    if module.is_system_module:
        allowed_fields = ['display_order', 'is_active']
    else:
        allowed_fields = ['name', 'description', 'icon', 'display_order', 'is_active']

    for field in allowed_fields:
        if field in data:
            setattr(module, field, data[field])

    db.session.commit()

    return jsonify(module.to_dict())


@modules_bp.route('/<secure_code>', methods=['DELETE'])
@system_admin_required
def delete_module(secure_code: str):
    """
    刪除模組

    系統模組無法刪除。
    會同時刪除關聯的頁面和選單。

    Query params:
        hard: bool - 是否硬刪除 (default: false)

    Returns:
        204 No Content
    """
    module = ResourceGateway.get(Module, secure_code)

    if module.is_system_module:
        return jsonify({'error': 'Cannot delete system module'}), 403

    hard_delete = request.args.get('hard', 'false') == 'true'

    success = ModuleBuilderService.delete_module(
        secure_code,
        hard_delete=hard_delete
    )

    if not success:
        return jsonify({'error': 'Failed to delete module'}), 400

    db.session.commit()

    return '', 204


@modules_bp.route('/<secure_code>/structure', methods=['GET'])
@login_required
def get_module_structure(secure_code: str):
    """
    取得模組的完整結構

    Returns:
        {module: {...}, pages: [...], menu_items: [...]}
    """
    structure = ModuleBuilderService.get_module_structure(secure_code)

    if not structure:
        return jsonify({'error': 'Module not found'}), 404

    return jsonify(structure)
