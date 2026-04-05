"""
BeakPlatform - Lookup Org Service
企業級 lookup CRUD 服務 -- 直接操作企業專屬 DB (org_{id})

系統級 lookup 留在主庫 (ORM)，企業級搬到 org DB (psycopg2 raw SQL)。
admin 角色建表/寫入，sync 角色讀取。
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

from psycopg2 import sql as psql

from ..utils.security import generate_secure_code

logger = logging.getLogger(__name__)


# =============================================================================
# 懶建表 DDL
# =============================================================================

_DDL_LOOKUP_CATEGORIES = """
CREATE TABLE IF NOT EXISTS lookup_categories (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    code VARCHAR(100) NOT NULL,
    name VARCHAR(200) NOT NULL,
    name_i18n JSONB DEFAULT '{}',
    description TEXT,
    is_hierarchical BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uix_org_lkcat_code
    ON lookup_categories (code) WHERE is_deleted = FALSE;
"""

_DDL_LOOKUP_ITEMS = """
CREATE TABLE IF NOT EXISTS lookup_items (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    category_code VARCHAR(100) NOT NULL,
    code VARCHAR(100) NOT NULL,
    label VARCHAR(200) NOT NULL,
    label_i18n JSONB DEFAULT '{}',
    value JSONB,
    value_str VARCHAR(500),
    value_int BIGINT,
    value_decimal NUMERIC(20,2),
    value_date DATE,
    value_time TIME WITHOUT TIME ZONE,
    value_datetime TIMESTAMP WITHOUT TIME ZONE,
    user_secure_code VARCHAR(32),
    parent_code VARCHAR(100),
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uix_org_lkitem_cat_code
    ON lookup_items (category_code, code) WHERE is_deleted = FALSE;
CREATE INDEX IF NOT EXISTS ix_org_lkitem_category_code
    ON lookup_items (category_code);
"""

_GRANT_TABLES = ['lookup_categories', 'lookup_items']
_GRANT_SEQUENCES = ['lookup_categories_id_seq', 'lookup_items_id_seq']


def _get_org_conn():
    """延遲引入 pool.get_org_conn"""
    from modules.form_workflow.services.sql_sync.pool import get_org_conn
    return get_org_conn


def _get_sync_user(org_secure_code):
    """取得企業的 sync 角色名稱"""
    from modules.form_workflow.models.org_database import FwOrgDatabase
    org_db = FwOrgDatabase.query.filter_by(
        org_secure_code=org_secure_code,
        is_ready=True,
        is_deleted=False,
    ).first()
    return org_db.sync_user if org_db else None


def _has_org_db(org_secure_code):
    """檢查企業是否有專屬 DB"""
    from modules.form_workflow.models.org_database import FwOrgDatabase
    return FwOrgDatabase.query.filter_by(
        org_secure_code=org_secure_code,
        is_ready=True,
        is_deleted=False,
    ).first() is not None


def _row_to_category_dict(row) -> dict:
    """將 DB row 轉為與 LookupCategory.to_dict() 相容的 dict"""
    return {
        'id': row[1],             # secure_code 作為 public ID
        'secure_code': row[1],
        'code': row[2],
        'name': row[3],
        'name_i18n': row[4] or {},
        'description': row[5],
        'is_system': False,       # 企業級一律 False
        'is_hierarchical': row[6],
        'is_active': row[7],
        'created_at': row[8].isoformat() if row[8] else None,
        'updated_at': row[9].isoformat() if row[9] else None,
    }


def _row_to_item_dict(row) -> dict:
    """將 DB row 轉為與 LookupItem.to_dict() 相容的 dict"""
    # 欄位順序對應 _ITEM_COLS
    return {
        'id': row[1],             # secure_code 作為 public ID
        'secure_code': row[1],
        'category_code': row[2],
        'code': row[3],
        'label': row[4],
        'label_i18n': row[5] or {},
        'value': row[6],
        'value_str': row[7],
        'value_int': row[8],
        'value_decimal': float(row[9]) if row[9] is not None else None,
        'value_date': row[10].isoformat() if row[10] else None,
        'value_time': row[11].strftime('%H:%M') if row[11] else None,
        'value_datetime': row[12].isoformat() if row[12] else None,
        'user_secure_code': row[13],
        'parent_code': row[14],
        'sort_order': row[15],
        'is_active': row[16],
        'created_at': row[17].isoformat() if row[17] else None,
        'updated_at': row[18].isoformat() if row[18] else None,
    }


# Category SELECT 欄位順序
_CAT_COLS = (
    'id, secure_code, code, name, name_i18n, description, '
    'is_hierarchical, is_active, created_at, updated_at'
)

# Item SELECT 欄位順序
_ITEM_COLS = (
    'id, secure_code, category_code, code, label, label_i18n, '
    'value, value_str, value_int, value_decimal, value_date, value_time, value_datetime, '
    'user_secure_code, parent_code, sort_order, is_active, created_at, updated_at'
)


class LookupOrgService:
    """企業級 Lookup CRUD -- 直接操作企業 DB"""

    _tables_ensured: set = set()

    # ----------------------------------------------------------------
    # 懶建表
    # ----------------------------------------------------------------

    @classmethod
    def ensure_tables(cls, org_secure_code):
        """
        在企業 DB 建立 lookup 表（冪等）。
        使用 admin 角色連線。
        """
        if org_secure_code in cls._tables_ensured:
            return

        if not _has_org_db(org_secure_code):
            raise RuntimeError(f'企業 {org_secure_code} 尚未建立專屬資料庫')

        get_org_conn = _get_org_conn()
        with get_org_conn(org_secure_code, role='admin') as conn:
            with conn.cursor() as cur:
                cur.execute(_DDL_LOOKUP_CATEGORIES)
                cur.execute(_DDL_LOOKUP_ITEMS)
            conn.commit()

            # GRANT DML 給 sync user
            sync_user = _get_sync_user(org_secure_code)
            if sync_user:
                with conn.cursor() as cur:
                    for tbl in _GRANT_TABLES:
                        cur.execute(
                            psql.SQL(
                                "GRANT SELECT, INSERT, UPDATE, DELETE ON {} TO {}"
                            ).format(
                                psql.Identifier(tbl),
                                psql.Identifier(sync_user),
                            )
                        )
                    for seq in _GRANT_SEQUENCES:
                        cur.execute(
                            psql.SQL(
                                "GRANT USAGE, SELECT ON SEQUENCE {} TO {}"
                            ).format(
                                psql.Identifier(seq),
                                psql.Identifier(sync_user),
                            )
                        )
                conn.commit()

            # 遷移: 為既有 lookup_categories 表補上 is_active 欄位
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'lookup_categories' AND column_name = 'is_active'
                """)
                if not cur.fetchone():
                    cur.execute(
                        "ALTER TABLE lookup_categories "
                        "ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE"
                    )
                    logger.info(
                        f'[LookupOrg] 已為企業 {org_secure_code} '
                        f'lookup_categories 補上 is_active 欄位'
                    )
            conn.commit()

            # 遷移: 為既有 lookup_items 表補上多型別值欄位
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'lookup_items' AND column_name = 'value_str'
                """)
                if not cur.fetchone():
                    cur.execute(
                        "ALTER TABLE lookup_items "
                        "ADD COLUMN value_str VARCHAR(500), "
                        "ADD COLUMN value_int BIGINT, "
                        "ADD COLUMN value_decimal NUMERIC(20,2), "
                        "ADD COLUMN value_date DATE, "
                        "ADD COLUMN value_time TIME WITHOUT TIME ZONE, "
                        "ADD COLUMN value_datetime TIMESTAMP WITHOUT TIME ZONE"
                    )
                    logger.info(
                        f'[LookupOrg] 已為企業 {org_secure_code} '
                        f'lookup_items 補上多型別值欄位'
                    )
            conn.commit()

            # 遷移: 為既有 lookup_items 表補上 user_secure_code 欄位
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'lookup_items' AND column_name = 'user_secure_code'
                """)
                if not cur.fetchone():
                    cur.execute(
                        "ALTER TABLE lookup_items "
                        "ADD COLUMN user_secure_code VARCHAR(32)"
                    )
                    cur.execute(
                        "CREATE INDEX IF NOT EXISTS ix_org_lkitem_user_sc "
                        "ON lookup_items (user_secure_code) "
                        "WHERE user_secure_code IS NOT NULL"
                    )
                    logger.info(
                        f'[LookupOrg] 已為企業 {org_secure_code} '
                        f'lookup_items 補上 user_secure_code 欄位'
                    )
            conn.commit()

        cls._tables_ensured.add(org_secure_code)
        logger.info(f'[LookupOrg] 已確認企業 {org_secure_code} lookup 表存在')

    # ----------------------------------------------------------------
    # Category CRUD
    # ----------------------------------------------------------------

    @classmethod
    def get_categories(cls, org_secure_code) -> List[dict]:
        """取得企業所有類別 (sync 角色讀)"""
        if not _has_org_db(org_secure_code):
            return []

        cls.ensure_tables(org_secure_code)
        get_org_conn = _get_org_conn()
        with get_org_conn(org_secure_code, role='sync') as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT {_CAT_COLS} FROM lookup_categories "
                    "WHERE is_deleted = FALSE ORDER BY code"
                )
                rows = cur.fetchall()
        return [_row_to_category_dict(r) for r in rows]

    @classmethod
    def get_category_by_secure_code(cls, org_secure_code, sc) -> Optional[dict]:
        """用 secure_code 取單一類別 (sync 角色讀)"""
        if not _has_org_db(org_secure_code):
            return None

        cls.ensure_tables(org_secure_code)
        get_org_conn = _get_org_conn()
        with get_org_conn(org_secure_code, role='sync') as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT {_CAT_COLS} FROM lookup_categories "
                    "WHERE secure_code = %s AND is_deleted = FALSE",
                    (sc,)
                )
                row = cur.fetchone()
        return _row_to_category_dict(row) if row else None

    @classmethod
    def get_category_by_code(cls, org_secure_code, code) -> Optional[dict]:
        """用 code 取單一類別 (sync 角色讀)"""
        if not _has_org_db(org_secure_code):
            return None

        cls.ensure_tables(org_secure_code)
        get_org_conn = _get_org_conn()
        with get_org_conn(org_secure_code, role='sync') as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT {_CAT_COLS} FROM lookup_categories "
                    "WHERE code = %s AND is_deleted = FALSE",
                    (code,)
                )
                row = cur.fetchone()
        return _row_to_category_dict(row) if row else None

    @classmethod
    def create_category(
        cls,
        org_secure_code: str,
        code: str,
        name: str,
        description: Optional[str] = None,
        is_hierarchical: bool = False,
        name_i18n: Optional[dict] = None,
    ) -> dict:
        """建立企業類別 (admin 角色寫)"""
        cls.ensure_tables(org_secure_code)
        sc = generate_secure_code()
        now = datetime.utcnow()
        name_i18n = name_i18n or {}

        get_org_conn = _get_org_conn()
        with get_org_conn(org_secure_code, role='admin') as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO lookup_categories "
                    "(secure_code, code, name, name_i18n, description, "
                    " is_hierarchical, created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s) "
                    "RETURNING id",
                    (sc, code, name, _json_str(name_i18n), description,
                     is_hierarchical, now, now)
                )
                row_id = cur.fetchone()[0]
            conn.commit()

        return {
            'id': sc,
            'secure_code': sc,
            'code': code,
            'name': name,
            'name_i18n': name_i18n,
            'description': description,
            'is_system': False,
            'is_hierarchical': is_hierarchical,
            'is_active': True,
            'created_at': now.isoformat(),
            'updated_at': now.isoformat(),
        }

    @classmethod
    def update_category(cls, org_secure_code: str, sc: str, **kwargs) -> Optional[dict]:
        """更新企業類別 (admin 角色寫)"""
        cls.ensure_tables(org_secure_code)
        allowed = ('name', 'name_i18n', 'description', 'is_hierarchical', 'is_active')
        updates = {}
        for f in allowed:
            if f in kwargs:
                updates[f] = kwargs[f]
        if not updates:
            return cls.get_category_by_secure_code(org_secure_code, sc)

        set_clauses = []
        params = []
        for field, value in updates.items():
            if field == 'name_i18n':
                set_clauses.append(f"{field} = %s::jsonb")
                params.append(_json_str(value))
            else:
                set_clauses.append(f"{field} = %s")
                params.append(value)
        set_clauses.append("updated_at = %s")
        params.append(datetime.utcnow())
        params.append(sc)

        get_org_conn = _get_org_conn()
        with get_org_conn(org_secure_code, role='admin') as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE lookup_categories SET {', '.join(set_clauses)} "
                    "WHERE secure_code = %s AND is_deleted = FALSE",
                    params
                )
                if cur.rowcount == 0:
                    return None
            conn.commit()

        return cls.get_category_by_secure_code(org_secure_code, sc)

    @classmethod
    def delete_category(cls, org_secure_code: str, sc: str) -> bool:
        """軟刪除企業類別 + 連帶軟刪 items (admin 角色寫)"""
        cls.ensure_tables(org_secure_code)
        now = datetime.utcnow()

        get_org_conn = _get_org_conn()
        with get_org_conn(org_secure_code, role='admin') as conn:
            with conn.cursor() as cur:
                # 先取得 category code
                cur.execute(
                    "SELECT code FROM lookup_categories "
                    "WHERE secure_code = %s AND is_deleted = FALSE",
                    (sc,)
                )
                row = cur.fetchone()
                if not row:
                    return False
                cat_code = row[0]

                # 軟刪 category
                cur.execute(
                    "UPDATE lookup_categories SET is_deleted = TRUE, deleted_at = %s "
                    "WHERE secure_code = %s AND is_deleted = FALSE",
                    (now, sc)
                )
                # 連帶軟刪所有 items
                cur.execute(
                    "UPDATE lookup_items SET is_deleted = TRUE, deleted_at = %s "
                    "WHERE category_code = %s AND is_deleted = FALSE",
                    (now, cat_code)
                )
            conn.commit()
        return True

    # ----------------------------------------------------------------
    # Item CRUD
    # ----------------------------------------------------------------

    @classmethod
    def get_items(cls, org_secure_code: str, category_code: str) -> List[dict]:
        """取得企業類別下 active items (sync 角色讀)"""
        if not _has_org_db(org_secure_code):
            return []

        cls.ensure_tables(org_secure_code)
        get_org_conn = _get_org_conn()
        with get_org_conn(org_secure_code, role='sync') as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT {_ITEM_COLS} FROM lookup_items "
                    "WHERE category_code = %s AND is_active = TRUE "
                    "AND is_deleted = FALSE "
                    "ORDER BY sort_order, code",
                    (category_code,)
                )
                rows = cur.fetchall()
        return [_row_to_item_dict(r) for r in rows]

    @classmethod
    def get_all_items(cls, org_secure_code: str, category_code: str) -> List[dict]:
        """取得企業類別下所有 items 含 inactive (sync 角色讀, 管理用)"""
        if not _has_org_db(org_secure_code):
            return []

        cls.ensure_tables(org_secure_code)
        get_org_conn = _get_org_conn()
        with get_org_conn(org_secure_code, role='sync') as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT {_ITEM_COLS} FROM lookup_items "
                    "WHERE category_code = %s AND is_deleted = FALSE "
                    "ORDER BY sort_order, code",
                    (category_code,)
                )
                rows = cur.fetchall()
        return [_row_to_item_dict(r) for r in rows]

    @classmethod
    def get_items_by_user(cls, org_secure_code: str, category_code: str,
                          user_secure_code: str) -> List[dict]:
        """取得特定用戶在某類別下的 active items (sync 角色讀)"""
        if not _has_org_db(org_secure_code):
            return []

        cls.ensure_tables(org_secure_code)
        get_org_conn = _get_org_conn()
        with get_org_conn(org_secure_code, role='sync') as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT {_ITEM_COLS} FROM lookup_items "
                    "WHERE category_code = %s AND user_secure_code = %s "
                    "AND is_active = TRUE AND is_deleted = FALSE "
                    "ORDER BY sort_order, code",
                    (category_code, user_secure_code)
                )
                rows = cur.fetchall()
        return [_row_to_item_dict(r) for r in rows]

    @classmethod
    def get_item_by_secure_code(cls, org_secure_code: str, sc: str) -> Optional[dict]:
        """用 secure_code 取單一 item (sync 角色讀)"""
        if not _has_org_db(org_secure_code):
            return None

        cls.ensure_tables(org_secure_code)
        get_org_conn = _get_org_conn()
        with get_org_conn(org_secure_code, role='sync') as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT {_ITEM_COLS} FROM lookup_items "
                    "WHERE secure_code = %s AND is_deleted = FALSE",
                    (sc,)
                )
                row = cur.fetchone()
        return _row_to_item_dict(row) if row else None

    @classmethod
    def create_item(
        cls,
        org_secure_code: str,
        category_code: str,
        code: str,
        label: str,
        label_i18n: Optional[dict] = None,
        value: Optional[Any] = None,
        value_str: Optional[str] = None,
        value_int: Optional[int] = None,
        value_decimal=None,
        value_date: Optional[str] = None,
        value_time: Optional[str] = None,
        value_datetime: Optional[str] = None,
        user_secure_code: Optional[str] = None,
        parent_code: Optional[str] = None,
        sort_order: int = 0,
    ) -> dict:
        """建立企業 item (admin 角色寫)"""
        cls.ensure_tables(org_secure_code)
        sc = generate_secure_code()
        now = datetime.utcnow()
        label_i18n = label_i18n or {}

        get_org_conn = _get_org_conn()
        with get_org_conn(org_secure_code, role='admin') as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO lookup_items "
                    "(secure_code, category_code, code, label, label_i18n, "
                    " value, value_str, value_int, value_decimal, "
                    " value_date, value_time, value_datetime, "
                    " user_secure_code, parent_code, sort_order, "
                    " created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, "
                    " %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "RETURNING id",
                    (sc, category_code, code, label, _json_str(label_i18n),
                     _json_str(value), value_str, value_int, value_decimal,
                     value_date, value_time, value_datetime,
                     user_secure_code, parent_code, sort_order, now, now)
                )
            conn.commit()

        return {
            'id': sc,
            'secure_code': sc,
            'category_code': category_code,
            'code': code,
            'label': label,
            'label_i18n': label_i18n,
            'value': value,
            'value_str': value_str,
            'value_int': value_int,
            'value_decimal': float(value_decimal) if value_decimal is not None else None,
            'value_date': value_date,
            'value_time': value_time,
            'value_datetime': value_datetime,
            'user_secure_code': user_secure_code,
            'parent_code': parent_code,
            'sort_order': sort_order,
            'is_active': True,
            'created_at': now.isoformat(),
            'updated_at': now.isoformat(),
        }

    @classmethod
    def update_item(cls, org_secure_code: str, sc: str, **kwargs) -> Optional[dict]:
        """更新企業 item (admin 角色寫)"""
        cls.ensure_tables(org_secure_code)
        allowed = ('label', 'label_i18n', 'value', 'value_str', 'value_int',
                    'value_decimal', 'value_date', 'value_time', 'value_datetime',
                    'parent_code', 'sort_order', 'is_active')
        updates = {}
        for f in allowed:
            if f in kwargs:
                updates[f] = kwargs[f]
        if not updates:
            return cls.get_item_by_secure_code(org_secure_code, sc)

        set_clauses = []
        params = []
        for field, value in updates.items():
            if field in ('label_i18n', 'value'):
                set_clauses.append(f"{field} = %s::jsonb")
                params.append(_json_str(value))
            else:
                set_clauses.append(f"{field} = %s")
                params.append(value)
        set_clauses.append("updated_at = %s")
        params.append(datetime.utcnow())
        params.append(sc)

        get_org_conn = _get_org_conn()
        with get_org_conn(org_secure_code, role='admin') as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE lookup_items SET {', '.join(set_clauses)} "
                    "WHERE secure_code = %s AND is_deleted = FALSE",
                    params
                )
                if cur.rowcount == 0:
                    return None
            conn.commit()

        return cls.get_item_by_secure_code(org_secure_code, sc)

    @classmethod
    def delete_item(cls, org_secure_code: str, sc: str) -> bool:
        """軟刪除企業 item + 所有子孫 (admin 角色寫)

        階層式類別中，刪除父項會連帶軟刪所有子孫。
        若子孫中有啟用中的項目，拒絕刪除並拋出 RuntimeError。
        """
        cls.ensure_tables(org_secure_code)
        now = datetime.utcnow()

        get_org_conn = _get_org_conn()
        with get_org_conn(org_secure_code, role='admin') as conn:
            with conn.cursor() as cur:
                # 取得被刪除項目的 code 和 category_code
                cur.execute(
                    "SELECT code, category_code FROM lookup_items "
                    "WHERE secure_code = %s AND is_deleted = FALSE",
                    (sc,)
                )
                row = cur.fetchone()
                if not row:
                    return False
                item_code, cat_code = row[0], row[1]

                # 用遞迴 CTE 找出所有子孫 code
                cur.execute(
                    "WITH RECURSIVE descendants AS ("
                    "  SELECT code FROM lookup_items "
                    "  WHERE parent_code = %s AND category_code = %s "
                    "    AND is_deleted = FALSE "
                    "  UNION ALL "
                    "  SELECT li.code FROM lookup_items li "
                    "  JOIN descendants d ON li.parent_code = d.code "
                    "  WHERE li.category_code = %s AND li.is_deleted = FALSE"
                    ") SELECT code FROM descendants",
                    (item_code, cat_code, cat_code)
                )
                descendant_codes = [r[0] for r in cur.fetchall()]

                # 檢查子孫中是否有啟用中的項目
                if descendant_codes:
                    cur.execute(
                        "SELECT code FROM lookup_items "
                        "WHERE category_code = %s AND code = ANY(%s) "
                        "  AND is_active = TRUE AND is_deleted = FALSE",
                        (cat_code, descendant_codes)
                    )
                    active_rows = cur.fetchall()
                    if active_rows:
                        active_codes = ', '.join(r[0] for r in active_rows)
                        raise RuntimeError(
                            f'以下子選項仍啟用中，請先停用：{active_codes}'
                        )

                # 軟刪除本項 + 所有子孫
                all_codes = [item_code] + descendant_codes
                cur.execute(
                    "UPDATE lookup_items SET is_deleted = TRUE, deleted_at = %s "
                    "WHERE category_code = %s AND code = ANY(%s) "
                    "  AND is_deleted = FALSE",
                    (now, cat_code, all_codes)
                )
                affected = cur.rowcount
            conn.commit()
        return affected > 0

    @classmethod
    def reorder_items(cls, org_secure_code: str, category_code: str,
                      order_list: list) -> bool:
        """批次更新排序 (admin 角色寫)"""
        cls.ensure_tables(org_secure_code)

        get_org_conn = _get_org_conn()
        with get_org_conn(org_secure_code, role='admin') as conn:
            with conn.cursor() as cur:
                for idx, entry in enumerate(order_list):
                    if isinstance(entry, str):
                        item_sc = entry
                        new_parent = None
                        new_sort = idx
                        update_parent = False
                    elif isinstance(entry, dict):
                        item_sc = entry.get('secure_code')
                        new_parent = entry.get('parent_code')
                        new_sort = entry.get('sort_order', idx)
                        update_parent = 'parent_code' in entry
                    else:
                        continue
                    if not item_sc:
                        continue

                    if update_parent:
                        cur.execute(
                            "UPDATE lookup_items "
                            "SET sort_order = %s, parent_code = %s, updated_at = %s "
                            "WHERE secure_code = %s AND category_code = %s "
                            "AND is_deleted = FALSE",
                            (new_sort, new_parent or None, datetime.utcnow(),
                             item_sc, category_code)
                        )
                    else:
                        cur.execute(
                            "UPDATE lookup_items "
                            "SET sort_order = %s, updated_at = %s "
                            "WHERE secure_code = %s AND category_code = %s "
                            "AND is_deleted = FALSE",
                            (new_sort, datetime.utcnow(), item_sc, category_code)
                        )
            conn.commit()
        return True

    @classmethod
    def check_item_code_exists(cls, org_secure_code: str,
                               category_code: str, code: str) -> bool:
        """檢查 item code 是否已存在"""
        if not _has_org_db(org_secure_code):
            return False

        cls.ensure_tables(org_secure_code)
        get_org_conn = _get_org_conn()
        with get_org_conn(org_secure_code, role='sync') as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM lookup_items "
                    "WHERE category_code = %s AND code = %s AND is_deleted = FALSE "
                    "LIMIT 1",
                    (category_code, code)
                )
                return cur.fetchone() is not None


def _json_str(obj) -> Optional[str]:
    """將 Python 物件轉為 JSON 字串 (for psycopg2 JSONB cast)"""
    import json
    if obj is None:
        return None
    return json.dumps(obj, ensure_ascii=False)
