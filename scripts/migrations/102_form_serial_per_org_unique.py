#!/usr/bin/env python3
"""
102 - 表單 serial_number 唯一性與序號池改為 per-org（冪等）

背景：
  fw_form_instances.serial_number 原本以全平台 partial unique index 保護：
  fw_form_instances_serial_number_key UNIQUE (serial_number) WHERE is_deleted = false。
  但企業自訂編號規則的主路徑本來就是 per-org counter；beluga
  (_9c8TewkRkCBEf3XsUdqeF) 與 lion (G4vbVX8IiBsm0koHISSYFs) 的預設 FORM 規則
  內容完全相同（Form- + yy + mm + 5 位序號、每月重置、從 1 開始），兩家在同月
  各送第一張表單時第二家必定撞上舊的全域 unique。

調整內容：
  1. 先建立 partial unique index uq_fw_fi_org_serial_number：
     (org_secure_code, serial_number) WHERE is_deleted = false
  2. 再移除舊的全域 partial unique index fw_form_instances_serial_number_key。

注意：
  正式環境重裝（PF-39）時要一併跑本 migration，確保 DB 約束與 model 定義一致。

使用方式：
    cd /opt/BeakPlatform-dev
    ./venv/bin/python scripts/migrations/102_form_serial_per_org_unique.py --dry-run
    ./venv/bin/python scripts/migrations/102_form_serial_per_org_unique.py
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import text

MIGRATION_ID = '102_form_serial_per_org_unique'
NEW_INDEX = 'uq_fw_fi_org_serial_number'
OLD_INDEX = 'fw_form_instances_serial_number_key'

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


def _duplicate_rows(conn):
    return conn.execute(
        text(
            """
            SELECT org_secure_code, serial_number, COUNT(*) AS cnt
            FROM fw_form_instances
            WHERE is_deleted = false
            GROUP BY org_secure_code, serial_number
            HAVING COUNT(*) > 1
            ORDER BY cnt DESC, org_secure_code, serial_number
            LIMIT 50
            """
        )
    ).fetchall()


def _index_exists(conn, index_name: str) -> bool:
    return bool(conn.execute(text("SELECT to_regclass(:name)"), {'name': index_name}).scalar())


def run(dry_run: bool) -> int:
    _load_env_file()
    if not os.environ.get('DATABASE_URL'):
        print(f'[{MIGRATION_ID}] [ERR] DATABASE_URL 未設定，且 .env 未提供，無法連線')
        return 1

    from app import create_app, db

    app = create_app()
    with app.app_context():
        conn = db.session
        print(f"[{MIGRATION_ID}] 模式: {'dry-run（未寫入）' if dry_run else 'run（會寫入）'}")

        duplicates = _duplicate_rows(conn)
        if duplicates:
            print('[ERR] 發現 active form instance 重複 (org_secure_code, serial_number)，中止：')
            for row in duplicates:
                print(
                    '  '
                    f'org_secure_code={row.org_secure_code}, '
                    f'serial_number={row.serial_number}, count={row.cnt}'
                )
            conn.rollback()
            return 1
        print('[CHECK] active (org_secure_code, serial_number) 無重複')

        create_sql = f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {NEW_INDEX}
            ON fw_form_instances (org_secure_code, serial_number)
            WHERE is_deleted = false
        """
        drop_sql = f"DROP INDEX IF EXISTS {OLD_INDEX}"

        print('[SQL ] ' + ' '.join(create_sql.split()))
        print('[SQL ] ' + drop_sql)

        before_new = _index_exists(conn, NEW_INDEX)
        before_old = _index_exists(conn, OLD_INDEX)
        print(f'[BEFORE] {NEW_INDEX}: {"exists" if before_new else "missing"}')
        print(f'[BEFORE] {OLD_INDEX}: {"exists" if before_old else "missing"}')

        if dry_run:
            conn.rollback()
            print('[DRY ] 已 rollback，未寫入')
            return 0

        conn.execute(text(create_sql))
        conn.execute(text(drop_sql))
        conn.commit()
        print('[DONE] 已 commit')

        after_new = _index_exists(conn, NEW_INDEX)
        after_old = _index_exists(conn, OLD_INDEX)
        print(f'[AFTER] {NEW_INDEX}: {"exists" if after_new else "missing"}')
        print(f'[AFTER] {OLD_INDEX}: {"exists" if after_old else "missing"}')
        return 0 if after_new and not after_old else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description='fw_form_instances.serial_number unique index 改為 per-org',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--dry-run', action='store_true', help='只列出檢查與 SQL，不寫入')
    args = parser.parse_args()
    return run(dry_run=args.dry_run)


if __name__ == '__main__':
    sys.exit(main())
