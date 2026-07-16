"""
BeakMask Menu API
選單管理 API
"""
import logging

from flask import Blueprint, jsonify, request
from flask_babel import gettext as _
from flask_login import current_user
from sqlalchemy import text

from ..security.decorators import login_required, admin_required, system_admin_required
from ..security.resource_gateway import ResourceGateway
from ..services.menu_service import MenuService
from ..services.page_role_guard import PageRoleGuard
from ..models.menu_item import MenuItem
from ..models.role import Role
from .. import db

logger = logging.getLogger(__name__)

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
@system_admin_required
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
@system_admin_required
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
@system_admin_required
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
@system_admin_required
def get_menu_item(secure_code: str):
    """
    取得單一選單項目

    Returns:
        MenuItem dict (含 children)
    """
    menu_item = ResourceGateway.get(MenuItem, secure_code, check_permission=False)
    return jsonify(menu_item.to_dict(include_children=True))


@menu_bp.route('/<secure_code>', methods=['PUT'])
@system_admin_required
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
    menu_item = ResourceGateway.get(MenuItem, secure_code, check_permission=False)
    data = request.get_json()

    # 允許更新的欄位
    allowed_fields = [
        'title', 'title_i18n', 'title_en', 'title_zh_cn',
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
@system_admin_required
def delete_menu_item(secure_code: str):
    """
    刪除選單項目

    如果有子項目則無法刪除。

    Returns:
        204 No Content
    """
    menu_item = ResourceGateway.get(MenuItem, secure_code, check_permission=False)

    if not menu_item.is_user_created:
        return jsonify({'error': _('預設選單項目禁止刪除')}), 403

    # 檢查子孫是否包含預設項目
    descendants = menu_item.get_descendants()
    protected = [d for d in descendants if not d.is_user_created]
    if protected:
        names = '、'.join(d.title for d in protected[:5])
        return jsonify({'error': _('子項目中包含預設選單（%(names)s），請先將其移出', names=names)}), 400

    success = MenuService.delete_menu_item(menu_item, soft=True)

    if not success:
        return jsonify({'error': 'Cannot delete menu item with children'}), 400

    db.session.commit()

    return '', 204


@menu_bp.route('/reorder', methods=['POST'])
@system_admin_required
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
@system_admin_required
def move_menu_item(secure_code: str):
    """
    移動選單項目到新的父節點

    Body:
        parent_secure_code: str | null (null = 移到根層級)
        display_order: int

    Returns:
        Updated MenuItem dict
    """
    menu_item = ResourceGateway.get(MenuItem, secure_code, check_permission=False)
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
        parent = ResourceGateway.get(MenuItem, new_parent, raise_on_not_found=False, check_permission=False)
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


# =============================================================================
# 選單角色需求 API (Page Role Guard)
# =============================================================================

@menu_bp.route('/<secure_code>/roles', methods=['GET'])
@admin_required
def get_menu_roles(secure_code: str):
    """
    取得選單項目的角色需求

    SYSTEM_ADMIN: 查所有企業的系統預設角色（去重 by code），已設定狀態取任一企業
    ORG_ADMIN: 查自己企業的角色（含企業自訂角色，如 SOC_L1）

    Returns:
        {roles: [...], available_roles: [...]}
    """
    # RLS context: 選單屬系統企業（全站共用物），管理員操作需繞過租戶隔離
    # （ORG_ADMIN 亦需讀取，故不可用 ResourceGateway 的租戶過濾取件）
    db.session.execute(text("SET LOCAL app.is_system_admin = 'true'"))

    menu_item = MenuItem.query.filter_by(
        secure_code=secure_code, is_deleted=False
    ).first()
    if not menu_item:
        return jsonify({'error': _('選單項目不存在')}), 404

    if current_user.is_system_admin:
        # SYSTEM_ADMIN: 查系統預設角色（去重 by code）
        all_system_roles = Role.query.filter(
            Role.is_system_role == True,
            Role.is_deleted == False,
            Role.is_active == True,
        ).order_by(Role.role_level, Role.name).all()

        # 去重 by code，取第一筆
        seen_codes = set()
        available_roles = []
        for r in all_system_roles:
            if r.code not in seen_codes:
                seen_codes.add(r.code)
                available_roles.append(r)

        # 已設定的角色需求：查所有企業，去重 by role code
        from ..models.menu_role_requirement import MenuRoleRequirement
        all_reqs = MenuRoleRequirement.query.filter(
            MenuRoleRequirement.menu_secure_code == menu_item.secure_code,
            MenuRoleRequirement.is_deleted == False,
        ).all()

        # 反查角色 code，去重
        req_role_scs = {r.role_secure_code for r in all_reqs}
        req_role_codes = set()
        deduped_roles = []  # 去重後的角色（用於「已設定」顯示）
        if req_role_scs:
            req_roles = Role.query.filter(
                Role.secure_code.in_(req_role_scs),
                Role.is_deleted == False,
            ).all()
            seen = set()
            for r in req_roles:
                if r.code not in seen:
                    seen.add(r.code)
                    deduped_roles.append(r)
            req_role_codes = seen

        return jsonify({
            'roles': [
                {
                    'role_secure_code': r.secure_code,
                    'role_code': r.code,
                    'role_name': r.name,
                    'role_type': r.role_type,
                }
                for r in deduped_roles
            ],
            'available_roles': [
                {
                    'id': r.code,  # SYSTEM_ADMIN 用 code 作為 ID
                    'code': r.code,
                    'name': r.name,
                    'role_type': r.role_type,
                    'role_level': r.role_level,
                    'scope_type': r.scope_type,
                    'selected': r.code in req_role_codes,
                }
                for r in available_roles
            ],
        })
    else:
        # ORG_ADMIN: 查自己企業的角色
        requirements = PageRoleGuard.get_menu_roles(
            menu_item.secure_code,
            current_user.org_secure_code,
        )

        available_roles = Role.query.filter(
            Role.org_secure_code == current_user.org_secure_code,
            Role.is_deleted == False,
            Role.is_active == True,
        ).order_by(Role.role_level, Role.name).all()

        selected_scs = {r.role_secure_code for r in requirements}

        return jsonify({
            'roles': [r.to_dict() for r in requirements],
            'available_roles': [
                {
                    'id': r.secure_code,
                    'code': r.code,
                    'name': r.name,
                    'role_type': r.role_type,
                    'role_level': r.role_level,
                    'scope_type': r.scope_type,
                    'selected': r.secure_code in selected_scs,
                }
                for r in available_roles
            ],
        })


@menu_bp.route('/<secure_code>/roles', methods=['PUT'])
@admin_required
def set_menu_roles(secure_code: str):
    """
    設定選單項目的角色需求（全量替換）

    Body:
        role_secure_codes: [str, ...]
            - ORG_ADMIN: role secure_codes（自己企業）
            - SYSTEM_ADMIN: role codes（批量套用到所有企業）

    Returns:
        {success: true, count: int}
    """
    data = request.get_json()

    role_identifiers = data.get('role_secure_codes', [])

    try:
        # RLS context: 選單屬系統企業（全站共用物），管理員操作需繞過租戶隔離
        db.session.execute(text("SET LOCAL app.is_system_admin = 'true'"))

        menu_item = MenuItem.query.filter_by(
            secure_code=secure_code, is_deleted=False
        ).first()
        if not menu_item:
            return jsonify({'error': _('選單項目不存在')}), 404

        if current_user.is_system_admin:
            # SYSTEM_ADMIN: role_identifiers 是 role codes，批量為所有企業設定
            from ..models.organization import Organization

            orgs = Organization.query.filter(
                Organization.is_deleted == False,
                Organization.is_active == True,
            ).all()

            total_count = 0
            for org in orgs:
                # 找到該企業中 code 匹配的角色 secure_codes
                if role_identifiers:
                    org_roles = Role.query.filter(
                        Role.org_secure_code == org.secure_code,
                        Role.code.in_(role_identifiers),
                        Role.is_deleted == False,
                    ).all()
                    org_role_scs = [r.secure_code for r in org_roles]
                else:
                    org_role_scs = []

                count = PageRoleGuard.set_menu_roles(
                    menu_item.secure_code,
                    org.secure_code,
                    org_role_scs,
                )
                total_count += count

            db.session.commit()
            return jsonify({
                'success': True,
                'count': total_count,
                'org_count': len(orgs),
            })
        else:
            # ORG_ADMIN: role_identifiers 是 role secure_codes
            # 只接受屬於自己企業的角色，防止跨租戶引用
            if role_identifiers:
                own_roles = Role.query.filter(
                    Role.org_secure_code == current_user.org_secure_code,
                    Role.secure_code.in_(role_identifiers),
                    Role.is_deleted == False,
                ).all()
                role_identifiers = [r.secure_code for r in own_roles]

            count = PageRoleGuard.set_menu_roles(
                menu_item.secure_code,
                current_user.org_secure_code,
                role_identifiers,
            )

            db.session.commit()
            return jsonify({'success': True, 'count': count})

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to set menu roles: {e}")
        return jsonify({'error': _('更新角色需求失敗')}), 500


# =============================================================================
# 選單重置 API
# =============================================================================

@menu_bp.route('/reset-positions', methods=['POST'])
@system_admin_required
def reset_menu_positions():
    """
    重置選單項目位置（只還原排序、父子關係、深度）

    不影響權限、標題、icon 等其他設定。

    Returns:
        {success: true, updated: int, skipped: int}
    """
    try:
        result = MenuService.reset_menu_positions()
        return jsonify({'success': True, **result})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to reset menu positions: {e}")
        return jsonify({'error': _('重置選單位置失敗')}), 500


@menu_bp.route('/reset-factory', methods=['POST'])
@system_admin_required
def reset_menu_factory():
    """
    重置選單所有設定成出廠值（完全覆蓋回預設值）

    資料來源：優先 menu_defaults 表，fallback menu_defaults.py。
    覆蓋範圍：位置、標題、icon、連結、權限等所有屬性。
    用戶自建選單不受影響。

    Returns:
        {success: true, updated: int, skipped: int, permissions_reset: int,
         source: str}
    """
    try:
        result = MenuService.reset_menu_factory()
        return jsonify({'success': True, **result})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to reset menu factory: {e}")
        return jsonify({'error': _('重置選單出廠值失敗')}), 500


@menu_bp.route('/save-factory-defaults', methods=['POST'])
@system_admin_required
def save_menu_factory_defaults():
    """
    設定目前組態成出廠值（系統管理員專用）

    將當前 menu_items + menu_permissions + menu_role_requirements
    快照到 menu_defaults 表。

    Returns:
        {message: str, count: int}
    """
    try:
        result = MenuService.save_menu_factory_defaults(
            operator_username=current_user.username
        )
        if 'error' in result:
            return jsonify({'error': result['error']}), 400
        return jsonify(result), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to save menu factory defaults: {e}")
        return jsonify({'error': _('儲存選單出廠預設值失敗')}), 500


@menu_bp.route('/export-factory-sql', methods=['POST'])
@system_admin_required
def export_factory_sql():
    """
    從 menu_defaults 表匯出安裝用 SQL（原廠專用）

    生成 058_seed_menu_defaults.sql，供全新安裝時灌入預設值。
    upgrade 不會覆蓋用戶已儲存的預設值。

    Returns:
        {message: str, count: int, sql_file: str}
    """
    try:
        result = MenuService.export_factory_sql()
        if 'error' in result:
            return jsonify({'error': result['error']}), 400
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Failed to export factory SQL: {e}")
        return jsonify({'error': _('匯出 SQL 失敗')}), 500
