#!/usr/bin/env python3
"""
WAF 熱備健康監看 heartbeat 看門狗。

用法:
    waf_monitor_watchdog.py [--dry-run]

無參數:正式執行,檢查 WAF 監看流程 heartbeat,異常時發 Telegram 告警。
--dry-run:只印出判定,不發送 Telegram,不更新告警狀態。

同一次停擺只告警一次；恢復時發一則恢復通知並清除狀態，之後再停擺才視為新事件。

排程 log 寫 /opt/tmp/BeakPlatform-cron-waf_monitor_watchdog.log,
heartbeat 寫 /opt/tmp/heartbeat/waf_monitor_watchdog.ok。
"""
import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import requests


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / 'backend'
ENV_FILE = REPO_ROOT / '.env'
DEFAULT_MONITOR_HEARTBEAT = Path('/opt/tmp/heartbeat/waf_monitor.ok')
DEFAULT_STOP_FLAG = Path('/opt/tmp/waf-monitor.stop')
DEFAULT_STATE_FILE = Path('/opt/tmp/waf_monitor_watchdog.state')
WATCHDOG_HEARTBEAT_PATH = Path('/opt/tmp/heartbeat/waf_monitor_watchdog.ok')
LOG_PATH = Path('/opt/tmp/BeakPlatform-cron-waf_monitor_watchdog.log')


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
    logging.getLogger('waf_monitor_watchdog').setLevel(logging.INFO)


def _write_heartbeat():
    WATCHDOG_HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    WATCHDOG_HEARTBEAT_PATH.write_text(
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'), encoding='utf-8')


def _read_state(path):
    """回傳已告警事件的識別字串（heartbeat 最後更新時間），無狀態回 None"""
    try:
        raw = path.read_text(encoding='utf-8').strip()
        return raw or None
    except OSError:
        return None


def _write_state(path, event_key):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(event_key, encoding='utf-8')


def _event_key(status):
    """同一次停擺期間 heartbeat 的 mtime 不變，以它辨識「同一事件」"""
    last_update = status['last_update']
    return last_update.isoformat(timespec='seconds') if last_update else 'missing'


def _clear_state(path):
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _heartbeat_status(path, stale_minutes):
    now = datetime.now()
    if not path.exists():
        return {
            'ok': False,
            'now': now,
            'last_update': None,
            'age_seconds': None,
            'reason': 'heartbeat 檔案不存在',
        }
    last_update = datetime.fromtimestamp(path.stat().st_mtime)
    age_seconds = max(0.0, (now - last_update).total_seconds())
    return {
        'ok': age_seconds <= stale_minutes * 60,
        'now': now,
        'last_update': last_update,
        'age_seconds': age_seconds,
        'reason': f'heartbeat 已停 {age_seconds / 60:.1f} 分鐘',
    }


def _format_last_update(last_update):
    if last_update is None:
        return '不存在'
    return last_update.strftime('%Y-%m-%d %H:%M:%S')


def _format_age(age_seconds):
    if age_seconds is None:
        return '未知'
    minutes = int(age_seconds // 60)
    seconds = int(age_seconds % 60)
    return f'{minutes} 分 {seconds} 秒'


def _send_telegram(args, text, log):
    from app.models import TelegramConfig

    cfg = TelegramConfig.query.filter_by(
        secure_code=args.telegram_config,
        is_deleted=False,
        is_active=True,
    ).first()
    if not cfg:
        log.error('找不到啟用中的 TelegramConfig: %s', args.telegram_config)
        return False

    bot_token = cfg.bot_token
    chat_id = cfg.get_channels().get(args.telegram_channel)
    if not chat_id:
        log.error('TelegramConfig %s 找不到頻道: %s',
                  args.telegram_config, args.telegram_channel)
        return False

    try:
        response = requests.post(
            f'https://api.telegram.org/bot{bot_token}/sendMessage',
            json={'chat_id': chat_id, 'text': text},
            timeout=10,
        )
        if response.status_code >= 400:
            log.error('Telegram 發送失敗: status=%s body=%s',
                      response.status_code, response.text[:500])
            return False
        result = response.json()
        if not result.get('ok'):
            log.error('Telegram 發送失敗: %s', result)
            return False
        return True
    except requests.RequestException as exc:
        log.error('Telegram 發送失敗: %s', exc)
        return False


def _send_telegram_with_app(args, text, log):
    """只有真的要發送時才載入 Flask app：正常情況每 5 分鐘一次不必付這個成本。"""
    try:
        from app import create_app
    except Exception as exc:
        log.error('無法載入 Flask app: %s', exc)
        return False
    app = create_app()
    with app.app_context():
        return _send_telegram(args, text, log)


def _alert_message(args, status):
    return (
        '⚠️ WAF 健康監看流程 heartbeat 異常\n'
        f'heartbeat：{args.heartbeat}\n'
        f'最後更新：{_format_last_update(status["last_update"])}\n'
        f'已停多久：{_format_age(status["age_seconds"])}\n'
        '監看流程可能已停止，請到流程管理頁確認 NODEDEMO_WAF_MONITOR_FLOW 的實例狀態。'
    )


def _recovery_message(args, status):
    return (
        'WAF 健康監看流程 heartbeat 已恢復\n'
        f'heartbeat：{args.heartbeat}\n'
        f'最後更新：{_format_last_update(status["last_update"])}'
    )


def build_parser():
    parser = argparse.ArgumentParser(
        description='WAF 熱備健康監看 heartbeat 看門狗')
    parser.add_argument('--heartbeat', type=Path, default=DEFAULT_MONITOR_HEARTBEAT,
                        help='monitor_probe.sh 寫入的 heartbeat 路徑（預設 /opt/tmp/heartbeat/waf_monitor.ok）')
    parser.add_argument('--stop-flag', type=Path, default=DEFAULT_STOP_FLAG,
                        help='人為停止監看的旗標路徑（預設 /opt/tmp/waf-monitor.stop）')
    parser.add_argument('--stale-minutes', type=int, default=12,
                        help='多久沒更新視為異常（預設 12）')
    parser.add_argument('--state-file', type=Path, default=DEFAULT_STATE_FILE,
                        help='已告警事件狀態檔，同一次停擺只告警一次（預設 /opt/tmp/waf_monitor_watchdog.state）')
    parser.add_argument('--telegram-config', default='c9WeYKveCBWxbn0t8kl6yn',
                        help='TelegramConfig secure_code（預設系統企業「系統TG」）')
    parser.add_argument('--telegram-channel', default='測試頻道',
                        help='Telegram 頻道名稱（預設 測試頻道）')
    parser.add_argument('--dry-run', action='store_true',
                        help='只印出判定,不發送 Telegram,不更新告警狀態')
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.stale_minutes < 1 or args.stale_minutes > 1440:
        parser.error('--stale-minutes 必須介於 1 到 1440')

    _bootstrap()
    _setup_logging()
    log = logging.getLogger('waf_monitor_watchdog')

    if args.stop_flag.exists():
        msg = f'OK stop_flag_exists heartbeat={args.heartbeat} stop_flag={args.stop_flag}'
        log.info(msg)
        _write_heartbeat()
        return 0

    status = _heartbeat_status(args.heartbeat, args.stale_minutes)
    alerted_event = _read_state(args.state_file)

    if not status['ok']:
        event_key = _event_key(status)
        already_alerted = alerted_event == event_key
        msg = (
            f'ABNORMAL heartbeat={args.heartbeat} '
            f'last_update={_format_last_update(status["last_update"])} '
            f'age={_format_age(status["age_seconds"])} already_alerted={already_alerted}'
        )
        log.warning(msg)
        if args.dry_run or already_alerted:
            _write_heartbeat()
            return 0
        if not _send_telegram_with_app(args, _alert_message(args, status), log):
            return 1
        _write_state(args.state_file, event_key)
        _write_heartbeat()
        return 0

    msg = (
        f'OK heartbeat={args.heartbeat} '
        f'last_update={_format_last_update(status["last_update"])} '
        f'age={_format_age(status["age_seconds"])}'
    )
    log.info(msg)
    if alerted_event is not None:
        if args.dry_run:
            log.info('RECOVERY dry_run=True（不發送、不清除告警狀態）')
        else:
            if not _send_telegram_with_app(args, _recovery_message(args, status), log):
                return 1
            _clear_state(args.state_file)
    _write_heartbeat()
    return 0


if __name__ == '__main__':
    sys.exit(main())
