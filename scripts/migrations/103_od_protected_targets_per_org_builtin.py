#!/usr/bin/env python3
"""
103 - OpenDefense 內建保護網段改為 per-org DB 出廠值（冪等）

調整內容：
  1. od_protected_targets 新增 origin 欄位，既有資料視為 custom。
  2. 對所有未刪除企業種入 origin='builtin' 的 OpenDefense 出廠保護清單。

注意：
  正式環境重裝（PF-39）時要一併跑本 migration，確保 DB 約束與 model 定義一致。

使用方式：
    cd /opt/BeakPlatform-dev
    ./venv/bin/python scripts/migrations/103_od_protected_targets_per_org_builtin.py --dry-run
    ./venv/bin/python scripts/migrations/103_od_protected_targets_per_org_builtin.py
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import text

MIGRATION_ID = '103_od_protected_targets_per_org_builtin'

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent.parent
BACKEND_DIR = PROJECT_DIR / 'backend'
sys.path.insert(0, str(BACKEND_DIR))


def _load_env_file() -> None:
    """讀取 repo 根目錄 .env；既有環境變數優先，不覆蓋呼叫端設定。"""
    env_path = PROJECT_DIR / '.env'
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _active_orgs(conn):
    return conn.execute(
        text(
            """
            SELECT secure_code, code, domain_name
            FROM organizations
            WHERE is_deleted = false
            ORDER BY id
            """
        )
    ).fetchall()


def run(dry_run: bool) -> int:
    _load_env_file()
    if not os.environ.get('DATABASE_URL'):
        print(f'[{MIGRATION_ID}] [ERR] DATABASE_URL 未設定，且 .env 未提供，無法連線')
        return 1

    from app import create_app, db
    from app.defaults.od_protected_defaults import seed_org_builtin_protected_targets

    app = create_app()
    with app.app_context():
        conn = db.session
        print(f"[{MIGRATION_ID}] 模式: {'dry-run（未寫入）' if dry_run else 'run（會寫入）'}")

        ddl = (
            "ALTER TABLE od_protected_targets "
            "ADD COLUMN IF NOT EXISTS origin VARCHAR(20) NOT NULL DEFAULT 'custom'"
        )
        print('[SQL ] ' + ddl)
        conn.execute(text(ddl))

        orgs = _active_orgs(conn)
        print(f'[CHECK] 待處理企業數: {len(orgs)}')

        results = []
        for org in orgs:
            created = seed_org_builtin_protected_targets(org.secure_code)
            results.append((org, created))
            print(
                '[DONE] '
                f'org={org.code} domain={org.domain_name} '
                f'secure_code={org.secure_code} created={created}'
            )

        if dry_run:
            conn.rollback()
            print('[DRY ] 已 rollback，未寫入')
            return 0

        conn.commit()
        total = sum(created for _org, created in results)
        print(f'[DONE] 已 commit，新增 builtin 條目總數: {total}')
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description='od_protected_targets 內建保護網段改為 per-org builtin',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--dry-run', action='store_true', help='只列出檢查與 SQL，不寫入')
    args = parser.parse_args()
    return run(dry_run=args.dry_run)


if __name__ == '__main__':
    sys.exit(main())
