"""
Data CRUD Module - CRUD Service
用 psycopg2 cursor 參數化查詢操作目標表資料
"""
import re
import logging
from typing import Any, Dict, List, Optional

from psycopg2 import sql as psql

from .schema_service import _SYSTEM_COLUMNS, is_approval_table, _PII_DB_TYPE

logger = logging.getLogger(__name__)

# 合法的 SQL 識別符格式
IDENTIFIER_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


def _validate_identifier(name: str) -> bool:
    """驗證表名/欄位名是否合法（防注入）"""
    return bool(IDENTIFIER_RE.match(name))


def _is_system_column(table_name: str, col_cfg: dict) -> bool:
    """伺服器端判斷欄位是否為系統欄位（不信任前端 config）"""
    col_name = col_cfg.get('column', '')
    # 規則 1: 簽核表全部欄位都是系統欄位
    if is_approval_table(table_name):
        return True
    # 規則 2: 系統欄位名
    if col_name in _SYSTEM_COLUMNS:
        return True
    # 規則 3: BYTEA = PII 加密
    db_type = (col_cfg.get('db_type') or '').upper()
    if db_type == _PII_DB_TYPE:
        return True
    return False


def _get_writable_columns(view) -> List[str]:
    """
    從視圖配置取得可寫入的欄位列表
    排除 PK、readonly、系統欄位
    """
    table_name = view.table_name or ''
    columns = []
    for col_cfg in (view.columns_config or []):
        col_name = col_cfg.get('column', '')
        if not col_name or not _validate_identifier(col_name):
            continue
        if col_cfg.get('is_pk', False):
            continue
        if col_cfg.get('readonly', False):
            continue
        if not col_cfg.get('visible_in_form', True):
            continue
        # 伺服器端強制: 系統欄位不可寫入
        if _is_system_column(table_name, col_cfg):
            continue
        columns.append(col_name)
    return columns


def _get_visible_columns(view) -> List[str]:
    """從視圖配置取得可見欄位列表"""
    columns = []
    for col_cfg in sorted(view.columns_config or [], key=lambda c: c.get('sort_order', 999)):
        col_name = col_cfg.get('column', '')
        if not col_name or not _validate_identifier(col_name):
            continue
        if col_cfg.get('visible', True):
            columns.append(col_name)
    return columns


def _get_searchable_columns(view) -> List[str]:
    """取得可搜尋的文字類型欄位"""
    text_types = ('VARCHAR', 'TEXT', 'CHAR', 'CHARACTER')
    columns = []
    for col_cfg in (view.columns_config or []):
        col_name = col_cfg.get('column', '')
        if not col_name or not _validate_identifier(col_name):
            continue
        db_type = (col_cfg.get('db_type') or '').upper()
        if any(t in db_type for t in text_types):
            columns.append(col_name)
    return columns


def _find_row_id_column(view) -> Optional[str]:
    """
    決定 row_id 用哪個欄位。
    優先找 secure_code，無則用主鍵。
    """
    cols_config = view.columns_config or []
    col_names = [c.get('column') for c in cols_config]

    if 'secure_code' in col_names:
        return 'secure_code'

    for c in cols_config:
        if c.get('is_pk'):
            return c.get('column')

    return None


def _ident(name: str) -> psql.Identifier:
    """建立 psycopg2 safe identifier"""
    return psql.Identifier(name)


class CrudService:
    """動態 CRUD 操作服務（接收 psycopg2 connection）"""

    @staticmethod
    def query_rows(
        conn,
        view,
        page: int = 1,
        per_page: int = 20,
        search: str = '',
        sort_column: Optional[str] = None,
        sort_dir: str = 'ASC',
    ) -> Dict[str, Any]:
        """
        查詢目標表的資料（分頁）

        Args:
            conn: psycopg2 connection
            view: DcCrudView instance

        Returns:
            {rows: [...], total: N, page: N, pages: N, per_page: N}
        """
        table_name = view.table_name
        if not _validate_identifier(table_name):
            return {'rows': [], 'total': 0, 'page': 1, 'pages': 0, 'per_page': per_page}

        # 決定要 SELECT 的欄位
        visible_cols = _get_visible_columns(view)
        row_id_col = _find_row_id_column(view)

        if row_id_col and row_id_col not in visible_cols:
            visible_cols.insert(0, row_id_col)

        if not visible_cols:
            select_part = psql.SQL('*')
        else:
            select_part = psql.SQL(', ').join(_ident(c) for c in visible_cols)

        table_ident = _ident(table_name)

        # WHERE 條件
        where_parts = []
        params = []

        # 軟刪除過濾
        if view.soft_delete_column and _validate_identifier(view.soft_delete_column):
            where_parts.append(
                psql.SQL('{} = FALSE').format(_ident(view.soft_delete_column))
            )

        # 固定篩選
        if view.fixed_filters:
            for col, val in view.fixed_filters.items():
                if _validate_identifier(col):
                    where_parts.append(
                        psql.SQL('{} = %s').format(_ident(col))
                    )
                    params.append(val)

        # 搜尋
        if search:
            searchable = _get_searchable_columns(view)
            if searchable:
                search_clauses = []
                for col in searchable:
                    search_clauses.append(
                        psql.SQL('{} ILIKE %s').format(_ident(col))
                    )
                    params.append(f'%{search}%')
                where_parts.append(
                    psql.SQL('({})').format(psql.SQL(' OR ').join(search_clauses))
                )

        where_sql = psql.SQL('')
        if where_parts:
            where_sql = psql.SQL(' WHERE ') + psql.SQL(' AND ').join(where_parts)

        # COUNT
        count_query = psql.SQL('SELECT COUNT(*) FROM {}').format(table_ident) + where_sql

        with conn.cursor() as cur:
            cur.execute(count_query, params)
            total = cur.fetchone()[0] or 0

        pages = max(1, (total + per_page - 1) // per_page)
        page = max(1, min(page, pages))

        # ORDER BY
        order_sql = psql.SQL('')
        if sort_column and _validate_identifier(sort_column):
            direction = psql.SQL('DESC') if sort_dir.upper() == 'DESC' else psql.SQL('ASC')
            order_sql = psql.SQL(' ORDER BY {} ').format(_ident(sort_column)) + direction

        # LIMIT / OFFSET
        offset = (page - 1) * per_page
        limit_sql = psql.SQL(' LIMIT %s OFFSET %s')
        query_params = params + [per_page, offset]

        full_query = (
            psql.SQL('SELECT {} FROM {}').format(select_part, table_ident)
            + where_sql + order_sql + limit_sql
        )

        with conn.cursor() as cur:
            cur.execute(full_query, query_params)
            col_names = [desc[0] for desc in cur.description]
            rows = []
            for db_row in cur.fetchall():
                row_dict = {}
                for i, val in enumerate(db_row):
                    row_dict[col_names[i]] = _serialize_value(val)
                if row_id_col and row_id_col in row_dict:
                    row_dict['_row_id'] = str(row_dict[row_id_col])
                rows.append(row_dict)

        conn.rollback()  # 結束 read-only transaction

        return {
            'rows': rows,
            'total': total,
            'page': page,
            'pages': pages,
            'per_page': per_page,
            'row_id_column': row_id_col,
        }

    @staticmethod
    def create_row(conn, view, row_data: Dict) -> Dict[str, Any]:
        """新增一筆資料到目標表"""
        table_name = view.table_name
        if not _validate_identifier(table_name):
            return {'success': False, 'error': 'Invalid table name'}

        writable = _get_writable_columns(view)
        if not writable:
            return {'success': False, 'error': 'No writable columns configured'}

        insert_data = {}
        for col in writable:
            if col in row_data:
                insert_data[col] = row_data[col]

        if not insert_data:
            return {'success': False, 'error': 'No valid data provided'}

        cols = list(insert_data.keys())
        col_idents = psql.SQL(', ').join(_ident(c) for c in cols)
        placeholders = psql.SQL(', ').join(psql.Placeholder() for _ in cols)
        values = [insert_data[c] for c in cols]

        query = psql.SQL('INSERT INTO {} ({}) VALUES ({})').format(
            _ident(table_name), col_idents, placeholders
        )

        try:
            with conn.cursor() as cur:
                cur.execute(query, values)
            conn.commit()
            return {'success': True, 'message': 'Row created'}
        except Exception as e:
            conn.rollback()
            logger.error(f'create_row error: {e}')
            return {'success': False, 'error': str(e)}

    @staticmethod
    def update_row(conn, view, row_id: str, row_data: Dict) -> Dict[str, Any]:
        """更新一筆資料"""
        table_name = view.table_name
        if not _validate_identifier(table_name):
            return {'success': False, 'error': 'Invalid table name'}

        row_id_col = _find_row_id_column(view)
        if not row_id_col:
            return {'success': False, 'error': 'Cannot determine row identifier'}

        writable = _get_writable_columns(view)
        if not writable:
            return {'success': False, 'error': 'No writable columns configured'}

        update_data = {}
        for col in writable:
            if col in row_data:
                update_data[col] = row_data[col]

        if not update_data:
            return {'success': False, 'error': 'No valid data provided'}

        cols = list(update_data.keys())
        set_clause = psql.SQL(', ').join(
            psql.SQL('{} = %s').format(_ident(c)) for c in cols
        )
        values = [update_data[c] for c in cols]
        values.append(row_id)

        query = psql.SQL('UPDATE {} SET {} WHERE {} = %s').format(
            _ident(table_name), set_clause, _ident(row_id_col)
        )

        try:
            with conn.cursor() as cur:
                cur.execute(query, values)
                if cur.rowcount == 0:
                    conn.rollback()
                    return {'success': False, 'error': 'Row not found'}
            conn.commit()
            return {'success': True, 'message': 'Row updated'}
        except Exception as e:
            conn.rollback()
            logger.error(f'update_row error: {e}')
            return {'success': False, 'error': str(e)}

    @staticmethod
    def delete_row(conn, view, row_id: str) -> Dict[str, Any]:
        """刪除一筆資料（軟刪除或物理刪除）"""
        table_name = view.table_name
        if not _validate_identifier(table_name):
            return {'success': False, 'error': 'Invalid table name'}

        row_id_col = _find_row_id_column(view)
        if not row_id_col:
            return {'success': False, 'error': 'Cannot determine row identifier'}

        if view.soft_delete_column and _validate_identifier(view.soft_delete_column):
            query = psql.SQL('UPDATE {} SET {} = TRUE WHERE {} = %s').format(
                _ident(table_name),
                _ident(view.soft_delete_column),
                _ident(row_id_col),
            )
        else:
            query = psql.SQL('DELETE FROM {} WHERE {} = %s').format(
                _ident(table_name), _ident(row_id_col)
            )

        try:
            with conn.cursor() as cur:
                cur.execute(query, (row_id,))
                if cur.rowcount == 0:
                    conn.rollback()
                    return {'success': False, 'error': 'Row not found'}
            conn.commit()
            return {'success': True, 'message': 'Row deleted'}
        except Exception as e:
            conn.rollback()
            logger.error(f'delete_row error: {e}')
            return {'success': False, 'error': str(e)}


def _serialize_value(val):
    """將 DB 值序列化為 JSON 相容格式"""
    if val is None:
        return None
    if isinstance(val, (int, float, bool, str)):
        return val
    if isinstance(val, bytes):
        return val.hex()
    from datetime import datetime, date, time
    from decimal import Decimal
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, date):
        return val.isoformat()
    if isinstance(val, time):
        return val.isoformat()
    if isinstance(val, Decimal):
        return float(val)
    # dict/list (JSONB) 已經是 Python 原生
    if isinstance(val, (dict, list)):
        return val
    return str(val)
