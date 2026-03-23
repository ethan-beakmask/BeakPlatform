"""
Data CRUD Module - CRUD Service
用 psycopg2 cursor 參數化查詢操作目標表資料
"""
import re
import secrets
import logging
from datetime import date
from typing import Any, Dict, List, Optional

from psycopg2 import sql as psql

from .schema_service import _SYSTEM_COLUMNS, is_approval_table, _PII_DB_TYPE

logger = logging.getLogger(__name__)

# 合法的 SQL 識別符格式（支援 Unicode，psql.Identifier 會自動加引號）
IDENTIFIER_RE = re.compile(r'^\w+$', re.UNICODE)


def _validate_identifier(name: str) -> bool:
    """驗證表名/欄位名是否合法（防注入）"""
    return bool(IDENTIFIER_RE.match(name))


def resolve_filter_variables(filters: Dict[str, str], user=None) -> Dict[str, str]:
    """
    替換篩選條件中的變數佔位符

    支援的變數:
      $CURRENT_USER       → user.secure_code
      $CURRENT_USER_NAME  → user.username
      $CURRENT_ORG        → user.org_secure_code
      $TODAY              → date.today().isoformat()

    Args:
        filters: {column: value} 篩選字典
        user: 當前用戶 (flask_login current_user)，None 時嘗試 flask context

    Returns:
        替換後的篩選字典 (新 dict，不修改原始)
    """
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
            # 不認識的變數保持原值
            resolved[col] = val

    return resolved


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


def _check_required_columns(conn, table_name: str, insert_data: dict) -> List[str]:
    """
    檢查 NOT NULL 且無 DB default 的欄位是否都有值。
    回傳缺少的欄位名稱列表（空 = 通過）。
    PK 欄位通常有 sequence default，不在此檢查範圍。
    """
    sql = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
          AND is_nullable = 'NO'
          AND column_default IS NULL
    """
    missing = []
    with conn.cursor() as cur:
        cur.execute(sql, (table_name,))
        for row in cur.fetchall():
            col = row[0]
            if col not in insert_data:
                missing.append(col)
    return missing


def _auto_fill_owner_org_code(insert_data: dict):
    """
    集團 DB 寫入時自動填入 owner_org_code（RLS 依據欄位）。
    不覆蓋前端已提供的值（正常情況前端不會送此欄位）。
    """
    if 'owner_org_code' not in insert_data:
        try:
            from flask_login import current_user
            insert_data['owner_org_code'] = current_user.org_secure_code
        except RuntimeError:
            pass


def _auto_fill_system_columns(conn, table_name: str, insert_data: dict):
    """
    自動填入系統欄位（in-place 修改 insert_data）。
    沿用表單系統相同的產生方式（sync_service.py / form_center.py）。
    """
    # 查 NOT NULL 且無 DB default 的欄位
    sql = """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
          AND is_nullable = 'NO' AND column_default IS NULL
    """
    with conn.cursor() as cur:
        cur.execute(sql, (table_name,))
        required = {r[0] for r in cur.fetchall()}

    # form_instance_secure_code — 同 form_center.py
    if 'form_instance_secure_code' in required and 'form_instance_secure_code' not in insert_data:
        insert_data['form_instance_secure_code'] = secrets.token_urlsafe(16)

    # row_index — 僅子表（表名含 _items_），同 sync_service._batch_insert_sub_rows
    if 'row_index' in required and 'row_index' not in insert_data and '_items_' in table_name:
        with conn.cursor() as cur:
            cur.execute(psql.SQL('SELECT COALESCE(MAX({}), -1) + 1 FROM {}').format(
                _ident('row_index'), _ident(table_name)))
            insert_data['row_index'] = cur.fetchone()[0]


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
        dynamic_filters: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        查詢目標表的資料（分頁）

        Args:
            conn: psycopg2 connection
            view: DcCrudView instance
            dynamic_filters: 動態篩選 {column: value}，
                             由 API 層白名單驗證後傳入

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

        # 固定篩選 (支援變數替換)
        if view.fixed_filters:
            resolved_fixed = resolve_filter_variables(view.fixed_filters)
            for col, val in resolved_fixed.items():
                if _validate_identifier(col):
                    where_parts.append(
                        psql.SQL('{} = %s').format(_ident(col))
                    )
                    params.append(val)

        # 動態篩選（EventBus binding 傳入，API 層已白名單驗證）
        if dynamic_filters:
            for col, val in dynamic_filters.items():
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
    def get_row(conn, view, row_id: str) -> Dict[str, Any]:
        """
        取得單筆資料，供編輯頁載入用。

        Returns:
            {success: True, data: {col: val, ...}} 或 {success: False, error: ...}
        """
        table_name = view.table_name
        if not _validate_identifier(table_name):
            return {'success': False, 'error': 'Invalid table name'}

        row_id_col = _find_row_id_column(view)
        if not row_id_col:
            return {'success': False, 'error': 'Cannot determine row identifier'}

        # SELECT 表單可見欄位 + row_id 欄位
        form_cols = []
        for col_cfg in sorted(view.columns_config or [], key=lambda c: c.get('sort_order', 999)):
            col_name = col_cfg.get('column', '')
            if not col_name or not _validate_identifier(col_name):
                continue
            if col_cfg.get('visible_in_form', True):
                form_cols.append(col_name)

        if row_id_col not in form_cols:
            form_cols.insert(0, row_id_col)

        select_part = psql.SQL(', ').join(_ident(c) for c in form_cols)
        query = psql.SQL('SELECT {} FROM {} WHERE {} = %s LIMIT 1').format(
            select_part, _ident(table_name), _ident(row_id_col)
        )

        try:
            with conn.cursor() as cur:
                cur.execute(query, (row_id,))
                db_row = cur.fetchone()
                if not db_row:
                    conn.rollback()
                    return {'success': False, 'error': 'Row not found'}
                col_names = [desc[0] for desc in cur.description]
                row_dict = {}
                for i, val in enumerate(db_row):
                    row_dict[col_names[i]] = _serialize_value(val)
            conn.rollback()
            return {'success': True, 'data': row_dict}
        except Exception as e:
            conn.rollback()
            logger.error(f'get_row error: {e}')
            return {'success': False, 'error': str(e)}

    @staticmethod
    def create_row(conn, view, row_data: Dict,
                   is_conglomerate: bool = False) -> Dict[str, Any]:
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

        # 集團 DB: 自動填入 owner_org_code（RLS 必要欄位）
        if is_conglomerate:
            _auto_fill_owner_org_code(insert_data)

        # 自動填入系統欄位（如 form_instance_secure_code）
        _auto_fill_system_columns(conn, table_name, insert_data)

        # 預檢: NOT NULL 且無 DB default 的欄位必須有值
        missing = _check_required_columns(conn, table_name, insert_data)
        if missing:
            names = ', '.join(sorted(missing))
            return {'success': False, 'error': f'必填欄位缺少值且無法自動填入: {names}'}

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
    def update_row(conn, view, row_id: str, row_data: Dict,
                   is_conglomerate: bool = False) -> Dict[str, Any]:
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

        # 禁止修改 owner_org_code（集團 DB RLS 欄位）
        update_data.pop('owner_org_code', None)

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
                    # 集團 DB: RLS 可能靜默拒絕非本企業的 row
                    if is_conglomerate:
                        return {
                            'success': False,
                            'error': '找不到資料，或該筆資料屬於其他企業無法修改',
                        }
                    return {'success': False, 'error': 'Row not found'}
            conn.commit()
            return {'success': True, 'message': 'Row updated'}
        except Exception as e:
            conn.rollback()
            logger.error(f'update_row error: {e}')
            return {'success': False, 'error': str(e)}

    @staticmethod
    def delete_row(conn, view, row_id: str,
                   is_conglomerate: bool = False) -> Dict[str, Any]:
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
                    if is_conglomerate:
                        return {
                            'success': False,
                            'error': '找不到資料，或該筆資料屬於其他企業無法刪除',
                        }
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
