#!/usr/bin/env python3
"""
OpenDefense 排程入口:平台端自產 EDL 黑名單檔案。

用法:
    od_render_edl.py [--dry-run] [--org ORG_SECURE_CODE]

無參數:正式執行,寫出所有企業 EDL,更新 heartbeat。
--dry-run:只計算各企業 EDL,不寫檔,不更新 heartbeat。
--org ORG_SECURE_CODE:只處理單一企業。

排程 log 寫 /opt/tmp/BeakPlatform-cron-od_render_edl.log,
heartbeat 寫 /opt/tmp/heartbeat/od_render_edl.ok。
"""
import argparse
import logging
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / 'backend'
ENV_FILE = REPO_ROOT / '.env'
HEARTBEAT_PATH = Path('/opt/tmp/heartbeat/od_render_edl.ok')
LOG_PATH = Path('/opt/tmp/BeakPlatform-cron-od_render_edl.log')


def _bootstrap():
    """讓此 script 能 standalone 執行(載入 .env、加入 backend 到 sys.path)"""
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
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
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    handlers = [logging.FileHandler(LOG_PATH, encoding='utf-8')]
    if sys.stdout.isatty():
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.WARNING,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=handlers,
    )
    logging.getLogger('od_render_edl').setLevel(logging.INFO)
    logging.getLogger('modules.open_defense').setLevel(logging.INFO)


def _write_heartbeat():
    HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    HEARTBEAT_PATH.touch()


def main() -> int:
    parser = argparse.ArgumentParser(
        description='OpenDefense 平台端 EDL 黑名單檔案產生')
    parser.add_argument('--dry-run', action='store_true',
                        help='只計算 EDL,不寫檔,不更新 heartbeat')
    parser.add_argument('--org', metavar='ORG_SECURE_CODE',
                        help='只處理指定企業 secure_code')
    args = parser.parse_args()

    _bootstrap()
    _setup_logging()
    log = logging.getLogger('od_render_edl')

    try:
        from app import create_app
    except Exception as exc:
        log.error('無法載入 Flask app: %s', exc)
        return 2

    app = create_app()
    with app.app_context():
        try:
            if args.org:
                from modules.open_defense.services.edl_service import (
                    collect_active_blocks,
                    get_output_dir,
                    write_org_edl,
                )
                if args.dry_run:
                    entries = collect_active_blocks(args.org)
                    result = {
                        'orgs': 1,
                        'written': 0,
                        'errors': [],
                        'dry_run': True,
                        'details': [{
                            'org_secure_code': args.org,
                            'path': str(Path(get_output_dir()) / args.org / 'blocklist.txt'),
                            'count': len(entries),
                            'written': False,
                            'error': None,
                        }],
                    }
                else:
                    detail = write_org_edl(args.org)
                    result = {
                        'orgs': 1,
                        'written': 1 if detail.get('written') else 0,
                        'errors': [detail] if detail.get('error') else [],
                        'dry_run': False,
                        'details': [detail],
                    }
            else:
                from modules.open_defense.services.edl_service import render_all_orgs
                result = render_all_orgs(dry_run=args.dry_run)
        except Exception as exc:
            log.exception('EDL render crashed: %s', exc)
            return 3

    log.info('render_edl result: orgs=%d written=%d errors=%d dry_run=%s',
             result['orgs'], result['written'],
             len(result['errors']), result['dry_run'])

    for detail in result['details']:
        log.info('  org=%s count=%d written=%s path=%s error=%s',
                 detail['org_secure_code'], detail['count'],
                 detail['written'], detail['path'], detail['error'])

    if result['errors']:
        for error in result['errors']:
            log.warning('  err: %s', error)
        return 1

    if not args.dry_run:
        _write_heartbeat()

    return 0


if __name__ == '__main__':
    sys.exit(main())
