"""
Data CRUD Module - SubSystem API
子系統管理與用戶 Portal API
"""
import logging

from flask import jsonify, request
from flask_login import current_user

from app import csrf, db
from app.security.decorators import module_access_required, admin_required
from app.security.resource_gateway import ResourceGateway
from app.platform.data import get_current_org

from . import api_bp

logger = logging.getLogger(__name__)


# =============================================================================
# 管理者 API (admin_required)
# =============================================================================

@api_bp.route('/sub-systems')
@module_access_required('nocode_builder')
def list_sub_systems():
    """列出子系統（依用戶過濾：企業管理員看全部，其餘只看 developers 含自己的）"""
    from ..models import DcSubSystem

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    user_sc = current_user.secure_code

    if current_user.is_org_admin:
        # 企業管理員：看自己企業全部子系統
        result = ResourceGateway.filter(
            DcSubSystem,
            is_deleted=False,
            order_by='-updated_at'
        )
    else:
        # 一般用戶：只看 developers JSONB 陣列包含自己的
        result = DcSubSystem.query.filter(
            DcSubSystem.org_secure_code == current_user.org_secure_code,
            DcSubSystem.is_deleted == False,
            DcSubSystem.developers.op('?')(user_sc),
        ).order_by(DcSubSystem.updated_at.desc()).all()

    # 系統管理員需要企業名稱，預先查詢快取
    org_name_cache = {}
    if current_user.is_system_admin:
        from app.models.organization import Organization
        for org_row in Organization.query.filter_by(is_deleted=False).all():
            org_name_cache[org_row.secure_code] = org_row.name

    # 預先查詢所有開發者名稱快取
    developer_name_cache = _build_developer_name_cache(result)

    items = []
    for ss in result:
        d = ss.to_dict()
        # 附加社群名稱
        d['group_name'] = _get_group_name(ss.group_unit_secure_code)
        # 附加頁面數
        d['page_count'] = _get_page_count(ss.secure_code, ss.org_secure_code)
        # 附加開發者顯示名稱
        d['developer_names'] = [
            developer_name_cache.get(sc, sc)
            for sc in (ss.developers or [])
        ]
        # 系統管理員：附加企業名稱
        if current_user.is_system_admin:
            d['org_name'] = org_name_cache.get(ss.org_secure_code, '')
        items.append(d)

    return jsonify({
        'success': True,
        'data': items,
        'meta': {
            'is_system_admin': current_user.is_system_admin,
            'is_org_admin': current_user.is_org_admin,
            'can_manage': current_user.is_system_admin or current_user.is_org_admin,
        },
    })


@api_bp.route('/sub-systems', methods=['POST'])
@csrf.exempt
@admin_required
def create_sub_system():
    """建立子系統（統一使用 SubSystemProvisionService）"""
    from ..services.provision_service import SubSystemProvisionService

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

    result = SubSystemProvisionService.create_sub_system(
        org_sc=org.secure_code,
        name=name,
        icon=data.get('icon', ''),
        description=data.get('description', ''),
        group_unit_secure_code=group_sc,
        menu_item_secure_code=data.get('menu_item_secure_code', ''),
    )

    if not result['success']:
        return jsonify({'success': False, 'error': result['error']}), 400

    return jsonify({
        'success': True,
        'data': result['data'],
        'message': '子系統已建立'
    })


@api_bp.route('/sub-systems/<secure_code>')
@module_access_required('nocode_builder')
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

    # 附加架構師/開發者顯示名稱
    developer_name_cache = _build_developer_name_cache([ss])
    d['developer_names'] = [
        developer_name_cache.get(sc, sc)
        for sc in (ss.developers or [])
    ]

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
@module_access_required('nocode_builder')
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
@module_access_required('nocode_builder', False)
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
@module_access_required('nocode_builder', False)
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
# 資料來源 API (Studio 設計用)
# =============================================================================

@api_bp.route('/sub-systems/<secure_code>/data-sources')
@module_access_required('nocode_builder')
def list_data_sources(secure_code):
    """
    列出子系統可用的資料來源

    固定回傳企業 DB（若已建立）+ 集團 DB（若企業屬於集團且有共享 DB）。
    未來可擴充 ODBC 等自訂來源。
    """
    from ..models import DcSubSystem
    from ..services.db_connector import check_cg_available

    ss = ResourceGateway.get(
        DcSubSystem, secure_code,
        raise_on_not_found=False,
        check_permission=False
    )
    if not ss or ss.is_deleted:
        return jsonify({'success': False, 'error': 'Sub system not found'}), 404

    org_sc = ss.org_secure_code
    sources = []

    # 企業 DB
    from modules.form_workflow.models.org_database import FwOrgDatabase
    org_db = FwOrgDatabase.query.filter_by(
        org_secure_code=org_sc,
        is_ready=True,
        is_deleted=False,
    ).first()
    sources.append({
        'key': 'org',
        'label': '企業資料庫',
        'db_name': org_db.db_name if org_db else None,
        'available': bool(org_db),
    })

    # 集團 DB
    cg_info = check_cg_available(org_sc)
    sources.append({
        'key': 'conglomerate',
        'label': '集團共享資料庫' + (
            f' ({cg_info["conglomerate_name"]})' if cg_info.get('conglomerate_name') else ''
        ),
        'db_name': cg_info.get('db_name'),
        'available': cg_info.get('available', False),
    })

    return jsonify({'success': True, 'data': sources})


@api_bp.route('/sub-systems/<secure_code>/data-sources/<source_key>/tables')
@module_access_required('nocode_builder')
def list_source_tables(secure_code, source_key):
    """
    列出指定資料來源下的可用表

    source_key: 'org' 或 'conglomerate'
    """
    from ..models import DcSubSystem
    from ..services.schema_service import SchemaService
    from ..services.db_connector import get_data_conn, OrgDatabaseNotFound, CgDatabaseNotFound

    if source_key not in ('org', 'conglomerate'):
        return jsonify({'success': False, 'error': f'Unknown source: {source_key}'}), 400

    ss = ResourceGateway.get(
        DcSubSystem, secure_code,
        raise_on_not_found=False,
        check_permission=False
    )
    if not ss or ss.is_deleted:
        return jsonify({'success': False, 'error': 'Sub system not found'}), 404

    try:
        with get_data_conn(ss.org_secure_code, data_source=source_key) as conn:
            tables = SchemaService.list_tables(conn)
    except (OrgDatabaseNotFound, CgDatabaseNotFound) as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    return jsonify({'success': True, 'data': tables})


@api_bp.route('/sub-systems/<secure_code>/resolve-view', methods=['POST'])
@csrf.exempt
@module_access_required('nocode_builder')
def resolve_view(secure_code):
    """
    為指定的資料來源+表取得或自動建立 View

    Body: { "data_source": "org|conglomerate", "table_name": "xxx" }

    邏輯:
    1. 找同 org + table_name + data_source 的既有 active view -> 回傳
    2. 沒有 -> 自動建立 (讀表結構生成 columns_config) -> 回傳
    """
    from ..models import DcSubSystem, DcCrudView
    from ..services.schema_service import SchemaService
    from ..services.db_connector import get_data_conn, OrgDatabaseNotFound, CgDatabaseNotFound

    ss = ResourceGateway.get(
        DcSubSystem, secure_code,
        raise_on_not_found=False,
        check_permission=False
    )
    if not ss or ss.is_deleted:
        return jsonify({'success': False, 'error': 'Sub system not found'}), 404

    data = request.get_json() or {}
    data_source = data.get('data_source', 'org')
    table_name = data.get('table_name', '').strip()

    if data_source not in ('org', 'conglomerate'):
        return jsonify({'success': False, 'error': 'Invalid data_source'}), 400
    if not table_name:
        return jsonify({'success': False, 'error': 'table_name is required'}), 400

    org_sc = ss.org_secure_code

    # 1. 找既有 view
    existing = DcCrudView.query.filter_by(
        org_secure_code=org_sc,
        table_name=table_name,
        data_source=data_source,
        is_deleted=False,
    ).first()
    if existing:
        return jsonify({'success': True, 'data': existing.to_dict(), 'created': False})

    # 2. 讀表結構 -> 自動建
    try:
        with get_data_conn(org_sc, data_source=data_source) as conn:
            columns = SchemaService.get_columns(conn, table_name)
    except (OrgDatabaseNotFound, CgDatabaseNotFound) as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    if columns is None:
        return jsonify({'success': False, 'error': f'Table {table_name} not found'}), 404

    # 生成 columns_config
    columns_config = []
    has_is_deleted = False
    for i, c in enumerate(columns):
        is_sys = c.get('is_system', False)
        is_pk = c.get('is_pk', False)
        if c['column'] == 'is_deleted':
            has_is_deleted = True
        columns_config.append({
            'column': c['column'],
            'db_type': c['db_type'],
            'nullable': c.get('nullable', True),
            'is_pk': is_pk,
            'is_system': is_sys,
            'system_reason': c.get('system_reason'),
            'label': c.get('comment') or c['column'],
            'visible': not is_sys,
            'visible_in_form': not is_pk and not is_sys,
            'readonly': is_sys or is_pk,
            'sort_order': i + 1,
            'width': 150,
            'lookup_category_code': None,
        })

    view = ResourceGateway.create(
        DcCrudView,
        check_permission=False,
        name=table_name,
        table_name=table_name,
        description='',
        columns_config=columns_config,
        data_source=data_source,
        soft_delete_column='is_deleted' if has_is_deleted else None,
        allow_create=True,
        allow_edit=True,
        allow_delete=True,
        is_active=True,
    )
    ResourceGateway.commit()

    return jsonify({'success': True, 'data': view.to_dict(), 'created': True})


# =============================================================================
# 內部輔助函式
# =============================================================================

def _build_developer_name_cache(sub_systems):
    """批次查詢所有開發者的顯示名稱"""
    from app.models.user import User

    all_scs = set()
    for ss in sub_systems:
        for sc in (ss.developers or []):
            all_scs.add(sc)

    if not all_scs:
        return {}

    users = User.query.filter(
        User.secure_code.in_(all_scs),
        User.is_deleted == False,
    ).all()
    return {u.secure_code: u.display_name for u in users}


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
