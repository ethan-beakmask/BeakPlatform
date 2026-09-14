"""CrowdSec enforcer — adds/removes decisions via LAPI.

Uses HTTP API (machine credentials).  On first start the bridge tries to
reuse credentials at /state/crowdsec_machine.json; if absent, it leaves
the enforcer disabled and logs a hint.

Register the bridge as a CrowdSec machine before starting:

  docker compose exec crowdsec cscli machines add od-bridge --auto \
      --file /tmp/od-bridge.yaml
  docker compose cp crowdsec:/tmp/od-bridge.yaml ./od-bridge/state/crowdsec_machine.json

(or write the JSON form manually with `machine_id` and `password`.)
"""
import asyncio
import json
import logging
import os
import time
from pathlib import Path

import aiohttp

log = logging.getLogger("enforce.crowdsec")
STATE = Path("/state/crowdsec_machine.json")

_token: str | None = None
_token_expires_at: float = 0.0


async def _login(session: aiohttp.ClientSession, base: str) -> str | None:
    if not STATE.exists():
        log.warning("crowdsec machine creds missing at %s — enforcer skipped", STATE)
        return None
    creds = json.loads(STATE.read_text())
    async with session.post(f"{base}/v1/watchers/login", json={
        "machine_id": creds["machine_id"], "password": creds["password"],
    }, timeout=aiohttp.ClientTimeout(total=10)) as r:
        if r.status != 200:
            log.warning("crowdsec login %s: %s", r.status, await r.text())
            return None
        j = await r.json()
        return j.get("token")


async def _token_get(session: aiohttp.ClientSession, base: str) -> str | None:
    global _token, _token_expires_at
    now = time.time()
    if _token and now < _token_expires_at - 60:
        return _token
    t = await _login(session, base)
    if t:
        _token = t
        _token_expires_at = now + 60 * 60   # CrowdSec default
    return t


_SCOPE_MAP = {"ip": "Ip", "cidr": "Range", "country": "Country", "asn": "AS"}


async def apply(decision: dict, cfg) -> dict:
    action = decision.get("action")
    target_type = decision.get("target_type")
    target = decision.get("target_value")
    ttl = decision.get("ttl_seconds")
    reason = (decision.get("reason") or "od-bridge")[:200]

    scope = _SCOPE_MAP.get(target_type)
    if not scope:
        return {"ok": False, "error": f"unsupported_target_type:{target_type}"}
    if not target:
        return {"ok": False, "error": "empty_target"}

    base = cfg.crowdsec_lapi_url.rstrip("/")

    async with aiohttp.ClientSession() as s:
        token = await _token_get(s, base)
        if not token:
            return {"ok": False, "error": "no_machine_creds"}
        headers = {"Authorization": f"Bearer {token}"}

        if action == "block":
            duration = f"{ttl}s" if ttl else "8760h"
            payload = [{
                "scope": scope,
                "value": target,
                "duration": duration,
                "type": "ban",
                "scenario": "od-bridge",
                "origin": "od-bridge",
                "reason": reason,
            }]
            async with s.post(f"{base}/v1/decisions", json=payload,
                              headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
                ok = r.status in (200, 201)
                return {"ok": ok, "status": r.status, "body": (await r.text())[:300]}

        if action == "unblock":
            async with s.delete(f"{base}/v1/decisions",
                                params={"scope": scope, "value": target},
                                headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
                ok = r.status in (200, 204)
                return {"ok": ok, "status": r.status, "body": (await r.text())[:300]}

        return {"ok": False, "error": f"unsupported_action:{action}"}
