"""
Data CRUD Module - API Routes
資料表工具 API

DB 路由策略:
  系統管理員 → 主資料庫 (beakplatform_dev)
  企業用戶   → 企業專屬資料庫 (org_{org_id})
"""
import re
import logging

from flask import Blueprint, jsonify, request
from flask_login import current_user

from app import csrf
from app.security.decorators import public_route
from app.security.resource_gateway import ResourceGateway
from app.platform.data import get_current_org

logger = logging.getLogger(__name__)

# 合法的識別符格式（表名/欄位名）
IDENTIFIER_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

api_bp = Blueprint(
    'data_crud_api',
    __name__,
    url_prefix='/api/data-crud'
)


# =============================================================================
# 模組資訊
# =============================================================================

@api_bp.route('/info')
@public_route
def module_info():
    """取得模組資訊"""
    from .. import MODULE_INFO
    return jsonify({
        'success': True,
        'data': {
            'name': MODULE_INFO['name'],
            'display_name': MODULE_INFO['display_name'],
            'version': MODULE_INFO['version'],
        }
    })


@api_bp.route('/db-info')
def db_info():
    """取得當前連線的資料庫資訊"""
    from ..services.db_connector import get_db_display_name
    return jsonify({
        'success': True,
        'data': {
            'db_name': get_db_display_name(),
            'is_system_admin': current_user.is_system_admin,
        }
    })


# =============================================================================
# Schema API -- 讀取資料庫表結構
# =============================================================================

@api_bp.route('/schema/tables')
def list_tables():
    """列出可用資料表"""
    from ..services.schema_service import SchemaService
    from ..services.db_connector import get_data_conn, OrgDatabaseNotFound

    try:
        with get_data_conn() as conn:
            tables = SchemaService.list_tables(conn)
    except OrgDatabaseNotFound as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    return jsonify({'success': True, 'data': tables})


@api_bp.route('/schema/tables/<table_name>/columns')
def get_table_columns(table_name):
    """取得指定表的欄位"""
    from ..services.schema_service import SchemaService
    from ..services.db_connector import get_data_conn, OrgDatabaseNotFound

    if not IDENTIFIER_RE.match(table_name):
        return jsonify({'success': False, 'error': 'Invalid table name'}), 400

    try:
        with get_data_conn() as conn:
            columns = SchemaService.get_columns(conn, table_name)
    except OrgDatabaseNotFound as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    if columns is None:
        return jsonify({'success': False, 'error': 'Table not found'}), 404

    return jsonify({'success': True, 'data': columns})


# =============================================================================
# 視圖配置 CRUD API (存在主資料庫，與目標 DB 無關)
# =============================================================================

@api_bp.route('/views')
def list_views():
    """列出視圖"""
    from ..models import DcCrudView

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    result = ResourceGateway.filter(
        DcCrudView,
        is_deleted=False,
        order_by='-updated_at'
    )

    return jsonify({
        'success': True,
        'data': [v.to_dict() for v in result]
    })


@api_bp.route('/views', methods=['POST'])
@csrf.exempt
def create_view():
    """建立視圖"""
    from ..models import DcCrudView

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}
    name = data.get('name', '').strip()
    table_name = data.get('table_name', '').strip()

    if not name:
        return jsonify({'success': False, 'error': 'Name is required'}), 400
    if not table_name:
        return jsonify({'success': False, 'error': 'Table name is required'}), 400
    if not IDENTIFIER_RE.match(table_name):
        return jsonify({'success': False, 'error': 'Invalid table name'}), 400

    view = ResourceGateway.create(
        DcCrudView,
        check_permission=False,
        name=name,
        table_name=table_name,
        description=data.get('description', ''),
        columns_config=data.get('columns_config', []),
        allow_create=data.get('allow_create', True),
        allow_edit=data.get('allow_edit', True),
        allow_delete=data.get('allow_delete', True),
        soft_delete_column=data.get('soft_delete_column'),
        default_sort_column=data.get('default_sort_column'),
        default_sort_dir=data.get('default_sort_dir', 'ASC'),
        page_size=data.get('page_size', 20),
        fixed_filters=data.get('fixed_filters', {}),
        is_active=data.get('is_active', True),
    )
    ResourceGateway.commit()

    return jsonify({
        'success': True,
        'data': view.to_dict(),
        'message': 'View created'
    })


@api_bp.route('/views/<secure_code>')
def get_view(secure_code):
    """取得視圖配置"""
    from ..models import DcCrudView

    view = ResourceGateway.get(
        DcCrudView, secure_code,
        raise_on_not_found=False,
        check_permission=False
    )
    if not view or view.is_deleted:
        return jsonify({'success': False, 'error': 'View not found'}), 404

    return jsonify({'success': True, 'data': view.to_dict()})


@api_bp.route('/views/<secure_code>', methods=['PUT'])
@csrf.exempt
def update_view(secure_code):
    """更新視圖配置"""
    from ..models import DcCrudView

    view = ResourceGateway.get(
        DcCrudView, secure_code,
        raise_on_not_found=False,
        check_permission=False
    )
    if not view or view.is_deleted:
        return jsonify({'success': False, 'error': 'View not found'}), 404

    data = request.get_json() or {}

    update_fields = {}
    allowed_fields = [
        'name', 'description', 'columns_config',
        'allow_create', 'allow_edit', 'allow_delete',
        'soft_delete_column', 'default_sort_column', 'default_sort_dir',
        'page_size', 'fixed_filters', 'is_active',
    ]
    for field in allowed_fields:
        if field in data:
            update_fields[field] = data[field]

    if 'name' in update_fields and not update_fields['name'].strip():
        return jsonify({'success': False, 'error': 'Name cannot be empty'}), 400

    ResourceGateway.update(view, check_permission=False, **update_fields)
    ResourceGateway.commit()

    return jsonify({
        'success': True,
        'data': view.to_dict(),
        'message': 'View updated'
    })


@api_bp.route('/views/<secure_code>', methods=['DELETE'])
@csrf.exempt
def delete_view(secure_code):
    """刪除視圖"""
    from ..models import DcCrudView

    view = ResourceGateway.get(
        DcCrudView, secure_code,
        raise_on_not_found=False,
        check_permission=False
    )
    if not view or view.is_deleted:
        return jsonify({'success': False, 'error': 'View not found'}), 404

    ResourceGateway.delete(view, check_permission=False, soft=True)
    ResourceGateway.commit()

    return jsonify({'success': True, 'message': 'View deleted'})


# =============================================================================
# 動態資料 API -- 操作目標表的資料 (使用 db_connector 路由到正確 DB)
# =============================================================================

@api_bp.route('/views/<secure_code>/rows')
def query_rows(secure_code):
    """查詢視圖資料（分頁）"""
    from ..models import DcCrudView
    from ..services.crud_service import CrudService
    from ..services.db_connector import get_data_conn, OrgDatabaseNotFound

    view = ResourceGateway.get(
        DcCrudView, secure_code,
        raise_on_not_found=False,
        check_permission=False
    )
    if not view or view.is_deleted:
        return jsonify({'success': False, 'error': 'View not found'}), 404

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', view.page_size, type=int)
    search = request.args.get('q', '').strip()
    sort_col = request.args.get('sort', view.default_sort_column)
    sort_dir = request.args.get('dir', view.default_sort_dir or 'ASC')

    per_page = max(1, min(per_page, 100))

    try:
        with get_data_conn() as conn:
            result = CrudService.query_rows(
                conn=conn,
                view=view,
                page=page,
                per_page=per_page,
                search=search,
                sort_column=sort_col,
                sort_dir=sort_dir,
            )
    except OrgDatabaseNotFound as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    return jsonify({'success': True, 'data': result})


@api_bp.route('/views/<secure_code>/rows', methods=['POST'])
@csrf.exempt
def create_row(secure_code):
    """新增一筆資料"""
    from ..models import DcCrudView
    from ..services.crud_service import CrudService
    from ..services.db_connector import get_data_conn, OrgDatabaseNotFound

    view = ResourceGateway.get(
        DcCrudView, secure_code,
        raise_on_not_found=False,
        check_permission=False
    )
    if not view or view.is_deleted:
        return jsonify({'success': False, 'error': 'View not found'}), 404

    if not view.allow_create:
        return jsonify({'success': False, 'error': 'Create not allowed'}), 403

    data = request.get_json() or {}
    try:
        with get_data_conn() as conn:
            result = CrudService.create_row(conn=conn, view=view, row_data=data)
    except OrgDatabaseNotFound as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    if not result['success']:
        return jsonify(result), 400
    return jsonify(result)


@api_bp.route('/views/<secure_code>/rows/<row_id>', methods=['PUT'])
@csrf.exempt
def update_row(secure_code, row_id):
    """更新一筆資料"""
    from ..models import DcCrudView
    from ..services.crud_service import CrudService
    from ..services.db_connector import get_data_conn, OrgDatabaseNotFound

    view = ResourceGateway.get(
        DcCrudView, secure_code,
        raise_on_not_found=False,
        check_permission=False
    )
    if not view or view.is_deleted:
        return jsonify({'success': False, 'error': 'View not found'}), 404

    if not view.allow_edit:
        return jsonify({'success': False, 'error': 'Edit not allowed'}), 403

    data = request.get_json() or {}
    try:
        with get_data_conn() as conn:
            result = CrudService.update_row(conn=conn, view=view, row_id=row_id, row_data=data)
    except OrgDatabaseNotFound as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    if not result['success']:
        return jsonify(result), 400
    return jsonify(result)


@api_bp.route('/views/<secure_code>/rows/<row_id>', methods=['DELETE'])
@csrf.exempt
def delete_row(secure_code, row_id):
    """刪除一筆資料"""
    from ..models import DcCrudView
    from ..services.crud_service import CrudService
    from ..services.db_connector import get_data_conn, OrgDatabaseNotFound

    view = ResourceGateway.get(
        DcCrudView, secure_code,
        raise_on_not_found=False,
        check_permission=False
    )
    if not view or view.is_deleted:
        return jsonify({'success': False, 'error': 'View not found'}), 404

    if not view.allow_delete:
        return jsonify({'success': False, 'error': 'Delete not allowed'}), 403

    try:
        with get_data_conn() as conn:
            result = CrudService.delete_row(conn=conn, view=view, row_id=row_id)
    except OrgDatabaseNotFound as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    if not result['success']:
        return jsonify(result), 400
    return jsonify(result)
