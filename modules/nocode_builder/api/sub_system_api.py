"""
Data CRUD Module - SubSystem API
子系統管理與用戶 Portal API
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
# 管理者 API (admin_required)
# =============================================================================

@api_bp.route('/sub-systems')
@login_required
def list_sub_systems():
    """列出子系統"""
    from ..models import DcSubSystem

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    result = ResourceGateway.filter(
        DcSubSystem,
        is_deleted=False,
        order_by='-updated_at'
    )

    items = []
    for ss in result:
        d = ss.to_dict()
        # 附加社群名稱
        d['group_name'] = _get_group_name(ss.group_unit_secure_code)
        # 附加頁面數
        d['page_count'] = _get_page_count(ss.secure_code, ss.org_secure_code)
        items.append(d)

    return jsonify({'success': True, 'data': items})


@api_bp.route('/sub-systems', methods=['POST'])
@csrf.exempt
@admin_required
def create_sub_system():
    """建立子系統"""
    from ..models import DcSubSystem

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}
    name = data.get('name', '').strip()
    group_sc = data.get('group_unit_secure_code', '').strip()

    if not name:
        return jsonify({'success': False, 'error': 'Name is required'}), 400
    if not group_sc:
        return jsonify({'success': False, 'error': 'Group unit is required'}), 400

    ss = ResourceGateway.create(
        DcSubSystem,
        check_permission=False,
        name=name,
        description=data.get('description', ''),
        icon=data.get('icon', ''),
        group_unit_secure_code=group_sc,
        menu_item_secure_code=data.get('menu_item_secure_code'),
        is_active=data.get('is_active', True),
    )
    ResourceGateway.commit()

    # 自動更新選單 link_target
    _update_menu_link(ss)

    return jsonify({
        'success': True,
        'data': ss.to_dict(),
        'message': '子系統已建立'
    })


@api_bp.route('/sub-systems/<secure_code>')
@login_required
def get_sub_system(secure_code):
    """取得子系統詳情"""
    from ..models import DcSubSystem

    ss = ResourceGateway.get(
        DcSubSystem, secure_code,
        raise_on_not_found=False,
        check_permission=False
    )
    if not ss or ss.is_deleted:
        return jsonify({'success': False, 'error': 'Sub system not found'}), 404

    d = ss.to_dict()
    d['group_name'] = _get_group_name(ss.group_unit_secure_code)
    return jsonify({'success': True, 'data': d})


@api_bp.route('/sub-systems/<secure_code>', methods=['PUT'])
@csrf.exempt
@admin_required
def update_sub_system(secure_code):
    """更新子系統"""
    from ..models import DcSubSystem

    ss = ResourceGateway.get(
        DcSubSystem, secure_code,
        raise_on_not_found=False,
        check_permission=False
    )
    if not ss or ss.is_deleted:
        return jsonify({'success': False, 'error': 'Sub system not found'}), 404

    data = request.get_json() or {}
    update_fields = {}
    for field in ('name', 'description', 'icon', 'group_unit_secure_code',
                  'menu_item_secure_code', 'is_active'):
        if field in data:
            update_fields[field] = data[field]

    if 'name' in update_fields and not update_fields['name'].strip():
        return jsonify({'success': False, 'error': 'Name cannot be empty'}), 400

    ResourceGateway.update(ss, check_permission=False, **update_fields)
    ResourceGateway.commit()

    # 更新選單 link_target
    _update_menu_link(ss)

    return jsonify({
        'success': True,
        'data': ss.to_dict(),
        'message': '子系統已更新'
    })


@api_bp.route('/sub-systems/<secure_code>', methods=['DELETE'])
@csrf.exempt
@admin_required
def delete_sub_system(secure_code):
    """刪除子系統"""
    from ..models import DcSubSystem

    ss = ResourceGateway.get(
        DcSubSystem, secure_code,
        raise_on_not_found=False,
        check_permission=False
    )
    if not ss or ss.is_deleted:
        return jsonify({'success': False, 'error': 'Sub system not found'}), 404

    ResourceGateway.delete(ss, check_permission=False, soft=True)
    ResourceGateway.commit()

    return jsonify({'success': True, 'message': '子系統已刪除'})


# =============================================================================
# 子系統頁面管理 API (admin_required)
# =============================================================================

@api_bp.route('/sub-systems/<secure_code>/pages')
@login_required
def list_sub_system_pages(secure_code):
    """列出子系統的頁面配置"""
    from ..models import DcSubSystem, DcSubSystemPage, DcPageLayout

    ss = ResourceGateway.get(
        DcSubSystem, secure_code,
        raise_on_not_found=False,
        check_permission=False
    )
    if not ss or ss.is_deleted:
        return jsonify({'success': False, 'error': 'Sub system not found'}), 404

    pages = DcSubSystemPage.query.filter_by(
        sub_system_secure_code=secure_code,
        org_secure_code=ss.org_secure_code,
        is_deleted=False,
    ).order_by(DcSubSystemPage.display_order).all()

    result = []
    for ssp in pages:
        d = ssp.to_dict()
        # 附加頁面佈局名稱
        layout = DcPageLayout.query.filter_by(
            secure_code=ssp.page_layout_secure_code,
            is_deleted=False,
        ).first()
        d['page_name'] = layout.name if layout else '(已刪除)'
        result.append(d)

    return jsonify({'success': True, 'data': result})


@api_bp.route('/sub-systems/<secure_code>/pages', methods=['POST'])
@csrf.exempt
@admin_required
def add_sub_system_page(secure_code):
    """新增頁面到子系統"""
    from ..models import DcSubSystem, DcSubSystemPage

    ss = ResourceGateway.get(
        DcSubSystem, secure_code,
        raise_on_not_found=False,
        check_permission=False
    )
    if not ss or ss.is_deleted:
        return jsonify({'success': False, 'error': 'Sub system not found'}), 404

    data = request.get_json() or {}
    page_sc = data.get('page_layout_secure_code', '').strip()
    if not page_sc:
        return jsonify({'success': False, 'error': 'page_layout_secure_code is required'}), 400

    # 檢查是否已加入
    existing = DcSubSystemPage.query.filter_by(
        sub_system_secure_code=secure_code,
        page_layout_secure_code=page_sc,
        org_secure_code=ss.org_secure_code,
        is_deleted=False,
    ).first()
    if existing:
        return jsonify({'success': False, 'error': '此頁面已加入子系統'}), 400

    ssp = ResourceGateway.create(
        DcSubSystemPage,
        check_permission=False,
        sub_system_secure_code=secure_code,
        page_layout_secure_code=page_sc,
        display_name=data.get('display_name', ''),
        display_order=data.get('display_order', 0),
        visible_roles=data.get('visible_roles', ['*']),
        crud_overrides=data.get('crud_overrides', {}),
        data_filters=data.get('data_filters', {}),
        is_active=data.get('is_active', True),
    )
    ResourceGateway.commit()

    return jsonify({
        'success': True,
        'data': ssp.to_dict(),
        'message': '頁面已加入子系統'
    })


@api_bp.route('/sub-systems/<ss_sc>/pages/<page_sc>', methods=['PUT'])
@csrf.exempt
@admin_required
def update_sub_system_page(ss_sc, page_sc):
    """更新子系統頁面設定"""
    from ..models import DcSubSystemPage

    ssp = ResourceGateway.get(
        DcSubSystemPage, page_sc,
        raise_on_not_found=False,
        check_permission=False
    )
    if not ssp or ssp.is_deleted:
        return jsonify({'success': False, 'error': 'Page config not found'}), 404

    data = request.get_json() or {}
    update_fields = {}
    for field in ('display_name', 'display_order', 'visible_roles',
                  'crud_overrides', 'data_filters', 'is_active'):
        if field in data:
            update_fields[field] = data[field]

    ResourceGateway.update(ssp, check_permission=False, **update_fields)
    ResourceGateway.commit()

    return jsonify({
        'success': True,
        'data': ssp.to_dict(),
        'message': '頁面設定已更新'
    })


@api_bp.route('/sub-systems/<ss_sc>/pages/<page_sc>', methods=['DELETE'])
@csrf.exempt
@admin_required
def remove_sub_system_page(ss_sc, page_sc):
    """從子系統移除頁面"""
    from ..models import DcSubSystemPage

    ssp = ResourceGateway.get(
        DcSubSystemPage, page_sc,
        raise_on_not_found=False,
        check_permission=False
    )
    if not ssp or ssp.is_deleted:
        return jsonify({'success': False, 'error': 'Page config not found'}), 404

    ResourceGateway.delete(ssp, check_permission=False, soft=True)
    ResourceGateway.commit()

    return jsonify({'success': True, 'message': '頁面已移除'})


# =============================================================================
# 用戶 Portal API (成員檢查)
# =============================================================================

@api_bp.route('/sub-systems/<secure_code>/portal')
@login_required
def sub_system_portal(secure_code):
    """取得用戶在子系統的 portal 資訊（角色 + 可見頁面）"""
    from ..models import DcSubSystem
    from ..services.sub_system_service import SubSystemService

    ss = ResourceGateway.get(
        DcSubSystem, secure_code,
        raise_on_not_found=False,
        check_permission=False
    )
    if not ss or ss.is_deleted or not ss.is_active:
        return jsonify({'success': False, 'error': 'Sub system not found'}), 404

    role_type = SubSystemService.get_user_role_type(current_user, ss)
    if role_type is None:
        return jsonify({'success': False, 'error': '您不是此子系統的成員'}), 403

    pages = SubSystemService.get_visible_pages(current_user, ss)

    return jsonify({
        'success': True,
        'data': {
            'sub_system': ss.to_dict(),
            'role_type': role_type,
            'is_admin': SubSystemService.is_admin_role(role_type),
            'pages': pages,
        }
    })


# =============================================================================
# 頁面權限 context API (供 lab_view 使用)
# =============================================================================

@api_bp.route('/sub-systems/<ss_sc>/pages/<ssp_sc>/context')
@login_required
def get_page_permission_context(ss_sc, ssp_sc):
    """取得用戶在指定子系統頁面的權限 context"""
    from ..models import DcSubSystem, DcSubSystemPage
    from ..services.sub_system_service import SubSystemService

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

    ssp = ResourceGateway.get(
        DcSubSystemPage, ssp_sc,
        raise_on_not_found=False,
        check_permission=False
    )
    if not ssp or ssp.is_deleted:
        return jsonify({'success': False, 'error': 'Page config not found'}), 404

    context = SubSystemService.get_page_context(role_type, ssp)

    # 替換資料篩選中的變數
    from ..services.crud_service import resolve_filter_variables
    context['data_filters'] = resolve_filter_variables(
        context['data_filters'], current_user
    )

    return jsonify({
        'success': True,
        'data': {
            'role_type': role_type,
            'is_admin': SubSystemService.is_admin_role(role_type),
            **context,
        }
    })


# =============================================================================
# 內部輔助函式
# =============================================================================

def _get_group_name(group_unit_sc):
    """取得社群名稱"""
    from app.models.organizational_unit import OrganizationalUnit
    unit = OrganizationalUnit.query.filter_by(
        secure_code=group_unit_sc,
        is_deleted=False,
    ).first()
    return unit.name if unit else '(未知社群)'


def _get_page_count(sub_system_sc, org_sc):
    """計算子系統頁面數"""
    from ..models import DcSubSystemPage
    return DcSubSystemPage.query.filter_by(
        sub_system_secure_code=sub_system_sc,
        org_secure_code=org_sc,
        is_deleted=False,
    ).count()


def _update_menu_link(sub_system):
    """更新選單項目的 link_target"""
    if not sub_system.menu_item_secure_code:
        return

    try:
        from app.models.menu_item import MenuItem
        menu = MenuItem.query.filter_by(
            secure_code=sub_system.menu_item_secure_code,
            is_deleted=False,
        ).first()
        if menu:
            menu.link_target = '/nocode-builder/sub-systems/' + sub_system.secure_code + '/portal'
            menu.link_type = 'url'
            db.session.commit()
            logger.info('Updated menu link_target for sub_system=%s', sub_system.name)
    except Exception as e:
        logger.warning('Failed to update menu link: %s', e)
