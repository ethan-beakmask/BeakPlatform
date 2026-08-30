#!/usr/bin/env python3
"""
OsExecutor 排程入口:清理 stdout/stderr 輸出檔與 failed transient systemd unit。

用法:
    os_node_cleanup.py [--dry-run] [--keep-days N] [--keep-days-error N]

無參數:正式執行,刪除過期輸出檔,reset failed unit,更新 heartbeat。
--dry-run:只列出會刪除的檔案,不刪檔,不 reset-failed,不更新 heartbeat。
--keep-days N:覆寫一般結果保留天數,預設 7。
--keep-days-error N:覆寫 exception/timeout 保留天數,預設 30。

排程 log 寫 /opt/tmp/{專案目錄名}-cron-os_node_cleanup.log,
heartbeat 寫 /opt/tmp/heartbeat/os_node_cleanup.ok。
"""
import argparse
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / 'backend'
ENV_FILE = REPO_ROOT / '.env'
HEARTBEAT_PATH = Path('/opt/tmp/heartbeat/os_node_cleanup.ok')
LOG_PATH = Path('/opt/tmp') / f'{REPO_ROOT.name}-cron-os_node_cleanup.log'
OSNODE_ROOT = Path('/opt/tmp/osnode')
ERROR_RESULTS = {'exception', 'timeout'}


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
    logging.getLogger('os_node_cleanup').setLevel(logging.INFO)


def _write_heartbeat():
    HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    HEARTBEAT_PATH.touch()


def _non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('必須是非負整數') from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError('必須是非負整數')
    return parsed


def _iter_output_files(root: Path):
    if not root.exists():
        return
    for day_dir in sorted(root.iterdir()):
        if not day_dir.is_dir():
            continue
        for path in sorted(day_dir.iterdir()):
            if path.is_file() and path.suffix in ('.out', '.err'):
                yield path


def _extract_result_kind(result) -> str:
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            return ''
    if not isinstance(result, dict):
        return ''
    data = result.get('data')
    if not isinstance(data, dict):
        return ''
    value = data.get('_result')
    return value if isinstance(value, str) else ''


def _fetch_result_kinds(db, stems):
    if not stems:
        return {}

    rows = db.session.execute(
        db.text("""
            SELECT secure_code, result
            FROM fw_node_execution_queue
            WHERE secure_code = ANY(:codes)
        """),
        {'codes': list(stems)},
    ).mappings()

    return {
        row['secure_code']: _extract_result_kind(row['result'])
        for row in rows
    }


def _remove_empty_day_dirs(root: Path, log) -> int:
    if not root.exists():
        return 0

    removed = 0
    for day_dir in sorted(root.iterdir()):
        if not day_dir.is_dir():
            continue
        try:
            next(day_dir.iterdir())
        except StopIteration:
            try:
                day_dir.rmdir()
                removed += 1
            except OSError as exc:
                log.warning('移除空目錄失敗 path=%s error=%s', day_dir, exc)
    return removed


def _cleanup_output_files(db, keep_days: int, keep_days_error: int, dry_run: bool, log):
    files = list(_iter_output_files(OSNODE_ROOT))
    stems = sorted({path.stem for path in files})
    result_kinds = _fetch_result_kinds(db, stems)
    now = time.time()
    deleted = 0
    kept = 0

    for path in files:
        result_kind = result_kinds.get(path.stem, '')
        retention_days = keep_days_error if result_kind in ERROR_RESULTS else keep_days
        cutoff = now - (retention_days * 86400)

        try:
            mtime = os.path.getmtime(path)
        except OSError as exc:
            log.warning('讀取檔案 mtime 失敗 path=%s error=%s', path, exc)
            kept += 1
            continue

        if mtime > cutoff:
            kept += 1
            continue

        deleted += 1
        if dry_run:
            log.info('dry-run delete path=%s result=%s keep_days=%d mtime=%s',
                     path, result_kind or 'unknown', retention_days,
                     time.strftime('%Y-%m-%dT%H:%M:%S%z', time.localtime(mtime)))
            continue

        try:
            path.unlink()
        except OSError as exc:
            deleted -= 1
            kept += 1
            log.warning('刪除檔案失敗 path=%s error=%s', path, exc)

    dirs_removed = 0 if dry_run else _remove_empty_day_dirs(OSNODE_ROOT, log)
    return {
        'scanned': len(files),
        'deleted': deleted,
        'kept': kept,
        'dirs_removed': dirs_removed,
    }


def _reset_failed_units(log) -> str:
    try:
        proc = subprocess.run(
            ['sudo', '-n', 'systemctl', 'reset-failed', 'bp-*'],
            capture_output=True,
            timeout=30,
        )
    except Exception as exc:
        log.warning('systemctl reset-failed 執行失敗: %s', exc)
        return 'warning'

    if proc.returncode != 0:
        stderr = proc.stderr.decode('utf-8', errors='replace').strip()
        stdout = proc.stdout.decode('utf-8', errors='replace').strip()
        log.warning('systemctl reset-failed 回傳非 0: rc=%s stdout=%s stderr=%s',
                    proc.returncode, stdout[:500], stderr[:500])
        return 'warning'

    return 'ok'


def main() -> int:
    parser = argparse.ArgumentParser(
        description='清理 OsExecutor 輸出檔與 failed transient systemd unit')
    parser.add_argument('--dry-run', action='store_true',
                        help='只列出會刪除的檔案,不刪檔,不 reset-failed,不更新 heartbeat')
    parser.add_argument('--keep-days', type=_non_negative_int, default=7, metavar='N',
                        help='一般結果輸出檔保留天數,預設 7')
    parser.add_argument('--keep-days-error', type=_non_negative_int, default=30, metavar='N',
                        help='exception/timeout 輸出檔保留天數,預設 30')
    args = parser.parse_args()

    _bootstrap()
    _setup_logging()
    log = logging.getLogger('os_node_cleanup')

    try:
        from app import create_app, db
    except Exception as exc:
        log.error('無法載入 Flask app: %s', exc)
        return 2

    app = create_app()
    with app.app_context():
        try:
            result = _cleanup_output_files(
                db, args.keep_days, args.keep_days_error, args.dry_run, log)
        except Exception as exc:
            log.exception('OsExecutor cleanup crashed: %s', exc)
            return 3

    reset_failed = 'skipped' if args.dry_run else _reset_failed_units(log)
    log.info(
        'os_node_cleanup: scanned=%d deleted=%d kept=%d dirs_removed=%d reset_failed=%s dry_run=%s',
        result['scanned'], result['deleted'], result['kept'],
        result['dirs_removed'], reset_failed, args.dry_run,
    )

    if not args.dry_run:
        _write_heartbeat()

    return 0


if __name__ == '__main__':
    sys.exit(main())
