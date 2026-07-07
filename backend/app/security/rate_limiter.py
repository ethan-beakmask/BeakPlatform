"""
BeakMask Security - Rate Limiter Custom Key Functions

OpenDefense 模組要求 /api/open_defense/* 端點以 key_id / sa_id 為計數軸,
不使用預設的 IP 計數,避免:
  - 多執行端共用同一出口 IP 互相吃額度
  - 機器流量吃掉人類用戶的全域配額

對外契約 §4.5 / §5.4 已載明計數軸。
"""
from typing import Optional

from flask import request, g
from flask_limiter.util import get_remote_address


def _intake_key_id() -> Optional[str]:
    """取 key_id:X-BP-Key-Id 優先,fallback 舊契約 X-OD-Key-Id(deprecated)"""
    return (request.headers.get('X-BP-Key-Id')
            or request.headers.get('X-OD-Key-Id') or None)


def key_func_from_intake_key() -> str:
    """
    /api/open_defense/intake 端點專用 key_func。

    優先用 key_id header(per intake source,X-BP-* 或舊 X-OD-*),
    缺值 fallback 來源 IP(防匿名 flood,雖然 decorator 也會擋下)。
    """
    key_id = _intake_key_id()
    if key_id:
        return f'od_intake:{key_id}'
    return f'od_intake_anon:{get_remote_address()}'


def key_func_from_api_key() -> str:
    """
    平台級 API Key 端點(/api/trigger/*)專用 key_func。

    優先用 X-BP-Key-Id header(per 外部系統),
    缺值 fallback 來源 IP。
    """
    key_id = request.headers.get('X-BP-Key-Id') or None
    if key_id:
        return f'bp_apikey:{key_id}'
    return f'bp_apikey_anon:{get_remote_address()}'


def auth_failure_limit_kwargs() -> dict:
    """
    認證失敗限流(B-1 修復,規格: docs/API_KEY_TRIGGER_SPEC.md §5)。

    per-key 限流的 bucket 取自未驗證的 header,攻擊者輪替假 key_id 可各自取得
    獨立額度。此限流以來源 IP 為軸、僅對 401 回應扣次:
      - 正常流量(2xx/4xx 業務錯誤)不扣,合法端不受影響
      - 假 key_id / 錯簽章連續 401 -> 30 次/分鐘後直接 429

    用法: @limiter.limit(**auth_failure_limit_kwargs())
    """
    return {
        'limit_value': '30 per minute',
        'key_func': lambda: f'auth_fail:{get_remote_address()}',
        'deduct_when': lambda response: response.status_code == 401,
    }


def key_func_from_sa_id() -> str:
    """
    /api/open_defense/decisions 端點專用 key_func。

    從 g.service_account 取 sa_id(由 @service_account_required decorator 注入)。
    缺值 fallback 來源 IP(理論上不會發生,因為 decorator 已驗 JWT)。
    """
    sa = getattr(g, 'service_account', None)
    if sa is not None:
        sa_id = getattr(sa, 'sa_id', None)
        if sa_id:
            return f'od_sa:{sa_id}'
    return f'od_sa_anon:{get_remote_address()}'
