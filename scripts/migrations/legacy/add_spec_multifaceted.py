#!/usr/bin/env python3
"""
Migration: 建立多面向規格表 fw_spec_multifaceted 與歷史表

變更：
1. 建立 fw_spec_multifaceted 表
2. 建立 fw_spec_multifaceted_histories 表
3. 建立所需索引

用法:
    python3 scripts/migrations/add_spec_multifaceted.py
    python3 scripts/migrations/add_spec_multifaceted.py --check   # 只檢查不執行
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from app import create_app, db


MIGRATIONS = [
    {
        'desc': '建立 fw_spec_multifaceted 表',
        'check': """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'fw_spec_multifaceted'
            )
        """,
        'check_val': 'True',
        'sql': """
            CREATE TABLE fw_spec_multifaceted (
                id BIGSERIAL PRIMARY KEY,
                secure_code VARCHAR(32) NOT NULL UNIQUE,
                org_secure_code VARCHAR(100) NOT NULL,
                name VARCHAR(200) NOT NULL,
                description TEXT,
                version INTEGER NOT NULL DEFAULT 1,
                fields JSONB NOT NULL DEFAULT '[]'::jsonb,
                active_facets JSONB NOT NULL DEFAULT '[]'::jsonb,
                status VARCHAR(20) NOT NULL DEFAULT 'active',
                linked_form_template_sc VARCHAR(32),
                linked_sql_table VARCHAR(100),
                last_modified_by VARCHAR(32),
                last_modified_by_name VARCHAR(200),
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                deleted_at TIMESTAMP
            )
        """,
    },
    {
        'desc': 'fw_spec_multifaceted: 建立 org_secure_code 索引',
        'check': """
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE indexname = 'idx_fw_spec_mf_org'
            )
        """,
        'check_val': 'True',
        'sql': """
            CREATE INDEX idx_fw_spec_mf_org
            ON fw_spec_multifaceted (org_secure_code)
        """,
    },
    {
        'desc': 'fw_spec_multifaceted: 建立 status 索引',
        'check': """
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE indexname = 'idx_fw_spec_mf_status'
            )
        """,
        'check_val': 'True',
        'sql': """
            CREATE INDEX idx_fw_spec_mf_status
            ON fw_spec_multifaceted (org_secure_code, status)
            WHERE is_deleted = FALSE
        """,
    },
    {
        'desc': '建立 fw_spec_multifaceted_histories 表',
        'check': """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'fw_spec_multifaceted_histories'
            )
        """,
        'check_val': 'True',
        'sql': """
            CREATE TABLE fw_spec_multifaceted_histories (
                id BIGSERIAL PRIMARY KEY,
                secure_code VARCHAR(32) NOT NULL UNIQUE,
                spec_secure_code VARCHAR(32) NOT NULL,
                version INTEGER NOT NULL,
                fields_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
                active_facets_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
                change_description TEXT,
                change_diff JSONB,
                changed_by VARCHAR(32),
                changed_by_name VARCHAR(200),
                org_secure_code VARCHAR(100) NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                deleted_at TIMESTAMP
            )
        """,
    },
    {
        'desc': 'fw_spec_multifaceted_histories: 建立 spec_secure_code 索引',
        'check': """
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE indexname = 'idx_fw_spec_mfh_spec'
            )
        """,
        'check_val': 'True',
        'sql': """
            CREATE INDEX idx_fw_spec_mfh_spec
            ON fw_spec_multifaceted_histories (spec_secure_code, version)
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
    parser = argparse.ArgumentParser(description='Spec Multifaceted Migration')
    parser.add_argument('--check', action='store_true', help='只檢查不執行')
    args = parser.parse_args()
    run_migration(check_only=args.check)
