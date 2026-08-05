"""
Data CRUD Module - DataSourceManager
管理 per-子系統的 SQLAlchemy Engine/Session (SQLite)

職責:
  - 建立/快取 SQLAlchemy Engine (per sub_system + source_type)
  - 提供 scoped session context manager
  - SQLite 建立時自動執行 PRAGMA
  - 子系統 SQLite 目錄初始化/清理

data_source 類型:
  'main'        → 主 DB (PostgreSQL)，不經此模組
  'org'         → 企業 DB (PostgreSQL)，不經此模組
  'conglomerate'→ 集團 DB (PostgreSQL)，不經此模組
  'portal'      → 子系統帳號角色 DB (SQLite)
  'portal_data' → 子系統公開資料 DB (SQLite)
"""
import os
import re
import shutil
import logging
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from flask_babel import gettext as _
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)

# SQLite 檔案對應
_SOURCE_DB_FILE = {
    'portal': 'portal.db',
    'portal_data': 'portal_data.db',
}

# 所有 SQLite data_source 類型
SQLITE_SOURCES = frozenset(_SOURCE_DB_FILE.keys())

# 基礎目錄 (相對於專案根)
_BASE_DIR = Path(__file__).resolve().parents[3] / 'data' / 'nocode_portals'

# sub_system_sc 會直接成為檔案系統路徑的一段，字元集必須白名單化，
# 否則 '../' 之類的值可讓路徑逃出 _BASE_DIR (路徑穿越)。
# secure_code 由 secrets.token_urlsafe 產生，字元集為 [A-Za-z0-9_-]；
# 長度放寬到 64 以相容測試與腳本使用的短代號。
_SC_PATTERN = re.compile(r'^[A-Za-z0-9_-]{1,64}$')


def _validate_sc(sub_system_sc) -> str:
    """
    驗證 sub_system_sc 可安全用於組成路徑，不合法一律拒絕 (fail-closed)。

    這是所有 SQLite 路徑組成的唯一入口，不要在其他地方另行拼接路徑。
    """
    if not isinstance(sub_system_sc, str) or not _SC_PATTERN.match(sub_system_sc):
        raise ValueError(f'Invalid sub_system_sc for path construction: {sub_system_sc!r}')
    return sub_system_sc


def _get_portal_dir(sub_system_sc: str) -> Path:
    """取得子系統 portal 目錄路徑"""
    return _BASE_DIR / _validate_sc(sub_system_sc)


def _get_db_path(sub_system_sc: str, source_type: str) -> Path:
    """取得 SQLite 檔案路徑"""
    filename = _SOURCE_DB_FILE.get(source_type)
    if not filename:
        raise ValueError(f'Unknown SQLite source_type: {source_type}')
    return _get_portal_dir(sub_system_sc) / filename


def _apply_pragmas(dbapi_conn, connection_record):
    """SQLAlchemy event listener: 連線建立時自動執行 PRAGMA"""
    cursor = dbapi_conn.cursor()
    cursor.execute('PRAGMA journal_mode=WAL')
    cursor.execute('PRAGMA foreign_keys=ON')
    cursor.execute('PRAGMA busy_timeout=5000')
    cursor.close()


class DataSourceManager:
    """
    SQLite Engine/Session 管理器 (singleton)

    Engine 快取 key: '{sub_system_sc}:{source_type}'
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._engines = {}
                    inst._session_factories = {}
                    inst._engine_lock = threading.Lock()
                    cls._instance = inst
        return cls._instance

    def _get_or_create_engine(self, sub_system_sc: str, source_type: str):
        """取得或建立 Engine (thread-safe)"""
        cache_key = f'{sub_system_sc}:{source_type}'

        engine = self._engines.get(cache_key)
        if engine is not None:
            return engine

        with self._engine_lock:
            # double-check
            engine = self._engines.get(cache_key)
            if engine is not None:
                return engine

            db_path = _get_db_path(sub_system_sc, source_type)
            if not db_path.exists():
                raise FileNotFoundError(
                    _('SQLite 檔案不存在: %(path)s (子系統 %(sc)s 可能尚未初始化)',
                      path=db_path, sc=sub_system_sc)
                )

            engine = create_engine(
                f'sqlite:///{db_path}',
                poolclass=NullPool,
                connect_args={'check_same_thread': False},
            )
            event.listen(engine, 'connect', _apply_pragmas)

            self._engines[cache_key] = engine
            self._session_factories[cache_key] = sessionmaker(bind=engine)
            logger.info('SQLite engine created: %s', cache_key)
            return engine

    @contextmanager
    def get_session(self, sub_system_sc: str, source_type: str):
        """
        取得 SQLAlchemy Session (context manager)

        Usage:
            mgr = DataSourceManager()
            with mgr.get_session(ss_sc, 'portal_data') as session:
                result = session.execute(text('SELECT ...'))
        """
        self._get_or_create_engine(sub_system_sc, source_type)
        cache_key = f'{sub_system_sc}:{source_type}'
        factory = self._session_factories[cache_key]
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def remove_engine(self, sub_system_sc: str, source_type: Optional[str] = None):
        """
        從快取移除 Engine (子系統刪除時呼叫)

        Args:
            sub_system_sc: 子系統 secure_code
            source_type: 指定 source，None = 移除該子系統的全部 engine
        """
        targets = [source_type] if source_type else list(_SOURCE_DB_FILE.keys())
        with self._engine_lock:
            for st in targets:
                cache_key = f'{sub_system_sc}:{st}'
                engine = self._engines.pop(cache_key, None)
                self._session_factories.pop(cache_key, None)
                if engine:
                    engine.dispose()
                    logger.info('SQLite engine disposed: %s', cache_key)

    def has_sqlite(self, sub_system_sc: str) -> bool:
        """檢查子系統是否已初始化 SQLite"""
        portal_dir = _get_portal_dir(sub_system_sc)
        return portal_dir.exists() and (portal_dir / 'portal.db').exists()


# =============================================================================
# 子系統 SQLite 初始化 / 清理
# =============================================================================

# portal.db 初始 schema: 帳號 + 角色 + 設定
_PORTAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS portal_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    secure_code TEXT NOT NULL UNIQUE,
    username TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    email TEXT DEFAULT '',
    password_hash TEXT NOT NULL,
    role_code TEXT NOT NULL DEFAULT 'GUEST',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS portal_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    permissions TEXT NOT NULL DEFAULT '{}',
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS portal_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 預設角色
INSERT OR IGNORE INTO portal_roles (code, name, description, display_order)
VALUES
    ('GUEST', '訪客', '匿名只讀角色', 0),
    ('PUBLIC_USER', '註冊用戶', '已註冊的公開用戶', 10);
"""

_PORTAL_SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS portal_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    display_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS portal_levels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    rank INTEGER NOT NULL,
    display_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO portal_groups (code, name, display_order)
VALUES ('GENERAL', '一般', 0);

INSERT OR IGNORE INTO portal_levels (code, name, rank, display_order)
VALUES
    ('GUEST', '訪客', 0, 0),
    ('MEMBER', '會員', 10, 10),
    ('STAFF', '幹部', 50, 50),
    ('ADMIN', '管理', 90, 90);
"""

_PORTAL_SCHEMA_V3 = """
CREATE TABLE IF NOT EXISTS portal_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    resource TEXT NOT NULL,
    action TEXT NOT NULL,
    description TEXT DEFAULT '',
    risk_level TEXT NOT NULL DEFAULT 'normal' CHECK (risk_level IN ('low', 'normal', 'high', 'critical')),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (resource, action)
);

CREATE TABLE IF NOT EXISTS portal_admin_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    is_system INTEGER NOT NULL DEFAULT 0 CHECK (is_system IN (0, 1)),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS portal_role_permissions (
    role_id INTEGER NOT NULL,
    permission_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (role_id, permission_id),
    FOREIGN KEY (role_id) REFERENCES portal_admin_roles(id) ON DELETE CASCADE,
    FOREIGN KEY (permission_id) REFERENCES portal_permissions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS portal_user_roles (
    user_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    valid_from TEXT,
    valid_until TEXT,
    assigned_by INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, role_id),
    FOREIGN KEY (user_id) REFERENCES portal_users(id) ON DELETE CASCADE,
    FOREIGN KEY (role_id) REFERENCES portal_admin_roles(id) ON DELETE CASCADE,
    CHECK (valid_until IS NULL OR valid_from IS NULL OR valid_until > valid_from)
);

CREATE TABLE IF NOT EXISTS portal_user_permissions (
    user_id INTEGER NOT NULL,
    permission_id INTEGER NOT NULL,
    effect TEXT NOT NULL CHECK (effect IN ('allow', 'deny')),
    valid_from TEXT,
    valid_until TEXT,
    reason TEXT,
    assigned_by INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, permission_id),
    FOREIGN KEY (user_id) REFERENCES portal_users(id) ON DELETE CASCADE,
    FOREIGN KEY (permission_id) REFERENCES portal_permissions(id) ON DELETE CASCADE,
    CHECK (valid_until IS NULL OR valid_from IS NULL OR valid_until > valid_from)
);

CREATE TABLE IF NOT EXISTS portal_level_permissions (
    level_id INTEGER NOT NULL,
    permission_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (level_id, permission_id),
    FOREIGN KEY (level_id) REFERENCES portal_levels(id) ON DELETE CASCADE,
    FOREIGN KEY (permission_id) REFERENCES portal_permissions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_portal_user_roles_user ON portal_user_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_portal_user_roles_role ON portal_user_roles(role_id);
CREATE INDEX IF NOT EXISTS idx_portal_role_permissions_role ON portal_role_permissions(role_id);
CREATE INDEX IF NOT EXISTS idx_portal_user_permissions_user ON portal_user_permissions(user_id);
CREATE INDEX IF NOT EXISTS idx_portal_level_permissions_level ON portal_level_permissions(level_id);
"""

_PORTAL_SCHEMA_V4 = """
CREATE TABLE IF NOT EXISTS portal_files (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    secure_code       TEXT NOT NULL UNIQUE,
    platform_file_sc  TEXT NOT NULL,
    page_sc           TEXT NOT NULL,
    widget_id         TEXT NOT NULL,
    uploader_ref      TEXT NOT NULL,
    original_name     TEXT NOT NULL,
    file_size         INTEGER NOT NULL DEFAULT 0,
    file_ext          TEXT DEFAULT '',
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_portal_files_widget ON portal_files(page_sc, widget_id, is_deleted);
CREATE INDEX IF NOT EXISTS idx_portal_files_uploader ON portal_files(uploader_ref, is_deleted);

CREATE TABLE IF NOT EXISTS portal_file_acl (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    file_secure_code  TEXT NOT NULL,
    grantee_type      TEXT NOT NULL,
    grantee_code      TEXT NOT NULL,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(file_secure_code, grantee_type, grantee_code)
);
"""


def _execute_schema(conn, schema: str):
    """逐句執行 SQLite schema script。"""
    for stmt in schema.strip().split(';'):
        stmt = stmt.strip()
        if stmt:
            conn.execute(text(stmt))


def _table_columns(conn, table_name: str) -> set[str]:
    rows = conn.execute(text(f'PRAGMA table_info({table_name})')).mappings().all()
    return {row['name'] for row in rows}


def ensure_portal_schema(sub_system_sc: str):
    """
    確保 portal.db schema 已升級至最新版本。

    不負責建立 DB；portal.db 不存在時維持 FileNotFoundError。

    v4 portal_files 欄位語意:
      - secure_code: portal 側識別碼，未來會出現在公開 URL。
      - platform_file_sc: 對應 platform_files.secure_code，實體與加密在平台側。
      - uploader_ref: designer:<平台 users.secure_code> 或 u:<portal_users.secure_code>。
        portal 使用者上傳時不寫 platform_files.uploader_sc，避免平台帳號授權誤判。
    """
    portal_path = _get_db_path(sub_system_sc, 'portal')
    if not portal_path.exists():
        raise FileNotFoundError(
            _('SQLite 檔案不存在: %(path)s (子系統 %(sc)s 可能尚未初始化)',
              path=portal_path, sc=sub_system_sc)
        )

    engine = create_engine(
        f'sqlite:///{portal_path}',
        poolclass=NullPool,
        connect_args={'check_same_thread': False},
    )
    try:
        with engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.execute(text("PRAGMA foreign_keys=ON"))
            conn.execute(text("PRAGMA busy_timeout=5000"))
            version = conn.execute(text('PRAGMA user_version')).scalar() or 0
            if version >= 4:
                conn.commit()
                return

            if version < 2:
                _execute_schema(conn, _PORTAL_SCHEMA_V2)
                columns = _table_columns(conn, 'portal_users')
                if 'group_code' not in columns:
                    conn.execute(text('ALTER TABLE portal_users ADD COLUMN group_code TEXT DEFAULT NULL'))
                if 'level_code' not in columns:
                    conn.execute(text('ALTER TABLE portal_users ADD COLUMN level_code TEXT DEFAULT NULL'))
                conn.execute(text('PRAGMA user_version = 2'))

            if version < 3:
                _execute_schema(conn, _PORTAL_SCHEMA_V3)
                conn.execute(text('PRAGMA user_version = 3'))

            if version < 4:
                _execute_schema(conn, _PORTAL_SCHEMA_V4)
                conn.execute(text('PRAGMA user_version = 4'))

            conn.commit()
    finally:
        engine.dispose()


def init_portal_sqlite(sub_system_sc: str) -> Path:
    """
    初始化子系統 SQLite 資料庫

    建立目錄結構:
        data/nocode_portals/{sub_system_sc}/
          portal.db        -- 帳號 + 角色 + 設定
          portal_data.db   -- 公開資料 (空)

    Returns:
        portal 目錄的 Path

    Raises:
        OSError: 目錄/檔案建立失敗
    """
    portal_dir = _get_portal_dir(sub_system_sc)
    portal_dir.mkdir(parents=True, exist_ok=True)

    # portal.db — 帳號角色
    portal_path = portal_dir / 'portal.db'
    engine = create_engine(
        f'sqlite:///{portal_path}',
        poolclass=NullPool,
        connect_args={'check_same_thread': False},
    )
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(text("PRAGMA busy_timeout=5000"))
        _execute_schema(conn, _PORTAL_SCHEMA)
        conn.commit()
    engine.dispose()
    ensure_portal_schema(sub_system_sc)
    from .portal_permission_admin_service import seed_default_admin_roles
    seed_default_admin_roles(sub_system_sc)

    # portal_data.db — 公開資料 (空, 只建檔 + PRAGMA)
    data_path = portal_dir / 'portal_data.db'
    engine = create_engine(
        f'sqlite:///{data_path}',
        poolclass=NullPool,
        connect_args={'check_same_thread': False},
    )
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(text("PRAGMA busy_timeout=5000"))
        conn.commit()
    engine.dispose()

    logger.info('Portal SQLite initialized: %s', portal_dir)
    return portal_dir


def cleanup_portal_sqlite(sub_system_sc: str):
    """
    清理子系統 SQLite 資料庫 (刪除整個目錄)

    先從 DataSourceManager 移除快取的 engine，再刪除檔案系統。
    """
    # 先釋放 engine
    mgr = DataSourceManager()
    mgr.remove_engine(sub_system_sc)

    portal_dir = _get_portal_dir(sub_system_sc)
    if portal_dir.exists():
        shutil.rmtree(portal_dir, ignore_errors=True)
        logger.info('Portal SQLite cleaned up: %s', portal_dir)
