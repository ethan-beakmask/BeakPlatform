#!/usr/bin/env python3
"""
055: 將系統企業識別碼從硬編碼 'system.local' 更新為環境變數值

此遷移腳本在部署時執行，將 DB 中所有 'system.local' 參照
更新為 SYSTEM_ORG_CODE 環境變數指定的值。

若 SYSTEM_ORG_CODE 未設定或等於 'system.local'，則跳過。

無參數執行時自動遷移（相容 run_migrations.py）。
若 SYSTEM_ORG_CODE 未設定或等於 'system.local'，自動跳過。

使用方式:
    python 055_system_org_code_env.py              # 自動執行遷移
    python 055_system_org_code_env.py --dry-run    # 預覽模式
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

# 遷移期間跳過模組同步，避免 DB 尚未更新時 FK violation
os.environ['SKIP_MODULE_SYNC'] = '1'

from app import create_app, db
from app.constants import SYSTEM_ORG_CODE
from sqlalchemy import text

OLD_CODE = 'system.local'


def migrate(dry_run=False):
    if SYSTEM_ORG_CODE == OLD_CODE:
        print(f"SYSTEM_ORG_CODE = '{OLD_CODE}'，與舊值相同，跳過遷移。")
        return

    app = create_app()
    with app.app_context():
        prefix = "[DRY-RUN] " if dry_run else ""

        # 1. 更新 organizations 表
        print(f"\n{prefix}更新 organizations 表...")
        if not dry_run:
            db.session.execute(text("""
                UPDATE organizations
                SET secure_code = :new_code,
                    domain_name = :new_code,
                    name = :new_code
                WHERE secure_code = :old_code
            """), {'new_code': SYSTEM_ORG_CODE, 'old_code': OLD_CODE})
        print(f"  {prefix}secure_code, domain_name, name: '{OLD_CODE}' -> '{SYSTEM_ORG_CODE}'")

        # 2. 更新 users 表 (org_secure_code + admin email)
        print(f"\n{prefix}更新 users 表...")
        if not dry_run:
            db.session.execute(text("""
                UPDATE users
                SET org_secure_code = :new_code
                WHERE org_secure_code = :old_code
            """), {'new_code': SYSTEM_ORG_CODE, 'old_code': OLD_CODE})

            # 更新 admin 郵箱
            old_email = f'admin@{OLD_CODE}'
            new_email = f'admin@{SYSTEM_ORG_CODE}'
            result = db.session.execute(text("""
                UPDATE users
                SET email = :new_email
                WHERE email = :old_email
            """), {'new_email': new_email, 'old_email': old_email})
            print(f"  {prefix}admin email: '{old_email}' -> '{new_email}' ({result.rowcount} rows)")

        # 3. 更新 menu_items 表
        print(f"\n{prefix}更新 menu_items 表...")
        if not dry_run:
            result = db.session.execute(text("""
                UPDATE menu_items
                SET org_secure_code = :new_code
                WHERE org_secure_code = :old_code
            """), {'new_code': SYSTEM_ORG_CODE, 'old_code': OLD_CODE})
            print(f"  {prefix}更新 {result.rowcount} 筆")

        # 4. 更新 roles 表
        print(f"\n{prefix}更新 roles 表...")
        if not dry_run:
            result = db.session.execute(text("""
                UPDATE roles
                SET org_secure_code = :new_code
                WHERE org_secure_code = :old_code
            """), {'new_code': SYSTEM_ORG_CODE, 'old_code': OLD_CODE})
            print(f"  {prefix}更新 {result.rowcount} 筆")

        # 5. 更新 modules 表
        print(f"\n{prefix}更新 modules 表...")
        if not dry_run:
            result = db.session.execute(text("""
                UPDATE modules
                SET org_secure_code = :new_code
                WHERE org_secure_code = :old_code
            """), {'new_code': SYSTEM_ORG_CODE, 'old_code': OLD_CODE})
            print(f"  {prefix}更新 {result.rowcount} 筆")

        # 6. 更新 menu_role_requirements 表
        print(f"\n{prefix}更新 menu_role_requirements 表...")
        if not dry_run:
            result = db.session.execute(text("""
                UPDATE menu_role_requirements
                SET org_secure_code = :new_code
                WHERE org_secure_code = :old_code
            """), {'new_code': SYSTEM_ORG_CODE, 'old_code': OLD_CODE})
            print(f"  {prefix}更新 {result.rowcount} 筆")

        if not dry_run:
            db.session.commit()
            print(f"\n遷移完成: '{OLD_CODE}' -> '{SYSTEM_ORG_CODE}'")
        else:
            db.session.rollback()
            print(f"\n[DRY-RUN] 預覽完成，未實際變更。")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='遷移系統企業識別碼')
    parser.add_argument('--dry-run', action='store_true', help='預覽模式')
    args = parser.parse_args()

    migrate(dry_run=args.dry_run)
