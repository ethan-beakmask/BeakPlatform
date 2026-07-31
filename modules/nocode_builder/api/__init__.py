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
from flask_babel import gettext as _
from flask_login import current_user

from app import csrf, db
from app.pageir import validate_page_ir
from app.security.decorators import public_route, module_access_required, admin_required
from app.security.resource_gateway import ResourceGateway
from app.platform.data import get_current_org

from ..services.page_ownership_service import is_page_reachable

logger = logging.getLogger(__name__)

# 合法的識別符格式（表名/欄位名，支援 Unicode）
IDENTIFIER_RE = re.compile(r'^\w+$', re.UNICODE)

api_bp = Blueprint(
    'nocode_builder_api',
    __name__,
    url_prefix='/api/nocode-builder'
)

# 額外 Blueprint（由 module_loader additional_blueprints 機制註冊）
from ..web.portal_public import public_portal_bp
additional_blueprints = [public_portal_bp]


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
@module_access_required('nocode_builder')
def db_info():
    """取得當前連線的資料庫資訊（支援 ?source=org|conglomerate）"""
    from ..services.db_connector import get_db_display_name, check_cg_available
    source = request.args.get('source', 'org')
    return jsonify({
        'success': True,
        'data': {
            'db_name': get_db_display_name(data_source=source),
            'is_system_admin': current_user.is_system_admin,
            'cg_info': check_cg_available(),
        }
    })


# =============================================================================
# Schema API -- 讀取資料庫表結構
# =============================================================================

@api_bp.route('/schema/tables')
@module_access_required('nocode_builder')
def list_tables():
    """列出可用資料表（支援 ?source=org|conglomerate）"""
    from ..services.schema_service import SchemaService
    from ..services.db_connector import get_data_conn, OrgDatabaseNotFound, CgDatabaseNotFound

    source = request.args.get('source', 'org')

    try:
        with get_data_conn(data_source=source) as conn:
            tables = SchemaService.list_tables(conn)
    except (OrgDatabaseNotFound, CgDatabaseNotFound) as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    return jsonify({'success': True, 'data': tables})


@api_bp.route('/schema/tables/<table_name>/columns')
@module_access_required('nocode_builder')
def get_table_columns(table_name):
    """取得指定表的欄位（支援 ?source=org|conglomerate）"""
    from ..services.schema_service import SchemaService
    from ..services.db_connector import get_data_conn, OrgDatabaseNotFound, CgDatabaseNotFound

    if not IDENTIFIER_RE.match(table_name):
        return jsonify({'success': False, 'error': 'Invalid table name'}), 400

    source = request.args.get('source', 'org')

    try:
        with get_data_conn(data_source=source) as conn:
            columns = SchemaService.get_columns(conn, table_name)
    except (OrgDatabaseNotFound, CgDatabaseNotFound) as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    if columns is None:
        return jsonify({'success': False, 'error': 'Table not found'}), 404

    return jsonify({'success': True, 'data': columns})


# =============================================================================
# 視圖配置 CRUD API (存在主資料庫，與目標 DB 無關)
# =============================================================================

@api_bp.route('/views')
@module_access_required('nocode_builder')
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
@admin_required
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

    data_source = data.get('data_source', 'org')
    if data_source not in ('org', 'conglomerate'):
        return jsonify({'success': False, 'error': 'Invalid data_source'}), 400

    row_owner_scope = data.get('row_owner_scope', 'own')
    if row_owner_scope not in {'own', 'all'}:
        return jsonify({'success': False, 'error': 'invalid_row_owner_scope'}), 400

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
        data_source=data_source,
        row_owner_scope=row_owner_scope,
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
@module_access_required('nocode_builder')
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
@admin_required
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
        'page_size', 'fixed_filters', 'is_active', 'data_source', 'row_owner_scope',
    ]
    for field in allowed_fields:
        if field in data:
            update_fields[field] = data[field]

    if 'name' in update_fields and not update_fields['name'].strip():
        return jsonify({'success': False, 'error': 'Name cannot be empty'}), 400
    if 'row_owner_scope' in update_fields and update_fields['row_owner_scope'] not in {'own', 'all'}:
        return jsonify({'success': False, 'error': 'invalid_row_owner_scope'}), 400

    ResourceGateway.update(view, check_permission=False, **update_fields)
    ResourceGateway.commit()

    return jsonify({
        'success': True,
        'data': view.to_dict(),
        'message': 'View updated'
    })


@api_bp.route('/views/<secure_code>', methods=['DELETE'])
@csrf.exempt
@admin_required
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
@module_access_required('nocode_builder', False)
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


def _spec_to_formio_schema(spec_fields):
    """將 spec fields 轉為 FormIO schema（內聯版）"""
    components = []
    for f in (spec_fields or []):
        ftype = f.get('formio_type', 'textfield')
        key = f.get('field_key', '')
        label = f.get('label', key)
        constraints = f.get('constraints') or {}
        comp = {
            'type': ftype,
            'key': key,
            'label': label,
            'input': True,
            'tableView': True,
        }
        if f.get('is_pii'):
            comp['properties'] = {'pii': 'true'}
        validate = {}
        if constraints.get('required'):
            validate['required'] = True
        if constraints.get('maxLength') is not None:
            validate['maxLength'] = constraints['maxLength']
        if validate:
            comp['validate'] = validate
        components.append(comp)
    return {'components': components}


def _spec_fields_to_columns(spec_fields):
    """將 spec fields 轉為 (field_key, pg_type, nullable, is_pii) tuples（內聯版）"""
    columns = []
    for sf in (spec_fields or []):
        key = sf.get('field_key')
        if not key:
            continue
        pg_type = sf.get('pg_type', 'TEXT')
        is_pii = bool(sf.get('is_pii', False))
        columns.append((key, pg_type, True, is_pii))
    return columns


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

        form_schema = _spec_to_formio_schema(spec_fields)

    # 生成 column_mapping（始終從 columns_config 建，不依賴 form_schema）
    spec_for_mapping = []
    for col in user_columns:
        spec_for_mapping.append({
            'field_key': col.get('column', ''),
            'pg_type': col.get('db_type', 'TEXT'),
            'is_pii': False,
        })
    columns = _spec_fields_to_columns(spec_for_mapping)
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
@module_access_required('nocode_builder', False)
def query_rows(secure_code):
    """查詢視圖資料（分頁）"""
    from ..models import DcCrudView
    from ..services.crud_service import CrudService, FilterVariableNotSupported
    from ..services.db_connector import (
        get_data_conn, get_sqlite_session, is_sqlite_source,
        OrgDatabaseNotFound, CgDatabaseNotFound, PortalDatabaseNotFound,
    )

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

    # 動態篩選：接受 filter_<column>=<value> 參數
    # 安全：只允許 view.columns_config 中存在的欄位名
    dynamic_filters = {}
    allowed_columns = {
        c.get('column') for c in (view.columns_config or []) if c.get('column')
    }
    for key in request.args:
        if key.startswith('filter_'):
            col_name = key[7:]  # 去掉 'filter_' 前綴
            if col_name in allowed_columns and IDENTIFIER_RE.match(col_name):
                dynamic_filters[col_name] = request.args.get(key)

    try:
        if is_sqlite_source(view.data_source):
            # SQLite 路徑
            from ..services.sqlite_crud_service import OWNER_REF_PLATFORM, SqliteCrudService
            ss_sc = request.args.get('sub_system_sc', '') or _resolve_sub_system_sc(view)
            with get_sqlite_session(ss_sc, view.data_source) as session:
                # 平台管理視角，刻意不做列級過濾（列級只在 portal 語境生效）。
                result = SqliteCrudService.query_rows(
                    session=session,
                    view=view,
                    page=page,
                    per_page=per_page,
                    search=search,
                    sort_column=sort_col,
                    sort_dir=sort_dir,
                    dynamic_filters=dynamic_filters,
                    owner_ref=OWNER_REF_PLATFORM,
                )
        else:
            # PostgreSQL 路徑
            with get_data_conn(view.org_secure_code, view.data_source) as conn:
                result = CrudService.query_rows(
                    conn=conn,
                    view=view,
                    page=page,
                    per_page=per_page,
                    search=search,
                    sort_column=sort_col,
                    sort_dir=sort_dir,
                    dynamic_filters=dynamic_filters,
                )
    except FilterVariableNotSupported:
        return jsonify({'success': False, 'error': 'filter_variable_not_supported'}), 400
    except (OrgDatabaseNotFound, CgDatabaseNotFound, PortalDatabaseNotFound) as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    return jsonify({'success': True, 'data': result})


@api_bp.route('/views/<secure_code>/rows/<row_id>')
@module_access_required('nocode_builder', False)
def get_row(secure_code, row_id):
    """取得單筆資料"""
    from ..models import DcCrudView
    from ..services.crud_service import CrudService, FilterVariableNotSupported
    from ..services.db_connector import (
        get_data_conn, get_sqlite_session, is_sqlite_source,
        OrgDatabaseNotFound, CgDatabaseNotFound, PortalDatabaseNotFound,
    )

    view = ResourceGateway.get(
        DcCrudView, secure_code,
        raise_on_not_found=False,
        check_permission=False
    )
    if not view or view.is_deleted:
        return jsonify({'success': False, 'error': 'View not found'}), 404

    try:
        if is_sqlite_source(view.data_source):
            from ..services.sqlite_crud_service import OWNER_REF_PLATFORM, SqliteCrudService
            ss_sc = request.args.get('sub_system_sc', '') or _resolve_sub_system_sc(view)
            with get_sqlite_session(ss_sc, view.data_source) as session:
                # 平台管理視角，刻意不做列級過濾（列級只在 portal 語境生效）。
                result = SqliteCrudService.get_row(
                    session=session,
                    view=view,
                    row_id=row_id,
                    owner_ref=OWNER_REF_PLATFORM,
                )
        else:
            with get_data_conn(view.org_secure_code, view.data_source) as conn:
                result = CrudService.get_row(conn=conn, view=view, row_id=row_id)
    except FilterVariableNotSupported:
        return jsonify({'success': False, 'error': 'filter_variable_not_supported'}), 400
    except (OrgDatabaseNotFound, CgDatabaseNotFound, PortalDatabaseNotFound) as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    if not result['success']:
        return jsonify(result), 404
    return jsonify(result)


def _check_formgrid_lock(request_obj):
    """
    FORMGRID 鎖定檢查。
    前端透過 X-Lock-Check-View + X-Lock-Check-RowId 傳入 Master 的 view code 和 row id，
    後端查詢 Master 記錄的 is_locked 欄位。若鎖定則回傳 403 回應。

    Returns:
        Flask response (403) if locked, None if OK or not applicable.
    """
    lock_view_code = request_obj.headers.get('X-Lock-Check-View', '').strip()
    lock_row_id = request_obj.headers.get('X-Lock-Check-RowId', '').strip()

    if not lock_view_code or not lock_row_id:
        return None  # 非 FORMGRID 操作或不需檢查

    from ..models import DcCrudView
    from ..services.db_connector import get_data_conn

    master_view = ResourceGateway.get(
        DcCrudView, lock_view_code,
        raise_on_not_found=False,
        check_permission=False
    )
    if not master_view:
        return None  # Master view 不存在，略過

    try:
        from psycopg2 import sql as psql
        from ..services.crud_service import _find_row_id_column

        row_id_col = _find_row_id_column(master_view)
        if not row_id_col:
            return None

        with get_data_conn(master_view.org_secure_code, master_view.data_source) as conn:
            with conn.cursor() as cur:
                query = psql.SQL('SELECT {} FROM {} WHERE {} = %s').format(
                    psql.Identifier('is_locked'),
                    psql.Identifier(master_view.table_name),
                    psql.Identifier(row_id_col),
                )
                cur.execute(query, (lock_row_id,))
                row = cur.fetchone()
                conn.rollback()  # read-only

                if row and row[0]:
                    return jsonify({
                        'success': False,
                        'error': _('此 Master 記錄已鎖定，無法修改關聯資料')
                    }), 403
    except Exception as e:
        logger.warning('FORMGRID lock check failed: %s', e)
        # 檢查失敗不阻擋操作（寬容策略）

    return None


@api_bp.route('/views/<secure_code>/rows', methods=['POST'])
@csrf.exempt
@module_access_required('nocode_builder', False)
def create_row(secure_code):
    """新增一筆資料"""
    from ..models import DcCrudView
    from ..services.crud_service import CrudService, FilterVariableNotSupported
    from ..services.db_connector import (
        get_data_conn, get_sqlite_session, is_sqlite_source,
        OrgDatabaseNotFound, CgDatabaseNotFound, PortalDatabaseNotFound,
    )

    view = ResourceGateway.get(
        DcCrudView, secure_code,
        raise_on_not_found=False,
        check_permission=False
    )
    if not view or view.is_deleted:
        return jsonify({'success': False, 'error': 'View not found'}), 404

    # 子系統 context 權限檢查
    denied = _check_sub_system_crud(request, 'create')
    if denied:
        return denied

    if not view.allow_create:
        return jsonify({'success': False, 'error': 'Create not allowed'}), 403

    # FORMGRID 鎖定檢查
    lock_denied = _check_formgrid_lock(request)
    if lock_denied:
        return lock_denied

    data = request.get_json() or {}
    try:
        if is_sqlite_source(view.data_source):
            from ..services.sqlite_crud_service import OWNER_REF_PLATFORM, SqliteCrudService
            ss_sc = request.args.get('sub_system_sc', '') or _resolve_sub_system_sc(view)
            with get_sqlite_session(ss_sc, view.data_source) as session:
                # 平台管理視角，刻意不做列級過濾（列級只在 portal 語境生效）。
                result = SqliteCrudService.create_row(
                    session=session,
                    view=view,
                    row_data=data,
                    owner_ref=OWNER_REF_PLATFORM,
                )
        else:
            with get_data_conn(view.org_secure_code, view.data_source) as conn:
                result = CrudService.create_row(
                    conn=conn, view=view, row_data=data,
                    is_conglomerate=(view.data_source == 'conglomerate'),
                )
    except FilterVariableNotSupported:
        return jsonify({'success': False, 'error': 'filter_variable_not_supported'}), 400
    except (OrgDatabaseNotFound, CgDatabaseNotFound, PortalDatabaseNotFound) as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    if not result['success']:
        return jsonify(result), 400
    return jsonify(result)


@api_bp.route('/views/<secure_code>/rows/<row_id>', methods=['PUT'])
@csrf.exempt
@module_access_required('nocode_builder', False)
def update_row(secure_code, row_id):
    """更新一筆資料"""
    from ..models import DcCrudView
    from ..services.crud_service import CrudService, FilterVariableNotSupported
    from ..services.db_connector import (
        get_data_conn, get_sqlite_session, is_sqlite_source,
        OrgDatabaseNotFound, CgDatabaseNotFound, PortalDatabaseNotFound,
    )

    view = ResourceGateway.get(
        DcCrudView, secure_code,
        raise_on_not_found=False,
        check_permission=False
    )
    if not view or view.is_deleted:
        return jsonify({'success': False, 'error': 'View not found'}), 404

    # 子系統 context 權限檢查
    denied = _check_sub_system_crud(request, 'edit')
    if denied:
        return denied

    if not view.allow_edit:
        return jsonify({'success': False, 'error': 'Edit not allowed'}), 403

    # FORMGRID 鎖定檢查
    lock_denied = _check_formgrid_lock(request)
    if lock_denied:
        return lock_denied

    data = request.get_json() or {}
    try:
        if is_sqlite_source(view.data_source):
            from ..services.sqlite_crud_service import OWNER_REF_PLATFORM, SqliteCrudService
            ss_sc = request.args.get('sub_system_sc', '') or _resolve_sub_system_sc(view)
            with get_sqlite_session(ss_sc, view.data_source) as session:
                # 平台管理視角，刻意不做列級過濾（列級只在 portal 語境生效）。
                result = SqliteCrudService.update_row(
                    session=session,
                    view=view,
                    row_id=row_id,
                    row_data=data,
                    owner_ref=OWNER_REF_PLATFORM,
                )
        else:
            with get_data_conn(view.org_secure_code, view.data_source) as conn:
                result = CrudService.update_row(
                    conn=conn, view=view, row_id=row_id, row_data=data,
                    is_conglomerate=(view.data_source == 'conglomerate'),
                )
    except FilterVariableNotSupported:
        return jsonify({'success': False, 'error': 'filter_variable_not_supported'}), 400
    except (OrgDatabaseNotFound, CgDatabaseNotFound, PortalDatabaseNotFound) as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    if not result['success']:
        return jsonify(result), 400
    return jsonify(result)


@api_bp.route('/views/<secure_code>/rows/<row_id>', methods=['DELETE'])
@csrf.exempt
@module_access_required('nocode_builder', False)
def delete_row(secure_code, row_id):
    """刪除一筆資料"""
    from ..models import DcCrudView
    from ..services.crud_service import CrudService, FilterVariableNotSupported
    from ..services.db_connector import (
        get_data_conn, get_sqlite_session, is_sqlite_source,
        OrgDatabaseNotFound, CgDatabaseNotFound, PortalDatabaseNotFound,
    )

    view = ResourceGateway.get(
        DcCrudView, secure_code,
        raise_on_not_found=False,
        check_permission=False
    )
    if not view or view.is_deleted:
        return jsonify({'success': False, 'error': 'View not found'}), 404

    # 子系統 context 權限檢查
    denied = _check_sub_system_crud(request, 'delete')
    if denied:
        return denied

    if not view.allow_delete:
        return jsonify({'success': False, 'error': 'Delete not allowed'}), 403

    # FORMGRID 鎖定檢查
    lock_denied = _check_formgrid_lock(request)
    if lock_denied:
        return lock_denied

    try:
        if is_sqlite_source(view.data_source):
            from ..services.sqlite_crud_service import OWNER_REF_PLATFORM, SqliteCrudService
            ss_sc = request.args.get('sub_system_sc', '') or _resolve_sub_system_sc(view)
            with get_sqlite_session(ss_sc, view.data_source) as session:
                # 平台管理視角，刻意不做列級過濾（列級只在 portal 語境生效）。
                result = SqliteCrudService.delete_row(
                    session=session,
                    view=view,
                    row_id=row_id,
                    owner_ref=OWNER_REF_PLATFORM,
                )
        else:
            with get_data_conn(view.org_secure_code, view.data_source) as conn:
                result = CrudService.delete_row(
                    conn=conn, view=view, row_id=row_id,
                    is_conglomerate=(view.data_source == 'conglomerate'),
                )
    except FilterVariableNotSupported:
        return jsonify({'success': False, 'error': 'filter_variable_not_supported'}), 400
    except (OrgDatabaseNotFound, CgDatabaseNotFound, PortalDatabaseNotFound) as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    if not result['success']:
        return jsonify(result), 400
    return jsonify(result)


# =============================================================================
# Page Layout CRUD API (Web Builder 佈局持久化)
# =============================================================================

@api_bp.route('/pages')
@module_access_required('nocode_builder')
def list_pages():
    """列出頁面佈局"""
    try:
        from ..models import DcPageLayout

        result = ResourceGateway.filter(
            DcPageLayout,
            is_deleted=False,
            order_by='-updated_at'
        )

        # 所屬子系統已刪的孤兒頁不列出（回應含完整 layout_json，
        # 不過濾等於繞過單頁端點的 fail-closed 判定）
        return jsonify({
            'success': True,
            'data': [
                p.to_dict() for p in result
                if is_page_reachable(p.secure_code)
            ]
        })
    except Exception as e:
        db.session.rollback()
        logger.exception('[PageLayout] list_pages error')
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/pages', methods=['POST'])
@csrf.exempt
@admin_required
def create_page():
    """建立頁面佈局"""
    try:
        from ..models import DcPageLayout

        data = request.get_json() or {}
        name = data.get('name', '').strip()
        if not name:
            return jsonify({'success': False, 'error': 'Name is required'}), 400

        layout_json = data.get('layout_json', {
            'ir_version': 3,
            'page': {
                'id': 'new-page',
                'title_i18n': {'zh-TW': name},
                'widgets': [],
            },
        })
        ok, errors = validate_page_ir(layout_json)
        if not ok:
            return jsonify({
                'success': False,
                'error': _('Page IR validation failed'),
                'errors': errors,
            }), 400

        create_kwargs = dict(
            name=name,
            description=data.get('description', ''),
            layout_json=layout_json,
            is_active=data.get('is_active', True),
        )
        if 'style_config' in data:
            create_kwargs['style_config'] = data['style_config']

        page = ResourceGateway.create(
            DcPageLayout,
            check_permission=False,
            **create_kwargs,
        )
        ResourceGateway.commit()

        return jsonify({
            'success': True,
            'data': page.to_dict(),
            'message': 'Page created'
        })
    except Exception as e:
        db.session.rollback()
        logger.exception('[PageLayout] create_page error')
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/pages/<secure_code>')
@module_access_required('nocode_builder')
def get_page(secure_code):
    """取得頁面佈局"""
    try:
        from ..models import DcPageLayout

        page = ResourceGateway.get(
            DcPageLayout, secure_code,
            raise_on_not_found=False,
            check_permission=False
        )
        if not page or page.is_deleted:
            return jsonify({'success': False, 'error': 'Page not found'}), 404

        if not is_page_reachable(secure_code):
            return jsonify({'success': False, 'error': 'Page not found'}), 404

        # 設計器要靠這個決定 portal 語境（元件准入 UI 的顯示條件）。
        # 純 form 頁沒有 portal: 前綴的 binding 可推導，只能從掛載關係取得。
        from ..models import DcSubSystemPage

        mount = DcSubSystemPage.query.filter_by(
            page_layout_secure_code=page.secure_code,
            org_secure_code=page.org_secure_code,
            is_deleted=False,
            is_active=True,
        ).order_by(DcSubSystemPage.display_order).first()

        data = page.to_dict()
        data['sub_system_secure_code'] = mount.sub_system_secure_code if mount else None
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        db.session.rollback()
        logger.exception('[PageLayout] get_page error')
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/pages/<secure_code>', methods=['PUT'])
@csrf.exempt
@admin_required
def update_page(secure_code):
    """更新頁面佈局"""
    try:
        from ..models import DcPageLayout

        page = ResourceGateway.get(
            DcPageLayout, secure_code,
            raise_on_not_found=False,
            check_permission=False
        )
        if not page or page.is_deleted:
            return jsonify({'success': False, 'error': 'Page not found'}), 404

        if not is_page_reachable(secure_code):
            return jsonify({'success': False, 'error': 'Page not found'}), 404

        data = request.get_json() or {}

        update_fields = {}
        for field in ('name', 'description', 'layout_json', 'style_config', 'is_active'):
            if field in data:
                update_fields[field] = data[field]

        if 'name' in update_fields and not update_fields['name'].strip():
            return jsonify({'success': False, 'error': 'Name cannot be empty'}), 400

        if 'layout_json' in update_fields:
            ok, errors = validate_page_ir(update_fields['layout_json'])
            if not ok:
                return jsonify({
                    'success': False,
                    'error': _('Page IR validation failed'),
                    'errors': errors,
                }), 400

        ResourceGateway.update(page, check_permission=False, **update_fields)
        ResourceGateway.commit()

        return jsonify({
            'success': True,
            'data': page.to_dict(),
            'message': 'Page updated'
        })
    except Exception as e:
        db.session.rollback()
        logger.exception('[PageLayout] update_page error')
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/pages/<secure_code>', methods=['DELETE'])
@csrf.exempt
@admin_required
def delete_page(secure_code):
    """刪除頁面佈局"""
    try:
        from ..models import DcPageLayout

        page = ResourceGateway.get(
            DcPageLayout, secure_code,
            raise_on_not_found=False,
            check_permission=False
        )
        if not page or page.is_deleted:
            return jsonify({'success': False, 'error': 'Page not found'}), 404

        ResourceGateway.delete(page, check_permission=False, soft=True)
        ResourceGateway.commit()

        return jsonify({'success': True, 'message': 'Page deleted'})
    except Exception as e:
        db.session.rollback()
        logger.exception('[PageLayout] delete_page error')
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# Page Layout Publish / Unpublish
# =============================================================================

@api_bp.route('/pages/<secure_code>/publish', methods=['PATCH'])
@csrf.exempt
@admin_required
def publish_page(secure_code):
    """發布頁面 (status -> published)"""
    try:
        from ..models import DcPageLayout

        page = ResourceGateway.get(
            DcPageLayout, secure_code,
            raise_on_not_found=False,
            check_permission=False
        )
        if not page or page.is_deleted:
            return jsonify({'success': False, 'error': 'Page not found'}), 404

        if not is_page_reachable(secure_code):
            return jsonify({'success': False, 'error': 'Page not found'}), 404

        ResourceGateway.update(page, check_permission=False, status='published')
        ResourceGateway.commit()

        return jsonify({
            'success': True,
            'data': page.to_dict(),
            'message': _('頁面已發布')
        })
    except Exception as e:
        db.session.rollback()
        logger.exception('[PageLayout] publish_page error')
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/pages/<secure_code>/unpublish', methods=['PATCH'])
@csrf.exempt
@admin_required
def unpublish_page(secure_code):
    """取消發布 (status -> draft)"""
    try:
        from ..models import DcPageLayout

        page = ResourceGateway.get(
            DcPageLayout, secure_code,
            raise_on_not_found=False,
            check_permission=False
        )
        if not page or page.is_deleted:
            return jsonify({'success': False, 'error': 'Page not found'}), 404

        if not is_page_reachable(secure_code):
            return jsonify({'success': False, 'error': 'Page not found'}), 404

        ResourceGateway.update(page, check_permission=False, status='draft')
        ResourceGateway.commit()

        return jsonify({
            'success': True,
            'data': page.to_dict(),
            'message': _('頁面已取消發布')
        })
    except Exception as e:
        db.session.rollback()
        logger.exception('[PageLayout] unpublish_page error')
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# SQLite 輔助: 從 view 反查子系統 secure_code
# =============================================================================

def _resolve_sub_system_sc(view) -> str:
    """
    從 DcCrudView 反查所屬子系統的 secure_code

    SQLite CRUD 需要 sub_system_sc 才能定位檔案路徑。
    優先讀 request header/param，不行再查 DB。
    """
    # 1. 嘗試從 request 取得 (前端設計器會送)
    ss_sc = request.headers.get('X-SubSystem-SC', '').strip()
    if ss_sc:
        return ss_sc

    ss_sc = request.args.get('sub_system_sc', '').strip()
    if ss_sc:
        return ss_sc

    # 2. 從 DcSubSystemPage 反查 (view 被某個子系統頁面引用)
    from ..models.sub_system_page import DcSubSystemPage
    ssp = DcSubSystemPage.query.filter_by(
        page_layout_secure_code=view.secure_code if hasattr(view, 'page_layout_secure_code') else None,
        org_secure_code=view.org_secure_code,
        is_deleted=False,
    ).first()
    if ssp:
        return ssp.sub_system_secure_code

    logger.warning(
        'Cannot resolve sub_system_sc for view %s (data_source=%s)',
        view.secure_code, view.data_source,
    )
    return ''


# =============================================================================
# 子系統 Row CRUD 權限檢查
# =============================================================================

def _check_sub_system_crud(req, action):
    """
    檢查 Row 寫操作的子系統權限

    支援兩種模式:
    1. 舊模式: X-SubSystem-SC + X-SubSystem-SSP (DcSubSystemPage)
    2. Site Map 模式: X-SubSystem-SC + X-SiteMap-Node (DcSiteMapNode)

    Args:
        req: Flask request
        action: 'create' / 'edit' / 'delete'

    Returns:
        None = 通過，Response = 拒絕
    """
    sub_sc = req.headers.get('X-SubSystem-SC') or req.args.get('sub_sc', '').strip()
    node_sc = req.headers.get('X-SiteMap-Node', '').strip()
    ssp_sc = req.headers.get('X-SubSystem-SSP') or req.args.get('ssp_sc', '').strip()

    if not sub_sc:
        return None  # 無子系統 context

    # Site Map 模式
    if node_sc:
        return _check_site_map_crud(sub_sc, node_sc, action)

    # 舊模式
    if not ssp_sc:
        return None  # 無子系統 context，回退到 view 本身權限

    try:
        from ..models import DcSubSystem, DcSubSystemPage
        from ..services.sub_system_service import SubSystemService

        ss = DcSubSystem.query.filter_by(
            secure_code=sub_sc,
            is_deleted=False,
        ).first()
        if not ss or not ss.is_active:
            return jsonify({'success': False, 'error': 'Sub system not found'}), 404

        role_type = SubSystemService.get_user_role_type(current_user, ss)
        if role_type is None:
            return jsonify({'success': False, 'error': _('非子系統成員')}), 403

        ssp = DcSubSystemPage.query.filter_by(
            secure_code=ssp_sc,
            is_deleted=False,
        ).first()
        if not ssp:
            return jsonify({'success': False, 'error': 'Page config not found'}), 404

        ctx = SubSystemService.get_page_context(role_type, ssp)
        crud = ctx.get('crud', {})

        if not crud.get(action, False):
            return jsonify({
                'success': False,
                'error': _('您的角色 (%(role_type)s) 不允許此操作', role_type=role_type)
            }), 403

        return None  # 通過
    except Exception as e:
        logger.warning('Sub system CRUD check error: %s', e)
        return None  # 檢查失敗時不阻擋（回退到 view 權限）


def _check_site_map_crud(sub_sc, node_sc, action):
    """
    Site Map 模式的 CRUD 權限檢查

    優先順序:
    1. Widget 層級 rolePermissions (從 layout_json 中按 X-Widget-Id 定位)
    2. 節點層級 crud_overrides (backward compat)
    """
    try:
        from ..models import DcSubSystem, DcPageLayout
        from ..services.sub_system_service import SubSystemService
        from ..services.site_map_service import SiteMapService

        ss = DcSubSystem.query.filter_by(
            secure_code=sub_sc,
            is_deleted=False,
        ).first()
        if not ss or not ss.is_active:
            return jsonify({'success': False, 'error': 'Sub system not found'}), 404

        role_type = SubSystemService.get_user_role_type(current_user, ss)
        if role_type is None:
            return jsonify({'success': False, 'error': _('非子系統成員')}), 403

        node = SiteMapService.get_node(node_sc, ss.org_secure_code)
        if not node:
            return jsonify({'success': False, 'error': 'Site map node not found'}), 404

        # 嘗試 widget 層級權限檢查
        widget_id = request.headers.get('X-Widget-Id', '').strip()
        if widget_id and node.page_layout_secure_code:
            widget_crud = _get_widget_role_crud(
                node.page_layout_secure_code, widget_id, role_type,
                SubSystemService.is_admin_role(role_type)
            )
            if widget_crud is not None:
                if not widget_crud.get(action, False):
                    return jsonify({
                        'success': False,
                        'error': _('您的角色 (%(role_type)s) 不允許此操作', role_type=role_type)
                    }), 403
                return None  # 通過

        # Fallback: 節點層級 crud_overrides
        ctx = SiteMapService.get_node_context(node, role_type)
        crud = ctx.get('crud', {})

        if not crud.get(action, False):
            return jsonify({
                'success': False,
                'error': _('您的角色 (%(role_type)s) 不允許此操作', role_type=role_type)
            }), 403

        return None  # 通過
    except Exception as e:
        logger.warning('Site map CRUD check error: %s', e)
        return None  # 檢查失敗時不阻擋


def _get_widget_role_crud(page_layout_sc, widget_id, role_type, is_admin):
    """
    從 layout_json 中定位 widget，取得其 rolePermissions 對應角色的 CRUD 設定。

    Returns:
        dict: {'create': bool, 'edit': bool, 'delete': bool} 或 None (無法定位時)
    """
    from ..models import DcPageLayout

    page = DcPageLayout.query.filter_by(
        secure_code=page_layout_sc,
        is_deleted=False,
    ).first()
    if not page:
        return None

    layout = page.layout_json or {}
    widgets = layout.get('widgets', [])

    # 在 widgets 中找到匹配的 widget
    role_perms = None
    for w in widgets:
        wc = w.get('widget') or w
        if wc.get('id') == widget_id and 'rolePermissions' in wc:
            role_perms = wc['rolePermissions']
            break

    if role_perms is None:
        return None  # widget 無 rolePermissions，呼叫端 fallback

    perm = role_perms.get(role_type)
    if perm:
        return perm

    # rolePermissions 存在但無此角色: 管理層全權，其他禁止
    if is_admin:
        return {'create': True, 'edit': True, 'delete': True}
    return {'create': False, 'edit': False, 'delete': False}


# =============================================================================
# 子系統樣式 API
# =============================================================================

@api_bp.route('/sub-systems/<ss_sc>/style')
@module_access_required('nocode_builder')
def get_subsystem_style(ss_sc):
    """取得子系統預設樣式"""
    try:
        from ..models import DcSubSystem
        ss = ResourceGateway.get(DcSubSystem, ss_sc, raise_on_not_found=False, check_permission=False)
        if not ss or ss.is_deleted:
            return jsonify({'success': False, 'error': 'SubSystem not found'}), 404
        return jsonify({'success': True, 'data': ss.style_config or {}})
    except Exception as e:
        db.session.rollback()
        logger.exception('[Style] get_subsystem_style error')
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/sub-systems/<ss_sc>/style', methods=['PUT'])
@csrf.exempt
@admin_required
def update_subsystem_style(ss_sc):
    """更新子系統預設樣式（成為子系統預設）"""
    try:
        from ..models import DcSubSystem
        ss = ResourceGateway.get(DcSubSystem, ss_sc, raise_on_not_found=False, check_permission=False)
        if not ss or ss.is_deleted:
            return jsonify({'success': False, 'error': 'SubSystem not found'}), 404

        data = request.get_json() or {}
        style = data.get('style_config', {})
        ResourceGateway.update(ss, check_permission=False, style_config=style)
        ResourceGateway.commit()
        return jsonify({'success': True, 'data': ss.style_config or {}, 'message': _('子系統預設樣式已更新')})
    except Exception as e:
        db.session.rollback()
        logger.exception('[Style] update_subsystem_style error')
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/sub-systems/<ss_sc>/style/apply-all', methods=['POST'])
@csrf.exempt
@admin_required
def apply_style_to_all_pages(ss_sc):
    """全域覆蓋：將樣式套用到子系統下所有頁面"""
    try:
        from ..models import DcSubSystem, DcSiteMapNode, DcPageLayout
        ss = ResourceGateway.get(DcSubSystem, ss_sc, raise_on_not_found=False, check_permission=False)
        if not ss or ss.is_deleted:
            return jsonify({'success': False, 'error': 'SubSystem not found'}), 404

        data = request.get_json() or {}
        style = data.get('style_config', {})

        # 取得此子系統下所有 site map node 關聯的 page layout
        nodes = ResourceGateway.filter(
            DcSiteMapNode,
            sub_system_secure_code=ss_sc,
            is_deleted=False
        )
        page_scs = set()
        for n in nodes:
            if n.page_layout_secure_code:
                page_scs.add(n.page_layout_secure_code)

        count = 0
        for psc in page_scs:
            page = ResourceGateway.get(DcPageLayout, psc, raise_on_not_found=False, check_permission=False)
            if page and not page.is_deleted:
                ResourceGateway.update(page, check_permission=False, style_config=style)
                count += 1

        ResourceGateway.commit()
        return jsonify({
            'success': True,
            'message': _('已套用到 %(count)s 個頁面', count=count),
            'count': count
        })
    except Exception as e:
        db.session.rollback()
        logger.exception('[Style] apply_style_to_all_pages error')
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# 底圖圖庫 API
# =============================================================================

@api_bp.route('/backgrounds')
@module_access_required('nocode_builder')
def list_backgrounds():
    """列出底圖圖庫"""
    try:
        from ..models import DcBackground
        result = ResourceGateway.filter(
            DcBackground,
            is_deleted=False,
            order_by='-created_at'
        )
        return jsonify({'success': True, 'data': [b.to_dict() for b in result]})
    except Exception as e:
        db.session.rollback()
        logger.exception('[Background] list error')
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/backgrounds/upload', methods=['POST'])
@csrf.exempt
@admin_required
def upload_background():
    """上傳底圖"""
    try:
        from ..models import DcBackground
        from app.services import file_service

        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400

        file = request.files['file']
        if not file.filename:
            return jsonify({'success': False, 'error': 'No file selected'}), 400

        org = get_current_org()
        record = file_service.upload_file(
            org_sc=org.secure_code,
            file=file,
            context_type='nc_background',
            uploader_sc=current_user.secure_code,
        )
        db.session.flush()

        # 取得圖片尺寸
        width, height = None, None
        try:
            from PIL import Image
            import io
            file.stream.seek(0)
            img = Image.open(io.BytesIO(file.stream.read()))
            width, height = img.size
            file.stream.seek(0)
        except Exception:
            pass

        bg = DcBackground(
            org_secure_code=org.secure_code,
            filename=record.storage_ref,
            original_filename=record.original_name,
            filepath=record.storage_ref or '',
            filesize=record.file_size,
            mimetype=record.mime_type,
            width=width,
            height=height,
            platform_file_sc=record.secure_code,
        )
        db.session.add(bg)
        db.session.commit()

        return jsonify({
            'success': True,
            'data': bg.to_dict(),
            'message': _('底圖上傳成功')
        })
    except Exception as e:
        db.session.rollback()
        logger.exception('[Background] upload error')
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/backgrounds/<secure_code>', methods=['DELETE'])
@csrf.exempt
@admin_required
def delete_background(secure_code):
    """刪除底圖"""
    try:
        from ..models import DcBackground
        from app.services import file_service

        bg = ResourceGateway.get(DcBackground, secure_code, raise_on_not_found=False, check_permission=False)
        if not bg or bg.is_deleted:
            return jsonify({'success': False, 'error': 'Background not found'}), 404

        # 刪除 FileService 記錄
        if bg.platform_file_sc:
            try:
                pf = file_service.get_file_by_sc(bg.platform_file_sc, org_sc=bg.org_secure_code)
                if pf:
                    file_service.delete_file(pf)
            except Exception:
                logger.warning(f'[Background] Failed to delete platform file {bg.platform_file_sc}')

        ResourceGateway.delete(bg, check_permission=False, soft=True)
        ResourceGateway.commit()
        return jsonify({'success': True, 'message': _('底圖已刪除')})
    except Exception as e:
        db.session.rollback()
        logger.exception('[Background] delete error')
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# Sub System API (獨立檔案)
# =============================================================================
from . import sub_system_api  # noqa: E402, F401
from . import site_map_api  # noqa: E402, F401
from . import portal_org_api  # noqa: E402, F401
from . import project_api  # noqa: E402, F401
from . import template_api  # noqa: E402, F401
from . import bridge_api  # noqa: E402, F401
