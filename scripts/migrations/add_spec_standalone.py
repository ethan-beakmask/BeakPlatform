#!/usr/bin/env python3
"""
Migration: 支援獨立 Spec（不綁定 form_template）

變更：
1. fw_form_field_specs.form_template_secure_code 改為 nullable
2. fw_form_field_specs 新增 name 欄位
3. fw_form_field_spec_histories.form_template_secure_code 改為 nullable

用法:
    python3 scripts/migrations/add_spec_standalone.py
    python3 scripts/migrations/add_spec_standalone.py --check   # 只檢查不執行
"""
import sys
import os
import argparse

# 加入專案路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from app import create_app, db


MIGRATIONS = [
    {
        'desc': 'fw_form_field_specs: form_template_secure_code 改 nullable',
        'check': """
            SELECT is_nullable FROM information_schema.columns
            WHERE table_name = 'fw_form_field_specs'
              AND column_name = 'form_template_secure_code'
        """,
        'check_val': 'YES',
        'sql': """
            ALTER TABLE fw_form_field_specs
            ALTER COLUMN form_template_secure_code DROP NOT NULL
        """,
    },
    {
        'desc': 'fw_form_field_specs: 新增 name 欄位',
        'check': """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'fw_form_field_specs'
              AND column_name = 'name'
        """,
        'check_val': 'name',
        'sql': """
            ALTER TABLE fw_form_field_specs
            ADD COLUMN name VARCHAR(200)
        """,
    },
    {
        'desc': 'fw_form_field_spec_histories: form_template_secure_code 改 nullable',
        'check': """
            SELECT is_nullable FROM information_schema.columns
            WHERE table_name = 'fw_form_field_spec_histories'
              AND column_name = 'form_template_secure_code'
        """,
        'check_val': 'YES',
        'sql': """
            ALTER TABLE fw_form_field_spec_histories
            ALTER COLUMN form_template_secure_code DROP NOT NULL
        """,
    },
]


def run_migration(check_only=False):
    app = create_app()
    with app.app_context():
        for m in MIGRATIONS:
            result = db.session.execute(db.text(m['check'].strip())).fetchone()
            val = result[0] if result else None

            if str(val) == str(m['check_val']):
                print(f"  [SKIP] {m['desc']} (already done)")
                continue

            if check_only:
                print(f"  [TODO] {m['desc']}")
                continue

            print(f"  [EXEC] {m['desc']}...")
            db.session.execute(db.text(m['sql'].strip()))
            db.session.commit()
            print(f"         Done.")

    print("\nMigration complete.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Spec Standalone Migration')
    parser.add_argument('--check', action='store_true', help='只檢查不執行')
    args = parser.parse_args()
    run_migration(check_only=args.check)
