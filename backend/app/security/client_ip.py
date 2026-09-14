"""
NET-01: 來源 IP 解析（唯一實作）

平台部署在多層代理之後，「客戶端 IP」有兩條互斥的取得方式，取錯會造成
稽核日誌記錯人、限流分桶失效、內網判定被繞過。本模組是唯一實作，
**禁止各處自行讀 remote_addr 或 X-Forwarded-For / CF-Connecting-IP**。

實際信任鏈有兩條：

  LAN 直連    訪客 -> nginx BeakPlatform-VM:7000 -> Flask
  Cloudflare  訪客 -> CF edge -> cloudflared -> nginx WAF-VM:8080
                    -> nginx BeakPlatform-VM:7000 -> Flask

`create_app()` 掛的 ProxyFix(x_for=1) 取 X-Forwarded-For 最右一筆，
也就是「直連我方 nginx 的對象」：LAN 路徑得到真實訪客 IP，
Cloudflare 路徑則恆為 WAF-VM。後者的真實訪客 IP 只存在於
Cloudflare 注入的 CF-Connecting-IP header。

因此信任邊界以「直連對象是否為已知前置代理」判定：

  remote_addr 在 TRUSTED_PROXY_IPS 內 -> 採信 CF-Connecting-IP
  否則                                -> 一律用 remote_addr

反過來說，任何人若能直接連到本服務並自帶 CF-Connecting-IP，
因其 remote_addr 不在白名單內，該 header 會被忽略 -- 這正是重點。
"""
from typing import Optional

from flask import current_app, request


def _first(value: Optional[str]) -> Optional[str]:
    """header 可能是 'client, proxy1, proxy2' 形式，取最前面那筆。"""
    if not value:
        return None
    return value.split(',')[0].strip() or None


def get_client_ip() -> Optional[str]:
    """取得客戶端 IP。無 request 語境時回 None。"""
    if not request:
        return None

    peer = request.remote_addr

    try:
        trusted = current_app.config.get('TRUSTED_PROXY_IPS', ())
    except RuntimeError:
        trusted = ()

    if peer and peer in trusted:
        forwarded = _first(request.headers.get('CF-Connecting-IP'))
        if forwarded:
            return forwarded

    return peer


def client_ip_key() -> str:
    """限流分桶用：與 get_client_ip() 同語意，但保證回傳字串。

    flask_limiter 的 key_func 不接受 None。取不到來源時回 'unknown'，
    該情況只會出現在無 request 語境（實務上限流器不會在那裡被呼叫）。
    """
    return get_client_ip() or 'unknown'
