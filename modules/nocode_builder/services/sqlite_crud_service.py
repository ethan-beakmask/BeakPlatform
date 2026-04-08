"""
Data CRUD Module - SQLite CRUD Service
用 SQLAlchemy session.execute(text()) 操作 SQLite 資料表

與 CrudService 相同介面，但:
  - 用 SQLAlchemy text() + bindparam 取代 psycopg2 composable SQL
  - ILIKE → LIKE (SQLite 預設不區分大小寫)
  - 不支援 information_schema (用 PRAGMA table_info 取代)
  - 不支援 RETURNING (用 lastrowid)
  - 識別符用雙引號包裹 (SQLite 標準)
"""
import re
import logging
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

# 合法 SQL 識別符
IDENTIFIER_RE = re.compile(r'^\w+$', re.UNICODE)


def _validate_identifier(name: str) -> bool:
    """驗證表名/欄位名是否合法（防注入）"""
    return bool(IDENTIFIER_RE.match(name))


def _quote(name: str) -> str:
    """安全引用識別符 (double-quote for SQLite)"""
    if not _validate_identifier(name):
        raise ValueError(f'Invalid identifier: {name}')
    return f'"{name}"'


def _serialize_value(val):
    """將 DB 值序列化為 JSON 相容格式"""
    if val is None:
        return None
    if isinstance(val, (int, float, bool, str)):
        return val
    if isinstance(val, bytes):
        return val.hex()
    from datetime import datetime, date as date_type, time
    from decimal import Decimal
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, date_type):
        return val.isoformat()
    if isinstance(val, time):
        return val.isoformat()
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, (dict, list)):
        return val
    return str(val)


# ── 系統欄位識別 (同 crud_service) ──
_SYSTEM_COLUMNS = {'id', 'form_instance_secure_code', 'row_index', 'owner_org_code'}


def _is_system_column(col_cfg: dict) -> bool:
    """判斷欄位是否為系統欄位"""
    col_name = col_cfg.get('column', '')
    if col_name in _SYSTEM_COLUMNS:
        return True
    if col_cfg.get('is_system', False):
        return True
    return False


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


def _get_writable_columns(view) -> List[str]:
    """從視圖配置取得可寫入的欄位列表"""
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
        if _is_system_column(col_cfg):
            continue
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
    """決定 row_id 用哪個欄位"""
    cols_config = view.columns_config or []
    col_names = [c.get('column') for c in cols_config]
    if 'secure_code' in col_names:
        return 'secure_code'
    for c in cols_config:
        if c.get('is_pk'):
            return c.get('column')
    return None


def resolve_filter_variables(filters: Dict[str, str], user=None) -> Dict[str, str]:
    """替換篩選條件中的變數佔位符 ($CURRENT_USER 等)"""
    if not filters:
        return {}

    if user is None:
        try:
            from flask_login import current_user
            user = current_user
        except RuntimeError:
            pass

    resolved = {}
    for col, val in filters.items():
        if not isinstance(val, str) or not val.startswith('$'):
            resolved[col] = val
            continue
        if val == '$CURRENT_USER' and user:
            resolved[col] = user.secure_code
        elif val == '$CURRENT_USER_NAME' and user:
            resolved[col] = getattr(user, 'username', '')
        elif val == '$CURRENT_ORG' and user:
            resolved[col] = getattr(user, 'org_secure_code', '')
        elif val == '$TODAY':
            resolved[col] = date.today().isoformat()
        else:
            resolved[col] = val
    return resolved


class SqliteCrudService:
    """SQLite 動態 CRUD 操作服務 (接收 SQLAlchemy Session)"""

    @staticmethod
    def query_rows(
        session,
        view,
        page: int = 1,
        per_page: int = 20,
        search: str = '',
        sort_column: Optional[str] = None,
        sort_dir: str = 'ASC',
        dynamic_filters: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """查詢目標表的資料（分頁）"""
        table_name = view.table_name
        if not _validate_identifier(table_name):
            return {'rows': [], 'total': 0, 'page': 1, 'pages': 0, 'per_page': per_page}

        visible_cols = _get_visible_columns(view)
        row_id_col = _find_row_id_column(view)

        if row_id_col and row_id_col not in visible_cols:
            visible_cols.insert(0, row_id_col)

        select_part = ', '.join(_quote(c) for c in visible_cols) if visible_cols else '*'
        tbl = _quote(table_name)

        # WHERE 條件
        where_parts = []
        params = {}
        param_idx = 0

        # 軟刪除過濾
        if view.soft_delete_column and _validate_identifier(view.soft_delete_column):
            where_parts.append(f'{_quote(view.soft_delete_column)} = 0')

        # 固定篩選
        if view.fixed_filters:
            resolved_fixed = resolve_filter_variables(view.fixed_filters)
            for col, val in resolved_fixed.items():
                if _validate_identifier(col):
                    pname = f'ff_{param_idx}'
                    where_parts.append(f'{_quote(col)} = :{pname}')
                    params[pname] = val
                    param_idx += 1

        # 動態篩選
        if dynamic_filters:
            for col, val in dynamic_filters.items():
                if _validate_identifier(col):
                    pname = f'df_{param_idx}'
                    where_parts.append(f'{_quote(col)} = :{pname}')
                    params[pname] = val
                    param_idx += 1

        # 搜尋 (SQLite LIKE 預設不區分大小寫)
        if search:
            searchable = _get_searchable_columns(view)
            if searchable:
                search_clauses = []
                for col in searchable:
                    pname = f'sq_{param_idx}'
                    search_clauses.append(f'{_quote(col)} LIKE :{pname}')
                    params[pname] = f'%{search}%'
                    param_idx += 1
                where_parts.append(f'({" OR ".join(search_clauses)})')

        where_sql = ''
        if where_parts:
            where_sql = ' WHERE ' + ' AND '.join(where_parts)

        # COUNT
        count_sql = f'SELECT COUNT(*) FROM {tbl}{where_sql}'
        total = session.execute(text(count_sql), params).scalar() or 0

        pages = max(1, (total + per_page - 1) // per_page)
        page = max(1, min(page, pages))

        # ORDER BY
        order_sql = ''
        if sort_column and _validate_identifier(sort_column):
            direction = 'DESC' if sort_dir.upper() == 'DESC' else 'ASC'
            order_sql = f' ORDER BY {_quote(sort_column)} {direction}'

        # LIMIT / OFFSET
        offset = (page - 1) * per_page
        limit_sql = f' LIMIT :_limit OFFSET :_offset'
        params['_limit'] = per_page
        params['_offset'] = offset

        full_sql = f'SELECT {select_part} FROM {tbl}{where_sql}{order_sql}{limit_sql}'
        result = session.execute(text(full_sql), params)
        col_names = list(result.keys())

        rows = []
        for db_row in result.fetchall():
            row_dict = {}
            for i, val in enumerate(db_row):
                row_dict[col_names[i]] = _serialize_value(val)
            if row_id_col and row_id_col in row_dict:
                row_dict['_row_id'] = str(row_dict[row_id_col])
            rows.append(row_dict)

        return {
            'rows': rows,
            'total': total,
            'page': page,
            'pages': pages,
            'per_page': per_page,
            'row_id_column': row_id_col,
        }

    @staticmethod
    def get_row(session, view, row_id: str) -> Dict[str, Any]:
        """取得單筆資料"""
        table_name = view.table_name
        if not _validate_identifier(table_name):
            return {'success': False, 'error': 'Invalid table name'}

        row_id_col = _find_row_id_column(view)
        if not row_id_col:
            return {'success': False, 'error': 'Cannot determine row identifier'}

        form_cols = []
        for col_cfg in sorted(view.columns_config or [], key=lambda c: c.get('sort_order', 999)):
            col_name = col_cfg.get('column', '')
            if not col_name or not _validate_identifier(col_name):
                continue
            if col_cfg.get('visible_in_form', True):
                form_cols.append(col_name)

        if row_id_col not in form_cols:
            form_cols.insert(0, row_id_col)

        select_part = ', '.join(_quote(c) for c in form_cols)
        sql = f'SELECT {select_part} FROM {_quote(table_name)} WHERE {_quote(row_id_col)} = :rid LIMIT 1'

        try:
            result = session.execute(text(sql), {'rid': row_id})
            db_row = result.fetchone()
            if not db_row:
                return {'success': False, 'error': 'Row not found'}
            col_names = list(result.keys())
            row_dict = {}
            for i, val in enumerate(db_row):
                row_dict[col_names[i]] = _serialize_value(val)
            return {'success': True, 'data': row_dict}
        except Exception as e:
            logger.error('sqlite get_row error: %s', e)
            return {'success': False, 'error': str(e)}

    @staticmethod
    def create_row(session, view, row_data: Dict) -> Dict[str, Any]:
        """新增一筆資料"""
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
        col_quoted = ', '.join(_quote(c) for c in cols)
        placeholders = ', '.join(f':v_{i}' for i in range(len(cols)))
        params = {f'v_{i}': insert_data[c] for i, c in enumerate(cols)}

        sql = f'INSERT INTO {_quote(table_name)} ({col_quoted}) VALUES ({placeholders})'

        try:
            session.execute(text(sql), params)
            session.flush()
            return {'success': True, 'message': 'Row created'}
        except Exception as e:
            logger.error('sqlite create_row error: %s', e)
            return {'success': False, 'error': str(e)}

    @staticmethod
    def update_row(session, view, row_id: str, row_data: Dict) -> Dict[str, Any]:
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
        set_clause = ', '.join(f'{_quote(c)} = :u_{i}' for i, c in enumerate(cols))
        params = {f'u_{i}': update_data[c] for i, c in enumerate(cols)}
        params['_rid'] = row_id

        sql = f'UPDATE {_quote(table_name)} SET {set_clause} WHERE {_quote(row_id_col)} = :_rid'

        try:
            result = session.execute(text(sql), params)
            if result.rowcount == 0:
                return {'success': False, 'error': 'Row not found'}
            session.flush()
            return {'success': True, 'message': 'Row updated'}
        except Exception as e:
            logger.error('sqlite update_row error: %s', e)
            return {'success': False, 'error': str(e)}

    @staticmethod
    def delete_row(session, view, row_id: str) -> Dict[str, Any]:
        """刪除一筆資料（軟刪除或物理刪除）"""
        table_name = view.table_name
        if not _validate_identifier(table_name):
            return {'success': False, 'error': 'Invalid table name'}

        row_id_col = _find_row_id_column(view)
        if not row_id_col:
            return {'success': False, 'error': 'Cannot determine row identifier'}

        if view.soft_delete_column and _validate_identifier(view.soft_delete_column):
            sql = (
                f'UPDATE {_quote(table_name)} '
                f'SET {_quote(view.soft_delete_column)} = 1 '
                f'WHERE {_quote(row_id_col)} = :_rid'
            )
        else:
            sql = f'DELETE FROM {_quote(table_name)} WHERE {_quote(row_id_col)} = :_rid'

        try:
            result = session.execute(text(sql), {'_rid': row_id})
            if result.rowcount == 0:
                return {'success': False, 'error': 'Row not found'}
            session.flush()
            return {'success': True, 'message': 'Row deleted'}
        except Exception as e:
            logger.error('sqlite delete_row error: %s', e)
            return {'success': False, 'error': str(e)}


class SqliteSchemaService:
    """SQLite 表結構讀取服務 (接收 SQLAlchemy Session)"""

    @staticmethod
    def list_tables(session) -> List[Dict]:
        """列出 SQLite 的使用者表 (排除 sqlite 內部表)"""
        sql = """
            SELECT name FROM sqlite_master
            WHERE type='table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """
        result = session.execute(text(sql))
        tables = []
        for row in result.fetchall():
            tables.append({
                'name': row[0],
                'comment': '',
                'is_approval_table': False,
            })
        return tables

    @staticmethod
    def get_columns(session, table_name: str) -> Optional[List[Dict]]:
        """取得指定表的欄位結構 (PRAGMA table_info)"""
        if not _validate_identifier(table_name):
            return None

        # 確認表存在
        check = session.execute(
            text("SELECT 1 FROM sqlite_master WHERE type='table' AND name = :tbl"),
            {'tbl': table_name}
        ).fetchone()
        if not check:
            return None

        # PRAGMA table_info 回傳:
        # cid, name, type, notnull, dflt_value, pk
        rows = session.execute(text(f'PRAGMA table_info({_quote(table_name)})')).fetchall()

        columns = []
        for row in rows:
            col_name = row[1]
            db_type = (row[2] or 'TEXT').upper()
            is_pk = bool(row[5])

            columns.append({
                'column': col_name,
                'db_type': db_type,
                'nullable': not bool(row[3]),
                'is_pk': is_pk,
                'default': row[4],
                'comment': '',
                'is_system': col_name in _SYSTEM_COLUMNS,
                'system_reason': 'system_column' if col_name in _SYSTEM_COLUMNS else None,
            })

        return columns
