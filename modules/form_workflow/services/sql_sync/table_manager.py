"""
SQL Sync — 表管理器

在企業專屬 DB (org_{id}) 中建立/刪除/檢查 SQL 同步表。
使用 admin 角色連線執行 DDL。
"""
import copy
import re
import logging

from psycopg2 import sql as psql

from .converter import (
    schema_to_columns,
    build_column_mapping,
    build_create_table_sql,
    build_create_table_ddl_text,
    grid_schema_to_columns,
    build_create_sub_table_sql,
    build_create_sub_table_ddl_text,
    build_sub_column_mapping,
    build_create_approval_table_sql,
    build_create_approval_table_ddl_text,
    GRID_TYPES,
)
from .pool import get_org_conn

logger = logging.getLogger(__name__)

# 表名前綴（安全檢查用）
TABLE_PREFIX = 'form_'


def make_table_name(mapping_id, publish_version):
    """
    計算 SQL 同步表名

    格式: form_{mapping_id}_v{publish_version}
    範例: form_23_v5

    Args:
        mapping_id: FwFormWorkflowMapping.id（主庫自增 ID）
        publish_version: 發行版本號

    Returns:
        str: 表名
    """
    return f'{TABLE_PREFIX}{mapping_id}_v{publish_version}'


def _validate_table_name(table_name):
    """驗證表名符合規則"""
    if not table_name.startswith(TABLE_PREFIX):
        raise ValueError(f'表名必須以 {TABLE_PREFIX} 開頭: {table_name}')
    if not re.match(r'^[a-z0-9_]+$', table_name):
        raise ValueError(f'表名只允許小寫英數和底線: {table_name}')


def table_exists(table_name, conn):
    """檢查表是否存在"""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = %s)",
            (table_name,)
        )
        return cur.fetchone()[0]


def create_sync_table(table_name, form_schema, conn, spec_fields=None):
    """
    在企業 DB 建立 SQL 同步表

    Args:
        table_name: 表名
        form_schema: form.io schema dict
        conn: psycopg2 connection (admin 角色)
        spec_fields: (optional) FwFormFieldSpec.fields list，有值時覆蓋型別

    Returns:
        tuple: (columns, ddl_text)
    """
    _validate_table_name(table_name)

    columns = schema_to_columns(form_schema, spec_fields=spec_fields)
    if not columns:
        raise ValueError('form.io schema 中沒有可同步的資料欄位')

    create_sql = build_create_table_sql(table_name, columns)
    ddl_text = build_create_table_ddl_text(table_name, columns)

    with conn.cursor() as cur:
        cur.execute(create_sql)
    conn.commit()

    logger.info(f'SQL Sync: 已建立表 {table_name} ({len(columns)} 個動態欄位)')
    return columns, ddl_text


def _find_grid_components(form_schema):
    """
    遞迴找出 form_schema 中所有 datagrid/editgrid 元件

    Returns:
        list of component dicts
    """
    grids = []

    def _walk(components):
        for comp in (components or []):
            comp_type = comp.get('type', '')
            if comp_type in GRID_TYPES:
                grids.append(comp)
                continue
            # 遞迴容器元件
            if 'components' in comp:
                _walk(comp.get('components', []))
            for col in comp.get('columns', []):
                if isinstance(col, dict):
                    _walk(col.get('components', []))

    _walk(form_schema.get('components', []))
    return grids


def _get_sync_user(org_secure_code):
    """取得企業的 sync 角色名稱"""
    from ...models.org_database import FwOrgDatabase
    org_db = FwOrgDatabase.query.filter_by(
        org_secure_code=org_secure_code,
        is_ready=True,
        is_deleted=False,
    ).first()
    return org_db.sync_user if org_db else None


def _grant_sub_table_permissions(conn, sub_table_name, sync_user):
    """GRANT SELECT, INSERT, UPDATE, DELETE ON 子表 TO sync user"""
    with conn.cursor() as cur:
        cur.execute(
            psql.SQL(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON {} TO {}"
            ).format(
                psql.Identifier(sub_table_name),
                psql.Identifier(sync_user),
            )
        )
        # 子表的 sequence 也需要 GRANT
        cur.execute(
            psql.SQL(
                "GRANT USAGE, SELECT ON SEQUENCE {} TO {}"
            ).format(
                psql.Identifier(f'{sub_table_name}_id_seq'),
                psql.Identifier(sync_user),
            )
        )
    conn.commit()


def create_sub_tables(base_table_name, form_schema, conn, org_secure_code):
    """
    為 form_schema 中的 datagrid/editgrid 元件建立子表

    Args:
        base_table_name: 主表名（如 form_38_v3）
        form_schema: form.io schema dict
        conn: psycopg2 connection (admin 角色)
        org_secure_code: 企業 secure_code（用於查 sync_user 名稱）

    Returns:
        dict: {grid_key: {'table_name': str, 'columns': {col_mapping}}}
    """
    grids = _find_grid_components(form_schema)
    if not grids:
        return {}

    sync_user = _get_sync_user(org_secure_code)

    sub_tables = {}
    for comp in grids:
        grid_key = comp.get('key')
        if not grid_key:
            continue

        sub_columns = grid_schema_to_columns(comp)
        if not sub_columns:
            logger.warning(f'SQL Sync: grid "{grid_key}" 沒有子欄位，跳過子表')
            continue

        # 子表名: 主表名_items_gridkey（小寫）
        sub_table_name = f'{base_table_name}_items_{grid_key.lower()}'
        _validate_table_name(sub_table_name)

        # 建子表
        sql_stmts = build_create_sub_table_sql(sub_table_name, sub_columns)
        with conn.cursor() as cur:
            for stmt in sql_stmts:
                cur.execute(stmt)
        conn.commit()

        # GRANT 權限給 sync user（含 DELETE，子表同步需要）
        if sync_user:
            _grant_sub_table_permissions(conn, sub_table_name, sync_user)

        sub_mapping = build_sub_column_mapping(sub_columns)
        sub_tables[grid_key] = {
            'table_name': sub_table_name,
            'columns': sub_mapping,
        }

        logger.info(
            f'SQL Sync: 已建立子表 {sub_table_name} '
            f'({len(sub_columns)} 個欄位，grid_key={grid_key})'
        )

    return sub_tables


def upgrade_registry_sub_tables(registry, form_schema):
    """
    為已存在的 registry 補建子表（Phase 1→2 升級用）

    Phase 1 建立的 registry 沒有子表 metadata，此函式：
    1. 在企業 DB 建立缺少的子表
    2. 更新 registry.column_mapping 嵌入 sub_table 資訊
    3. 更新 registry.create_ddl

    Args:
        registry: FwSqlFormRegistry 實例
        form_schema: form.io schema dict

    Returns:
        dict: 新建的子表 {grid_key: sub_info}，空 dict 表示沒有需要建的
    """
    from app import db

    table_name = registry.table_name
    column_mapping = copy.deepcopy(registry.column_mapping or {})

    # 檢查哪些 grid 欄位還沒有 sub_table
    grids = _find_grid_components(form_schema)
    need_build = []
    for comp in grids:
        grid_key = comp.get('key')
        if not grid_key or grid_key not in column_mapping:
            continue
        if 'sub_table' in column_mapping[grid_key]:
            continue  # 已有子表
        need_build.append(comp)

    if not need_build:
        logger.info(f'SQL Sync: {table_name} 不需要補建子表')
        return {}

    # 建子表
    sync_user = _get_sync_user(registry.org_secure_code)
    new_sub_tables = {}
    with get_org_conn(registry.org_secure_code, role='admin') as conn:
        for comp in need_build:
            grid_key = comp.get('key')
            sub_columns = grid_schema_to_columns(comp)
            if not sub_columns:
                continue

            sub_table_name = f'{table_name}_items_{grid_key.lower()}'
            _validate_table_name(sub_table_name)

            # CREATE TABLE IF NOT EXISTS（冪等）
            sql_stmts = build_create_sub_table_sql(sub_table_name, sub_columns)
            with conn.cursor() as cur:
                for stmt in sql_stmts:
                    cur.execute(stmt)
            conn.commit()

            # GRANT 權限給 sync user
            if sync_user:
                _grant_sub_table_permissions(conn, sub_table_name, sync_user)

            sub_mapping = build_sub_column_mapping(sub_columns)
            sub_info = {
                'table_name': sub_table_name,
                'columns': sub_mapping,
            }
            new_sub_tables[grid_key] = sub_info

            # 嵌入 column_mapping
            column_mapping[grid_key]['sub_table'] = sub_info

            logger.info(f'SQL Sync: 補建子表 {sub_table_name} (grid_key={grid_key})')

    # 更新 registry（flag_modified 確保 SQLAlchemy 偵測到 JSON 變化）
    from sqlalchemy.orm.attributes import flag_modified
    registry.column_mapping = column_mapping
    flag_modified(registry, 'column_mapping')

    # 更新 DDL
    ddl = registry.create_ddl or ''
    for grid_key, sub_info in new_sub_tables.items():
        sub_cols_list = [
            (k, v['pg_type'], v['nullable'], v.get('is_pii', False))
            for k, v in sub_info['columns'].items()
        ]
        sub_ddl = build_create_sub_table_ddl_text(sub_info['table_name'], sub_cols_list)
        ddl += f'\n\n-- Sub-table for {grid_key}\n{sub_ddl}'
    registry.create_ddl = ddl

    db.session.commit()
    return new_sub_tables


def create_approval_table(base_table_name, conn, org_secure_code):
    """
    為主表建立 approval 子表（固定 schema）

    Args:
        base_table_name: 主表名（如 form_38_v3）
        conn: psycopg2 connection (admin 角色)
        org_secure_code: 企業 secure_code（用於查 sync_user）

    Returns:
        str: approval 子表名
    """
    approval_table = f'{base_table_name}_approvals'
    _validate_table_name(approval_table)

    sql_stmts = build_create_approval_table_sql(approval_table)
    with conn.cursor() as cur:
        for stmt in sql_stmts:
            cur.execute(stmt)
    conn.commit()

    # GRANT 權限給 sync user
    sync_user = _get_sync_user(org_secure_code)
    if sync_user:
        _grant_sub_table_permissions(conn, approval_table, sync_user)

    logger.info(f'SQL Sync: 已建立 approval 子表 {approval_table}')
    return approval_table


def upgrade_registry_approval_table(registry):
    """
    為已存在的 registry 補建 approval 子表（Phase 2→3 升級用）

    Phase 2 建立的 registry 沒有 _approval_table metadata，此函式：
    1. 在企業 DB 建立 approval 表
    2. 更新 registry.column_mapping 嵌入 _approval_table
    3. 更新 registry.create_ddl

    Args:
        registry: FwSqlFormRegistry 實例

    Returns:
        str or None: 新建的 approval 表名，None 表示已存在
    """
    from app import db

    column_mapping = copy.deepcopy(registry.column_mapping or {})

    # 已有 approval 表 metadata，跳過
    if '_approval_table' in column_mapping:
        logger.info(
            f'SQL Sync: {registry.table_name} 已有 approval 表，跳過'
        )
        return None

    approval_table = f'{registry.table_name}_approvals'

    with get_org_conn(registry.org_secure_code, role='admin') as conn:
        # 若表已存在也沒關係（CREATE IF NOT EXISTS）
        create_approval_table(
            registry.table_name, conn, registry.org_secure_code
        )

    # 更新 column_mapping
    from sqlalchemy.orm.attributes import flag_modified
    column_mapping['_approval_table'] = approval_table
    registry.column_mapping = column_mapping
    flag_modified(registry, 'column_mapping')

    # 更新 DDL
    ddl = registry.create_ddl or ''
    approval_ddl = build_create_approval_table_ddl_text(approval_table)
    ddl += f'\n\n-- Approval sub-table\n{approval_ddl}'
    registry.create_ddl = ddl

    db.session.commit()
    logger.info(
        f'SQL Sync: 已為 {registry.table_name} 補建 approval 子表'
    )
    return approval_table


def drop_sync_table(table_name, conn):
    """刪除 SQL 同步表"""
    _validate_table_name(table_name)
    with conn.cursor() as cur:
        cur.execute(
            psql.SQL('DROP TABLE IF EXISTS {}').format(
                psql.Identifier(table_name)
            )
        )
    conn.commit()
    logger.info(f'SQL Sync: 已刪除表 {table_name}')


def create_sync_table_for_published(published, form_schema, org_secure_code, mapping_id):
    """
    為發行版本建立 SQL 同步表（高層 API）

    完整流程:
    1. 計算 table_name (form_{mapping_id}_v{version})
    2. 在企業專屬 DB 建表（用 admin 連線）
    3. 在主 DB 建立 FwSqlFormRegistry 記錄

    Args:
        published: FwPublishedFormWorkflow 實例
        form_schema: form.io schema dict
        org_secure_code: 組織 secure_code
        mapping_id: FwFormWorkflowMapping.id

    Returns:
        FwSqlFormRegistry or None
    """
    from ...models.sql_form_registry import FwSqlFormRegistry
    from app import db

    table_name = make_table_name(mapping_id, published.publish_version)

    # 檢查是否已建立
    existing = FwSqlFormRegistry.query.filter_by(table_name=table_name).first()
    if existing:
        logger.info(f'SQL Sync: 表 {table_name} 的 registry 已存在，跳過')
        return existing

    # 查詢 FwFormFieldSpec（有 spec 時優先用 spec 的 pg_type 和 is_pii）
    spec_fields = None
    try:
        from ...models.form_field_spec import FwFormFieldSpec
        spec = FwFormFieldSpec.query.filter_by(
            org_secure_code=org_secure_code,
            form_template_secure_code=published.source_form_template_secure_code,
            status='active',
            is_deleted=False,
        ).first()
        if spec:
            spec_fields = spec.fields
            logger.info(f'SQL Sync: 使用 spec v{spec.version} 的型別定義建表')
    except Exception as e:
        logger.warning(f'SQL Sync: 查詢 spec 失敗（不影響建表）: {e}')

    try:
        with get_org_conn(org_secure_code, role='admin') as conn:
            columns, ddl_text = create_sync_table(
                table_name, form_schema, conn, spec_fields=spec_fields
            )

            # 建立 datagrid/editgrid 子表
            sub_tables = create_sub_tables(table_name, form_schema, conn, org_secure_code)

            # 建立 approval 子表（固定 schema）
            approval_table = create_approval_table(table_name, conn, org_secure_code)

        column_mapping = build_column_mapping(columns)

        # 將子表 metadata 嵌入對應 grid 欄位的 column_mapping
        for grid_key, sub_info in sub_tables.items():
            if grid_key in column_mapping:
                column_mapping[grid_key]['sub_table'] = sub_info

        # 嵌入 approval 表 metadata（_ 前綴為保留 metadata）
        column_mapping['_approval_table'] = approval_table

        # 合併所有子表 DDL 到 create_ddl
        all_ddl = ddl_text
        for grid_key, sub_info in sub_tables.items():
            sub_cols_list = [
                (k, v['pg_type'], v['nullable'], v.get('is_pii', False))
                for k, v in sub_info['columns'].items()
            ]
            sub_ddl = build_create_sub_table_ddl_text(sub_info['table_name'], sub_cols_list)
            all_ddl += f'\n\n-- Sub-table for {grid_key}\n{sub_ddl}'

        # Approval 子表 DDL
        approval_ddl = build_create_approval_table_ddl_text(approval_table)
        all_ddl += f'\n\n-- Approval sub-table\n{approval_ddl}'

        registry = FwSqlFormRegistry(
            org_secure_code=org_secure_code,
            mapping_secure_code=published.source_mapping_secure_code,
            published_secure_code=published.secure_code,
            form_template_secure_code=published.source_form_template_secure_code,
            table_name=table_name,
            form_version=published.source_form_version,
            publish_version=published.publish_version,
            column_mapping=column_mapping,
            status='active',
            row_count=0,
            create_ddl=all_ddl,
        )
        db.session.add(registry)
        db.session.flush()

        logger.info(f'SQL Sync: 已為發行版本建立同步表 {table_name}')
        return registry

    except Exception as e:
        logger.error(f'SQL Sync: 建表失敗 ({table_name}): {e}')
        return None
