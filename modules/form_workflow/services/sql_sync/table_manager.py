"""
SQL Sync — 表管理器

在 beakform_data DB 中建立/刪除/檢查 SQL 同步表。
"""
import logging

from psycopg2 import sql as psql

from .converter import (
    schema_to_columns,
    build_column_mapping,
    build_create_table_sql,
    build_create_table_ddl_text,
)
from .pool import get_conn, is_pool_ready

logger = logging.getLogger(__name__)

# 安全前綴檢查
TABLE_PREFIX = 'fw_data_'


def _validate_table_name(table_name):
    """驗證表名符合前綴規則"""
    if not table_name.startswith(TABLE_PREFIX):
        raise ValueError(f'表名必須以 {TABLE_PREFIX} 開頭: {table_name}')
    # 只允許英數底線
    import re
    if not re.match(r'^[a-z0-9_]+$', table_name):
        raise ValueError(f'表名只允許小寫英數和底線: {table_name}')


def make_table_name(form_template_secure_code, publish_version):
    """
    計算 SQL 同步表名

    格式: fw_data_{form_template_secure_code前8字元}_v{publish_version}

    Args:
        form_template_secure_code: 表單模板 secure_code
        publish_version: 發行版本號

    Returns:
        str: 表名
    """
    # secure_code 可能含 - _ 等字元，統一轉小寫並只取英數
    import re
    safe_code = re.sub(r'[^a-z0-9]', '', form_template_secure_code.lower())[:8]
    return f'{TABLE_PREFIX}{safe_code}_v{publish_version}'


def table_exists(table_name, conn):
    """
    檢查表是否存在於 beakform_data

    Args:
        table_name: 表名
        conn: psycopg2 connection

    Returns:
        bool
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = %s)",
            (table_name,)
        )
        return cur.fetchone()[0]


def create_sync_table(table_name, form_schema, conn):
    """
    在 beakform_data DB 建立 SQL 同步表

    Args:
        table_name: 表名（已驗證前綴）
        form_schema: form.io schema dict
        conn: psycopg2 connection

    Returns:
        tuple: (columns, ddl_text) — columns 為 [(key, pg_type, nullable)]
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
    """
    刪除 SQL 同步表

    Args:
        table_name: 表名
        conn: psycopg2 connection
    """
    _validate_table_name(table_name)

    with conn.cursor() as cur:
        cur.execute(
            psql.SQL('DROP TABLE IF EXISTS {}').format(
                psql.Identifier(table_name)
            )
        )
    conn.commit()
    logger.info(f'SQL Sync: 已刪除表 {table_name}')


def create_sync_table_for_published(published, form_schema, org_secure_code):
    """
    為發行版本建立 SQL 同步表（高層 API）

    完整流程:
    1. 計算 table_name
    2. 在 beakform_data 建表
    3. 在主 DB 建立 FwSqlFormRegistry 記錄

    Args:
        published: FwPublishedFormWorkflow 實例
        form_schema: form.io schema dict
        org_secure_code: 組織 secure_code

    Returns:
        FwSqlFormRegistry or None
    """
    if not is_pool_ready():
        logger.warning('SQL Sync: 連線池未初始化，跳過建表')
        return None

    from ...models.sql_form_registry import FwSqlFormRegistry
    from app import db

    table_name = make_table_name(
        published.source_form_template_secure_code,
        published.publish_version,
    )

    # 檢查是否已建立
    existing = FwSqlFormRegistry.query.filter_by(table_name=table_name).first()
    if existing:
        logger.info(f'SQL Sync: 表 {table_name} 的 registry 已存在，跳過')
        return existing

    try:
        with get_conn() as conn:
            columns, ddl_text = create_sync_table(table_name, form_schema, conn)

        column_mapping = build_column_mapping(columns)

        # 在主 DB 建立登記記錄
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
        # 不 commit — 讓呼叫者統一 commit
        db.session.flush()

        logger.info(f'SQL Sync: 已為發行版本建立同步表 {table_name}')
        return registry

    except Exception as e:
        logger.error(f'SQL Sync: 建表失敗 ({table_name}): {e}')
        return None
