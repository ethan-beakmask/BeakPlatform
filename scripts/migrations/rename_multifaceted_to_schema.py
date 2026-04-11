"""
Migration: spec_multifaceted → spec_schema 全面改名

已於 2026-04-12 手動執行完成，此腳本僅作記錄。

變更內容:
1. ALTER TABLE fw_spec_multifaceted RENAME TO fw_spec_schema
2. ALTER TABLE fw_spec_multifaceted_histories RENAME TO fw_spec_schema_histories
3. 全部索引統一改名
4. menu_items.code: spec_formulate.spec_multifaceted → spec_formulate.spec_schema
5. menu_items.link_target: spec_formulate_web.spec_multifaceted → spec_formulate_web.spec_schema
"""
import argparse
import sys
sys.path.insert(0, '/opt/BeakPlatform-dev/backend')

STEPS = [
    {
        'desc': 'fw_spec_multifaceted → fw_spec_schema',
        'check': "SELECT 1 FROM information_schema.tables WHERE table_name = 'fw_spec_schema'",
        'sql': "ALTER TABLE fw_spec_multifaceted RENAME TO fw_spec_schema",
    },
    {
        'desc': 'fw_spec_multifaceted_histories → fw_spec_schema_histories',
        'check': "SELECT 1 FROM information_schema.tables WHERE table_name = 'fw_spec_schema_histories'",
        'sql': "ALTER TABLE fw_spec_multifaceted_histories RENAME TO fw_spec_schema_histories",
    },
    {
        'desc': '索引改名: pkey, secure_code_key, org, status, histories',
        'check': "SELECT 1 FROM pg_indexes WHERE indexname = 'fw_spec_schema_pkey'",
        'sql': """
            ALTER INDEX IF EXISTS fw_spec_multifaceted_pkey RENAME TO fw_spec_schema_pkey;
            ALTER INDEX IF EXISTS fw_spec_multifaceted_secure_code_key RENAME TO fw_spec_schema_secure_code_key;
            ALTER INDEX IF EXISTS fw_spec_multifaceted_histories_pkey RENAME TO fw_spec_schema_histories_pkey;
            ALTER INDEX IF EXISTS fw_spec_multifaceted_histories_secure_code_key RENAME TO fw_spec_schema_histories_secure_code_key;
            ALTER INDEX IF EXISTS idx_fw_spec_mf_org RENAME TO idx_fw_spec_schema_org;
            ALTER INDEX IF EXISTS idx_fw_spec_mf_status RENAME TO idx_fw_spec_schema_status;
            ALTER INDEX IF EXISTS idx_fw_spec_mfh_spec RENAME TO idx_fw_spec_schema_histories_spec;
        """,
    },
    {
        'desc': 'menu_items code 更新',
        'check': "SELECT 1 FROM menu_items WHERE code = 'spec_formulate.spec_schema'",
        'sql': """
            UPDATE menu_items
            SET code = 'spec_formulate.spec_schema',
                link_target = 'spec_formulate_web.spec_schema'
            WHERE code = 'spec_formulate.spec_multifaceted'
        """,
    },
]


def main():
    parser = argparse.ArgumentParser(description='Spec Multifaceted → Schema Migration')
    parser.add_argument('--check', action='store_true', help='只檢查不執行')
    args = parser.parse_args()

    from app import create_app
    from sqlalchemy import text
    app = create_app()

    with app.app_context():
        from app.database import db
        for step in STEPS:
            result = db.session.execute(text(step['check'])).fetchone()
            if result:
                print(f"[SKIP] {step['desc']} (已完成)")
                continue
            if args.check:
                print(f"[TODO] {step['desc']}")
                continue
            db.session.execute(text(step['sql']))
            db.session.commit()
            print(f"[DONE] {step['desc']}")


if __name__ == '__main__':
    main()
