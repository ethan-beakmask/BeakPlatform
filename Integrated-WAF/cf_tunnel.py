#!/usr/bin/env python3
"""
Cloudflare Tunnel 自動建置（防禦節點對外入口）。

用 Cloudflare API 一次做完 Zero Trust 後台要手點的三件事：
  1. 建立（或沿用同名的）tunnel
  2. 設定 tunnel 的 ingress：<hostname> → http://waf-nginx:8080（其餘回 404）
  3. 在 DNS 建 <hostname> 的 CNAME 指向 tunnel（proxied）
然後印出 connector token，貼進 .env 的 CLOUDFLARE_TUNNEL_TOKEN 即可啟動 cloudflared。

不想給 API Token 的人可以在 Zero Trust 後台手動做同樣三件事，本工具不是必要的。

API Token 需要的權限：
  Account → Cloudflare Tunnel：Edit
  Zone    → DNS：Edit
  Zone    → Zone：Read

用法：
  python3 cf_tunnel.py setup  --api-token <T> --hostname app.example.com [--tunnel-name ithome2026-waf]
                              [--service http://waf-nginx:8080] [--account-id <id>] [--write-env <.env 路徑>]
  python3 cf_tunnel.py setup  ... --hostname www.example.com --path '^/app(/|$)'   # 同 hostname 只導某路徑
  python3 cf_tunnel.py remove --api-token <T> --hostname old.example.com [--tunnel-name ithome2026-waf]
  python3 cf_tunnel.py status --api-token <T> --tunnel-name ithome2026-waf
  python3 cf_tunnel.py token  --api-token <T> --tunnel-name ithome2026-waf

API Token 也可以用環境變數 CF_API_TOKEN 傳入，避免進入 shell history。
本程式只用 Python 標準函式庫，不需要安裝任何套件。
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

API = "https://api.cloudflare.com/client/v4"


class CfError(Exception):
    pass


def _req(token, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode())
        except Exception:
            raise CfError(f"HTTP {e.code} {method} {path}")
    if not payload.get("success"):
        errs = "; ".join(f"{x.get('code')}: {x.get('message')}" for x in payload.get("errors", []))
        raise CfError(f"{method} {path} 失敗：{errs or payload}")
    return payload.get("result")


def pick_account(token, account_id, zone=None):
    if account_id:
        return account_id
    # 由 zone 反查 account 只需要 Zone: Read；列 /accounts 還要 Account Settings: Read
    if zone and (zone.get("account") or {}).get("id"):
        return zone["account"]["id"]
    try:
        accounts = _req(token, "GET", "/accounts?per_page=50") or []
    except CfError:
        accounts = []
    if not accounts:
        # 沒有 Account Settings: Read 時退而求其次：任一 zone 都帶 account.id
        zones = _req(token, "GET", "/zones?per_page=50") or []
        ids = sorted({(z.get("account") or {}).get("id") for z in zones if (z.get("account") or {}).get("id")})
        if len(ids) == 1:
            return ids[0]
        if len(ids) > 1:
            raise CfError("Token 可見多個 account，請用 --account-id 指定：" + ", ".join(ids))
        raise CfError("Token 無法列出 account，請用 --account-id 指定（Cloudflare 後台網域總覽頁右側可見）")
    if len(accounts) == 1:
        return accounts[0]["id"]
    if not accounts:
        raise CfError("這個 API Token 看不到任何 account，請確認權限含 Cloudflare Tunnel: Edit")
    names = ", ".join(f"{a['name']}={a['id']}" for a in accounts)
    raise CfError(f"Token 可見多個 account，請用 --account-id 指定其中一個：{names}")


def find_zone(token, hostname):
    """由 hostname 反推 zone：逐段往上找第一個存在的 zone。"""
    parts = hostname.split(".")
    for i in range(1, len(parts) - 1):
        cand = ".".join(parts[i:])
        zones = _req(token, "GET", f"/zones?name={cand}") or []
        if zones:
            return zones[0]
    raise CfError(f"找不到 {hostname} 所屬的 zone，請確認網域已託管到 Cloudflare 且 Token 有 Zone: Read")


def find_tunnel(token, acc, name):
    items = _req(token, "GET", f"/accounts/{acc}/cfd_tunnel?name={name}&is_deleted=false") or []
    for t in items:
        if t.get("name") == name:
            return t
    return None


def ensure_tunnel(token, acc, name):
    t = find_tunnel(token, acc, name)
    if t:
        return t, False
    t = _req(token, "POST", f"/accounts/{acc}/cfd_tunnel", {"name": name, "config_src": "cloudflare"})
    return t, True


def _rule_key(r):
    return (r.get("hostname") or "", r.get("path") or "")


def upsert_ingress(token, acc, tunnel_id, hostname, service, path=None):
    """新增或取代一條 ingress。同 hostname 可有多條：帶 path 的排前面（先比對），沒 path 的當該 hostname 的預設。"""
    cur = _req(token, "GET", f"/accounts/{acc}/cfd_tunnel/{tunnel_id}/configurations") or {}
    config = (cur.get("config") or {}) if isinstance(cur, dict) else {}
    ingress = [r for r in (config.get("ingress") or [])
               if r.get("hostname") and _rule_key(r) != (hostname, path or "")]
    rule = {"hostname": hostname, "service": service, "originRequest": {"httpHostHeader": hostname}}
    if path:
        rule["path"] = path
    ingress.append(rule)
    # 穩定排序：同 hostname 內帶 path 的在前；不同 hostname 維持原順序
    ingress.sort(key=lambda r: (0 if r.get("path") else 1))
    ingress.append({"service": "http_status:404"})
    config["ingress"] = ingress
    _req(token, "PUT", f"/accounts/{acc}/cfd_tunnel/{tunnel_id}/configurations", {"config": config})
    return ingress


def remove_hostname(token, acc, tunnel_id, zone_id, hostname):
    cur = _req(token, "GET", f"/accounts/{acc}/cfd_tunnel/{tunnel_id}/configurations") or {}
    config = (cur.get("config") or {}) if isinstance(cur, dict) else {}
    ingress = [r for r in (config.get("ingress") or []) if r.get("hostname") and r.get("hostname") != hostname]
    ingress.append({"service": "http_status:404"})
    config["ingress"] = ingress
    _req(token, "PUT", f"/accounts/{acc}/cfd_tunnel/{tunnel_id}/configurations", {"config": config})
    removed = 0
    for r in _req(token, "GET", f"/zones/{zone_id}/dns_records?name={hostname}") or []:
        if r["type"] == "CNAME" and r["content"].endswith(".cfargotunnel.com"):
            _req(token, "DELETE", f"/zones/{zone_id}/dns_records/{r['id']}")
            removed += 1
    return len(ingress) - 1, removed


def upsert_dns(token, zone_id, hostname, tunnel_id):
    target = f"{tunnel_id}.cfargotunnel.com"
    recs = _req(token, "GET", f"/zones/{zone_id}/dns_records?name={hostname}") or []
    body = {"type": "CNAME", "name": hostname, "content": target, "proxied": True, "ttl": 1,
            "comment": "Integrated-WAF tunnel"}
    for r in recs:
        if r["type"] == "CNAME":
            if r["content"] == target and r.get("proxied"):
                return "unchanged"
            _req(token, "PUT", f"/zones/{zone_id}/dns_records/{r['id']}", body)
            return "updated"
        raise CfError(f"{hostname} 已有 {r['type']} 記錄（{r['content']}），請先手動刪除再重試")
    _req(token, "POST", f"/zones/{zone_id}/dns_records", body)
    return "created"


def get_token(token, acc, tunnel_id):
    return _req(token, "GET", f"/accounts/{acc}/cfd_tunnel/{tunnel_id}/token")


def write_env(path, key, value):
    lines = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    done = False
    for i, line in enumerate(lines):
        if re.match(rf"^{re.escape(key)}=", line):
            lines[i] = f"{key}={value}"
            done = True
    if not done:
        lines.append(f"{key}={value}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(path, 0o600)


def cmd_setup(a):
    zone = find_zone(a.api_token, a.hostname)
    acc = pick_account(a.api_token, a.account_id, zone)
    tunnel, created = ensure_tunnel(a.api_token, acc, a.tunnel_name)
    tid = tunnel["id"]
    print(f"[+] account {acc}")
    print(f"[+] zone    {zone['name']} ({zone['id']}, {zone['status']})")
    print(f"[+] tunnel  {a.tunnel_name} = {tid} ({'新建' if created else '沿用既有'})")
    ingress = upsert_ingress(a.api_token, acc, tid, a.hostname, a.service, a.path or None)
    print(f"[+] ingress {a.hostname}{a.path or ''} -> {a.service}（共 {len(ingress)} 條，含 404 收尾）")
    dns = upsert_dns(a.api_token, zone["id"], a.hostname, tid)
    print(f"[+] DNS     CNAME {a.hostname} -> {tid}.cfargotunnel.com（{dns}）")
    tok = get_token(a.api_token, acc, tid)
    if a.write_env:
        write_env(a.write_env, "CLOUDFLARE_TUNNEL_TOKEN", tok)
        print(f"[+] token 已寫入 {a.write_env} 的 CLOUDFLARE_TUNNEL_TOKEN")
    else:
        print("CLOUDFLARE_TUNNEL_TOKEN=" + tok)
    print(f"[i] 對外網址：https://{a.hostname}/  （cloudflared 容器啟動後約 30 秒生效）")
    return 0


def cmd_remove(a):
    zone = find_zone(a.api_token, a.hostname)
    acc = pick_account(a.api_token, a.account_id, zone)
    t = find_tunnel(a.api_token, acc, a.tunnel_name)
    if not t:
        raise CfError(f"tunnel {a.tunnel_name} 不存在")
    n, d = remove_hostname(a.api_token, acc, t["id"], zone["id"], a.hostname)
    print(f"[+] 已移除 {a.hostname} 的 ingress（剩 {n} 條）與 {d} 筆 CNAME")
    return 0


def cmd_status(a):
    acc = pick_account(a.api_token, a.account_id)
    t = find_tunnel(a.api_token, acc, a.tunnel_name)
    if not t:
        print(f"tunnel {a.tunnel_name} 不存在")
        return 1
    conns = t.get("connections") or []
    print(f"tunnel {t['name']} id={t['id']} status={t.get('status')} connections={len(conns)}")
    for c in conns:
        print(f"  - {c.get('colo_name')} origin_ip={c.get('origin_ip')} opened={c.get('opened_at')}")
    cfg = _req(a.api_token, "GET", f"/accounts/{acc}/cfd_tunnel/{t['id']}/configurations") or {}
    for r in ((cfg.get("config") or {}).get("ingress") or []):
        print(f"  ingress {r.get('hostname','*')}{r.get('path','')} -> {r.get('service')}")
    return 0


def cmd_token(a):
    acc = pick_account(a.api_token, a.account_id)
    t = find_tunnel(a.api_token, acc, a.tunnel_name)
    if not t:
        print(f"tunnel {a.tunnel_name} 不存在")
        return 1
    print(get_token(a.api_token, acc, t["id"]))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="Cloudflare Tunnel 自動建置（防禦節點）",
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--api-token", default=os.environ.get("CF_API_TOKEN", ""),
                        help="Cloudflare API Token（或環境變數 CF_API_TOKEN）")
        sp.add_argument("--account-id", default="", help="Token 可見多個 account 時指定")
        sp.add_argument("--tunnel-name", default="ithome2026-waf", help="tunnel 名稱（預設 ithome2026-waf）")

    s = sub.add_parser("setup", help="建立 tunnel + ingress + DNS，印出 connector token")
    common(s)
    s.add_argument("--hostname", required=True, help="對外主機名稱，例 app.example.com")
    s.add_argument("--service", default="http://waf-nginx:8080",
                   help="tunnel 後端（compose 服務名，預設 http://waf-nginx:8080）")
    s.add_argument("--path", default="",
                   help="只把符合此 regex 的路徑導到 --service（例 '^/beakplatform(/|$)'），"
                        "同 hostname 其餘路徑由另一條沒有 --path 的規則接手")
    s.add_argument("--write-env", default="", help="把 token 寫入指定 .env 的 CLOUDFLARE_TUNNEL_TOKEN")
    s.set_defaults(fn=cmd_setup)

    s = sub.add_parser("remove", help="移除某個 hostname 的全部 ingress 與 CNAME")
    common(s)
    s.add_argument("--hostname", required=True)
    s.set_defaults(fn=cmd_remove)

    s = sub.add_parser("status", help="顯示 tunnel 連線與 ingress")
    common(s)
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("token", help="只印出 connector token")
    common(s)
    s.set_defaults(fn=cmd_token)

    a = p.parse_args(argv)
    if not a.api_token:
        p.error("缺 --api-token（或環境變數 CF_API_TOKEN）")
    try:
        return a.fn(a)
    except CfError as e:
        print(f"[!] {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
