"""
Data CRUD Module - SiteMap API
網站地圖管理 API

Admin API: 完整樹 CRUD + 權限管理
User API: 用戶可見樹 + 節點 context
"""
import logging
import re
from datetime import date

from flask import jsonify, request
from flask_babel import gettext as _
from flask_login import current_user

from app import csrf, db
from app.security.decorators import module_access_required, admin_required
from app.security.resource_gateway import ResourceGateway
from app.platform.data import get_current_org

from . import api_bp

logger = logging.getLogger(__name__)

_PORTAL_PERMISSION_RE = re.compile(r'^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$')


def _validate_access_matrix(value):
    """Validate design-time portal access matrix JSON."""
    if value is None:
        return True, ''
    if not isinstance(value, dict):
        return False, _('access_matrix 必須為物件或 null')
    if set(value.keys()) != {'read'}:
        return False, _('access_matrix 目前只允許 read 設定')

    read = value.get('read')
    if not isinstance(read, dict):
        return False, _('access_matrix.read 必須為物件')
    allowed_read_keys = {'required_permissions', 'match_mode'}
    if not set(read.keys()).issubset(allowed_read_keys):
        return False, _('access_matrix.read 包含不支援的欄位')
    has_required_permissions = 'required_permissions' in read
    if not has_required_permissions:
        return False, _('access_matrix.read 必須包含 required_permissions')

    if has_required_permissions:
        required_permissions = read.get('required_permissions')
        if not isinstance(required_permissions, list) or not required_permissions:
            return False, _('required_permissions 必須為非空陣列')
        for permission_code in required_permissions:
            if not isinstance(permission_code, str) or not _PORTAL_PERMISSION_RE.match(permission_code):
                return False, _('required_permissions 權限碼格式不正確')

    if 'match_mode' in read:
        if read.get('match_mode') not in ('any', 'all'):
            return False, _('match_mode 必須為 any 或 all')

    return True, ''


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
        return jsonify({'success': False, 'error': _('名稱不可為空')}), 400

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
            'message': _('網頁已建立')
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
    if node.sub_system_secure_code != ss_sc:
        return jsonify({'success': False, 'error': 'Node not found'}), 404

    data = request.get_json() or {}
    update_fields = {}
    for field in ('name', 'icon', 'page_layout_secure_code',
                  'display_order', 'access_roles', 'redirect_to',
                  'crud_overrides', 'data_filters', 'is_active',
                  'permission_mode', 'permission_policy_secure_code',
                  'access_matrix'):
        if field in data:
            update_fields[field] = data[field]

    if 'name' in update_fields and not update_fields['name'].strip():
        return jsonify({'success': False, 'error': _('名稱不可為空')}), 400
    if 'access_matrix' in update_fields:
        ok, err = _validate_access_matrix(update_fields['access_matrix'])
        if not ok:
            return jsonify({'success': False, 'error': err}), 400

    try:
        SiteMapService.update_node(node, **update_fields)
        db.session.commit()
        return jsonify({
            'success': True,
            'data': node.to_dict(),
            'message': _('節點已更新')
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
            'message': _('已刪除 %(count)s 個節點', count=count)
        })
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
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
            'message': _('已更新 %(count)s 個節點', count=count)
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
        return None, (jsonify({'success': False, 'error': _('您不是此子系統的開發者')}), 403)

    return ss, None


@api_bp.route('/sub-systems/<ss_sc>/site-map/access-matrix/batch', methods=['POST'])
@csrf.exempt
@module_access_required('nocode_builder')
def batch_update_site_map_access_matrix(ss_sc):
    """批次更新 Site Map 節點 Portal 准入矩陣。"""
    from ..models.site_map_node import DcSiteMapNode

    ss, err = _check_developer(ss_sc)
    if err:
        return err
    org = get_current_org()
    if not org or ss.org_secure_code != org.secure_code:
        return jsonify({'success': False, 'error': _('Sub system not found')}), 404

    data = request.get_json() or {}
    node_scs = data.get('node_secure_codes')
    if not isinstance(node_scs, list) or not node_scs:
        return jsonify({'success': False, 'error': _('node_secure_codes 必須為非空陣列')}), 400
    if len(node_scs) > 200:
        return jsonify({'success': False, 'error': _('一次最多套用 200 個節點')}), 400
    if any(not isinstance(sc, str) or not sc.strip() for sc in node_scs):
        return jsonify({'success': False, 'error': _('node_secure_codes 格式不正確')}), 400
    if 'access_matrix' not in data:
        return jsonify({'success': False, 'error': _('access_matrix 為必填')}), 400

    unique_scs = list(dict.fromkeys(node_scs))
    access_matrix = data.get('access_matrix')
    ok, validate_err = _validate_access_matrix(access_matrix)
    if not ok:
        return jsonify({'success': False, 'error': validate_err}), 400

    nodes = DcSiteMapNode.query.filter(
        DcSiteMapNode.secure_code.in_(unique_scs),
        DcSiteMapNode.org_secure_code == org.secure_code,
        DcSiteMapNode.sub_system_secure_code == ss_sc,
        DcSiteMapNode.is_deleted == False,
    ).all()
    if len(nodes) != len(unique_scs):
        return jsonify({'success': False, 'error': _('節點不屬於此子系統或租戶')}), 400

    try:
        for node in nodes:
            node.access_matrix = access_matrix
        db.session.commit()
        return jsonify({'success': True, 'updated': len(nodes)})
    except Exception as e:
        db.session.rollback()
        logger.exception('[SiteMap] batch_update_access_matrix error')
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/sub-systems/<ss_sc>/site-map/nodes/<node_sc>/permissions')
@module_access_required('nocode_builder')
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
@module_access_required('nocode_builder')
def add_site_map_node_permission(ss_sc, node_sc):
    """
    新增節點准入權限（開發者+管理員）

    Body (grant-based，推薦):
        grant_type: department / group / user
        grant_target: 目標 secure_code
        grant_target_name: 顯示名稱
        include_children: boolean (僅 department/group 有效)

    Body (舊格式，相容):
        target_type: ROLE / DEPARTMENT / GROUP / ACCOUNT
        target_secure_code: 目標 secure_code
    """
    from ..services.site_map_service import SiteMapService

    ss, err = _check_developer(ss_sc)
    if err:
        return err

    node = SiteMapService.get_node(node_sc, ss.org_secure_code)
    if not node:
        return jsonify({'success': False, 'error': 'Node not found'}), 404

    data = request.get_json() or {}

    # 新格式 (grant-based)
    grant_type = data.get('grant_type', '').strip()
    grant_target = data.get('grant_target', '').strip()

    if grant_type and grant_target:
        if grant_type not in ('department', 'group', 'user'):
            return jsonify({'success': False, 'error': _('grant_type 必須為 department / group / user')}), 400

        grant_target_name = data.get('grant_target_name', '').strip()
        include_children = bool(data.get('include_children', False)) if grant_type in ('department', 'group') else False

        try:
            perm = SiteMapService.add_grant_permission(
                node_sc=node_sc,
                org_sc=ss.org_secure_code,
                grant_type=grant_type,
                grant_target=grant_target,
                grant_target_name=grant_target_name,
                include_children=include_children,
            )
            db.session.commit()
            if not perm:
                return jsonify({'success': False, 'error': _('此規則已存在')}), 400
            return jsonify({
                'success': True,
                'data': perm.to_dict(),
                'message': _('准入規則已新增')
            })
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400
        except Exception as e:
            db.session.rollback()
            logger.exception('[SiteMap] add_grant_permission error')
            return jsonify({'success': False, 'error': str(e)}), 500

    # 舊格式 (相容)
    target_type = data.get('target_type', '').strip()
    target_sc = data.get('target_secure_code', '').strip()

    if not target_type or not target_sc:
        return jsonify({'success': False, 'error': _('grant_type+grant_target 或 target_type+target_secure_code 為必填')}), 400

    try:
        perm = SiteMapService.add_permission(node_sc, ss.org_secure_code, target_type, target_sc)
        db.session.commit()
        if not perm:
            return jsonify({'success': False, 'error': _('此權限已存在')}), 400
        return jsonify({
            'success': True,
            'data': perm.to_dict(),
            'message': _('權限已新增')
        })
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        logger.exception('[SiteMap] add_permission error')
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/sub-systems/<ss_sc>/site-map/permissions/<perm_sc>', methods=['DELETE'])
@csrf.exempt
@module_access_required('nocode_builder')
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
    return jsonify({'success': True, 'message': _('權限已刪除')})


@api_bp.route('/sub-systems/<ss_sc>/site-map/targets')
@module_access_required('nocode_builder')
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
# User API (module_access_required + 成員檢查)
# =============================================================================

@api_bp.route('/sub-systems/<ss_sc>/site-map/user-tree')
@module_access_required('nocode_builder', False)
def get_user_site_map_tree(ss_sc):
    """取得用戶可見的 site map 樹（含 GUEST 節點）"""
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
    return jsonify({'success': True, 'data': result})


@api_bp.route('/sub-systems/<ss_sc>/site-map/menu-tree')
@module_access_required('nocode_builder', False)
def get_site_map_menu_tree(ss_sc):
    """SITEMENU Widget 用: 取得權限過濾後的 menu tree"""
    from ..models import DcSubSystem
    from ..services.site_map_service import SiteMapService

    ss = ResourceGateway.get(
        DcSubSystem, ss_sc,
        raise_on_not_found=False,
        check_permission=False
    )
    if not ss or ss.is_deleted or not ss.is_active:
        return jsonify({'success': False, 'error': 'Sub system not found'}), 404

    result = SiteMapService.get_menu_tree(current_user, ss)
    return jsonify({'success': True, 'data': result})


@api_bp.route('/sub-systems/<ss_sc>/site-map/nodes/<node_sc>/context')
@module_access_required('nocode_builder', False)
def get_site_map_node_context(ss_sc, node_sc):
    """取得節點權限 context (准入檢查 + CRUD + data_filters)"""
    from ..models import DcSubSystem
    from ..services.site_map_service import SiteMapService
    from ..services.sub_system_service import SubSystemService
    from ..services.crud_service import FilterVariableNotSupported, resolve_filter_variables

    ss = ResourceGateway.get(
        DcSubSystem, ss_sc,
        raise_on_not_found=False,
        check_permission=False
    )
    if not ss or ss.is_deleted or not ss.is_active:
        return jsonify({'success': False, 'error': 'Sub system not found'}), 404

    role_type = SubSystemService.get_user_role_type(current_user, ss)
    if role_type is None:
        role_type = 'GUEST'
    is_admin = SubSystemService.is_admin_role(role_type)

    node = SiteMapService.get_node(node_sc, ss.org_secure_code)
    if not node:
        return jsonify({'success': False, 'error': 'Node not found'}), 404

    # 准入檢查（管理層跳過）
    if not is_admin and not SiteMapService.check_page_access(role_type, node, user=current_user):
        redirect_to = node.redirect_to or '/dashboard'
        return jsonify({
            'success': False,
            'error': _('您沒有存取此頁面的權限'),
            'redirect_to': redirect_to,
        }), 403

    context = SiteMapService.get_node_context(node, role_type)
    try:
        context['data_filters'] = resolve_filter_variables(
            context['data_filters'], current_user
        )
    except FilterVariableNotSupported:
        return jsonify({'success': False, 'error': 'filter_variable_not_supported'}), 400

    # 提供已解析的變數值，供前端解析 widget-level roleFilters
    resolved_vars = {
        '$CURRENT_USER': getattr(current_user, 'secure_code', ''),
        '$CURRENT_USER_NAME': getattr(current_user, 'username', ''),
        '$CURRENT_ORG': getattr(current_user, 'org_secure_code', ''),
        '$TODAY': date.today().isoformat(),
    }

    return jsonify({
        'success': True,
        'data': {
            'role_type': role_type,
            'is_admin': is_admin,
            'node_secure_code': node_sc,
            'page_layout_secure_code': node.page_layout_secure_code,
            'resolved_vars': resolved_vars,
            **context,
        }
    })


# =============================================================================
# 權限政策組 API
# =============================================================================

@api_bp.route('/sub-systems/<ss_sc>/permission-policies')
@admin_required
def list_permission_policies(ss_sc):
    """列出子系統的權限政策組"""
    from ..models import DcSubSystem
    from ..services.permission_policy_service import PermissionPolicyService

    ss = ResourceGateway.get(DcSubSystem, ss_sc, raise_on_not_found=False, check_permission=False)
    if not ss or ss.is_deleted:
        return jsonify({'success': False, 'error': 'Sub system not found'}), 404

    groups = PermissionPolicyService.list_groups(ss_sc, ss.org_secure_code)
    return jsonify({'success': True, 'data': groups})


@api_bp.route('/sub-systems/<ss_sc>/permission-policies', methods=['POST'])
@csrf.exempt
@admin_required
def create_permission_policy(ss_sc):
    """建立權限政策組"""
    from ..models import DcSubSystem
    from ..services.permission_policy_service import PermissionPolicyService

    ss = ResourceGateway.get(DcSubSystem, ss_sc, raise_on_not_found=False, check_permission=False)
    if not ss or ss.is_deleted:
        return jsonify({'success': False, 'error': 'Sub system not found'}), 404

    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': _('名稱不可為空')}), 400

    try:
        group = PermissionPolicyService.create_group(
            ss_sc, ss.org_secure_code,
            name=name,
            description=data.get('description', ''),
        )
        db.session.commit()
        return jsonify({'success': True, 'data': group.to_dict(), 'message': _('政策組已建立')})
    except Exception as e:
        db.session.rollback()
        logger.exception('[PermPolicy] create error')
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/sub-systems/<ss_sc>/permission-policies/<pp_sc>', methods=['PUT'])
@csrf.exempt
@admin_required
def update_permission_policy(ss_sc, pp_sc):
    """更新權限政策組"""
    from ..services.permission_policy_service import PermissionPolicyService

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    group = PermissionPolicyService.get_group(pp_sc, org.secure_code)
    if not group:
        return jsonify({'success': False, 'error': 'Policy group not found'}), 404

    data = request.get_json() or {}
    if 'name' in data and not (data['name'] or '').strip():
        return jsonify({'success': False, 'error': _('名稱不可為空')}), 400

    try:
        PermissionPolicyService.update_group(group, **data)
        db.session.commit()
        return jsonify({'success': True, 'data': group.to_dict(), 'message': _('政策組已更新')})
    except Exception as e:
        db.session.rollback()
        logger.exception('[PermPolicy] update error')
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/sub-systems/<ss_sc>/permission-policies/<pp_sc>', methods=['DELETE'])
@csrf.exempt
@admin_required
def delete_permission_policy(ss_sc, pp_sc):
    """刪除權限政策組"""
    from ..services.permission_policy_service import PermissionPolicyService

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    group = PermissionPolicyService.get_group(pp_sc, org.secure_code)
    if not group:
        return jsonify({'success': False, 'error': 'Policy group not found'}), 404

    try:
        result = PermissionPolicyService.delete_group(group)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': _('政策組已刪除，%(n)s 個節點權限已重設', n=result['affected_nodes'])
        })
    except Exception as e:
        db.session.rollback()
        logger.exception('[PermPolicy] delete error')
        return jsonify({'success': False, 'error': str(e)}), 500


# --- 政策規則 ---

@api_bp.route('/sub-systems/<ss_sc>/permission-policies/<pp_sc>/rules')
@admin_required
def list_policy_rules(ss_sc, pp_sc):
    """列出政策組的規則"""
    from ..services.permission_policy_service import PermissionPolicyService

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    group = PermissionPolicyService.get_group(pp_sc, org.secure_code)
    if not group:
        return jsonify({'success': False, 'error': 'Policy group not found'}), 404

    rules = PermissionPolicyService.list_rules(pp_sc, org.secure_code)
    return jsonify({'success': True, 'data': rules})


@api_bp.route('/sub-systems/<ss_sc>/permission-policies/<pp_sc>/rules', methods=['POST'])
@csrf.exempt
@admin_required
def add_policy_rule(ss_sc, pp_sc):
    """新增規則到政策組"""
    from ..services.permission_policy_service import PermissionPolicyService

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    group = PermissionPolicyService.get_group(pp_sc, org.secure_code)
    if not group:
        return jsonify({'success': False, 'error': 'Policy group not found'}), 404

    data = request.get_json() or {}
    grant_type = data.get('grant_type', '')
    grant_target = data.get('grant_target', '')

    if not grant_type or not grant_target:
        return jsonify({'success': False, 'error': _('缺少必要欄位')}), 400

    try:
        rule = PermissionPolicyService.add_rule(
            pp_sc, org.secure_code,
            grant_type=grant_type,
            grant_target=grant_target,
            grant_target_name=data.get('grant_target_name', ''),
            include_children=data.get('include_children', False),
        )
        db.session.commit()
        return jsonify({'success': True, 'data': rule.to_dict(), 'message': _('規則已新增')})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        logger.exception('[PermPolicy] add_rule error')
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/sub-systems/<ss_sc>/permission-policies/rules/<rule_sc>', methods=['DELETE'])
@csrf.exempt
@admin_required
def delete_policy_rule(ss_sc, rule_sc):
    """刪除政策規則"""
    from ..services.permission_policy_service import PermissionPolicyService

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    try:
        ok = PermissionPolicyService.delete_rule(rule_sc, org.secure_code)
        if not ok:
            return jsonify({'success': False, 'error': 'Rule not found'}), 404
        db.session.commit()
        return jsonify({'success': True, 'message': _('規則已刪除')})
    except Exception as e:
        db.session.rollback()
        logger.exception('[PermPolicy] delete_rule error')
        return jsonify({'success': False, 'error': str(e)}), 500


# --- 向下套用 ---

@api_bp.route('/sub-systems/<ss_sc>/site-map/nodes/<node_sc>/apply-down', methods=['POST'])
@csrf.exempt
@admin_required
def apply_permission_down(ss_sc, node_sc):
    """向下套用：把節點的權限推送給所有子節點"""
    from ..services.site_map_service import SiteMapService
    from ..services.permission_policy_service import PermissionPolicyService

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    node = SiteMapService.get_node(node_sc, org.secure_code)
    if not node:
        return jsonify({'success': False, 'error': 'Node not found'}), 404

    data = request.get_json() or {}
    skip_custom = data.get('skip_custom', True)

    try:
        affected = PermissionPolicyService.apply_down(node, org.secure_code, skip_custom=skip_custom)
        db.session.commit()
        return jsonify({
            'success': True,
            'data': {'affected': affected},
            'message': _('已套用到 %(affected)s 個子節點', affected=affected)
        })
    except Exception as e:
        db.session.rollback()
        logger.exception('[PermPolicy] apply_down error')
        return jsonify({'success': False, 'error': str(e)}), 500
