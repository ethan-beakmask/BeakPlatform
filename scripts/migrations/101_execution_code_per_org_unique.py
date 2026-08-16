#!/usr/bin/env python3
"""
101 - PF-116：workflow execution_code 序號池改為 per-org（冪等）

背景：
  fw_workflow_instances.execution_code 原本以 SELECT MAX(...)+1 產生，但唯一性與查詢池
  都是全平台共用。這會造成兩個問題：
    1. 側信道洩漏：企業可從 OD-YYYYMMDD-NNNN 推知平台其他企業同日案件量。
    2. 並發撞號：OpenDefense intake 的 advisory lock 是 per-org，但 MAX 查詢是全域；
       多企業同時 intake 可能算出同一序號並撞上舊的全域 unique index。

調整內容：
  1. 先建立 partial unique index uq_fw_wi_org_execution_code：
     (org_secure_code, execution_code) WHERE is_deleted = false
  2. 再移除舊的全域 partial unique index fw_workflow_instances_execution_code_key。

注意：
  正式環境重裝（PF-39）時要一併跑本 migration，確保 DB 約束與 model 定義一致。

使用方式：
    cd /opt/BeakPlatform-dev
    ./venv/bin/python scripts/migrations/101_execution_code_per_org_unique.py --dry-run
    ./venv/bin/python scripts/migrations/101_execution_code_per_org_unique.py
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import text

MIGRATION_ID = '101_execution_code_per_org_unique'
NEW_INDEX = 'uq_fw_wi_org_execution_code'
OLD_INDEX = 'fw_workflow_instances_execution_code_key'

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
            SELECT org_secure_code, execution_code, COUNT(*) AS cnt
            FROM fw_workflow_instances
            WHERE is_deleted = false
            GROUP BY org_secure_code, execution_code
            HAVING COUNT(*) > 1
            ORDER BY cnt DESC, org_secure_code, execution_code
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
            print('[ERR] 發現 active workflow instance 重複 (org_secure_code, execution_code)，中止：')
            for row in duplicates:
                print(
                    '  '
                    f'org_secure_code={row.org_secure_code}, '
                    f'execution_code={row.execution_code}, count={row.cnt}'
                )
            conn.rollback()
            return 1
        print('[CHECK] active (org_secure_code, execution_code) 無重複')

        create_sql = f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {NEW_INDEX}
            ON fw_workflow_instances (org_secure_code, execution_code)
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
        description='PF-116: fw_workflow_instances.execution_code unique index 改為 per-org',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--dry-run', action='store_true', help='只列出檢查與 SQL，不寫入')
    args = parser.parse_args()
    return run(dry_run=args.dry_run)


if __name__ == '__main__':
    sys.exit(main())
