"""
Data CRUD Module - DataBridgeService
PG <-> SQLite 資料橋接服務

職責:
  - publish: PG -> SQLite (INSERT，簽核通過後發布公開資料)
  - update:  PG -> SQLite (UPSERT，更新已發布的公開資料)
  - collect: SQLite -> PG (受限回收，如問卷填答結果)
  - execute_rule: 依 bridge_rule 定義執行橋接
  - 所有操作寫入 dc_bridge_logs 審計日誌

設計原則:
  - 內 -> 外為主要方向 (PG -> SQLite)
  - 外 -> 內有限制 (只允許特定 context)
  - SQLite 注意: 不用 RETURNING / JSON 需 dumps/loads / 時間用 UTC ISO / WAL 下短鎖
"""
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from flask_babel import gettext as _
from sqlalchemy import text

from app import db
from app.utils.security import generate_secure_code

logger = logging.getLogger(__name__)

# 合法的 SQL 識別符（防注入）
_IDENT_RE = re.compile(r'^[A-Za-z_]\w*$')

# collect 方向允許的 context（限制外 -> 內寫入範圍）
ALLOWED_COLLECT_CONTEXTS = frozenset({
    'survey_response',
    'registration',
    'feedback',
})

# bridge_rule 必要欄位
_REQUIRED_RULE_FIELDS = {
    'source_db', 'source_table', 'target_db', 'target_table',
    'field_mapping', 'trigger_type',
}


def _validate_ident(name: str) -> bool:
    """驗證表名/欄位名是否合法"""
    return bool(_IDENT_RE.match(name))


def _utc_now_iso() -> str:
    """UTC ISO 時間字串"""
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _serialize_for_sqlite(value: Any) -> Any:
    """將 Python 值序列化為 SQLite 可存入的格式"""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%dT%H:%M:%SZ')
    if isinstance(value, bool):
        return 1 if value else 0
    return value


def _deserialize_from_sqlite(value: Any, pg_hint: str = None) -> Any:
    """將 SQLite 取出的值還原為 Python 物件"""
    if value is None:
        return None
    if isinstance(value, str) and value.startswith(('{', '[')):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            pass
    return value


class DataBridgeService:
    """PG <-> SQLite 資料橋接服務"""

    def __init__(self):
        from .data_source_manager import DataSourceManager
        self._dsm = DataSourceManager()

    # =====================================================================
    #  publish: PG -> SQLite (INSERT)
    # =====================================================================
    def publish(
        self,
        sub_system_sc: str,
        source_table: str,
        target_table: str,
        record_key: Dict[str, Any],
        field_mapping: Dict[str, str],
        *,
        org_secure_code: str,
        operator_sc: str = None,
        rule_id: str = None,
    ) -> Dict[str, Any]:
        """
        從 PG 讀取指定記錄，依 field_mapping 轉換後 INSERT 到 SQLite portal_data.db

        Args:
            sub_system_sc: 子系統 secure_code
            source_table: PG 來源表名
            target_table: SQLite 目標表名
            record_key: 來源記錄主鍵條件 e.g. {'secure_code': 'abc123'}
            field_mapping: {pg_col: sqlite_col} 欄位對應
            org_secure_code: 企業 secure_code (PG 連線用)
            operator_sc: 操作者 secure_code
            rule_id: 關聯的橋接規則 ID

        Returns:
            {success: bool, message: str, records_affected: int}
        """
        if not self._validate_params(source_table, target_table, field_mapping):
            return {'success': False, 'error': _('參數驗證失敗: 表名或欄位名不合法')}

        if not record_key:
            return {'success': False, 'error': _('record_key 不可為空')}

        try:
            # Step 1: 從 PG 讀取來源記錄
            pg_rows = self._read_from_pg(
                org_secure_code, source_table, record_key, list(field_mapping.keys())
            )
            if not pg_rows:
                return {'success': False, 'error': _('來源記錄不存在')}

            # Step 2: 轉換欄位並寫入 SQLite
            affected = 0
            with self._dsm.get_session(sub_system_sc, 'portal_data') as session:
                for row in pg_rows:
                    mapped = self._map_fields(row, field_mapping)
                    mapped['_bridge_published_at'] = _utc_now_iso()
                    self._sqlite_insert(session, target_table, mapped)
                    affected += 1

            # Step 3: 寫入審計日誌
            self._write_log(
                org_secure_code=org_secure_code,
                sub_system_sc=sub_system_sc,
                rule_id=rule_id,
                direction='publish',
                source_db='org',
                source_table=source_table,
                target_db='portal_data',
                target_table=target_table,
                record_key=record_key,
                records_affected=affected,
                field_mapping=field_mapping,
                status='success',
                operator_sc=operator_sc,
            )

            return {
                'success': True,
                'message': _('已發布 %(affected)s 筆記錄', affected=affected),
                'records_affected': affected,
            }

        except Exception as e:
            logger.error('publish failed: %s', e, exc_info=True)
            self._write_log(
                org_secure_code=org_secure_code,
                sub_system_sc=sub_system_sc,
                rule_id=rule_id,
                direction='publish',
                source_db='org',
                source_table=source_table,
                target_db='portal_data',
                target_table=target_table,
                record_key=record_key,
                records_affected=0,
                field_mapping=field_mapping,
                status='failed',
                error_message=str(e),
                operator_sc=operator_sc,
            )
            return {'success': False, 'error': str(e)}

    # =====================================================================
    #  update: PG -> SQLite (UPSERT)
    # =====================================================================
    def update(
        self,
        sub_system_sc: str,
        source_table: str,
        target_table: str,
        record_key: Dict[str, Any],
        field_mapping: Dict[str, str],
        *,
        org_secure_code: str,
        key_field: str = 'secure_code',
        operator_sc: str = None,
        rule_id: str = None,
    ) -> Dict[str, Any]:
        """
        從 PG 讀取記錄，UPSERT 到 SQLite portal_data.db
        先查 SQLite 是否已有記錄 -> UPDATE；不存在則 INSERT

        Args:
            key_field: SQLite 側用來比對的欄位名（必須在 field_mapping 的 value 中）
            其餘參數同 publish
        """
        if not self._validate_params(source_table, target_table, field_mapping):
            return {'success': False, 'error': _('參數驗證失敗: 表名或欄位名不合法')}

        if not record_key:
            return {'success': False, 'error': _('record_key 不可為空')}

        if not _validate_ident(key_field):
            return {'success': False, 'error': _('key_field 不合法: %(key_field)s', key_field=key_field)}

        try:
            # Step 1: 從 PG 讀取
            pg_rows = self._read_from_pg(
                org_secure_code, source_table, record_key, list(field_mapping.keys())
            )
            if not pg_rows:
                return {'success': False, 'error': _('來源記錄不存在')}

            # Step 2: UPSERT 到 SQLite
            affected = 0
            with self._dsm.get_session(sub_system_sc, 'portal_data') as session:
                for row in pg_rows:
                    mapped = self._map_fields(row, field_mapping)
                    mapped['_bridge_updated_at'] = _utc_now_iso()

                    key_value = mapped.get(key_field)
                    if key_value is None:
                        logger.warning(
                            'update skip: key_field %s 無值, row=%s', key_field, row
                        )
                        continue

                    # 查 SQLite 是否已有該記錄
                    exists = self._sqlite_exists(
                        session, target_table, key_field, key_value
                    )
                    if exists:
                        self._sqlite_update(
                            session, target_table, mapped, key_field, key_value
                        )
                    else:
                        self._sqlite_insert(session, target_table, mapped)
                    affected += 1

            self._write_log(
                org_secure_code=org_secure_code,
                sub_system_sc=sub_system_sc,
                rule_id=rule_id,
                direction='update',
                source_db='org',
                source_table=source_table,
                target_db='portal_data',
                target_table=target_table,
                record_key=record_key,
                records_affected=affected,
                field_mapping=field_mapping,
                status='success',
                operator_sc=operator_sc,
            )

            return {
                'success': True,
                'message': _('已更新 %(affected)s 筆記錄', affected=affected),
                'records_affected': affected,
            }

        except Exception as e:
            logger.error('update failed: %s', e, exc_info=True)
            self._write_log(
                org_secure_code=org_secure_code,
                sub_system_sc=sub_system_sc,
                rule_id=rule_id,
                direction='update',
                source_db='org',
                source_table=source_table,
                target_db='portal_data',
                target_table=target_table,
                record_key=record_key,
                records_affected=0,
                field_mapping=field_mapping,
                status='failed',
                error_message=str(e),
                operator_sc=operator_sc,
            )
            return {'success': False, 'error': str(e)}

    # =====================================================================
    #  collect: SQLite -> PG (受限回收)
    # =====================================================================
    def collect(
        self,
        sub_system_sc: str,
        source_table: str,
        target_table: str,
        field_mapping: Dict[str, str],
        context: str,
        *,
        org_secure_code: str,
        collect_filter: Dict[str, Any] = None,
        key_field: str = None,
        operator_sc: str = None,
        rule_id: str = None,
    ) -> Dict[str, Any]:
        """
        從 SQLite portal_data.db 讀取，INSERT/UPDATE 到 PG
        此方向僅限特定 context，不開放通用寫入。

        Args:
            sub_system_sc: 子系統 secure_code
            source_table: SQLite 來源表名
            target_table: PG 目標表名
            field_mapping: {sqlite_col: pg_col} 欄位對應
            context: 回收情境 (必須在 ALLOWED_COLLECT_CONTEXTS 中)
            org_secure_code: 企業 secure_code
            collect_filter: SQLite 讀取過濾條件 e.g. {'is_submitted': 1}
            key_field: PG 側 upsert 用的比對欄位。None=純 INSERT
            operator_sc: 操作者 secure_code
            rule_id: 關聯的橋接規則 ID
        """
        if context not in ALLOWED_COLLECT_CONTEXTS:
            return {
                'success': False,
                'error': _('不允許的回收情境: %(context)s。允許的情境: %(allowed)s',
                           context=context,
                           allowed=', '.join(sorted(ALLOWED_COLLECT_CONTEXTS))),
            }

        if not self._validate_params(source_table, target_table, field_mapping):
            return {'success': False, 'error': _('參數驗證失敗: 表名或欄位名不合法')}

        if key_field and not _validate_ident(key_field):
            return {'success': False, 'error': _('key_field 不合法: %(key_field)s', key_field=key_field)}

        try:
            # Step 1: 從 SQLite 讀取
            sqlite_rows = self._read_from_sqlite(
                sub_system_sc, source_table,
                list(field_mapping.keys()), collect_filter,
            )
            if not sqlite_rows:
                return {
                    'success': True,
                    'message': _('無符合條件的記錄'),
                    'records_affected': 0,
                }

            # Step 2: 寫入 PG
            affected = self._write_to_pg(
                org_secure_code, target_table, sqlite_rows,
                field_mapping, key_field,
            )

            self._write_log(
                org_secure_code=org_secure_code,
                sub_system_sc=sub_system_sc,
                rule_id=rule_id,
                direction='collect',
                source_db='portal_data',
                source_table=source_table,
                target_db='org',
                target_table=target_table,
                record_key=collect_filter,
                records_affected=affected,
                field_mapping=field_mapping,
                status='success',
                operator_sc=operator_sc,
            )

            return {
                'success': True,
                'message': _('已回收 %(affected)s 筆記錄', affected=affected),
                'records_affected': affected,
            }

        except Exception as e:
            logger.error('collect failed: %s', e, exc_info=True)
            self._write_log(
                org_secure_code=org_secure_code,
                sub_system_sc=sub_system_sc,
                rule_id=rule_id,
                direction='collect',
                source_db='portal_data',
                source_table=source_table,
                target_db='org',
                target_table=target_table,
                record_key=collect_filter,
                records_affected=0,
                field_mapping=field_mapping,
                status='failed',
                error_message=str(e),
                operator_sc=operator_sc,
            )
            return {'success': False, 'error': str(e)}

    # =====================================================================
    #  execute_rule: 依 bridge_rule 定義執行橋接
    # =====================================================================
    def execute_rule(
        self,
        sub_system_sc: str,
        rule: Dict[str, Any],
        record_key: Dict[str, Any] = None,
        *,
        org_secure_code: str,
        operator_sc: str = None,
        collect_context: str = None,
        collect_filter: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        依 bridge_rule 定義執行對應的橋接操作

        Args:
            rule: bridge_rules 中的單條規則
            record_key: publish/update 方向的來源記錄鍵值
            collect_context: collect 方向的情境
            collect_filter: collect 方向的過濾條件
        """
        missing = _REQUIRED_RULE_FIELDS - set(rule.keys())
        if missing:
            return {'success': False, 'error': _('規則缺少必要欄位: %(missing)s', missing=', '.join(sorted(missing)))}

        if not rule.get('is_active', True):
            return {'success': False, 'error': _('規則已停用')}

        rule_id = rule.get('rule_id')
        source_db = rule['source_db']
        target_db = rule['target_db']
        source_table = rule['source_table']
        target_table = rule['target_table']
        field_mapping = rule['field_mapping']
        key_field = rule.get('key_field', 'secure_code')

        # 判斷方向
        if source_db in ('org', 'conglomerate') and target_db == 'portal_data':
            # PG -> SQLite
            if not record_key:
                return {'success': False, 'error': _('PG->SQLite 方向需要 record_key')}

            # 先嘗試 update (upsert)，key_field 存在即用 update 語意
            return self.update(
                sub_system_sc=sub_system_sc,
                source_table=source_table,
                target_table=target_table,
                record_key=record_key,
                field_mapping=field_mapping,
                org_secure_code=org_secure_code,
                key_field=key_field,
                operator_sc=operator_sc,
                rule_id=rule_id,
            )

        elif source_db == 'portal_data' and target_db in ('org', 'conglomerate'):
            # SQLite -> PG (受限)
            if not collect_context:
                return {'success': False, 'error': _('SQLite->PG 方向需要 collect_context')}

            return self.collect(
                sub_system_sc=sub_system_sc,
                source_table=source_table,
                target_table=target_table,
                field_mapping=field_mapping,
                context=collect_context,
                org_secure_code=org_secure_code,
                collect_filter=collect_filter,
                key_field=key_field,
                operator_sc=operator_sc,
                rule_id=rule_id,
            )

        else:
            return {
                'success': False,
                'error': _('不支援的橋接方向: %(source_db)s -> %(target_db)s',
                           source_db=source_db, target_db=target_db),
            }

    # =====================================================================
    #  validate_rule: 驗證 bridge_rule 結構
    # =====================================================================
    @staticmethod
    def validate_rule(rule: Dict[str, Any]) -> Dict[str, Any]:
        """
        驗證單條 bridge_rule 的結構與欄位名合法性

        Returns:
            {valid: bool, errors: [str]}
        """
        errors = []

        missing = _REQUIRED_RULE_FIELDS - set(rule.keys())
        if missing:
            errors.append(_('缺少必要欄位: %(fields)s', fields=', '.join(sorted(missing))))

        for key in ('source_table', 'target_table'):
            val = rule.get(key, '')
            if val and not _validate_ident(val):
                errors.append(_('%(key)s 不合法: %(val)s', key=key, val=val))

        mapping = rule.get('field_mapping', {})
        if not isinstance(mapping, dict) or not mapping:
            errors.append(_('field_mapping 必須是非空的 dict'))
        else:
            for src, tgt in mapping.items():
                if not _validate_ident(src):
                    errors.append(_('field_mapping key 不合法: %(src)s', src=src))
                if not _validate_ident(tgt):
                    errors.append(_('field_mapping value 不合法: %(tgt)s', tgt=tgt))

        trigger = rule.get('trigger_type', '')
        if trigger not in ('manual', 'on_approve', 'scheduled'):
            errors.append(_('trigger_type 不合法: %(trigger)s', trigger=trigger))

        source_db = rule.get('source_db', '')
        target_db = rule.get('target_db', '')
        valid_dbs = {'org', 'conglomerate', 'portal_data'}
        if source_db not in valid_dbs:
            errors.append(_('source_db 不合法: %(source_db)s', source_db=source_db))
        if target_db not in valid_dbs:
            errors.append(_('target_db 不合法: %(target_db)s', target_db=target_db))

        return {'valid': len(errors) == 0, 'errors': errors}

    # =====================================================================
    #  Internal: PG 讀取
    # =====================================================================
    def _read_from_pg(
        self,
        org_secure_code: str,
        table_name: str,
        record_key: Dict[str, Any],
        columns: List[str],
    ) -> List[Dict[str, Any]]:
        """從企業 PG 資料庫讀取記錄"""
        from .db_connector import get_data_conn

        # 驗證所有欄位名
        for col in columns:
            if not _validate_ident(col):
                raise ValueError(f'不合法的欄位名: {col}')
        for col in record_key:
            if not _validate_ident(col):
                raise ValueError(f'不合法的條件欄位名: {col}')

        from psycopg2 import sql as psql

        col_idents = psql.SQL(', ').join(
            psql.Identifier(c) for c in columns
        )
        where_parts = []
        where_values = []
        for col, val in record_key.items():
            where_parts.append(
                psql.SQL('{} = %s').format(psql.Identifier(col))
            )
            where_values.append(val)

        where_clause = psql.SQL(' AND ').join(where_parts)
        query = psql.SQL('SELECT {} FROM {} WHERE {}').format(
            col_idents, psql.Identifier(table_name), where_clause,
        )

        rows = []
        with get_data_conn(org_secure_code, 'org') as conn:
            with conn.cursor() as cur:
                cur.execute(query, where_values)
                col_names = [desc[0] for desc in cur.description]
                for db_row in cur.fetchall():
                    rows.append(dict(zip(col_names, db_row)))
            conn.rollback()  # 唯讀，不 commit

        return rows

    # =====================================================================
    #  Internal: SQLite 讀取
    # =====================================================================
    def _read_from_sqlite(
        self,
        sub_system_sc: str,
        table_name: str,
        columns: List[str],
        filters: Dict[str, Any] = None,
    ) -> List[Dict[str, Any]]:
        """從 SQLite portal_data.db 讀取記錄"""
        for col in columns:
            if not _validate_ident(col):
                raise ValueError(f'不合法的欄位名: {col}')

        col_list = ', '.join(f'"{c}"' for c in columns)
        sql = f'SELECT {col_list} FROM "{table_name}"'
        params = {}

        if filters:
            conditions = []
            for i, (col, val) in enumerate(filters.items()):
                if not _validate_ident(col):
                    raise ValueError(f'不合法的過濾欄位名: {col}')
                param_name = f'f_{i}'
                conditions.append(f'"{col}" = :{param_name}')
                params[param_name] = _serialize_for_sqlite(val)
            sql += ' WHERE ' + ' AND '.join(conditions)

        rows = []
        with self._dsm.get_session(sub_system_sc, 'portal_data') as session:
            result = session.execute(text(sql), params)
            col_names = list(result.keys())
            for db_row in result.fetchall():
                row_dict = {}
                for i, val in enumerate(db_row):
                    row_dict[col_names[i]] = _deserialize_from_sqlite(val)
                rows.append(row_dict)

        return rows

    # =====================================================================
    #  Internal: SQLite 寫入操作
    # =====================================================================
    def _sqlite_insert(self, session, table_name: str, data: Dict[str, Any]):
        """INSERT 一筆到 SQLite"""
        cols = list(data.keys())
        col_list = ', '.join(f'"{c}"' for c in cols)
        param_list = ', '.join(f':p_{i}' for i in range(len(cols)))
        params = {
            f'p_{i}': _serialize_for_sqlite(data[c])
            for i, c in enumerate(cols)
        }

        sql = f'INSERT INTO "{table_name}" ({col_list}) VALUES ({param_list})'
        session.execute(text(sql), params)

    def _sqlite_update(
        self, session, table_name: str, data: Dict[str, Any],
        key_field: str, key_value: Any,
    ):
        """UPDATE SQLite 中的一筆記錄"""
        set_parts = []
        params = {}
        idx = 0
        for col, val in data.items():
            if col == key_field:
                continue
            param_name = f's_{idx}'
            set_parts.append(f'"{col}" = :{param_name}')
            params[param_name] = _serialize_for_sqlite(val)
            idx += 1

        if not set_parts:
            return

        params['key_val'] = _serialize_for_sqlite(key_value)
        set_clause = ', '.join(set_parts)
        sql = f'UPDATE "{table_name}" SET {set_clause} WHERE "{key_field}" = :key_val'
        session.execute(text(sql), params)

    def _sqlite_exists(
        self, session, table_name: str, key_field: str, key_value: Any,
    ) -> bool:
        """檢查 SQLite 中是否已有該記錄"""
        sql = f'SELECT 1 FROM "{table_name}" WHERE "{key_field}" = :kv LIMIT 1'
        result = session.execute(
            text(sql), {'kv': _serialize_for_sqlite(key_value)}
        )
        return result.fetchone() is not None

    # =====================================================================
    #  Internal: PG 寫入 (collect 方向)
    # =====================================================================
    def _write_to_pg(
        self,
        org_secure_code: str,
        target_table: str,
        sqlite_rows: List[Dict[str, Any]],
        field_mapping: Dict[str, str],
        key_field: str = None,
    ) -> int:
        """將 SQLite 讀出的資料寫入企業 PG 資料庫"""
        from .db_connector import get_data_conn
        from psycopg2 import sql as psql

        affected = 0
        with get_data_conn(org_secure_code, 'org') as conn:
            for row in sqlite_rows:
                mapped = self._map_fields(row, field_mapping)
                if not mapped:
                    continue

                if key_field and key_field in mapped:
                    # 嘗試 UPDATE
                    updated = self._pg_update(
                        conn, target_table, mapped, key_field, mapped[key_field]
                    )
                    if not updated:
                        # 不存在則 INSERT
                        self._pg_insert(conn, target_table, mapped)
                else:
                    self._pg_insert(conn, target_table, mapped)

                affected += 1
            conn.commit()

        return affected

    def _pg_insert(self, conn, table_name: str, data: Dict[str, Any]):
        """INSERT 一筆到 PG"""
        from psycopg2 import sql as psql

        cols = list(data.keys())
        col_idents = psql.SQL(', ').join(psql.Identifier(c) for c in cols)
        placeholders = psql.SQL(', ').join(psql.Placeholder() for _ in cols)
        values = [data[c] for c in cols]

        query = psql.SQL('INSERT INTO {} ({}) VALUES ({})').format(
            psql.Identifier(table_name), col_idents, placeholders,
        )
        with conn.cursor() as cur:
            cur.execute(query, values)

    def _pg_update(
        self, conn, table_name: str, data: Dict[str, Any],
        key_field: str, key_value: Any,
    ) -> bool:
        """UPDATE PG 中的一筆記錄，回傳是否有更新到"""
        from psycopg2 import sql as psql

        update_data = {k: v for k, v in data.items() if k != key_field}
        if not update_data:
            return False

        cols = list(update_data.keys())
        set_clause = psql.SQL(', ').join(
            psql.SQL('{} = %s').format(psql.Identifier(c)) for c in cols
        )
        values = [update_data[c] for c in cols]
        values.append(key_value)

        query = psql.SQL('UPDATE {} SET {} WHERE {} = %s').format(
            psql.Identifier(table_name), set_clause, psql.Identifier(key_field),
        )
        with conn.cursor() as cur:
            cur.execute(query, values)
            return cur.rowcount > 0

    # =====================================================================
    #  Internal: 欄位映射
    # =====================================================================
    @staticmethod
    def _map_fields(
        row: Dict[str, Any], field_mapping: Dict[str, str],
    ) -> Dict[str, Any]:
        """依 field_mapping 轉換欄位名"""
        mapped = {}
        for src_col, tgt_col in field_mapping.items():
            if src_col in row:
                mapped[tgt_col] = row[src_col]
        return mapped

    # =====================================================================
    #  Internal: 參數驗證
    # =====================================================================
    @staticmethod
    def _validate_params(
        source_table: str, target_table: str, field_mapping: Dict[str, str],
    ) -> bool:
        """驗證表名和欄位名"""
        if not _validate_ident(source_table) or not _validate_ident(target_table):
            return False
        for src, tgt in field_mapping.items():
            if not _validate_ident(src) or not _validate_ident(tgt):
                return False
        return True

    # =====================================================================
    #  Internal: 審計日誌
    # =====================================================================
    @staticmethod
    def _write_log(
        org_secure_code: str,
        sub_system_sc: str,
        direction: str,
        source_db: str,
        source_table: str,
        target_db: str,
        target_table: str,
        records_affected: int,
        status: str,
        rule_id: str = None,
        record_key: Dict = None,
        field_mapping: Dict = None,
        error_message: str = None,
        operator_sc: str = None,
    ):
        """寫入 dc_bridge_logs 審計日誌"""
        try:
            from .bridge_log_writer import write_bridge_log
            write_bridge_log(
                org_secure_code=org_secure_code,
                sub_system_sc=sub_system_sc,
                direction=direction,
                source_db=source_db,
                source_table=source_table,
                target_db=target_db,
                target_table=target_table,
                records_affected=records_affected,
                status=status,
                rule_id=rule_id,
                record_key=record_key,
                field_mapping=field_mapping,
                error_message=error_message,
                operator_sc=operator_sc,
            )
        except Exception as e:
            # 日誌寫入失敗不應中斷主流程
            logger.error('bridge log write failed: %s', e)
