"""
Data CRUD Module - SiteMap API
網站地圖管理 API

Admin API: 完整樹 CRUD + 權限管理
User API: 用戶可見樹 + 節點 context
"""
import logging

from flask import jsonify, request
from flask_login import current_user

from app import csrf, db
from app.security.decorators import login_required, admin_required
from app.security.resource_gateway import ResourceGateway
from app.platform.data import get_current_org

from . import api_bp

logger = logging.getLogger(__name__)


# =============================================================================
# Admin API (@admin_required)
# =============================================================================

@api_bp.route('/sub-systems/<ss_sc>/site-map')
@admin_required
def get_site_map_tree(ss_sc):
    """取得完整 site map 樹"""
    from ..models import DcSubSystem
    from ..services.site_map_service import SiteMapService

    ss = ResourceGateway.get(
        DcSubSystem, ss_sc,
        raise_on_not_found=False,
        check_permission=False
    )
    if not ss or ss.is_deleted:
        return jsonify({'success': False, 'error': 'Sub system not found'}), 404

    tree = SiteMapService.get_tree(ss_sc, ss.org_secure_code)
    return jsonify({'success': True, 'data': tree})


@api_bp.route('/sub-systems/<ss_sc>/site-map/nodes', methods=['POST'])
@csrf.exempt
@admin_required
def create_site_map_node(ss_sc):
    """新增 site map 節點"""
    from ..models import DcSubSystem
    from ..services.site_map_service import SiteMapService

    ss = ResourceGateway.get(
        DcSubSystem, ss_sc,
        raise_on_not_found=False,
        check_permission=False
    )
    if not ss or ss.is_deleted:
        return jsonify({'success': False, 'error': 'Sub system not found'}), 404

    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'error': '名稱不可為空'}), 400

    node_type = data.get('node_type', 'page')

    try:
        node = SiteMapService.create_node(
            sub_system_sc=ss_sc,
            org_sc=ss.org_secure_code,
            name=name,
            node_type=node_type,
            parent_sc=data.get('parent_secure_code') or None,
            icon=data.get('icon'),
            page_layout_sc=data.get('page_layout_secure_code') or None,
            display_order=data.get('display_order', 0),
        )
        db.session.commit()
        return jsonify({
            'success': True,
            'data': node.to_dict(),
            'message': '節點已建立'
        })
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        logger.exception('[SiteMap] create_node error')
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/sub-systems/<ss_sc>/site-map/nodes/<node_sc>', methods=['PUT'])
@csrf.exempt
@admin_required
def update_site_map_node(ss_sc, node_sc):
    """更新 site map 節點"""
    from ..services.site_map_service import SiteMapService

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    node = SiteMapService.get_node(node_sc, org.secure_code)
    if not node:
        return jsonify({'success': False, 'error': 'Node not found'}), 404

    data = request.get_json() or {}
    update_fields = {}
    for field in ('name', 'icon', 'page_layout_secure_code',
                  'display_order', 'crud_overrides', 'data_filters', 'is_active'):
        if field in data:
            update_fields[field] = data[field]

    if 'name' in update_fields and not update_fields['name'].strip():
        return jsonify({'success': False, 'error': '名稱不可為空'}), 400

    try:
        SiteMapService.update_node(node, **update_fields)
        db.session.commit()
        return jsonify({
            'success': True,
            'data': node.to_dict(),
            'message': '節點已更新'
        })
    except Exception as e:
        db.session.rollback()
        logger.exception('[SiteMap] update_node error')
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/sub-systems/<ss_sc>/site-map/nodes/<node_sc>', methods=['DELETE'])
@csrf.exempt
@admin_required
def delete_site_map_node(ss_sc, node_sc):
    """刪除 site map 節點 (含子節點遞迴)"""
    from ..services.site_map_service import SiteMapService

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    try:
        count = SiteMapService.delete_node(node_sc, org.secure_code)
        db.session.commit()
        if count == 0:
            return jsonify({'success': False, 'error': 'Node not found'}), 404
        return jsonify({
            'success': True,
            'message': f'已刪除 {count} 個節點'
        })
    except Exception as e:
        db.session.rollback()
        logger.exception('[SiteMap] delete_node error')
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/sub-systems/<ss_sc>/site-map/reorder', methods=['PUT'])
@csrf.exempt
@admin_required
def reorder_site_map_nodes(ss_sc):
    """批量重排序節點"""
    from ..services.site_map_service import SiteMapService

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}
    nodes_order = data.get('nodes', [])
    if not nodes_order:
        return jsonify({'success': False, 'error': 'nodes is required'}), 400

    try:
        count = SiteMapService.reorder_nodes(nodes_order, org.secure_code)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'已更新 {count} 個節點'
        })
    except Exception as e:
        db.session.rollback()
        logger.exception('[SiteMap] reorder_nodes error')
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# 節點權限管理 API (開發者 + 管理員)
# =============================================================================

def _check_developer(ss_sc):
    """
    檢查當前用戶是否為子系統開發者（或管理員）。
    返回 (DcSubSystem, error_response)，其中一個為 None。
    """
    from ..models import DcSubSystem
    from ..services.project_service import ProjectService

    ss = ResourceGateway.get(
        DcSubSystem, ss_sc,
        raise_on_not_found=False,
        check_permission=False
    )
    if not ss or ss.is_deleted:
        return None, (jsonify({'success': False, 'error': 'Sub system not found'}), 404)

    if not ProjectService.is_developer(current_user, ss):
        return None, (jsonify({'success': False, 'error': '您不是此子系統的開發者'}), 403)

    return ss, None


@api_bp.route('/sub-systems/<ss_sc>/site-map/nodes/<node_sc>/permissions')
@login_required
def get_site_map_node_permissions(ss_sc, node_sc):
    """取得節點權限列表（開發者+管理員）"""
    from ..services.site_map_service import SiteMapService

    ss, err = _check_developer(ss_sc)
    if err:
        return err

    node = SiteMapService.get_node(node_sc, ss.org_secure_code)
    if not node:
        return jsonify({'success': False, 'error': 'Node not found'}), 404

    perms = SiteMapService.get_node_permissions(node_sc, ss.org_secure_code)
    return jsonify({'success': True, 'data': perms})


@api_bp.route('/sub-systems/<ss_sc>/site-map/nodes/<node_sc>/permissions', methods=['POST'])
@csrf.exempt
@login_required
def add_site_map_node_permission(ss_sc, node_sc):
    """新增節點權限（開發者+管理員）"""
    from ..services.site_map_service import SiteMapService

    ss, err = _check_developer(ss_sc)
    if err:
        return err

    node = SiteMapService.get_node(node_sc, ss.org_secure_code)
    if not node:
        return jsonify({'success': False, 'error': 'Node not found'}), 404

    data = request.get_json() or {}
    target_type = data.get('target_type', '').strip()
    target_sc = data.get('target_secure_code', '').strip()

    if not target_type or not target_sc:
        return jsonify({'success': False, 'error': 'target_type and target_secure_code are required'}), 400

    try:
        perm = SiteMapService.add_permission(node_sc, ss.org_secure_code, target_type, target_sc)
        db.session.commit()
        if not perm:
            return jsonify({'success': False, 'error': '此權限已存在'}), 400
        return jsonify({
            'success': True,
            'data': perm.to_dict(),
            'message': '權限已新增'
        })
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        logger.exception('[SiteMap] add_permission error')
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/sub-systems/<ss_sc>/site-map/permissions/<perm_sc>', methods=['DELETE'])
@csrf.exempt
@login_required
def remove_site_map_permission(ss_sc, perm_sc):
    """刪除節點權限（開發者+管理員）"""
    from ..services.site_map_service import SiteMapService

    ss, err = _check_developer(ss_sc)
    if err:
        return err

    ok = SiteMapService.remove_permission(perm_sc, ss.org_secure_code)
    if not ok:
        return jsonify({'success': False, 'error': 'Permission not found'}), 404

    db.session.commit()
    return jsonify({'success': True, 'message': '權限已刪除'})


@api_bp.route('/sub-systems/<ss_sc>/site-map/targets')
@login_required
def get_site_map_targets(ss_sc):
    """
    取得可選的權限目標清單（開發者+管理員）

    Query params:
        type: ROLE / DEPARTMENT / GROUP / ACCOUNT
    """
    from app.services.module_access_service import ModuleAccessService

    ss, err = _check_developer(ss_sc)
    if err:
        return err

    target_type = request.args.get('type', '').strip()
    valid_types = ('ROLE', 'DEPARTMENT', 'GROUP', 'ACCOUNT')
    if target_type not in valid_types:
        return jsonify({
            'success': False,
            'error': f'Invalid type. Must be one of: {", ".join(valid_types)}'
        }), 400

    targets = ModuleAccessService.get_available_targets(
        ss.org_secure_code,
        target_type,
    )

    return jsonify({'success': True, 'data': targets})


# =============================================================================
# User API (@login_required + 成員檢查)
# =============================================================================

@api_bp.route('/sub-systems/<ss_sc>/site-map/user-tree')
@login_required
def get_user_site_map_tree(ss_sc):
    """取得用戶可見的 site map 樹"""
    from ..models import DcSubSystem
    from ..services.site_map_service import SiteMapService

    ss = ResourceGateway.get(
        DcSubSystem, ss_sc,
        raise_on_not_found=False,
        check_permission=False
    )
    if not ss or ss.is_deleted or not ss.is_active:
        return jsonify({'success': False, 'error': 'Sub system not found'}), 404

    result = SiteMapService.get_user_tree(current_user, ss)
    if result is None:
        return jsonify({'success': False, 'error': '您不是此子系統的成員'}), 403

    return jsonify({'success': True, 'data': result})


@api_bp.route('/sub-systems/<ss_sc>/site-map/nodes/<node_sc>/context')
@login_required
def get_site_map_node_context(ss_sc, node_sc):
    """取得節點權限 context (CRUD + data_filters)"""
    from ..models import DcSubSystem
    from ..services.site_map_service import SiteMapService
    from ..services.sub_system_service import SubSystemService
    from ..services.crud_service import resolve_filter_variables

    ss = ResourceGateway.get(
        DcSubSystem, ss_sc,
        raise_on_not_found=False,
        check_permission=False
    )
    if not ss or ss.is_deleted or not ss.is_active:
        return jsonify({'success': False, 'error': 'Sub system not found'}), 404

    role_type = SubSystemService.get_user_role_type(current_user, ss)
    if role_type is None:
        return jsonify({'success': False, 'error': '您不是此子系統的成員'}), 403

    node = SiteMapService.get_node(node_sc, ss.org_secure_code)
    if not node:
        return jsonify({'success': False, 'error': 'Node not found'}), 404

    # 檢查節點存取權限
    is_admin = SubSystemService.is_admin_role(role_type)
    if not is_admin and not SiteMapService.check_node_access(current_user, node):
        return jsonify({'success': False, 'error': '您沒有存取此節點的權限'}), 403

    context = SiteMapService.get_node_context(node, role_type)
    context['data_filters'] = resolve_filter_variables(
        context['data_filters'], current_user
    )

    return jsonify({
        'success': True,
        'data': {
            'role_type': role_type,
            'is_admin': is_admin,
            'node_secure_code': node_sc,
            'page_layout_secure_code': node.page_layout_secure_code,
            **context,
        }
    })
