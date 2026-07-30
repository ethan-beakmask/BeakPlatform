"""
Data CRUD Module - Schema Service
用 psycopg2 cursor 讀取資料庫表結構
"""
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 系統表前綴/名稱，不應暴露給用戶
SYSTEM_TABLE_PREFIXES = (
    'pg_', 'sql_', 'alembic_',
)
SYSTEM_TABLE_NAMES = {
    'spatial_ref_sys',
    'geography_columns',
    'geometry_columns',
    'raster_columns',
    'raster_overviews',
}

# --- 系統欄位識別 ---
# SQL Sync 產生的系統欄位（主表 + 明細子表共用）
# owner_org_code: 集團 DB RLS 隔離欄位，由系統自動填入
_SYSTEM_COLUMNS = {'id', 'form_instance_secure_code', 'row_index', 'owner_org_code', 'portal_user_ref'}

# 簽核子表後綴
_APPROVAL_TABLE_SUFFIX = '_approvals'

# PII 加密欄位的 DB 型別
_PII_DB_TYPE = 'BYTEA'


def is_approval_table(table_name: str) -> bool:
    """判斷是否為簽核記錄子表"""
    return table_name.endswith(_APPROVAL_TABLE_SUFFIX)


def classify_column(table_name: str, col_name: str, db_type: str) -> dict:
    """
    判斷欄位是否為系統欄位，回傳 is_system + system_reason

    規則:
    1. _approvals 表 → 全部欄位都是系統欄位
    2. 欄位名在 _SYSTEM_COLUMNS → 系統欄位
    3. BYTEA 型別 → PII 加密欄位，標為系統
    4. 其他 → 用戶自訂
    """
    if is_approval_table(table_name):
        return {'is_system': True, 'system_reason': 'approval_table'}

    if col_name in _SYSTEM_COLUMNS:
        return {'is_system': True, 'system_reason': 'system_column'}

    if db_type and db_type.upper() == _PII_DB_TYPE:
        return {'is_system': True, 'system_reason': 'pii_encrypted'}

    return {'is_system': False, 'system_reason': None}


class SchemaService:
    """資料庫 schema 讀取服務（接收 psycopg2 connection）"""

    @staticmethod
    def list_tables(conn) -> List[Dict]:
        """
        列出 public schema 的使用者表（排除系統表）

        Args:
            conn: psycopg2 connection

        Returns:
            [{'name': 'users', 'comment': '...'}, ...]
        """
        sql = """
            SELECT c.relname AS table_name,
                   obj_description(c.oid) AS comment
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relkind = 'r'
            ORDER BY c.relname
        """
        tables = []
        with conn.cursor() as cur:
            cur.execute(sql)
            for row in cur.fetchall():
                table_name = row[0]
                if table_name.startswith(SYSTEM_TABLE_PREFIXES):
                    continue
                if table_name in SYSTEM_TABLE_NAMES:
                    continue
                tables.append({
                    'name': table_name,
                    'comment': row[1] or '',
                    'is_approval_table': is_approval_table(table_name),
                })

        # 不要留殘餘 transaction（純 SELECT 也會開 tx）
        conn.rollback()
        return tables

    @staticmethod
    def get_columns(conn, table_name: str) -> Optional[List[Dict]]:
        """
        取得指定表的欄位結構

        Args:
            conn: psycopg2 connection
            table_name: 資料表名稱

        Returns:
            欄位列表，或 None（表不存在）
        """
        # 確認表存在
        check_sql = """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
        """
        with conn.cursor() as cur:
            cur.execute(check_sql, (table_name,))
            if cur.fetchone() is None:
                conn.rollback()
                return None

        # 取得主鍵欄位
        pk_sql = """
            SELECT a.attname
            FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            WHERE i.indrelid = %s::regclass AND i.indisprimary
        """
        pk_columns = set()
        with conn.cursor() as cur:
            cur.execute(pk_sql, (table_name,))
            for row in cur.fetchall():
                pk_columns.add(row[0])

        # 取得欄位資訊
        col_sql = """
            SELECT column_name,
                   CASE
                     WHEN character_maximum_length IS NOT NULL
                       THEN UPPER(data_type) || '(' || character_maximum_length || ')'
                     WHEN data_type = 'numeric' AND numeric_precision IS NOT NULL
                       THEN 'NUMERIC(' || numeric_precision || ',' || COALESCE(numeric_scale, 0) || ')'
                     ELSE UPPER(data_type)
                   END AS db_type,
                   is_nullable,
                   column_default
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
        """
        # 欄位 comment
        comment_sql = """
            SELECT a.attname, col_description(c.oid, a.attnum)
            FROM pg_class c
            JOIN pg_attribute a ON a.attrelid = c.oid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname = %s
              AND a.attnum > 0
              AND NOT a.attisdropped
        """

        columns = []
        comments = {}

        with conn.cursor() as cur:
            cur.execute(comment_sql, (table_name,))
            for row in cur.fetchall():
                if row[1]:
                    comments[row[0]] = row[1]

            cur.execute(col_sql, (table_name,))
            for row in cur.fetchall():
                col_name = row[0]
                db_type = row[1]
                sys_info = classify_column(table_name, col_name, db_type)
                columns.append({
                    'column': col_name,
                    'db_type': db_type,
                    'nullable': row[2] == 'YES',
                    'is_pk': col_name in pk_columns,
                    'default': row[3],
                    'comment': comments.get(col_name, ''),
                    'is_system': sys_info['is_system'],
                    'system_reason': sys_info['system_reason'],
                })

        conn.rollback()
        return columns
