"""
Migration 071: 建立內部商場資料表

store_items - 商場商品 (官方範本、軟體等)
store_installations - 企業安裝記錄

用法:
    python scripts/migrations/071_create_store_tables.py          顯示說明
    python scripts/migrations/071_create_store_tables.py --run    執行遷移
    python scripts/migrations/071_create_store_tables.py --status 檢查狀態
"""
import argparse
import secrets
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from app import create_app, db
from sqlalchemy import text

MIGRATION_ID = '071'
DESCRIPTION = 'Create store_items and store_installations tables'


def check_status():
    """檢查表是否已存在"""
    result = db.session.execute(text("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'store_items'
    """))
    return result.fetchone() is not None


def run_migration():
    """執行遷移"""
    app = create_app()
    with app.app_context():
        if check_status():
            print(f"[{MIGRATION_ID}] store_items 表已存在，跳過")
            return True

        print(f"[{MIGRATION_ID}] {DESCRIPTION}")

        # ── store_items ──
        db.session.execute(text("""
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
        """))

        # ── store_installations ──
        db.session.execute(text("""
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
        """))

        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_store_items_type ON store_items(item_type)"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_store_items_source ON store_items(source)"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_store_items_scope ON store_items(scope)"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_store_installations_org ON store_installations(org_secure_code)"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_store_installations_item ON store_installations(store_item_secure_code)"))

        # ── 選單項目: 內部商場 ──
        result = db.session.execute(text(
            "SELECT 1 FROM menu_items WHERE code = 'store' AND is_deleted = false"
        ))
        if not result.fetchone():
            # 動態取得系統企業 secure_code
            sys_org = db.session.execute(text(
                "SELECT secure_code FROM organizations WHERE is_system_org = true LIMIT 1"
            )).fetchone()
            if not sys_org:
                print(f"  [WARN] 找不到系統企業，跳過選單建立")
            else:
                sc = secrets.token_urlsafe(16)
                db.session.execute(text("""
                    INSERT INTO menu_items
                    (secure_code, org_secure_code, code, title, link_type, link_target,
                     display_order, required_level, icon, is_active, is_deleted,
                     open_in_new_tab, depth, is_expanded, is_shared, is_user_created,
                     created_at, updated_at)
                    VALUES (:sc, :org_sc, 'store', '內部商場', 'url', '/store/',
                     3, 2, 'ri-store-2-line', true, false, false, 0, false, false, false,
                     NOW(), NOW())
                """), {'sc': sc, 'org_sc': sys_org[0]})
                print(f"  Created menu item: store (sc={sc})")

        db.session.commit()
        print(f"[{MIGRATION_ID}] Done")
        return True


def show_status():
    app = create_app()
    with app.app_context():
        exists = check_status()
        if exists:
            result = db.session.execute(text("SELECT count(*) FROM store_items"))
            count = result.scalar()
            print(f"[{MIGRATION_ID}] store_items 表已存在，{count} 筆記錄")
        else:
            print(f"[{MIGRATION_ID}] store_items 表尚未建立")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='071: 建立內部商場資料表')
    parser.add_argument('--run', action='store_true', help='執行遷移')
    parser.add_argument('--status', action='store_true', help='檢查狀態')
    args = parser.parse_args()

    if args.run:
        run_migration()
    elif args.status:
        show_status()
    else:
        parser.print_help()
