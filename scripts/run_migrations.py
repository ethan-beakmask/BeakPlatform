#!/usr/bin/env python3
"""
run_migrations.py - Schema migration runner with version tracking

追蹤 scripts/migrations/ 及 modules/*/migrations/ 下的 .sql/.py 檔案，
記錄已執行的 migration，支援平台級與模組級統一管理。

用法:
    python3 scripts/run_migrations.py                # 顯示說明
    python3 scripts/run_migrations.py --status       # 顯示 migration 狀態
    python3 scripts/run_migrations.py --run          # 執行待處理的 migrations
    python3 scripts/run_migrations.py --mark-all     # 標記所有為已執行（不實際跑）
    python3 scripts/run_migrations.py --scan         # 掃描所有 migration 檔案

環境變數:
    DATABASE_URL  PostgreSQL 連線字串（必要）

Migration 檔案規範:
    - 平台級:  scripts/migrations/NNN_description.sql
    - 模組級:  modules/<name>/migrations/NNN_description.sql
    - 追蹤名稱:
        平台 → "001_menu_system.sql"（向下相容）
        模組 → "modules/form_workflow/001_create_tables.sql"
    - .sql 必須冪等（IF NOT EXISTS / ADD COLUMN IF NOT EXISTS）
    - .py  必須無參數可執行
    - 檔名含 _drop_ 的視為 rollback 腳本，自動排除
    - 檔名含 .deprecated 的自動排除
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


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLATFORM_MIGRATIONS_DIR = os.path.join(PROJECT_ROOT, 'scripts', 'migrations')
MODULES_DIR = os.path.join(PROJECT_ROOT, 'modules')

# 排除模式：rollback 腳本、deprecated 檔案
EXCLUDE_PATTERNS = [
    re.compile(r'_drop_'),
    re.compile(r'\.deprecated$'),
]


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


def _is_excluded(filename):
    """檢查檔案是否該排除（rollback / deprecated）"""
    for pattern in EXCLUDE_PATTERNS:
        if pattern.search(filename):
            return True
    return False


def _number_sort_key(filename):
    """從檔名提取編號排序，有編號在前，無編號在後"""
    match = re.match(r'^(\d+)', filename)
    if match:
        return (0, int(match.group(1)), filename)
    return (1, 0, filename)


def get_all_migration_files():
    """
    掃描平台級與模組級 migration 檔案。

    回傳: list of (tracking_key, filepath)
      - tracking_key: 存入 schema_migrations 的名稱
        平台: "001_menu_system.sql"
        模組: "modules/form_workflow/001_create_tables.sql"
      - filepath: 磁碟上的完整路徑
    """
    migrations = []

    # --- 平台級 ---
    if os.path.isdir(PLATFORM_MIGRATIONS_DIR):
        for f in sorted(os.listdir(PLATFORM_MIGRATIONS_DIR)):
            if not f.endswith(('.sql', '.py')):
                continue
            if f.startswith('__'):
                continue
            if _is_excluded(f):
                continue
            migrations.append((f, os.path.join(PLATFORM_MIGRATIONS_DIR, f)))

    # --- 模組級 ---
    if os.path.isdir(MODULES_DIR):
        for module_name in sorted(os.listdir(MODULES_DIR)):
            module_mig_dir = os.path.join(MODULES_DIR, module_name, 'migrations')
            if not os.path.isdir(module_mig_dir):
                continue
            for f in sorted(os.listdir(module_mig_dir)):
                if not f.endswith(('.sql', '.py')):
                    continue
                if f.startswith('__'):
                    continue
                if _is_excluded(f):
                    continue
                key = f"modules/{module_name}/{f}"
                migrations.append((key, os.path.join(module_mig_dir, f)))

    # 排序：平台先（依編號），模組後（依模組名 + 編號）
    def sort_key(item):
        key, _ = item
        if not key.startswith('modules/'):
            num_key = _number_sort_key(key)
            return (0, '', num_key)
        parts = key.split('/', 2)  # modules/<name>/<file>
        module_name = parts[1]
        filename = parts[2]
        num_key = _number_sort_key(filename)
        return (1, module_name, num_key)

    migrations.sort(key=sort_key)
    return migrations


def execute_sql_file(conn, filepath):
    """執行 .sql migration"""
    with open(filepath, 'r', encoding='utf-8') as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)


def execute_py_file(filepath):
    """執行 .py migration（subprocess）"""
    env = os.environ.copy()
    backend_dir = os.path.join(PROJECT_ROOT, 'backend')
    env['PYTHONPATH'] = backend_dir

    result = subprocess.run(
        [sys.executable, filepath],
        env=env,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    if result.stdout:
        for line in result.stdout.rstrip().split('\n'):
            print(f"    {line}")
    if result.returncode != 0:
        if result.stderr:
            for line in result.stderr.rstrip().split('\n'):
                print(f"    [ERR] {line}")
        raise RuntimeError(f"Migration failed with exit code {result.returncode}")


def terminate_other_connections(conn):
    """終止同 DB 的其他連線，避免 idle in transaction 鎖住後續 DDL"""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = current_database()
                  AND pid <> pg_backend_pid()
                  AND state = 'idle in transaction'
            """)
    except Exception:
        pass  # 非關鍵操作，失敗不中斷


def record_applied(conn, tracking_key):
    """記錄 migration 為已執行"""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO schema_migrations (filename) VALUES (%s) ON CONFLICT (filename) DO NOTHING",
            (tracking_key,),
        )


# =========================================================================
#  指令
# =========================================================================

def cmd_status(conn):
    """顯示 migration 狀態"""
    ensure_tracking_table(conn)
    applied = get_applied(conn)
    all_files = get_all_migration_files()

    pending_platform = []
    pending_modules = {}
    total_platform = 0
    total_modules = {}

    for key, _ in all_files:
        if key.startswith('modules/'):
            module = key.split('/')[1]
            total_modules.setdefault(module, 0)
            total_modules[module] += 1
            if key not in applied:
                pending_modules.setdefault(module, [])
                pending_modules[module].append(key)
        else:
            total_platform += 1
            if key not in applied:
                pending_platform.append(key)

    total = len(all_files)
    total_applied = len([k for k, _ in all_files if k in applied])
    total_pending = total - total_applied

    print(f"Migration 總覽: {total} 個檔案, {total_applied} 已執行, {total_pending} 待執行")
    print()

    # 平台
    print(f"[平台] {total_platform} 個, {total_platform - len(pending_platform)} 已執行, {len(pending_platform)} 待執行")
    if pending_platform:
        for f in pending_platform:
            print(f"  待執行: {f}")
    print()

    # 模組
    all_module_names = sorted(set(list(total_modules.keys()) + list(pending_modules.keys())))
    for module in all_module_names:
        t = total_modules.get(module, 0)
        p = pending_modules.get(module, [])
        print(f"[模組: {module}] {t} 個, {t - len(p)} 已執行, {len(p)} 待執行")
        for f in p:
            print(f"  待執行: {f}")

    if total_pending == 0:
        print("\n全部已執行，無待處理項目。")


def cmd_scan():
    """掃描所有 migration 檔案（不需 DB 連線）"""
    all_files = get_all_migration_files()

    current_section = None
    for key, filepath in all_files:
        if key.startswith('modules/'):
            section = f"modules/{key.split('/')[1]}"
        else:
            section = "platform"

        if section != current_section:
            if current_section is not None:
                print()
            current_section = section
            print(f"[{section}]")

        print(f"  {key}")

    print(f"\n共 {len(all_files)} 個 migration 檔案")


def cmd_run(conn):
    """執行待處理的 migrations"""
    ensure_tracking_table(conn)
    applied = get_applied(conn)
    all_files = get_all_migration_files()
    pending = [(key, path) for key, path in all_files if key not in applied]

    if not pending:
        print("無待執行的 migration。")
        return

    print(f"執行 {len(pending)} 個待處理 migration...\n")
    success = 0
    for key, filepath in pending:
        print(f"  [{key}] ", end="", flush=True)
        try:
            if filepath.endswith('.sql'):
                execute_sql_file(conn, filepath)
            elif filepath.endswith('.py'):
                print()  # .py 會有子輸出，換行
                execute_py_file(filepath)
                # .py migration 可能透過 create_app() 產生背景 DB 連線
                # 終止這些 idle in transaction 連線，避免鎖住後續 DDL
                terminate_other_connections(conn)
            record_applied(conn, key)
            if filepath.endswith('.sql'):
                print("OK")
            else:
                print(f"  [{key}] OK")
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
    all_files = get_all_migration_files()
    pending = [(key, path) for key, path in all_files if key not in applied]

    if not pending:
        print("所有 migration 已標記為已執行。")
        return

    for key, _ in pending:
        record_applied(conn, key)

    print(f"已標記 {len(pending)} 個 migration 為已執行:")
    for key, _ in pending:
        print(f"  {key}")


def main():
    parser = argparse.ArgumentParser(
        description='BeakPlatform Schema Migration Runner',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python3 scripts/run_migrations.py --status       # 查看狀態
  python3 scripts/run_migrations.py --scan         # 掃描檔案（不需 DB）
  python3 scripts/run_migrations.py --run          # 執行 pending migrations
  python3 scripts/run_migrations.py --mark-all     # 全部標記為已執行

掃描範圍:
  - scripts/migrations/*.sql|*.py          (平台級)
  - modules/*/migrations/*.sql|*.py        (模組級)

排除規則:
  - 檔名含 _drop_ → rollback 腳本，不自動執行
  - 檔名含 .deprecated → 已廢棄
""",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--status', action='store_true', help='顯示 migration 狀態')
    group.add_argument('--scan', action='store_true', help='掃描所有 migration 檔案')
    group.add_argument('--run', action='store_true', help='執行待處理的 migrations')
    group.add_argument('--mark-all', action='store_true', help='標記所有為已執行')
    args = parser.parse_args()

    # --scan 不需要 DB 連線
    if args.scan:
        cmd_scan()
        return

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
