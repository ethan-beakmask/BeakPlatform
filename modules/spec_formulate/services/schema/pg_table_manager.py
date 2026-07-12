"""
Schema PostgreSQL Table Manager

負責：
1. 確保企業專屬 DB 存在（複用 form_workflow 的 provision 機制）
2. 列出企業 DB 中的資料表
3. 讀取資料表結構（introspect）
4. 比對 SPEC 與 DB 結構差異
5. 從 SPEC 建立資料表

集團 DB 支援（cg_ 前綴函數）：
6. 確保集團共享 DB 存在
7. 在集團 DB 建表（自動附加 owner_org_code + RLS policy）
8. 表管理權限檢查（只有建立者企業能改表/刪表）
"""
import logging

import psycopg2
from flask_babel import gettext as _
from psycopg2 import sql as psql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

logger = logging.getLogger(__name__)


# data_class -> pg_type 映射（從 data_class_registry 簡化）
_DC_TO_PG_FALLBACK = {
    'text': 'VARCHAR(500)',
    'text_long': 'TEXT',
    'integer': 'INTEGER',
    'decimal': 'NUMERIC',
    'currency': 'NUMERIC(15,2)',
    'serial': 'SERIAL',
    'boolean': 'BOOLEAN',
    'date': 'DATE',
    'datetime': 'TIMESTAMP',
    'email': 'VARCHAR(200)',
    'phone': 'VARCHAR(50)',
    'url': 'VARCHAR(1000)',
    'enum_single': 'VARCHAR(500)',
    'enum_multi': 'JSONB',
    'json': 'JSONB',
    'tags': 'JSONB',
    'binary': 'BYTEA',
    'signature': 'TEXT',
}


def ensure_org_database(org):
    """
    確保企業專屬 DB 存在，回傳 FwOrgDatabase。

    Args:
        org: Organization 物件（需有 id 和 secure_code）

    Returns:
        FwOrgDatabase instance
    """
    from modules.form_workflow.services.sql_sync.org_db_manager import (
        get_org_database,
        provision_org_database,
    )
    from app import db

    org_db = get_org_database(org.secure_code)
    if org_db:
        return org_db

    # 尚未建立，執行 provision
    org_db = provision_org_database(org.id, org.secure_code)
    db.session.commit()
    return org_db


def list_tables(org_secure_code):
    """
    列出企業 DB 中的所有使用者資料表

    Returns:
        list of str (table names)
    """
    from modules.form_workflow.services.sql_sync.pool import get_org_conn

    with get_org_conn(org_secure_code, role='admin') as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """)
            return [row[0] for row in cur.fetchall()]


def introspect_table(org_secure_code, table_name):
    """
    讀取資料表結構

    Returns:
        list of dict: [{column_name, data_type, is_nullable, column_default, ordinal_position}, ...]
    """
    from modules.form_workflow.services.sql_sync.pool import get_org_conn

    with get_org_conn(org_secure_code, role='admin') as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT column_name, data_type, udt_name,
                       character_maximum_length, numeric_precision, numeric_scale,
                       is_nullable, column_default, ordinal_position
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s
                ORDER BY ordinal_position
            """, (table_name,))

            columns = []
            for row in cur.fetchall():
                col_name, data_type, udt_name, char_max, num_prec, num_scale, \
                    is_nullable, col_default, ordinal = row

                # 組合顯示型別
                display_type = _format_pg_type(
                    udt_name, char_max, num_prec, num_scale
                )

                columns.append({
                    'column_name': col_name,
                    'data_type': data_type,
                    'udt_name': udt_name,
                    'display_type': display_type,
                    'char_max_length': char_max,
                    'numeric_precision': num_prec,
                    'numeric_scale': num_scale,
                    'is_nullable': is_nullable == 'YES',
                    'column_default': col_default,
                    'ordinal_position': ordinal,
                })

            # 查詢主鍵
            cur.execute("""
                SELECT a.attname
                FROM pg_index i
                JOIN pg_attribute a ON a.attrelid = i.indrelid
                  AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = %s::regclass
                  AND i.indisprimary
            """, (table_name,))
            pk_cols = set(row[0] for row in cur.fetchall())

            for col in columns:
                col['is_primary_key'] = col['column_name'] in pk_cols

            return columns


def _format_pg_type(udt_name, char_max, num_prec, num_scale):
    """格式化 PostgreSQL 型別顯示"""
    udt_upper = udt_name.upper()

    # 常見映射
    type_map = {
        'INT4': 'INTEGER',
        'INT8': 'BIGINT',
        'INT2': 'SMALLINT',
        'FLOAT4': 'REAL',
        'FLOAT8': 'DOUBLE PRECISION',
        'BOOL': 'BOOLEAN',
        'TIMESTAMPTZ': 'TIMESTAMP WITH TIME ZONE',
    }

    display = type_map.get(udt_upper, udt_upper)

    if udt_name == 'varchar' and char_max:
        display = f'VARCHAR({char_max})'
    elif udt_name == 'numeric' and num_prec:
        if num_scale:
            display = f'NUMERIC({num_prec},{num_scale})'
        else:
            display = f'NUMERIC({num_prec})'
    elif udt_name == 'bpchar' and char_max:
        display = f'CHAR({char_max})'

    return display


def compare_spec_with_table(spec_fields, table_columns):
    """
    比對 SPEC 的 postgresql facet 與實際資料表結構

    Args:
        spec_fields: SPEC 的 fields JSONB 陣列
        table_columns: introspect_table 的結果

    Returns:
        dict: {
            match: bool,
            spec_only: [{field_key, pg_type}],    # SPEC 有但 DB 沒有
            db_only: [{column_name, display_type}], # DB 有但 SPEC 沒有
            type_mismatch: [{field_key, spec_type, db_type}],  # 型別不符
            matched: [{field_key, pg_type}],       # 完全相符
        }
    """
    # SPEC 欄位 → pg_type
    spec_map = {}
    for f in (spec_fields or []):
        fk = f.get('field_key', '')
        if not fk:
            continue
        pg_facet = f.get('facets', {}).get('postgresql', {})
        pg_type = pg_facet.get('pg_type', '')
        if not pg_type:
            # fallback from data_class
            dc = f.get('core', {}).get('data_class', 'text')
            pg_type = _DC_TO_PG_FALLBACK.get(dc, 'TEXT')
        spec_map[fk] = pg_type.upper()

    # DB 欄位（排除自動附加的系統/稽核欄位）
    _SYSTEM_COLS = {'id', 'created_at', 'updated_at', 'created_by',
                    'updated_by', 'is_deleted'}
    db_map = {}
    for col in (table_columns or []):
        cn = col['column_name']
        if cn in _SYSTEM_COLS:
            continue
        db_map[cn] = col['display_type'].upper()

    spec_keys = set(spec_map.keys())
    db_keys = set(db_map.keys())

    spec_only = [
        {'field_key': k, 'pg_type': spec_map[k]}
        for k in sorted(spec_keys - db_keys)
    ]
    db_only = [
        {'column_name': k, 'display_type': db_map[k]}
        for k in sorted(db_keys - spec_keys)
    ]

    type_mismatch = []
    matched = []
    for k in sorted(spec_keys & db_keys):
        st = _normalize_type(spec_map[k])
        dt = _normalize_type(db_map[k])
        if st == dt:
            matched.append({'field_key': k, 'pg_type': spec_map[k]})
        else:
            type_mismatch.append({
                'field_key': k,
                'spec_type': spec_map[k],
                'db_type': db_map[k],
            })

    is_match = not spec_only and not db_only and not type_mismatch

    return {
        'match': is_match,
        'spec_only': spec_only,
        'db_only': db_only,
        'type_mismatch': type_mismatch,
        'matched': matched,
    }


def _normalize_type(pg_type):
    """正規化型別字串用於比對"""
    t = pg_type.strip().upper()
    # SERIAL 和 INTEGER 在 introspect 時都會顯示為 INTEGER
    if t == 'SERIAL':
        t = 'INTEGER'
    return t


def create_table_from_spec(org_secure_code, table_name, spec_fields):
    """
    從 SPEC 的 postgresql facet 建立資料表

    Args:
        org_secure_code: 企業 secure_code
        table_name: 資料表名稱
        spec_fields: SPEC 的 fields JSONB 陣列

    Returns:
        dict: { success, message, ddl, warnings }
    """
    from modules.form_workflow.services.sql_sync.pool import get_org_conn

    columns = []
    warnings = []
    has_pk = False

    for f in (spec_fields or []):
        fk = f.get('field_key', '')
        if not fk:
            continue

        pg_facet = f.get('facets', {}).get('postgresql', {})
        pg_type = pg_facet.get('pg_type', '')
        if not pg_type:
            dc = f.get('core', {}).get('data_class', 'text')
            pg_type = _DC_TO_PG_FALLBACK.get(dc, 'TEXT')
            warnings.append(_('%(fk)s: 無 PostgreSQL facet，使用預設型別 %(pg_type)s',
                              fk=fk, pg_type=pg_type))

        core = f.get('core', {})
        nullable = pg_facet.get('nullable', True)
        is_pk = pg_facet.get('primary_key', False)
        default = pg_facet.get('default')
        required = core.get('required', False)

        if is_pk:
            has_pk = True

        columns.append({
            'name': fk,
            'type': pg_type,
            'nullable': nullable,
            'primary_key': is_pk,
            'default': default,
            'required': required,
            'index': pg_facet.get('index', False),
            'unique': pg_facet.get('unique', False),
            'foreign_key': pg_facet.get('foreign_key') or None,
        })

    if not columns:
        return {
            'success': False,
            'message': _('無有效欄位可建立資料表'),
            'ddl': '',
            'warnings': warnings,
        }

    # 組合 DDL
    col_defs = []
    pk_cols = []
    index_cols = []
    unique_cols = []
    fk_clauses = []

    # 自動附加: id 主鍵
    col_defs.append('id SERIAL PRIMARY KEY')

    for col in columns:
        parts = [col['name'], col['type']]
        if col['primary_key']:
            pk_cols.append(col['name'])
        # NOT NULL: 明確設定或 core.required 為 True
        if (not col['nullable'] or col.get('required')) \
                and not col['primary_key']:
            parts.append('NOT NULL')
        if col['default'] is not None:
            parts.append(f"DEFAULT {col['default']}")
        col_defs.append(' '.join(parts))

        # 收集 INDEX / UNIQUE / FK
        if col.get('index'):
            index_cols.append(col['name'])
        if col.get('unique'):
            unique_cols.append(col['name'])
        if col.get('foreign_key'):
            fk_clauses.append(
                f"FOREIGN KEY ({col['name']}) REFERENCES {col['foreign_key']}"
            )

    # 使用者自訂複合主鍵（排除 id 以外的 PK 欄位）
    if pk_cols:
        col_defs.append(f"CONSTRAINT pk_{table_name}_custom "
                        f"UNIQUE ({', '.join(pk_cols)})")

    # UNIQUE 約束
    for uc in unique_cols:
        col_defs.append(f"CONSTRAINT uq_{table_name}_{uc} UNIQUE ({uc})")

    # FK 約束
    col_defs.extend(fk_clauses)

    # 自動附加: 稽核欄位
    col_defs.append('created_at TIMESTAMP NOT NULL DEFAULT NOW()')
    col_defs.append('updated_at TIMESTAMP NOT NULL DEFAULT NOW()')
    col_defs.append('created_by VARCHAR(100)')
    col_defs.append('updated_by VARCHAR(100)')
    col_defs.append('is_deleted BOOLEAN NOT NULL DEFAULT FALSE')

    ddl = f"CREATE TABLE {table_name} (\n  " + \
          ',\n  '.join(col_defs) + \
          '\n)'

    # INDEX 語句（CREATE TABLE 之後執行）
    index_sqls = []
    for ic in index_cols:
        index_sqls.append(
            f"CREATE INDEX idx_{table_name}_{ic} ON {table_name} ({ic})"
        )

    # 執行
    try:
        with get_org_conn(org_secure_code, role='admin') as conn:
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            with conn.cursor() as cur:
                cur.execute(ddl)
                for idx_sql in index_sqls:
                    cur.execute(idx_sql)

        return {
            'success': True,
            'message': _('資料表 %(table)s 建立成功', table=table_name),
            'ddl': ddl,
            'warnings': warnings,
        }
    except psycopg2.Error as e:
        return {
            'success': False,
            'message': _('建立失敗: %(error)s', error=e.pgerror or str(e)),
            'ddl': ddl,
            'warnings': warnings,
        }


def apply_spec_to_table(org_secure_code, table_name, spec_fields, table_columns):
    """
    SPEC 覆蓋資料表：新增缺少的欄位、修改型別不符的欄位

    Returns:
        dict: { success, message, executed_sql, errors }
    """
    from modules.form_workflow.services.sql_sync.pool import get_org_conn

    diff = compare_spec_with_table(spec_fields, table_columns)
    executed = []
    errors = []

    try:
        with get_org_conn(org_secure_code, role='admin') as conn:
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            with conn.cursor() as cur:
                # 新增 SPEC 有但 DB 沒有的欄位
                for col in diff['spec_only']:
                    alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {col['field_key']} {col['pg_type']}"
                    try:
                        cur.execute(alter_sql)
                        executed.append(alter_sql)
                    except psycopg2.Error as e:
                        errors.append(f"{col['field_key']}: {e.pgerror or str(e)}")

                # 修改型別不符的欄位
                for col in diff['type_mismatch']:
                    spec_type = col['spec_type']
                    # SERIAL 不能 ALTER
                    if spec_type.upper() == 'SERIAL':
                        errors.append(
                            _('%(fk)s: SERIAL 型別無法透過 ALTER 修改，目前為 %(db_type)s',
                              fk=col['field_key'], db_type=col['db_type'])
                        )
                        continue
                    alter_sql = (
                        f"ALTER TABLE {table_name} "
                        f"ALTER COLUMN {col['field_key']} "
                        f"TYPE {spec_type} USING {col['field_key']}::{spec_type}"
                    )
                    try:
                        cur.execute(alter_sql)
                        executed.append(alter_sql)
                    except psycopg2.Error as e:
                        errors.append(f"{col['field_key']}: {e.pgerror or str(e)}")

        success = len(errors) == 0
        return {
            'success': success,
            'message': (
                _('已執行 %(n)s 項變更', n=len(executed))
                + (_('，%(n)s 項失敗', n=len(errors)) if errors else '')
            ),
            'executed_sql': executed,
            'errors': errors,
        }

    except Exception as e:
        return {
            'success': False,
            'message': _('操作失敗: %(error)s', error=str(e)),
            'executed_sql': executed,
            'errors': errors,
        }


# ====================================================================
# 集團 DB 操作（cg_ 前綴）
# ====================================================================

# 集團 DB 表的系統欄位（比企業 DB 多一個 owner_org_code）
_CG_SYSTEM_COLS = {
    'id', 'owner_org_code',
    'created_at', 'updated_at', 'created_by', 'updated_by', 'is_deleted',
}


def ensure_conglomerate_database(conglomerate):
    """
    確保集團共享 DB 存在，回傳 FwConglomerateDatabase。

    Args:
        conglomerate: Conglomerate 物件（需有 id 和 secure_code）

    Returns:
        FwConglomerateDatabase instance
    """
    from modules.form_workflow.services.sql_sync.cg_db_manager import (
        get_conglomerate_database,
        provision_conglomerate_database,
    )
    from app import db

    cg_db = get_conglomerate_database(conglomerate.secure_code)
    if cg_db:
        return cg_db

    cg_db = provision_conglomerate_database(
        conglomerate.id, conglomerate.secure_code
    )
    # 更新 Conglomerate.has_shared_db
    conglomerate.has_shared_db = True
    db.session.commit()
    return cg_db


def cg_list_tables(conglomerate_secure_code):
    """
    列出集團 DB 中的所有使用者資料表

    Returns:
        list of str (table names)
    """
    from modules.form_workflow.services.sql_sync.pool import get_cg_conn

    with get_cg_conn(conglomerate_secure_code, role='admin') as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """)
            return [row[0] for row in cur.fetchall()]


def cg_introspect_table(conglomerate_secure_code, table_name):
    """
    讀取集團 DB 中指定表的結構

    Returns:
        list of dict (同 introspect_table 格式)
    """
    from modules.form_workflow.services.sql_sync.pool import get_cg_conn

    with get_cg_conn(conglomerate_secure_code, role='admin') as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT column_name, data_type, udt_name,
                       character_maximum_length, numeric_precision,
                       numeric_scale,
                       is_nullable, column_default, ordinal_position
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s
                ORDER BY ordinal_position
            """, (table_name,))

            columns = []
            for row in cur.fetchall():
                (col_name, data_type, udt_name, char_max,
                 num_prec, num_scale,
                 is_nullable, col_default, ordinal) = row

                display_type = _format_pg_type(
                    udt_name, char_max, num_prec, num_scale
                )

                columns.append({
                    'column_name': col_name,
                    'data_type': data_type,
                    'udt_name': udt_name,
                    'display_type': display_type,
                    'char_max_length': char_max,
                    'numeric_precision': num_prec,
                    'numeric_scale': num_scale,
                    'is_nullable': is_nullable == 'YES',
                    'column_default': col_default,
                    'ordinal_position': ordinal,
                })

            # 查詢主鍵
            cur.execute("""
                SELECT a.attname
                FROM pg_index i
                JOIN pg_attribute a ON a.attrelid = i.indrelid
                  AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = %s::regclass
                  AND i.indisprimary
            """, (table_name,))
            pk_cols = set(row[0] for row in cur.fetchall())

            for col in columns:
                col['is_primary_key'] = col['column_name'] in pk_cols

            return columns


def cg_compare_spec_with_table(spec_fields, table_columns):
    """
    比對 SPEC 與集團 DB 表結構（排除集團系統欄位）

    用法同 compare_spec_with_table，但排除 owner_org_code 等集團系統欄位
    """
    # 過濾掉集團系統欄位
    filtered_columns = [
        col for col in (table_columns or [])
        if col['column_name'] not in _CG_SYSTEM_COLS
    ]
    # 複用既有比對邏輯（內部已排除基本系統欄位）
    return compare_spec_with_table(spec_fields, filtered_columns)


def cg_check_table_ownership(conglomerate_secure_code, table_name,
                             org_secure_code):
    """
    檢查企業是否為集團 DB 中指定表的建立者

    Args:
        conglomerate_secure_code: 集團 SC
        table_name: 表名
        org_secure_code: 要檢查的企業 SC

    Returns:
        bool: True 表示該企業是建立者（有管理權限）
    """
    from modules.spec_formulate.models.conglomerate_table_registry import (
        FwConglomerateTableRegistry,
    )

    registry = FwConglomerateTableRegistry.query.filter_by(
        conglomerate_secure_code=conglomerate_secure_code,
        table_name=table_name,
        status='active',
        is_deleted=False,
    ).first()

    if not registry:
        return False

    return registry.creator_org_secure_code == org_secure_code


def cg_create_table_from_spec(
    conglomerate_secure_code, table_name, spec_fields,
    creator_org_secure_code, creator_org_name=None,
    spec_secure_code=None
):
    """
    從 SPEC 在集團 DB 建立資料表

    與企業版差異：
    - 自動附加 owner_org_code VARCHAR(32) NOT NULL 欄位 + 索引
    - 建表後自動套用 RLS policy
    - 登記表建立者到 FwConglomerateTableRegistry

    Args:
        conglomerate_secure_code: 集團 SC
        table_name: 資料表名稱
        spec_fields: SPEC 的 fields JSONB 陣列
        creator_org_secure_code: 建立者企業 SC
        creator_org_name: 建立者企業名稱（快照）
        spec_secure_code: 關聯 SPEC 的 SC（可選）

    Returns:
        dict: { success, message, ddl, warnings }
    """
    from modules.form_workflow.services.sql_sync.pool import get_cg_conn
    from modules.form_workflow.services.sql_sync.cg_db_manager import (
        apply_rls_to_table,
    )
    from modules.spec_formulate.models.conglomerate_table_registry import (
        FwConglomerateTableRegistry,
    )
    from app import db

    columns = []
    warnings = []

    for f in (spec_fields or []):
        fk = f.get('field_key', '')
        if not fk:
            continue

        pg_facet = f.get('facets', {}).get('postgresql', {})
        pg_type = pg_facet.get('pg_type', '')
        if not pg_type:
            dc = f.get('core', {}).get('data_class', 'text')
            pg_type = _DC_TO_PG_FALLBACK.get(dc, 'TEXT')
            warnings.append(
                _('%(fk)s: 無 PostgreSQL facet，使用預設型別 %(pg_type)s',
                  fk=fk, pg_type=pg_type)
            )

        core = f.get('core', {})
        nullable = pg_facet.get('nullable', True)
        is_pk = pg_facet.get('primary_key', False)
        default = pg_facet.get('default')
        required = core.get('required', False)

        columns.append({
            'name': fk,
            'type': pg_type,
            'nullable': nullable,
            'primary_key': is_pk,
            'default': default,
            'required': required,
            'index': pg_facet.get('index', False),
            'unique': pg_facet.get('unique', False),
            'foreign_key': pg_facet.get('foreign_key') or None,
        })

    if not columns:
        return {
            'success': False,
            'message': _('無有效欄位可建立資料表'),
            'ddl': '',
            'warnings': warnings,
        }

    # 組合 DDL
    col_defs = []
    pk_cols = []
    index_cols = []
    unique_cols = []
    fk_clauses = []

    # 自動附加: id 主鍵
    col_defs.append('id SERIAL PRIMARY KEY')

    # 集團 DB 專屬: owner_org_code（RLS 依據欄位）
    col_defs.append('owner_org_code VARCHAR(32) NOT NULL')

    for col in columns:
        parts = [col['name'], col['type']]
        if col['primary_key']:
            pk_cols.append(col['name'])
        if (not col['nullable'] or col.get('required')) \
                and not col['primary_key']:
            parts.append('NOT NULL')
        if col['default'] is not None:
            parts.append(f"DEFAULT {col['default']}")
        col_defs.append(' '.join(parts))

        if col.get('index'):
            index_cols.append(col['name'])
        if col.get('unique'):
            unique_cols.append(col['name'])
        if col.get('foreign_key'):
            fk_clauses.append(
                f"FOREIGN KEY ({col['name']}) "
                f"REFERENCES {col['foreign_key']}"
            )

    if pk_cols:
        col_defs.append(
            f"CONSTRAINT pk_{table_name}_custom "
            f"UNIQUE ({', '.join(pk_cols)})"
        )

    for uc in unique_cols:
        col_defs.append(
            f"CONSTRAINT uq_{table_name}_{uc} UNIQUE ({uc})"
        )

    col_defs.extend(fk_clauses)

    # 自動附加: 稽核欄位
    col_defs.append('created_at TIMESTAMP NOT NULL DEFAULT NOW()')
    col_defs.append('updated_at TIMESTAMP NOT NULL DEFAULT NOW()')
    col_defs.append('created_by VARCHAR(100)')
    col_defs.append('updated_by VARCHAR(100)')
    col_defs.append('is_deleted BOOLEAN NOT NULL DEFAULT FALSE')

    ddl = (
        f"CREATE TABLE {table_name} (\n  "
        + ',\n  '.join(col_defs)
        + '\n)'
    )

    # INDEX 語句
    index_sqls = [
        # owner_org_code 必建索引（RLS 查詢效能）
        f"CREATE INDEX idx_{table_name}_owner_org "
        f"ON {table_name} (owner_org_code)",
    ]
    for ic in index_cols:
        index_sqls.append(
            f"CREATE INDEX idx_{table_name}_{ic} ON {table_name} ({ic})"
        )

    # 執行 DDL
    try:
        with get_cg_conn(conglomerate_secure_code, role='admin') as conn:
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            with conn.cursor() as cur:
                cur.execute(ddl)
                for idx_sql in index_sqls:
                    cur.execute(idx_sql)

        # 套用 RLS policy
        apply_rls_to_table(conglomerate_secure_code, table_name)

        # 登記建立者
        registry = FwConglomerateTableRegistry(
            conglomerate_secure_code=conglomerate_secure_code,
            table_name=table_name,
            creator_org_secure_code=creator_org_secure_code,
            creator_org_name=creator_org_name,
            spec_secure_code=spec_secure_code,
            status='active',
        )
        db.session.add(registry)
        db.session.flush()

        return {
            'success': True,
            'message': _('集團共享資料表 %(table)s 建立成功（含 RLS）', table=table_name),
            'ddl': ddl,
            'warnings': warnings,
        }
    except psycopg2.Error as e:
        return {
            'success': False,
            'message': _('建立失敗: %(error)s', error=e.pgerror or str(e)),
            'ddl': ddl,
            'warnings': warnings,
        }


def cg_apply_spec_to_table(
    conglomerate_secure_code, table_name, spec_fields, table_columns,
    org_secure_code
):
    """
    SPEC 覆蓋集團 DB 表：新增缺少的欄位、修改型別不符的欄位

    需先通過 cg_check_table_ownership 權限檢查。

    Args:
        conglomerate_secure_code: 集團 SC
        table_name: 資料表名稱
        spec_fields: SPEC fields
        table_columns: cg_introspect_table 結果
        org_secure_code: 操作者企業 SC（用於權限檢查）

    Returns:
        dict: { success, message, executed_sql, errors }
    """
    from modules.form_workflow.services.sql_sync.pool import get_cg_conn

    # 權限檢查：只有建立者能改表
    if not cg_check_table_ownership(
        conglomerate_secure_code, table_name, org_secure_code
    ):
        return {
            'success': False,
            'message': _('權限不足：只有建立此表的企業才能修改結構'),
            'executed_sql': [],
            'errors': ['NOT_TABLE_OWNER'],
        }

    diff = cg_compare_spec_with_table(spec_fields, table_columns)
    executed = []
    errors = []

    try:
        with get_cg_conn(conglomerate_secure_code, role='admin') as conn:
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            with conn.cursor() as cur:
                for col in diff['spec_only']:
                    alter_sql = (
                        f"ALTER TABLE {table_name} "
                        f"ADD COLUMN {col['field_key']} {col['pg_type']}"
                    )
                    try:
                        cur.execute(alter_sql)
                        executed.append(alter_sql)
                    except psycopg2.Error as e:
                        errors.append(
                            f"{col['field_key']}: {e.pgerror or str(e)}"
                        )

                for col in diff['type_mismatch']:
                    spec_type = col['spec_type']
                    if spec_type.upper() == 'SERIAL':
                        errors.append(
                            _('%(fk)s: SERIAL 型別無法透過 ALTER 修改，目前為 %(db_type)s',
                              fk=col['field_key'], db_type=col['db_type'])
                        )
                        continue
                    alter_sql = (
                        f"ALTER TABLE {table_name} "
                        f"ALTER COLUMN {col['field_key']} "
                        f"TYPE {spec_type} "
                        f"USING {col['field_key']}::{spec_type}"
                    )
                    try:
                        cur.execute(alter_sql)
                        executed.append(alter_sql)
                    except psycopg2.Error as e:
                        errors.append(
                            f"{col['field_key']}: {e.pgerror or str(e)}"
                        )

        success = len(errors) == 0
        return {
            'success': success,
            'message': (
                _('已執行 %(n)s 項變更', n=len(executed))
                + (_('，%(n)s 項失敗', n=len(errors)) if errors else '')
            ),
            'executed_sql': executed,
            'errors': errors,
        }

    except Exception as e:
        return {
            'success': False,
            'message': _('操作失敗: %(error)s', error=str(e)),
            'executed_sql': executed,
            'errors': errors,
        }
