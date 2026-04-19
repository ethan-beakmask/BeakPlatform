"""
Migration 070: modules 表新增 scope 欄位

區分模組用途：
- tenant: 一般業務模組，可透過合約授權給任何企業
- platform: 基礎設施模組，僅系統企業可用，合約選單不顯示
"""
from datetime import datetime

MIGRATION_ID = '070'
DESCRIPTION = 'Add scope column to modules table'


def run(conn):
    print(f"[{MIGRATION_ID}] {DESCRIPTION}")

    # 檢查欄位是否已存在
    result = conn.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'modules' AND column_name = 'scope'
    """)
    if result.fetchone():
        print(f"  scope column already exists, skipping")
        return

    conn.execute("""
        ALTER TABLE modules
        ADD COLUMN scope VARCHAR(20) NOT NULL DEFAULT 'tenant'
    """)

    # 加檢查約束
    conn.execute("""
        ALTER TABLE modules
        ADD CONSTRAINT ck_modules_scope CHECK (scope IN ('tenant', 'platform'))
    """)

    print(f"  Added scope column to modules table (default: 'tenant')")
    print(f"  [{MIGRATION_ID}] Done")
