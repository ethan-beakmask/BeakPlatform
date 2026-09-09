"""Minimal HTML dashboard for od-bridge — /stats, /decisions, /forwards.

No auth, no cookies, no JS — designed for LAN-trust ops view.
"""
import html
import os
from datetime import datetime, timezone

from aiohttp import web

from .enforcers import edl, nftables
from .state import stats


_CSS = """
<style>
body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 24px; max-width: 1200px; }
h1 { font-size: 18px; margin-bottom: 4px; }
h2 { font-size: 14px; color: #444; margin-top: 28px; border-bottom: 1px solid #ddd; padding-bottom: 4px; }
nav a { margin-right: 12px; font-size: 13px; }
table { border-collapse: collapse; width: 100%; font-size: 12px; margin-top: 8px; }
th, td { border: 1px solid #ddd; padding: 4px 8px; text-align: left; vertical-align: top; }
th { background: #f5f5f5; }
.k { color: #666; }
.ok { color: #2c7a2c; }
.warn { color: #b97a00; }
.err { color: #c93333; }
.mono { font-family: 'SF Mono', Menlo, Consolas, monospace; }
.metric { display: inline-block; margin-right: 24px; }
.metric .v { font-size: 22px; font-weight: 600; }
.metric .l { font-size: 11px; color: #888; text-transform: uppercase; }
small { color: #888; }
</style>
"""

_NAV = """
<nav>
  <a href="/stats">Stats</a>
  <a href="/forwards">Forwards</a>
  <a href="/decisions">Decisions</a>
  <a href="/edl">EDL block</a>
  <a href="/edl/allow">EDL allow</a>
  <a href="/health">Health (JSON)</a>
</nav>
"""


def _fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M:%S")


def _status_class(status) -> str:
    if isinstance(status, int):
        if 200 <= status < 300: return "ok"
        if 400 <= status < 500: return "warn"
        return "err"
    if status == "applied": return "ok"
    if status == "partial": return "warn"
    if status in ("failed", "error"): return "err"
    return ""


def _layout(title: str, body: str) -> str:
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)} · od-bridge</title>{_CSS}</head><body>{_NAV}<h1>{html.escape(title)}</h1>{body}</body></html>"


async def page_stats(request: web.Request) -> web.Response:
    s = stats.snapshot()
    c = s["counters"]
    sa_left = s["sa_token_valid_for_sec"]
    sa_class = "ok" if sa_left > 60 else ("warn" if sa_left > 0 else "err")
    body = f"""
    <p class="k">uptime {s['uptime_sec']}s · last executor iter
       {('+' + str(s['last_executor_iter_ago_sec']) + 's ago') if s['last_executor_iter_ago_sec'] is not None else 'n/a'}
    </p>
    <h2>Intake (Vector → bridge → BP)</h2>
    <div>
      <div class="metric"><div class="v">{c['intake_total']}</div><div class="l">total</div></div>
      <div class="metric"><div class="v ok">{c['intake_2xx']}</div><div class="l">2xx</div></div>
      <div class="metric"><div class="v warn">{c['intake_4xx']}</div><div class="l">4xx</div></div>
      <div class="metric"><div class="v err">{c['intake_5xx']}</div><div class="l">5xx</div></div>
      <div class="metric"><div class="v err">{c['intake_unreachable']}</div><div class="l">unreachable</div></div>
    </div>
    <h2>Executor (BP /decisions)</h2>
    <div>
      <div class="metric"><div class="v">{c['decisions_processed']}</div><div class="l">processed</div></div>
      <div class="metric"><div class="v ok">{c['decisions_applied']}</div><div class="l">applied</div></div>
      <div class="metric"><div class="v warn">{c['decisions_partial']}</div><div class="l">partial</div></div>
      <div class="metric"><div class="v err">{c['decisions_failed']}</div><div class="l">failed</div></div>
    </div>
    <h2>SA token</h2>
    <p>logins: <strong>{c['sa_logins']}</strong>
       · 429: <strong class="{'err' if c['sa_login_429s'] else ''}">{c['sa_login_429s']}</strong>
       · GET 401: <strong class="{'err' if c['decisions_get_401'] else ''}">{c['decisions_get_401']}</strong>
       · current token valid for: <strong class="{sa_class}">{sa_left}s</strong></p>
    <p><small>Auto-refresh every 5s.</small></p>
    <meta http-equiv="refresh" content="5">
    """
    return web.Response(text=_layout("Stats", body), content_type="text/html")


async def page_forwards(request: web.Request) -> web.Response:
    s = stats.snapshot()
    rows = "".join(
        f"<tr><td class='mono'>{_fmt_ts(f['ts'])}</td>"
        f"<td>{html.escape(str(f['src']))}</td>"
        f"<td class='mono {_status_class(f['status'])}'>{f['status']}</td>"
        f"<td class='mono'>{html.escape(str(f['cid']))}</td></tr>"
        for f in s["recent_forwards"]
    )
    body = f"""
    <p class="k">最近 50 筆 intake 轉送(在記憶體,重啟即清)</p>
    <table>
      <tr><th>time (UTC)</th><th>source</th><th>upstream status</th><th>correlation_id</th></tr>
      {rows or '<tr><td colspan="4" class="k">no forwards yet</td></tr>'}
    </table>
    <meta http-equiv="refresh" content="10">
    """
    return web.Response(text=_layout("Forwards", body), content_type="text/html")


async def page_decisions(request: web.Request) -> web.Response:
    s = stats.snapshot()
    rows = "".join(
        f"<tr><td class='mono'>{_fmt_ts(d['ts'])}</td>"
        f"<td>{html.escape(d['action'])}</td>"
        f"<td class='mono'>{html.escape(d['target'])}</td>"
        f"<td>{html.escape(','.join(d['eps']))}</td>"
        f"<td class='{_status_class(d['status'])}'>{html.escape(d['status'])}</td>"
        f"<td class='mono'><small>{html.escape(d['err'])}</small></td>"
        f"<td class='mono'><small>{html.escape(d['sc'])}</small></td></tr>"
        for d in s["recent_decisions"]
    )
    body = f"""
    <p class="k">最近 50 筆 executor 處理過的決策</p>
    <table>
      <tr><th>time (UTC)</th><th>action</th><th>target</th><th>EPs</th><th>status</th><th>err</th><th>sc</th></tr>
      {rows or '<tr><td colspan="7" class="k">no decisions yet</td></tr>'}
    </table>
    <meta http-equiv="refresh" content="10">
    """
    return web.Response(text=_layout("Decisions", body), content_type="text/html")


async def _serve_edl(request: web.Request, which: str) -> web.Response:
    """Serve an EDL file as text/plain — this is what PAN-OS fetches.

    Returns an empty list rather than 404 when nothing has been blocked yet:
    a 404 makes PAN-OS keep the *previous* contents, which would silently pin
    a stale blocklist.
    """
    cfg = request.app["cfg"]
    path = os.path.join(cfg.edl_dir, edl.BLOCK_FILE if which == "block" else edl.ALLOW_FILE)
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError:
        text = f"# OpenDefense EDL — {which}list\n# entries 0\n" if cfg.edl_header else ""
    return web.Response(text=text, content_type="text/plain", charset="utf-8")


async def page_edl_block(request: web.Request) -> web.Response:
    return await _serve_edl(request, "block")


async def page_edl_allow(request: web.Request) -> web.Response:
    return await _serve_edl(request, "allow")


async def state_nft(request: web.Request) -> web.Response:
    ok, payload = await nftables.list_sets()
    if not ok:
        return web.json_response(payload, status=503)
    return web.json_response(payload)


def register_routes(app: web.Application) -> None:
    app.router.add_get("/", page_stats)
    app.router.add_get("/stats", page_stats)
    app.router.add_get("/forwards", page_forwards)
    app.router.add_get("/decisions", page_decisions)
    app.router.add_get("/edl", page_edl_block)
    app.router.add_get("/edl/allow", page_edl_allow)
    app.router.add_get("/state/nft", state_nft)
