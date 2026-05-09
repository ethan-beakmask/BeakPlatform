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
    """從 X-OD-Key-Id header 取 key_id"""
    return request.headers.get('X-OD-Key-Id') or None


def key_func_from_intake_key() -> str:
    """
    /api/open_defense/intake 端點專用 key_func。

    優先用 X-OD-Key-Id header(per intake source),
    缺值 fallback 來源 IP(防匿名 flood,雖然 decorator 也會擋下)。
    """
    key_id = _intake_key_id()
    if key_id:
        return f'od_intake:{key_id}'
    return f'od_intake_anon:{get_remote_address()}'


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
