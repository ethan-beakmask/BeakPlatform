"""
062: fw_workflow_backgrounds 表新增 platform_file_sc 欄位

關聯到 platform_files 表，讓背景圖走 FileService 統一管理。
既有資料的 platform_file_sc 為 NULL，保持向下相容。

用法:
    python scripts/migrations/062_background_platform_file_sc.py          顯示說明
    python scripts/migrations/062_background_platform_file_sc.py --run    執行遷移
    python scripts/migrations/062_background_platform_file_sc.py --status 檢查狀態
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from app import create_app, db
from sqlalchemy import text


MIGRATION_ID = '062_background_platform_file_sc'


def check_status():
    """檢查欄位是否已存在"""
    result = db.session.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'fw_workflow_backgrounds'
          AND column_name = 'platform_file_sc'
    """))
    return result.fetchone() is not None


def run_migration():
    app = create_app()
    with app.app_context():
        if check_status():
            print(f"[{MIGRATION_ID}] 欄位 platform_file_sc 已存在，跳過")
            return True

        print(f"[{MIGRATION_ID}] 新增 platform_file_sc 欄位...")

        db.session.execute(text("""
            ALTER TABLE fw_workflow_backgrounds
            ADD COLUMN platform_file_sc VARCHAR(32)
        """))

        db.session.commit()
        print(f"[{MIGRATION_ID}] 完成")
        return True


def show_status():
    app = create_app()
    with app.app_context():
        exists = check_status()
        if exists:
            print(f"[{MIGRATION_ID}] 欄位 platform_file_sc 已存在")
        else:
            print(f"[{MIGRATION_ID}] 欄位尚未建立")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='062: fw_workflow_backgrounds 新增 platform_file_sc 欄位')
    parser.add_argument('--run', action='store_true', help='執行遷移')
    parser.add_argument('--status', action='store_true', help='檢查狀態')
    args = parser.parse_args()

    if args.run:
        run_migration()
    elif args.status:
        show_status()
    else:
        parser.print_help()
