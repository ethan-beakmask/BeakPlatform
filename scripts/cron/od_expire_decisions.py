#!/usr/bin/env python3
"""
OpenDefense 排程入口:掃過期 applied 決策 → 自動產生 unblock。

用法:
    od_expire_decisions.py [--dry-run] [--limit N]

無參數:正式執行,寫入 DB,更新 heartbeat。
--dry-run:只列要做什麼,不寫 DB,不更新 heartbeat。
--limit N:單次掃描上限(預設 500)。

排程於 /etc/crontab(每分鐘),log 寫 /opt/tmp/BeakPlatform-cron-od_expire_decisions.log,
heartbeat 寫 /opt/tmp/heartbeat/od_expire_decisions.ok。
"""
import argparse
import logging
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / 'backend'
ENV_FILE = REPO_ROOT / '.env'
HEARTBEAT_PATH = Path('/opt/tmp/heartbeat/od_expire_decisions.ok')
LOG_PATH = Path('/opt/tmp/BeakPlatform-cron-od_expire_decisions.log')


def _bootstrap():
    """讓此 script 能 standalone 執行(載入 .env、加入 backend 到 sys.path)"""
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    # 載入 .env
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            os.environ.setdefault(k, v)


def _setup_logging():
    """
    2026-08-09 修訂：原設定讓此 log 長到 1.2 GB（每分鐘一輪，全量 INFO）。
    兩個成因各修一半：
      1. 根 logger 開在 INFO → Flask create_app() 的 module loader 每輪吐數十行。
         改成根 WARNING，只把本排程與 open_defense 自己的 logger 留在 INFO。
      2. 同時掛 FileHandler + StreamHandler(stdout)，而 crontab 又用
         `>> 同一個檔 2>&1`，於是每一行都被寫進去兩次。
         改成只在互動式執行(tty)時才額外輸出到 stdout。
    """
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    handlers = [logging.FileHandler(LOG_PATH, encoding='utf-8')]
    if sys.stdout.isatty():
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.WARNING,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=handlers,
    )
    logging.getLogger('od_expire_decisions').setLevel(logging.INFO)
    logging.getLogger('modules.open_defense').setLevel(logging.INFO)


def _write_heartbeat():
    HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    HEARTBEAT_PATH.touch()


def main() -> int:
    parser = argparse.ArgumentParser(
        description='OpenDefense 過期決策掃描 → 自動產生 unblock')
    parser.add_argument('--dry-run', action='store_true',
                        help='只列要做什麼,不寫 DB,不更新 heartbeat')
    parser.add_argument('--limit', type=int, default=500,
                        help='單次掃描上限(預設 500)')
    args = parser.parse_args()

    _bootstrap()
    _setup_logging()
    log = logging.getLogger('od_expire_decisions')

    try:
        from app import create_app
    except Exception as exc:
        log.error('無法載入 Flask app: %s', exc)
        return 2

    app = create_app()
    with app.app_context():
        try:
            from modules.open_defense.services.expiry_service import (
                run_expiry_pass,
            )
            result = run_expiry_pass(dry_run=args.dry_run, limit=args.limit)
        except Exception as exc:
            log.exception('expiry pass crashed: %s', exc)
            return 3

    log.info('expiry_pass result: scanned=%d unblocked=%d errors=%d dry_run=%s',
             result['scanned'], result['unblocked'],
             len(result['errors']), result['dry_run'])

    if result['errors']:
        for e in result['errors']:
            log.warning('  err: %s', e)
        # 有 error 不算成功,不更新 heartbeat
        return 1

    if not args.dry_run:
        _write_heartbeat()

    return 0


if __name__ == '__main__':
    sys.exit(main())
