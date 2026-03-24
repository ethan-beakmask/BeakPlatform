#!/usr/bin/env python3
"""
run_migrations.py - Schema migration runner with version tracking

追蹤 scripts/migrations/ 下的 .sql/.py 檔案，記錄已執行的 migration。

用法:
    python3 scripts/run_migrations.py                # 顯示說明
    python3 scripts/run_migrations.py --status       # 顯示 migration 狀態
    python3 scripts/run_migrations.py --run          # 執行待處理的 migrations
    python3 scripts/run_migrations.py --mark-all     # 標記所有為已執行（不實際跑）

環境變數:
    DATABASE_URL  PostgreSQL 連線字串（必要）
"""
import os
import sys
import re
import subprocess
import argparse
import urllib.parse

try:
    import psycopg2
except ImportError:
    print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)


MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'migrations')


def get_db_connection():
    """從 DATABASE_URL 建立資料庫連線"""
    url = os.environ.get('DATABASE_URL', '')
    if not url:
        print("ERROR: DATABASE_URL 環境變數未設定")
        sys.exit(1)

    parsed = urllib.parse.urlparse(url)
    conn = psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        user=parsed.username,
        password=parsed.password,
        dbname=parsed.path.lstrip('/'),
    )
    conn.autocommit = True
    return conn


def ensure_tracking_table(conn):
    """建立 schema_migrations 追蹤表（若不存在）"""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id SERIAL PRIMARY KEY,
                filename VARCHAR(255) NOT NULL UNIQUE,
                applied_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)


def get_applied(conn):
    """取得已執行的 migration 檔名集合"""
    with conn.cursor() as cur:
        cur.execute("SELECT filename FROM schema_migrations ORDER BY filename")
        return {row[0] for row in cur.fetchall()}


def get_migration_files():
    """取得排序後的 migration 檔案清單"""
    if not os.path.isdir(MIGRATIONS_DIR):
        print(f"ERROR: migrations 目錄不存在: {MIGRATIONS_DIR}")
        sys.exit(1)

    files = []
    for f in os.listdir(MIGRATIONS_DIR):
        if f.endswith(('.sql', '.py')) and not f.startswith('__'):
            files.append(f)

    def sort_key(name):
        """編號檔在前（依編號排序），無編號檔在後（依名稱排序）"""
        match = re.match(r'^(\d+)', name)
        if match:
            return (0, int(match.group(1)), name)
        return (1, 0, name)

    return sorted(files, key=sort_key)


def execute_sql_file(conn, filepath):
    """執行 .sql migration"""
    with open(filepath, 'r', encoding='utf-8') as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)


def execute_py_file(filepath):
    """執行 .py migration（subprocess）"""
    project_root = os.path.join(os.path.dirname(filepath), '..', '..')
    project_root = os.path.abspath(project_root)

    env = os.environ.copy()
    backend_dir = os.path.join(project_root, 'backend')
    env['PYTHONPATH'] = backend_dir

    result = subprocess.run(
        [sys.executable, filepath],
        env=env,
        capture_output=True,
        text=True,
        cwd=project_root,
    )
    if result.stdout:
        for line in result.stdout.rstrip().split('\n'):
            print(f"    {line}")
    if result.returncode != 0:
        if result.stderr:
            for line in result.stderr.rstrip().split('\n'):
                print(f"    [ERR] {line}")
        raise RuntimeError(f"Migration failed with exit code {result.returncode}")


def record_applied(conn, filename):
    """記錄 migration 為已執行"""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO schema_migrations (filename) VALUES (%s) ON CONFLICT (filename) DO NOTHING",
            (filename,),
        )


def cmd_status(conn):
    """顯示 migration 狀態"""
    ensure_tracking_table(conn)
    applied = get_applied(conn)
    all_files = get_migration_files()
    pending = [f for f in all_files if f not in applied]

    print(f"Migration 檔案: {len(all_files)}")
    print(f"已執行: {len(applied)}")
    print(f"待執行: {len(pending)}")
    if pending:
        print("\n待執行:")
        for f in pending:
            print(f"  - {f}")
    else:
        print("\n全部已執行，無待處理項目。")


def cmd_run(conn):
    """執行待處理的 migrations"""
    ensure_tracking_table(conn)
    applied = get_applied(conn)
    all_files = get_migration_files()
    pending = [f for f in all_files if f not in applied]

    if not pending:
        print("無待執行的 migration。")
        return

    print(f"執行 {len(pending)} 個待處理 migration...\n")
    success = 0
    for filename in pending:
        filepath = os.path.join(MIGRATIONS_DIR, filename)
        print(f"  [{filename}] ", end="", flush=True)
        try:
            if filename.endswith('.sql'):
                execute_sql_file(conn, filepath)
            elif filename.endswith('.py'):
                print()  # .py 會有子輸出，換行
                execute_py_file(filepath)
            record_applied(conn, filename)
            if filename.endswith('.sql'):
                print("OK")
            else:
                print(f"  [{filename}] OK")
            success += 1
        except Exception as e:
            print(f"FAILED: {e}")
            print(f"\n中斷。已完成 {success}/{len(pending)} 個。")
            sys.exit(1)

    print(f"\n完成。已執行 {success} 個 migration。")


def cmd_mark_all(conn):
    """標記所有 migrations 為已執行（不實際執行）"""
    ensure_tracking_table(conn)
    applied = get_applied(conn)
    all_files = get_migration_files()
    pending = [f for f in all_files if f not in applied]

    if not pending:
        print("所有 migration 已標記為已執行。")
        return

    for filename in pending:
        record_applied(conn, filename)

    print(f"已標記 {len(pending)} 個 migration 為已執行。")


def main():
    parser = argparse.ArgumentParser(
        description='BeakPlatform Schema Migration Runner',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python3 scripts/run_migrations.py --status       # 查看狀態
  python3 scripts/run_migrations.py --run          # 執行 pending migrations
  python3 scripts/run_migrations.py --mark-all     # 全部標記為已執行

新增 migration 檔案規範:
  - 檔名格式: NNN_description.sql 或 NNN_description.py
  - .sql: 純 SQL，建議用 IF NOT EXISTS 確保冪等
  - .py:  必須無參數即可執行 (python3 <file>)
""",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--status', action='store_true', help='顯示 migration 狀態')
    group.add_argument('--run', action='store_true', help='執行待處理的 migrations')
    group.add_argument('--mark-all', action='store_true', help='標記所有為已執行')
    args = parser.parse_args()

    conn = get_db_connection()
    try:
        if args.status:
            cmd_status(conn)
        elif args.run:
            cmd_run(conn)
        elif args.mark_all:
            cmd_mark_all(conn)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
