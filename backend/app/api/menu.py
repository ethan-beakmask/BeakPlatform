"""
BeakMask Menu API
選單管理 API
"""
from flask import Blueprint, jsonify, request
from flask_login import current_user

from ..security.decorators import login_required, admin_required
from ..security.resource_gateway import ResourceGateway
from ..services.menu_service import MenuService
from ..models.menu_item import MenuItem
from .. import db

menu_bp = Blueprint('api_menu', __name__)


@menu_bp.route('', methods=['GET'])
@login_required
def get_user_menu():
    """
    取得當前用戶可見的選單樹

    Query params:
        layout: 'sidebar' | 'navbar' (default: 'sidebar')

    Returns:
        {menu: [...], user_type: str}
    """
    layout = request.args.get('layout', 'sidebar')
    menu_tree = MenuService.get_user_menu_tree(current_user, layout)
    return jsonify({
        'menu': menu_tree,
        'user_type': str(current_user.user_type)  # 用於前端顯示邏輯
    })


@menu_bp.route('/all', methods=['GET'])
@admin_required
def get_all_menu_items():
    """
    取得企業內所有選單項目 (管理用)

    Returns:
        {items: [...], total: int}
    """
    include_deleted = request.args.get('include_deleted', 'false') == 'true'

    items = MenuService.get_all_menu_items(
        current_user.org_secure_code,
        include_deleted=include_deleted
    )

    return jsonify({
        'items': [item.to_dict(include_children=False) for item in items],
        'total': len(items)
    })


@menu_bp.route('/tree', methods=['GET'])
@admin_required
def get_menu_tree():
    """
    取得選單樹結構 (管理用，包含所有選單)

    Returns:
        {menu: [...]}
    """
    menu_tree = MenuService.get_user_menu_tree(
        current_user,
        include_inactive=True
    )
    return jsonify({'menu': menu_tree})


@menu_bp.route('', methods=['POST'])
@admin_required
def create_menu_item():
    """
    新增選單項目

    Body:
        code: str (required)
        title: str (required)
        link_type: str (default: 'route')
        link_target: str
        parent_secure_code: str
        module_secure_code: str
        icon: str
        display_order: int
        required_level: int (0-2)
        is_expanded: bool
        open_in_new_tab: bool

    Returns:
        MenuItem dict
    """
    data = request.get_json()

    # 驗證必要欄位
    if not data.get('code') or not data.get('title'):
        return jsonify({'error': 'code and title are required'}), 400

    # 檢查代碼是否已存在
    if ResourceGateway.exists(MenuItem, code=data['code'], is_deleted=False):
        return jsonify({'error': f'Menu item with code "{data["code"]}" already exists'}), 400

    # 建立選單項目
    menu_item = MenuService.create_menu_item(
        org_secure_code=current_user.org_secure_code,
        code=data['code'],
        title=data['title'],
        link_type=data.get('link_type', 'route'),
        link_target=data.get('link_target'),
        parent_secure_code=data.get('parent_secure_code'),
        module_secure_code=data.get('module_secure_code'),
        icon=data.get('icon'),
        display_order=data.get('display_order', 0),
        required_level=data.get('required_level', 2),
        is_expanded=data.get('is_expanded', False),
        open_in_new_tab=data.get('open_in_new_tab', False),
    )

    db.session.commit()

    return jsonify(menu_item.to_dict()), 201


@menu_bp.route('/<secure_code>', methods=['GET'])
@admin_required
def get_menu_item(secure_code: str):
    """
    取得單一選單項目

    Returns:
        MenuItem dict (含 children)
    """
    menu_item = ResourceGateway.get(MenuItem, secure_code)
    return jsonify(menu_item.to_dict(include_children=True))


@menu_bp.route('/<secure_code>', methods=['PUT'])
@admin_required
def update_menu_item(secure_code: str):
    """
    更新選單項目

    Body:
        title: str
        icon: str
        link_type: str
        link_target: str
        display_order: int
        required_level: int
        is_expanded: bool
        open_in_new_tab: bool
        is_active: bool

    Returns:
        Updated MenuItem dict
    """
    menu_item = ResourceGateway.get(MenuItem, secure_code)
    data = request.get_json()

    # 允許更新的欄位
    allowed_fields = [
        'title', 'title_en', 'title_zh_cn',
        'icon', 'link_type', 'link_target',
        'display_order', 'required_level', 'is_expanded',
        'open_in_new_tab', 'is_active'
    ]

    for field in allowed_fields:
        if field in data:
            setattr(menu_item, field, data[field])

    db.session.commit()

    return jsonify(menu_item.to_dict())


@menu_bp.route('/<secure_code>', methods=['DELETE'])
@admin_required
def delete_menu_item(secure_code: str):
    """
    刪除選單項目

    如果有子項目則無法刪除。

    Returns:
        204 No Content
    """
    menu_item = ResourceGateway.get(MenuItem, secure_code)

    success = MenuService.delete_menu_item(menu_item, soft=True)

    if not success:
        return jsonify({'error': 'Cannot delete menu item with children'}), 400

    db.session.commit()

    return '', 204


@menu_bp.route('/reorder', methods=['POST'])
@admin_required
def reorder_menu():
    """
    重新排序選單項目

    Body:
        items: [{secure_code, display_order, parent_secure_code}, ...]

    Returns:
        {success: true}
    """
    data = request.get_json()
    items = data.get('items', [])

    if not items:
        return jsonify({'error': 'items is required'}), 400

    MenuService.update_menu_order(items)
    db.session.commit()

    return jsonify({'success': True})


@menu_bp.route('/move/<secure_code>', methods=['POST'])
@admin_required
def move_menu_item(secure_code: str):
    """
    移動選單項目到新的父節點

    Body:
        parent_secure_code: str | null (null = 移到根層級)
        display_order: int

    Returns:
        Updated MenuItem dict
    """
    menu_item = ResourceGateway.get(MenuItem, secure_code)
    data = request.get_json()

    new_parent = data.get('parent_secure_code')

    # 防止循環：不能把節點移到自己的子孫下
    if new_parent:
        descendants = menu_item.get_descendants()
        if any(d.secure_code == new_parent for d in descendants):
            return jsonify({'error': 'Cannot move menu item under its own descendant'}), 400

    # 更新父節點
    menu_item.parent_secure_code = new_parent

    # 重新計算深度
    if new_parent:
        parent = ResourceGateway.get(MenuItem, new_parent, raise_on_not_found=False)
        menu_item.depth = parent.depth + 1 if parent else 0
    else:
        menu_item.depth = 0

    # 更新順序
    if 'display_order' in data:
        menu_item.display_order = data['display_order']

    # 更新所有子孫的深度
    for descendant in menu_item.get_descendants():
        descendant.depth = descendant.calculate_depth()

    db.session.commit()

    return jsonify(menu_item.to_dict(include_children=True))
