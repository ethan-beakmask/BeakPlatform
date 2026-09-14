"""
OpenDefense Module - Cross-Source Correlation Service (PF-106)

案件頁「跨系統關聯」分頁的資料來源：同一個 actor_ip 在時間窗內，防禦節點 上
各資安套件（coraza/suricata/...）各自記錄了什麼。這是本工單的重點功能，
承接 PF-100 的問題分析——平台把同一攻擊者的多系統告警拆成各自獨立的案件，
UI 上看不出關聯，此服務把它們重新串起來（唯讀查詢，不改變既有聚合/建案邏輯）。

租戶隔離（TENANT-01）：ClickHouse 的 `secstack.events` 沒有 org 概念。
本服務只接受呼叫端「已驗過歸屬本企業」的 actor_ip + 時間窗，不提供其他
查詢介面；呼叫端（API 層）必須先用既有的 org 過濾查詢確認案件屬於當前企業，
才可以把該案件的 actor_ip 傳進來。

資料可信度：2026-08-08 之前的 ClickHouse 資料是從 eve.json 歸檔回灌的（原 TTL
只有 6 小時），該日期之前「查到的筆數」不代表當時的真實全量，見 PF-106 工單
【重要修正】段落。本服務把 RELIABLE_FROM 常數暴露給呼叫端，讓 UI 標示。
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from . import clickhouse_client

logger = logging.getLogger(__name__)

# ClickHouse events 表明細的分層 TTL 是 2026-08-08 才生效（見
# sec-vm-bootstrap/clickhouse/ch_ttl_mv.sql 檔頭），此日期前的資料是一次性
# 從 eve.json 歸檔回灌，不代表當時的真實全量。
#
# [TZ-01] 平台慣例：DB 存 naive datetime，值即 UTC（不掛 tzinfo）。本模組全程
# 沿用這個慣例（呼叫端傳入的 form_instance.submitted_at 本來就是 naive UTC），
# 避免與 aware datetime 混用時互相比較噴 TypeError。
RELIABLE_FROM = datetime(2026, 8, 8)

# 案件頁的關聯查詢一次回傳的事件數上限（防爆，不是分頁機制）
MAX_EVENTS = 300


def _iso(dt: datetime) -> str:
    """naive UTC datetime -> ISO8601 字串（補 Z，前端 TZ-01 慣例）。"""
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def _ch_timestamp(dt: datetime) -> str:
    """ClickHouse DateTime64 參數化查詢吃的字串格式（無時區後綴，值本身即 UTC）。"""
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def _ch_event_time_to_iso(raw: str) -> Optional[str]:
    """ClickHouse `toString(DateTime64(3,'UTC'))` 格式 -> ISO8601 UTC（補 Z，TZ-01）。"""
    if not raw:
        return None
    return raw.replace(' ', 'T', 1) + 'Z'


def _actor_ip_match_clause(actor_ip: str) -> str:
    """
    回傳固定的 SQL 樣板片段（不含使用者輸入，actor_ip 本身一律走
    `{ip:String}` 參數化替換）。依格式挑選 IPv4-mapped 或原生 IPv6 比對式，
    這裡的分支只決定「用哪個固定樣板」，不會把 actor_ip 字串接進 SQL。
    """
    if ':' in actor_ip:
        return "toString(actor_ip) = {ip:String}"
    return "toString(actor_ip) = concat('::ffff:', {ip:String})"


def _clean_country(value: Any) -> Optional[str]:
    if not value:
        return None
    text = str(value).replace('\x00', '').strip()
    return text or None


def get_cross_source(
    actor_ip: str,
    window_start: datetime,
    window_end: datetime,
) -> Dict[str, Any]:
    """
    查詢某 actor_ip 在時間窗內、跨 防禦節點 各資安套件的關聯事件。

    Returns:
        {
            'available': bool,
            'reason': None | 'clickhouse_unavailable' | 'no_actor_ip',
            'window': {'start': iso, 'end': iso},
            'reliable_from': iso,
            'window_crosses_backfill_boundary': bool,
            'sources': [{'source_system','count','first_seen','last_seen'}, ...],
            'first_detected_by': {'source_system','event_time'} | None,
            'last_detected_by': {'source_system','event_time'} | None,
            'events': [...],
            'truncated': bool,
        }
        ClickHouse 不可用時只有 available/reason/window/reliable_from 有意義，
        呼叫端據此隱藏相關分頁，不當成錯誤處理。
    """
    result: Dict[str, Any] = {
        'available': False,
        'reason': None,
        'window': {'start': _iso(window_start), 'end': _iso(window_end)},
        'reliable_from': _iso(RELIABLE_FROM),
        'window_crosses_backfill_boundary': window_start < RELIABLE_FROM,
        'sources': [],
        'first_detected_by': None,
        'last_detected_by': None,
        'events': [],
        'truncated': False,
    }

    if not actor_ip:
        result['reason'] = 'no_actor_ip'
        return result

    if not clickhouse_client.available():
        result['reason'] = 'clickhouse_unavailable'
        return result

    match_clause = _actor_ip_match_clause(actor_ip)
    params = {
        'ip': actor_ip,
        'start': _ch_timestamp(window_start),
        'end': _ch_timestamp(window_end),
        'limit': MAX_EVENTS,
    }

    agg_sql = f"""
        SELECT
            source_system,
            count() AS n,
            toString(min(event_time)) AS first_seen,
            toString(max(event_time)) AS last_seen
        FROM {{db:Identifier}}.events
        WHERE {match_clause}
          AND event_time >= parseDateTime64BestEffort({{start:String}})
          AND event_time <= parseDateTime64BestEffort({{end:String}})
        GROUP BY source_system
    """
    agg_rows = clickhouse_client.query(agg_sql, params)
    if agg_rows is None:
        result['reason'] = 'clickhouse_unavailable'
        return result

    if not agg_rows:
        result['available'] = True
        return result

    sources = []
    total_count = 0
    for row in agg_rows:
        n = int(row.get('n') or 0)
        total_count += n
        sources.append({
            'source_system': row.get('source_system'),
            'count': n,
            'first_seen': _ch_event_time_to_iso(row.get('first_seen')),
            'last_seen': _ch_event_time_to_iso(row.get('last_seen')),
        })
    sources.sort(key=lambda s: s['first_seen'] or '')

    first_detected = min(sources, key=lambda s: s['first_seen'] or '9999')
    last_detected = max(sources, key=lambda s: s['last_seen'] or '')
    result['first_detected_by'] = {
        'source_system': first_detected['source_system'],
        'event_time': first_detected['first_seen'],
    }
    result['last_detected_by'] = {
        'source_system': last_detected['source_system'],
        'event_time': last_detected['last_seen'],
    }
    result['sources'] = sources

    events_sql = f"""
        SELECT
            toString(event_time) AS event_time_str,
            source_system,
            event_class,
            severity_id,
            confidence,
            finding_rule_id,
            finding_rule_set,
            finding_title,
            target_host,
            target_url,
            target_service,
            actor_country,
            actor_asn,
            actor_ua,
            actor_xff
        FROM {{db:Identifier}}.events
        WHERE {match_clause}
          AND event_time >= parseDateTime64BestEffort({{start:String}})
          AND event_time <= parseDateTime64BestEffort({{end:String}})
        ORDER BY event_time ASC
        LIMIT {{limit:UInt32}}
    """
    event_rows = clickhouse_client.query(events_sql, params)
    if event_rows is None:
        # 聚合查詢剛剛才成功過，這裡失敗多半是短暫逾時；仍然回傳已取得的
        # sources/first/last（events 維持初始的空陣列）。前端的分頁顯示條件
        # 是「events 非空」，所以這種情況下跨系統關聯與各套件分頁會跟「真的
        # 沒有關聯資料」一樣不出現——這是刻意的簡化（寧可暫時不顯示，也不要
        # 顯示一個只有聚合數字、沒有明細可查的空殼分頁），不是遺漏。
        result['available'] = True
        return result

    events = []
    for row in event_rows:
        events.append({
            'event_time': _ch_event_time_to_iso(row.get('event_time_str')),
            'source_system': row.get('source_system'),
            'event_class': row.get('event_class'),
            'severity_id': row.get('severity_id'),
            'confidence': row.get('confidence'),
            'finding_rule_id': row.get('finding_rule_id') or None,
            'finding_rule_set': row.get('finding_rule_set') or None,
            'finding_title': row.get('finding_title') or None,
            'target_host': row.get('target_host') or None,
            'target_url': row.get('target_url') or None,
            'target_service': row.get('target_service') or None,
            'actor_country': _clean_country(row.get('actor_country')),
            'actor_asn': row.get('actor_asn') or None,
            'actor_ua': row.get('actor_ua') or None,
            'actor_xff': row.get('actor_xff') or None,
        })

    result['available'] = True
    result['events'] = events
    result['truncated'] = total_count > len(events)
    return result
