"""
Data CRUD Module - API Routes
資料表工具 API

DB 路由策略:
  統一透過 view.org_secure_code 路由到企業專屬資料庫 (org_{org_id})
  SQL Sync 表都在企業 DB，與表單系統使用相同的連線路徑。
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

# 合法的識別符格式（表名/欄位名，支援 Unicode）
IDENTIFIER_RE = re.compile(r'^\w+$', re.UNICODE)

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

    # 自動補建 Registry（失敗不影響視圖建立）
    try:
        _auto_ensure_registry(
            org.secure_code, table_name, data.get('columns_config', [])
        )
    except Exception as e:
        logger.warning('Auto-ensure registry failed for table=%s: %s', table_name, e)

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

@api_bp.route('/views/<secure_code>/formio-schema')
def get_formio_schema(secure_code):
    """取得 form.io schema（若此表來自 SQL Sync）"""
    from ..models import DcCrudView

    view = ResourceGateway.get(
        DcCrudView, secure_code,
        raise_on_not_found=False,
        check_permission=False
    )
    if not view or view.is_deleted:
        return jsonify({'success': False, 'error': 'View not found'}), 404

    schema = _lookup_formio_schema(view.table_name, view.org_secure_code)
    return jsonify({'success': True, 'data': {'schema': schema}})


def _lookup_formio_schema(table_name, org_secure_code):
    """
    透過 SQL Sync registry 取得 form.io schema

    registry 建立時已從 published.form_snapshot.schema 快取到 form_schema 欄位，
    單次查詢即可取得，不需再跳到 published 表。
    """
    try:
        from modules.form_workflow.models.sql_form_registry import FwSqlFormRegistry

        registry = FwSqlFormRegistry.query.filter_by(
            table_name=table_name,
            org_secure_code=org_secure_code,
            status='active'
        ).first()
        if not registry:
            return None

        return registry.form_schema
    except Exception as e:
        logger.warning('formio schema lookup failed: %s', e)
        return None


_VARCHAR_LEN_RE = re.compile(
    r'(?:VARCHAR|CHARACTER VARYING)\((\d+)\)', re.IGNORECASE
)


def _db_type_to_formio_type(db_type):
    """
    將 DB 型別（SchemaService 格式）映射到 form.io 元件類型

    例: VARCHAR(500) → textfield, INTEGER → number, BOOLEAN → checkbox

    注意：DB 型別到 form.io 型別是不可逆的。
    VARCHAR(200) 可能原本是 email / phoneNumber / url / select 等，
    但從 DB 結構無法區分，統一回退為 textfield。
    """
    if not db_type:
        return 'textfield'

    upper = db_type.upper().strip()

    if upper.startswith('VARCHAR') or upper.startswith('CHARACTER VARYING'):
        return 'textfield'
    if upper == 'TEXT':
        return 'textarea'
    if upper in ('INTEGER', 'BIGINT', 'SMALLINT', 'INT', 'SERIAL', 'BIGSERIAL'):
        return 'number'
    if upper.startswith('NUMERIC') or upper.startswith('DECIMAL'):
        return 'number'
    if upper in ('REAL', 'DOUBLE PRECISION'):
        return 'number'
    if upper == 'BOOLEAN':
        return 'checkbox'
    if upper == 'DATE':
        return 'day'
    if upper.startswith('TIMESTAMP'):
        return 'datetime'
    if upper in ('JSONB', 'JSON'):
        return 'textarea'

    return 'textfield'


def _build_constraints(col):
    """
    從 columns_config 的單筆欄位推導 form.io 驗證約束

    可推導的規則：
    - nullable=false 且非 PK → required
    - VARCHAR(n) → maxLength
    """
    constraints = {}
    db_type = col.get('db_type', '')

    # required: 非 nullable 且非主鍵
    if not col.get('nullable', True) and not col.get('is_pk', False):
        constraints['required'] = True

    # maxLength: 從 VARCHAR(n) / CHARACTER VARYING(n) 提取
    m = _VARCHAR_LEN_RE.search(db_type)
    if m:
        constraints['maxLength'] = int(m.group(1))

    return constraints if constraints else None


def _try_find_published_schema(org_secure_code, table_name):
    """
    嘗試從已發行的表單找回原始 form.io schema

    SQL Sync 建立的表（如 form_59_v1）在 registry 中會有 published_secure_code，
    指向 FwPublishedFormWorkflow 的 form_snapshot.schema。
    若 registry 已被刪除但 published form 仍存在，可以透過比對找回。

    Returns:
        dict or None: 原始 form.io schema，找不到則 None
    """
    try:
        from modules.form_workflow.models.published_form_workflow import (
            FwPublishedFormWorkflow,
        )

        # 查找所有同企業的 published forms，比對 form_snapshot 中是否有匹配資訊
        pubs = FwPublishedFormWorkflow.query.filter_by(
            org_secure_code=org_secure_code
        ).all()

        for pub in pubs:
            fs = pub.form_snapshot or {}
            # SQL Sync registry 的 table_name 記錄在 form_snapshot 的 metadata 中
            # 或透過 registry 的 published_secure_code 反查
            # 這裡直接從已有 registry 反查: 找有 pub_sc 的 registry 指向此 published
            from modules.form_workflow.models.sql_form_registry import (
                FwSqlFormRegistry,
            )
            linked_reg = FwSqlFormRegistry.query.filter_by(
                published_secure_code=pub.secure_code,
                org_secure_code=org_secure_code,
            ).first()
            # 如果有其他 registry 指向這個 pub，且表名相同，就用它的 schema
            if linked_reg and linked_reg.table_name == table_name:
                schema = fs.get('schema', fs)
                if schema and schema.get('components'):
                    return schema

        return None
    except Exception:
        return None


def _auto_ensure_registry(org_secure_code, table_name, columns_config):
    """
    視圖建立時自動補建 FwSqlFormRegistry

    策略（依優先順序）：
    1. 已有 Registry → 不覆蓋
    2. 嘗試從已發行表單找回原始 form.io schema → 還原完整型別與驗證
    3. 從 DB 結構反推 → 基本型別 + DB 約束驗證（required / maxLength）
    """
    from app import db
    from modules.form_workflow.models.sql_form_registry import FwSqlFormRegistry
    from modules.form_workflow.services.field_spec.spec_generator import (
        spec_to_formio_schema,
    )
    from modules.form_workflow.services.field_spec.spec_sql_table import (
        spec_fields_to_columns,
    )
    from modules.form_workflow.services.sql_sync.converter import build_column_mapping

    # 已存在 → 不覆蓋
    existing = FwSqlFormRegistry.query.filter_by(
        org_secure_code=org_secure_code,
        table_name=table_name,
        status='active'
    ).first()
    if existing:
        return

    # 過濾：排除系統欄位和 BYTEA（PII 加密欄位）
    user_columns = [
        c for c in (columns_config or [])
        if not c.get('is_system') and c.get('db_type', '').upper() != 'BYTEA'
    ]
    if not user_columns:
        return

    # 策略 1: 嘗試從 published form 找回原始 schema
    published_schema = _try_find_published_schema(org_secure_code, table_name)
    if published_schema:
        form_schema = published_schema
        logger.info(
            'Auto-registry: recovered published schema for table=%s', table_name
        )
    else:
        # 策略 2: 從 DB 結構反推 spec fields → form.io schema
        spec_fields = []
        for col in user_columns:
            field = {
                'field_key': col.get('column', ''),
                'label': col.get('label') or col.get('column', ''),
                'formio_type': _db_type_to_formio_type(col.get('db_type')),
                'pg_type': col.get('db_type', 'TEXT'),
                'is_pii': False,
            }
            constraints = _build_constraints(col)
            if constraints:
                field['constraints'] = constraints
            spec_fields.append(field)

        form_schema = spec_to_formio_schema(spec_fields)

    # 生成 column_mapping（始終從 columns_config 建，不依賴 form_schema）
    spec_for_mapping = []
    for col in user_columns:
        spec_for_mapping.append({
            'field_key': col.get('column', ''),
            'pg_type': col.get('db_type', 'TEXT'),
            'is_pii': False,
        })
    columns = spec_fields_to_columns(spec_for_mapping)
    column_mapping = build_column_mapping(columns)

    # 建立 Registry（來源追蹤欄位全部 NULL 標記為自動生成）
    registry = FwSqlFormRegistry(
        org_secure_code=org_secure_code,
        table_name=table_name,
        form_schema=form_schema,
        column_mapping=column_mapping,
        status='active',
        mapping_secure_code=None,
        published_secure_code=None,
        form_template_secure_code=None,
        spec_secure_code=None,
    )
    db.session.add(registry)
    db.session.commit()

    logger.info(
        'Auto-created registry for table=%s org=%s (%d user fields)',
        table_name, org_secure_code, len(user_columns)
    )


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
        with get_data_conn(view.org_secure_code) as conn:
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


@api_bp.route('/views/<secure_code>/rows/<row_id>')
def get_row(secure_code, row_id):
    """取得單筆資料"""
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

    try:
        with get_data_conn(view.org_secure_code) as conn:
            result = CrudService.get_row(conn=conn, view=view, row_id=row_id)
    except OrgDatabaseNotFound as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    if not result['success']:
        return jsonify(result), 404
    return jsonify(result)


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
        with get_data_conn(view.org_secure_code) as conn:
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
        with get_data_conn(view.org_secure_code) as conn:
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
        with get_data_conn(view.org_secure_code) as conn:
            result = CrudService.delete_row(conn=conn, view=view, row_id=row_id)
    except OrgDatabaseNotFound as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    if not result['success']:
        return jsonify(result), 400
    return jsonify(result)
