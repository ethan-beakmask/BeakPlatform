import hashlib
import hmac
import json
import logging
import time

from aiohttp import ClientSession, ClientTimeout, web

from .state import stats
from .web import register_routes

log = logging.getLogger("ingest")


def _sign(secret: bytes, ts: str, body: bytes) -> str:
    canonical = ts.encode() + b"\n" + body
    return "sha256=" + hmac.new(secret, canonical, hashlib.sha256).hexdigest()


async def _forward(cfg, body: bytes) -> tuple[int, str]:
    ts = str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        "X-OD-Key-Id": cfg.intake_key_id,
        "X-OD-Timestamp": ts,
        "X-OD-Signature": _sign(cfg.intake_secret, ts, body),
    }
    async with ClientSession(timeout=ClientTimeout(total=10)) as s:
        async with s.post(cfg.intake_url, data=body, headers=headers) as r:
            return r.status, await r.text()


async def handle_event(request: web.Request) -> web.Response:
    cfg = request.app["cfg"]
    # 一律以 bytes 比對：compare_digest 的 str 形式只接受 ASCII，
    # 送非 ASCII 的 Authorization 會拋 TypeError 變成 500 而不是 401。
    auth = request.headers.get("Authorization", "").encode("utf-8", "surrogateescape")
    expected = f"Bearer {cfg.ingest_token}".encode() if cfg.ingest_token else b""
    if not cfg.ingest_token:
        if not request.app.get("missing_ingest_token_logged", False):
            log.error("BRIDGE_INGEST_TOKEN not set; /events is closed")
            request.app["missing_ingest_token_logged"] = True
    if not expected or not hmac.compare_digest(auth, expected):
        log.warning("unauthorized /events request from %s", request.remote)
        return web.json_response({"error": "unauthorized"}, status=401)

    body = await request.read()
    if not body:
        return web.json_response({"error": "empty_body"}, status=400)
    try:
        data = json.loads(body)
    except Exception:
        return web.json_response({"error": "invalid_json"}, status=400)
    if "correlation_id" not in data or "source_system" not in data:
        return web.json_response(
            {"error": "missing_required", "need": ["correlation_id", "source_system"]},
            status=400,
        )
    cid = str(data.get("correlation_id", ""))
    src = str(data.get("source_system", ""))
    try:
        status, text = await _forward(cfg, body)
    except Exception as e:
        log.exception("forward failed")
        stats.record_forward(cid, src, 0)
        return web.json_response({"error": "upstream_unreachable", "detail": str(e)}, status=502)
    stats.record_forward(cid, src, status)
    log.info("forwarded cid=%s src=%s status=%s", cid, src, status)
    return web.Response(
        body=text,
        status=status if status < 500 else 502,
        content_type="application/json",
    )


async def health(_: web.Request) -> web.Response:
    return web.json_response({"ok": True})


async def run_ingest_server(cfg) -> None:
    app = web.Application(client_max_size=2 * 1024 * 1024)
    app["cfg"] = cfg
    app.router.add_post("/events", handle_event)
    app.router.add_get("/health", health)
    register_routes(app)   # /, /stats, /forwards, /decisions
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, cfg.ingest_listen_host, cfg.ingest_listen_port)
    await site.start()
    log.info("ingest server :%d → %s", cfg.ingest_listen_port, cfg.intake_url)
    import asyncio
    await asyncio.Event().wait()
