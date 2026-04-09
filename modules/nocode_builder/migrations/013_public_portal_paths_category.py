#!/usr/bin/env python3
"""
013: 建立 PUBLIC_PORTAL_PATHS lookup category

公開子系統路徑管理用的 lookup 類別。
子系統建立時自動在此 category 下建立 lookup_item，
item.code = 隨機路徑 ID，item.value_str = sub_system_secure_code。

由 run_migrations.py 無參數執行。冪等：已存在則 SKIP。
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'backend'))

from app import create_app, db
from sqlalchemy import text

CATEGORY_CODE = 'PUBLIC_PORTAL_PATHS'


def check_exists():
    """檢查 category 是否已存在"""
    row = db.session.execute(
        text("SELECT id FROM lookup_categories WHERE code = :code"),
        {'code': CATEGORY_CODE},
    ).fetchone()
    return row is not None


def run_migration(dry_run=True):
    """執行 migration"""
    if check_exists():
        print(f'[SKIP] Category {CATEGORY_CODE} already exists')
        return

    if dry_run:
        print(f'[DRY-RUN] Would insert lookup_category: code={CATEGORY_CODE}')
        return

    from app.utils.security import generate_secure_code

    sc = generate_secure_code()
    db.session.execute(
        text("""
            INSERT INTO lookup_categories
                (secure_code, code, name, description, is_system, is_hierarchical,
                 org_secure_code, created_at, updated_at, is_deleted)
            VALUES
                (:sc, :code, :name, :desc, TRUE, FALSE,
                 NULL, NOW(), NOW(), FALSE)
        """),
        {
            'sc': sc,
            'code': CATEGORY_CODE,
            'name': '公開 Portal 路徑',
            'desc': '子系統公開存取路徑對照表 (path_id -> sub_system_secure_code)',
        },
    )
    db.session.commit()
    print(f'[OK] Inserted lookup_category: code={CATEGORY_CODE}, secure_code={sc}')


def main():
    app = create_app()
    with app.app_context():
        run_migration(dry_run=False)


if __name__ == '__main__':
    main()
