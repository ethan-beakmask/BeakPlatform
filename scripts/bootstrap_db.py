#!/usr/bin/env python3
"""
BeakPlatform DB bootstrap 入口。

用法：
  cd backend && python3 ../scripts/bootstrap_db.py --fresh
      全新安裝（需環境變數 ADMIN_INITIAL_PASSWORD）
  cd backend && python3 ../scripts/bootstrap_db.py --update
      升級（只補新表、冪等 seed、同步選單權限模組）
"""
import argparse
import logging
import os
import sys


os.environ.setdefault('SKIP_MODULE_SYNC', '1')
os.environ.setdefault('EXECUTOR_STANDALONE', '1')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
BACKEND_DIR = os.path.join(REPO_ROOT, 'backend')
sys.path.insert(0, BACKEND_DIR)


USAGE = """用法：
  cd backend && python3 ../scripts/bootstrap_db.py --fresh
      全新安裝（需環境變數 ADMIN_INITIAL_PASSWORD）
  cd backend && python3 ../scripts/bootstrap_db.py --update
      升級（只補新表、冪等 seed、同步選單權限模組）

選項：
  --sql-dir <dir>   SQL extras 目錄（預設 <repo>/scripts/sql）
  --verbose         顯示 app 的 INFO log（預設只顯示 WARNING 以上）
"""


def parse_args(argv):
    if not argv:
        print(USAGE)
        sys.exit(2)

    parser = argparse.ArgumentParser(
        description='BeakPlatform 安裝與升級共用 DB bootstrap',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=USAGE,
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--fresh', action='store_true', help='全新安裝')
    mode.add_argument('--update', action='store_true', help='升級')
    parser.add_argument('--sql-dir', help='SQL extras 目錄（預設 <repo>/scripts/sql）')
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='顯示 app 的 INFO log（預設只顯示 WARNING 以上）',
    )
    return parser.parse_args(argv)


def print_summary(summary):
    labels = {
        'create_tables': '建表',
        'verify_superuser_objects': 'superuser 物件驗證',
        'ensure_system_org': '系統企業與管理員',
        'check_system_org': '系統企業檢查',
        'apply_sql_extras': 'SQL extras',
        'seed_platform_menus': '平台選單',
        'seed_system_permissions': '平台權限',
        'sync_modules': '模組同步',
        'seed_system_org_defaults': '系統企業出廠資料',
    }
    for key, value in summary.items():
        print(f"{labels.get(key, key)}: {value}")


def main():
    args = parse_args(sys.argv[1:])
    level = logging.INFO if args.verbose else logging.WARNING
    logging.basicConfig(level=level, format='%(levelname)s:%(name)s:%(message)s')

    try:
        from sqlalchemy.engine import make_url
        from app import create_app
        from app.defaults.bootstrap import BootstrapError, run_bootstrap

        app = create_app()
        with app.app_context():
            url = make_url(app.config['SQLALCHEMY_DATABASE_URI'])
            mode = 'fresh' if args.fresh else 'update'
            print(f"bootstrap 模式: {mode}，資料庫: {url.database}")
            summary = run_bootstrap(
                mode,
                admin_password=os.environ.get('ADMIN_INITIAL_PASSWORD', '').strip(),
                sql_dir=args.sql_dir,
            )
            print_summary(summary)
        return 0
    except BootstrapError as exc:
        print(f"錯誤: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        logging.exception('bootstrap 失敗')
        print(f"錯誤: bootstrap 失敗: {exc}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
