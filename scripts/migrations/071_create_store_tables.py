"""
Migration 071: 建立內部商場資料表

store_items - 商場商品 (官方範本、軟體等)
store_installations - 企業安裝記錄
"""

MIGRATION_ID = '071'
DESCRIPTION = 'Create store_items and store_installations tables'


def run(conn):
    print(f"[{MIGRATION_ID}] {DESCRIPTION}")

    # ── store_items ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS store_items (
            id BIGSERIAL PRIMARY KEY,
            secure_code VARCHAR(32) NOT NULL UNIQUE,
            org_secure_code VARCHAR(100),

            code VARCHAR(100) NOT NULL UNIQUE,
            name VARCHAR(200) NOT NULL,
            description TEXT,
            icon VARCHAR(50),

            item_type VARCHAR(30) NOT NULL DEFAULT 'workflow_bundle',
            category VARCHAR(100),
            version VARCHAR(20) NOT NULL DEFAULT '1.0',

            payload JSONB,

            source VARCHAR(20) NOT NULL DEFAULT 'official',
            scope VARCHAR(20) NOT NULL DEFAULT 'tenant',

            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,

            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP,
            deleted_at TIMESTAMP,

            CONSTRAINT ck_store_items_type CHECK (item_type IN ('form_template', 'workflow_bundle', 'software')),
            CONSTRAINT ck_store_items_source CHECK (source IN ('official', 'enterprise')),
            CONSTRAINT ck_store_items_scope CHECK (scope IN ('tenant', 'platform'))
        )
    """)

    # ── store_installations ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS store_installations (
            id BIGSERIAL PRIMARY KEY,
            secure_code VARCHAR(32) NOT NULL UNIQUE,
            org_secure_code VARCHAR(100) NOT NULL,

            store_item_secure_code VARCHAR(32) NOT NULL REFERENCES store_items(secure_code),
            store_item_code VARCHAR(100) NOT NULL,
            installed_version VARCHAR(20) NOT NULL,

            installed_by_secure_code VARCHAR(32) NOT NULL,
            installed_by_name VARCHAR(100),
            installed_at TIMESTAMP NOT NULL DEFAULT NOW(),

            result_summary JSONB,

            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            deleted_at TIMESTAMP
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_store_items_type ON store_items(item_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_store_items_source ON store_items(source)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_store_items_scope ON store_items(scope)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_store_installations_org ON store_installations(org_secure_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_store_installations_item ON store_installations(store_item_secure_code)")

    # ── 選單項目: 內部商場 ──
    import secrets
    result = conn.execute(
        "SELECT 1 FROM menu_items WHERE code = 'store' AND is_deleted = false"
    )
    if not result.fetchone():
        sc = secrets.token_urlsafe(16)
        conn.execute(
            """INSERT INTO menu_items
               (secure_code, org_secure_code, code, title, link_type, link_target,
                display_order, required_level, icon, is_active, is_deleted,
                open_in_new_tab, depth, created_at, updated_at)
               VALUES (%s, 'system.local', 'store', '內部商場', 'route', 'store.index',
                3, 2, 'ri-store-2-line', true, false, false, 0, NOW(), NOW())""",
            (sc,)
        )
        print(f"  Created menu item: store (sc={sc})")

    print(f"  [{MIGRATION_ID}] Done")
