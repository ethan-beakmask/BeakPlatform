#!/usr/bin/env python3
"""
OpenDefense 合成演習檢查器:確認 .20 每小時打出的 canary 有沒有變成 .16 的案件。

用法:
    od_canary_check.py [--hours N] [--dry-run] [--force-alert]

    無參數      正式執行:檢查兩條路徑、必要時發 Telegram、更新 heartbeat
    --hours N   檢查窗(預設 3 小時)。設 3 是為了容忍 Suricata 那條被 throttle
                壓掉一次(該路徑閾值是 1 筆/3600 秒,canary 每小時 1 次剛好在邊界)
    --dry-run   只印結果,不發 Telegram、不寫 heartbeat
    --force-alert  忽略去重視窗,強制發一次告警(測試通知管道用)

為什麼要有這支:
    2026-05-13 ~ 08-08 管線斷流三個月,期間 Vector health=true、7 個容器全綠、
    Grafana 照常畫圖——所有「程式有在跑」的指標都是綠的。能戳破的只有
    「該出現的案件沒出現」。這支就是在檢查那件事。

    檢查器刻意放在 .16 而不是 .20:檢查資料流是否活著,這件事本身不能跟
    被檢查的對象同生共死。

排程於 /etc/crontab,log 寫 /opt/tmp/BeakPlatform-dev-cron-od_canary_check.log,
heartbeat 寫 /opt/tmp/heartbeat/od_canary_check.ok
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2

REPO_ROOT = Path('/opt/BeakPlatform-dev')
ENV_FILE = REPO_ROOT / '.env'
HEARTBEAT_PATH = Path('/opt/tmp/heartbeat/od_canary_check.ok')
LOG_PATH = Path('/opt/tmp/BeakPlatform-dev-cron-od_canary_check.log')
STATE_PATH = Path('/opt/tmp/od_canary_last_alert')
TG_NOTIFIER_DIR = '/opt/line-bot'

# canary 的辨識特徵(必須與 .20 的 /etc/cron.hourly/secstack-canary 一致)
CANARY_IP = '203.0.113.1'          # TEST-NET-3,路徑 A 專用來源 IP
SURICATA_CANARY_RULE = '2013224'   # ET HUNTING Suspicious User-Agent Containing .exe
SURICATA_CANARY_ACTOR = '192.168.0.20'

ALERT_DEDUP_HOURS = 6              # 同樣的故障 6 小時內只吵一次

logger = logging.getLogger('od_canary_check')


def _setup_logging():
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        handlers=[logging.FileHandler(LOG_PATH, encoding='utf-8'),
                  logging.StreamHandler(sys.stdout)],
    )


def _database_url():
    """從 .env 取 DATABASE_URL,禁止硬編碼認證"""
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line.startswith('DATABASE_URL='):
                return line.split('=', 1)[1].strip().strip('"').strip("'")
    url = os.environ.get('DATABASE_URL')
    if not url:
        raise RuntimeError('找不到 DATABASE_URL(.env 或環境變數皆無)')
    return url


def _check_paths(conn, hours):
    """回傳 [(路徑代號, 說明, 最近一筆時間或 None), ...]

    注意 TZ-01:od_intake_events.received_at 存的是 UTC naive,
    直接跟 psql 的 now() 比會差 8 小時(踩過一次),所以這裡用 Python
    算出 UTC naive 的 cutoff 再傳進去。
    """
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)
    results = []

    with conn.cursor() as cur:
        # 路徑 A:Coraza / WAF
        cur.execute(
            """
            SELECT max(received_at)
            FROM od_intake_events
            WHERE source_system = 'coraza'
              AND raw_body->'actor'->>'ip' = %s
              AND received_at >= %s
            """,
            (CANARY_IP, cutoff),
        )
        results.append(('A', 'Coraza/WAF → 案件', cur.fetchone()[0]))

        # 路徑 B:Suricata
        cur.execute(
            """
            SELECT max(received_at)
            FROM od_intake_events
            WHERE source_system = 'suricata'
              AND raw_body->'finding'->>'rule_id' = %s
              AND raw_body->'actor'->>'ip' = %s
              AND received_at >= %s
            """,
            (SURICATA_CANARY_RULE, SURICATA_CANARY_ACTOR, cutoff),
        )
        results.append(('B', 'Suricata → 案件', cur.fetchone()[0]))

    return results


def _should_alert(force):
    """告警去重:同一輪故障 ALERT_DEDUP_HOURS 小時內只發一次"""
    if force:
        return True
    if not STATE_PATH.exists():
        return True
    try:
        last = datetime.fromisoformat(STATE_PATH.read_text(encoding='utf-8').strip())
    except (ValueError, OSError):
        return True
    return datetime.now(timezone.utc) - last >= timedelta(hours=ALERT_DEDUP_HOURS)


def _mark_alerted():
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(datetime.now(timezone.utc).isoformat(), encoding='utf-8')


def _send_telegram(message):
    """透過既有的 /opt/line-bot/tg_notifier.py 發送(token 由它自己從 config.json 讀)"""
    if TG_NOTIFIER_DIR not in sys.path:
        sys.path.insert(0, TG_NOTIFIER_DIR)
    try:
        from tg_notifier import send_to_ethan
    except ImportError as exc:
        logger.error('載入 tg_notifier 失敗: %s', exc)
        return False
    return send_to_ethan(message)


def main():
    parser = argparse.ArgumentParser(
        description='OpenDefense 合成演習檢查器:確認 canary 有沒有變成案件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--hours', type=int, default=3,
                        help='檢查窗小時數(預設 3,容忍 Suricata 路徑被 throttle 壓掉一次)')
    parser.add_argument('--dry-run', action='store_true',
                        help='只印結果,不發 Telegram、不寫 heartbeat')
    parser.add_argument('--force-alert', action='store_true',
                        help='忽略去重視窗強制發一次告警(測試通知管道用)')
    args = parser.parse_args()

    _setup_logging()

    try:
        conn = psycopg2.connect(_database_url())
    except Exception as exc:
        logger.error('資料庫連線失敗: %s', exc)
        # 連不上 DB 本身就是故障,要吵
        if not args.dry_run and _should_alert(args.force_alert):
            _send_telegram(f'[OpenDefense canary] 檢查器連不上資料庫:{exc}')
            _mark_alerted()
        return 2

    try:
        results = _check_paths(conn, args.hours)
    finally:
        conn.close()

    failed = [(code, desc) for code, desc, seen in results if seen is None]

    for code, desc, seen in results:
        if seen:
            logger.info('路徑 %s %s:最近一筆 %s UTC', code, desc, seen)
        else:
            logger.warning('路徑 %s %s:最近 %s 小時內沒有 canary 案件', code, desc, args.hours)

    if args.dry_run:
        logger.info('dry-run:不發通知、不寫 heartbeat')
        return 1 if failed else 0

    if failed:
        lines = [f'[OpenDefense] 合成演習失敗:{len(failed)}/2 條偵測路徑沒有產生案件',
                 f'檢查窗:最近 {args.hours} 小時', '']
        for code, desc in failed:
            lines.append(f'  ✗ 路徑 {code}:{desc}')
        for code, desc, seen in results:
            if seen:
                lines.append(f'  ✓ 路徑 {code}:{desc}(最近 {seen} UTC)')
        lines += [
            '',
            '排查順序:',
            '  1. .20 是否有打出 canary:tail /opt/tmp/sec-vm-canary.log',
            '  2. Vector 有沒有收到並送出:'
            'curl -s -X POST http://192.168.0.20:8686/graphql '
            '-d \'{"query":"{transforms{edges{node{componentId '
            'metrics{sentEventsTotal{sentEventsTotal}}}}}}"}\'',
            '  3. od-bridge 有沒有轉送:docker logs --tail 50 secstack-od-bridge-1',
            '  4. .16 dev 實例還活著嗎:curl -s -o /dev/null -w "%{http_code}" '
            'http://127.0.0.1:7000/',
        ]
        message = '\n'.join(lines)
        if _should_alert(args.force_alert):
            if _send_telegram(message):
                _mark_alerted()
                logger.info('已發送 Telegram 告警')
            else:
                logger.error('Telegram 發送失敗,告警未送出')
        else:
            logger.info('去重視窗內(%s 小時),本次不重複告警', ALERT_DEDUP_HOURS)
        return 1

    logger.info('兩條路徑皆正常')
    HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    HEARTBEAT_PATH.write_text(datetime.now(timezone.utc).isoformat(), encoding='utf-8')
    # 復原時清掉去重狀態,下次故障能立刻吵
    STATE_PATH.unlink(missing_ok=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
