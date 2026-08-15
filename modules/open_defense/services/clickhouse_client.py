"""
OpenDefense Module - ClickHouse Client (PF-106)

唯讀查詢 `.20` 的 ClickHouse（secstack DB），供資安案件頁「跨系統關聯」使用。
只提供窄範圍查詢（actor_ip + 時間窗），不提供全表瀏覽介面——ClickHouse 沒有
org 概念（TENANT-01），租戶隔離必須靠呼叫端先用 ResourceGateway 風格的查詢
驗過案件歸屬，拿到「已驗證屬於本企業」的 actor_ip 之後才呼叫本模組。

認證一律用 header（PF-106 硬性約束）：
    X-ClickHouse-User / X-ClickHouse-Key
禁止 `?user=&password=` 或 `requests.get(..., auth=(...))`（會變成 HTTP Basic
Auth，一樣是明文過 LAN，且會觸發 Suricata 的
`ET INFO Outgoing Basic Auth Base64 HTTP Password detected unencrypted`）。

查詢一律走 ClickHouse 參數化語法 `{name:Type}` + query string `param_<name>`，
由伺服器端做型別化替換，不是字串拼接——呼叫端不得自行拼接使用者輸入組 SQL。

連線失敗（容器停機、逾時、認證錯誤、未設定）一律回 None，呼叫端據此隱藏
「跨系統關聯」等分頁，不讓案件頁整頁 500（PF-106 驗收項 5）。
"""
import logging
from typing import Any, Dict, List, Optional

import requests
from flask import current_app

logger = logging.getLogger(__name__)

# 案件頁是同步請求，ClickHouse 逾時要短，不能拖慢整頁載入
TIMEOUT_SECONDS = 5


def _config() -> Optional[tuple]:
    url = current_app.config.get('CLICKHOUSE_URL')
    db = current_app.config.get('CLICKHOUSE_DB')
    user = current_app.config.get('CLICKHOUSE_USER')
    password = current_app.config.get('CLICKHOUSE_PASSWORD')
    if not url or not db or not user or not password:
        return None
    return url, db, user, password


def available() -> bool:
    """設定是否齊全（不代表連線得上，只是快速篩掉「根本沒設定」的情況）。"""
    return _config() is not None


def query(sql: str, params: Optional[Dict[str, Any]] = None) -> Optional[List[dict]]:
    """
    執行參數化唯讀查詢，回傳 list[dict]；不可用時回 None（未設定/連線失敗/逾時/
    回應非預期格式），呼叫端一律要能處理 None 而不是讓例外往上炸。

    sql 不含 FORMAT 子句（本函式自動附加 FORMAT JSON），且應以 ClickHouse
    的 `{name:Type}` 佔位符表示變數（含資料庫名，用 `{db:Identifier}`），
    對應值放進 params，本函式轉成 `param_<name>` query string 傳遞。
    """
    cfg = _config()
    if cfg is None:
        logger.warning('ClickHouse 未設定完整連線資訊，跨系統關聯查詢跳過')
        return None
    base_url, db, user, password = cfg

    query_params = {'param_db': db}
    for key, value in (params or {}).items():
        query_params[f'param_{key}'] = value

    body = sql.strip().rstrip(';') + ' FORMAT JSON'

    try:
        resp = requests.post(
            base_url,
            params=query_params,
            data=body.encode('utf-8'),
            headers={
                'X-ClickHouse-User': user,
                'X-ClickHouse-Key': password,
            },
            timeout=TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning('ClickHouse 查詢失敗，跨系統關聯資料不可用: %s', exc)
        return None

    try:
        payload = resp.json()
    except ValueError:
        logger.warning('ClickHouse 回應非 JSON，跨系統關聯資料不可用')
        return None

    data = payload.get('data')
    if not isinstance(data, list):
        return []
    return data
