"""
056: organizations 表新增 is_system_org 欄位

在 DB 層面標記系統企業，不再依賴環境變數比對。
每套部署只有一筆 is_system_org=TRUE。

用法:
    python scripts/migrations/056_add_is_system_org_column.py          顯示說明
    python scripts/migrations/056_add_is_system_org_column.py --run    執行遷移
    python scripts/migrations/056_add_is_system_org_column.py --status 檢查狀態
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from app import create_app, db
from sqlalchemy import text


MIGRATION_ID = '056_add_is_system_org_column'


def check_status():
    """檢查欄位是否已存在"""
    result = db.session.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'organizations' AND column_name = 'is_system_org'
    """))
    return result.fetchone() is not None


def run_migration():
    app = create_app()
    with app.app_context():
        if check_status():
            print(f"[{MIGRATION_ID}] 欄位 is_system_org 已存在，跳過")
            return True

        from app.constants import SYSTEM_ORG_CODE

        print(f"[{MIGRATION_ID}] 新增 is_system_org 欄位...")

        # 加欄位，預設 FALSE
        db.session.execute(text("""
            ALTER TABLE organizations
            ADD COLUMN is_system_org BOOLEAN NOT NULL DEFAULT FALSE
        """))

        # 依據 SYSTEM_ORG_CODE 回填
        result = db.session.execute(text("""
            UPDATE organizations
            SET is_system_org = TRUE
            WHERE secure_code = :sys_code
        """), {'sys_code': SYSTEM_ORG_CODE})

        if result.rowcount == 1:
            print(f"  已標記系統企業: {SYSTEM_ORG_CODE}")
        elif result.rowcount == 0:
            print(f"  警告: 找不到 secure_code={SYSTEM_ORG_CODE} 的企業")
        else:
            print(f"  異常: 影響 {result.rowcount} 筆（應為 1）")

        # 建立索引
        db.session.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_organizations_is_system_org
            ON organizations (is_system_org) WHERE is_system_org = TRUE
        """))

        db.session.commit()
        print(f"[{MIGRATION_ID}] 完成")
        return True


def show_status():
    app = create_app()
    with app.app_context():
        exists = check_status()
        if exists:
            result = db.session.execute(text("""
                SELECT secure_code, domain_name, is_system_org
                FROM organizations WHERE is_system_org = TRUE
            """))
            rows = result.fetchall()
            print(f"[{MIGRATION_ID}] 欄位已存在，系統企業: {len(rows)} 筆")
            for r in rows:
                print(f"  - {r[0]} ({r[1]})")
        else:
            print(f"[{MIGRATION_ID}] 欄位尚未建立")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='056: organizations 新增 is_system_org 欄位')
    parser.add_argument('--run', action='store_true', help='執行遷移')
    parser.add_argument('--status', action='store_true', help='檢查狀態')
    args = parser.parse_args()

    if args.run:
        run_migration()
    elif args.status:
        show_status()
    else:
        parser.print_help()
