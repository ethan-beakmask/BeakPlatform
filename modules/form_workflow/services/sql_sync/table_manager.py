"""
SQL Sync — 表管理器

在企業專屬 DB (org_{id}) 中建立/刪除/檢查 SQL 同步表。
使用 admin 角色連線執行 DDL。
"""
import re
import logging

from psycopg2 import sql as psql

from .converter import (
    schema_to_columns,
    build_column_mapping,
    build_create_table_sql,
    build_create_table_ddl_text,
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


def create_sync_table(table_name, form_schema, conn):
    """
    在企業 DB 建立 SQL 同步表

    Args:
        table_name: 表名
        form_schema: form.io schema dict
        conn: psycopg2 connection (admin 角色)

    Returns:
        tuple: (columns, ddl_text)
    """
    _validate_table_name(table_name)

    columns = schema_to_columns(form_schema)
    if not columns:
        raise ValueError('form.io schema 中沒有可同步的資料欄位')

    create_sql = build_create_table_sql(table_name, columns)
    ddl_text = build_create_table_ddl_text(table_name, columns)

    with conn.cursor() as cur:
        cur.execute(create_sql)
    conn.commit()

    logger.info(f'SQL Sync: 已建立表 {table_name} ({len(columns)} 個動態欄位)')
    return columns, ddl_text


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

    try:
        with get_org_conn(org_secure_code, role='admin') as conn:
            columns, ddl_text = create_sync_table(table_name, form_schema, conn)

        column_mapping = build_column_mapping(columns)

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
            create_ddl=ddl_text,
        )
        db.session.add(registry)
        db.session.flush()

        logger.info(f'SQL Sync: 已為發行版本建立同步表 {table_name}')
        return registry

    except Exception as e:
        logger.error(f'SQL Sync: 建表失敗 ({table_name}): {e}')
        return None
