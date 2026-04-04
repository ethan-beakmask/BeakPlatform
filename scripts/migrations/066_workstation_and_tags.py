"""
066: 工作站與標籤系統

新增表單工作站（表單中心的專業視角）和標籤系統。

變更內容：
1. 建立 fw_workstations 表 - 工作站定義
2. 建立 fw_workstation_permissions 表 - 工作站存取權限
3. 建立 fw_form_tags 表 - 表單標籤
4. 建立 fw_form_template_tags 表 - 表單模板-標籤關聯

用法:
    python scripts/migrations/066_workstation_and_tags.py          顯示說明
    python scripts/migrations/066_workstation_and_tags.py --status 檢查狀態
    python scripts/migrations/066_workstation_and_tags.py --run    執行遷移
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from app import create_app, db

MIGRATION_ID = '066_workstation_and_tags'

TABLES = [
    'fw_workstations',
    'fw_workstation_permissions',
    'fw_form_tags',
    'fw_form_template_tags',
]


def check_status():
    """檢查遷移狀態"""
    app = create_app()
    with app.app_context():
        for table in TABLES:
            exists = db.session.execute(
                db.text(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = :t)"
                ),
                {'t': table}
            ).scalar()
            status = 'EXISTS' if exists else 'MISSING'
            print(f'  {table}: {status}')


def run_migration():
    """執行遷移"""
    app = create_app()
    with app.app_context():
        # 匯入 Model 確保 metadata 已註冊
        from modules.form_workflow.models import (
            FwWorkstation, FwWorkstationPermission,
            FwFormTag, FwFormTemplateTag,
        )

        created = []
        for table in TABLES:
            exists = db.session.execute(
                db.text(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = :t)"
                ),
                {'t': table}
            ).scalar()
            if not exists:
                created.append(table)

        if not created:
            print('All tables already exist. Nothing to do.')
            return

        # 建立缺失的表
        target_tables = []
        table_map = {
            'fw_workstations': FwWorkstation.__table__,
            'fw_workstation_permissions': FwWorkstationPermission.__table__,
            'fw_form_tags': FwFormTag.__table__,
            'fw_form_template_tags': FwFormTemplateTag.__table__,
        }
        for name in created:
            target_tables.append(table_map[name])

        db.metadata.create_all(db.engine, tables=target_tables)
        print(f'Created tables: {", ".join(created)}')

        db.session.commit()
        print('Migration completed successfully.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=MIGRATION_ID)
    parser.add_argument('--run', action='store_true', help='Execute migration')
    parser.add_argument('--status', action='store_true', help='Check status')
    args = parser.parse_args()

    if args.status:
        check_status()
    elif args.run:
        run_migration()
    else:
        print(__doc__)
