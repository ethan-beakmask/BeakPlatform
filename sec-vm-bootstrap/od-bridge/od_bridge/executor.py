import asyncio
import json
import logging
import time

from aiohttp import ClientSession, ClientTimeout

from .enforcers import crowdsec, edl, nftables
from .enforcers import cloudflare as cf
from .state import stats

log = logging.getLogger("executor")

ENFORCERS = {
    "crowdsec": crowdsec.apply,
    "nftables": nftables.apply,
    "cloudflare": cf.apply,
    "edl": edl.apply,
}


class TokenManager:
    def __init__(self, cfg):
        self.cfg = cfg
        self._token: str | None = None
        self._expires_at: float = 0.0

    async def get(self, session: ClientSession) -> str:
        now = time.time()
        if self._token and now < self._expires_at - 60:
            return self._token
        async with session.post(
            self.cfg.sa_login_url,
            json={"sa_id": self.cfg.sa_id, "sa_secret": self.cfg.sa_secret},
            timeout=ClientTimeout(total=10),
        ) as r:
            if r.status != 200:
                body = await r.text()
                raise RuntimeError(f"SA login {r.status}: {body}")
            j = await r.json()
        self._token = j["access_token"]
        self._expires_at = now + float(j.get("expires_in", 900))
        stats.record_sa_login(True, self._expires_at)
        log.info("SA login ok, expires in %ss", j.get("expires_in"))
        return self._token

    def invalidate(self) -> None:
        self._token = None


async def process_decision(session: ClientSession, token: str, cfg, d: dict) -> None:
    points = [p for p in d.get("enforcement_points") or [] if p in cfg.my_enforcement_points]
    if not points:
        return  # not for us

    sc = d["secure_code"]
    log.info("decision %s action=%s target=%s/%s points=%s",
             sc, d.get("action"), d.get("target_type"), d.get("target_value"), points)

    # Optional optimistic lock: PATCH picked_up before applying
    await _patch(session, token, cfg, sc, {
        "status": "picked_up", "applied_by": cfg.applied_by, "application_result": {}
    })

    results: dict = {}
    any_ok = False
    any_fail = False
    for ep in points:
        fn = ENFORCERS.get(ep)
        if not fn:
            results[ep] = {"ok": False, "error": "unsupported_enforcer"}
            any_fail = True
            continue
        try:
            r = await fn(d, cfg)
            results[ep] = r
            if r.get("ok"):
                any_ok = True
            else:
                any_fail = True
        except Exception as e:
            log.exception("enforcer %s failed", ep)
            results[ep] = {"ok": False, "error": str(e)}
            any_fail = True

    status = "applied" if (any_ok and not any_fail) else ("partial" if any_ok else "failed")
    body = {
        "status": status,
        "applied_by": cfg.applied_by,
        "application_result": results,
    }
    err_short = ""
    if status == "failed":
        body["error_message"] = json.dumps(results)[:1000]
        err_short = json.dumps({k: v.get("error", "") for k, v in results.items() if not v.get("ok")})
    stats.record_decision(
        sc, str(d.get("action", "")), str(d.get("target_value", "")),
        list(points), status, err_short,
    )
    await _patch(session, token, cfg, sc, body)


async def _patch(session, token, cfg, sc, payload) -> None:
    url = f"{cfg.decisions_url}/{sc}"
    async with session.patch(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
        timeout=ClientTimeout(total=10),
    ) as r:
        if r.status >= 400:
            log.warning("PATCH %s → %s: %s", sc, r.status, await r.text())


async def run_executor_loop(cfg) -> None:
    tm = TokenManager(cfg)
    backoff = 1.0
    consec_401 = 0
    async with ClientSession() as session:
        while True:
            sleep_after = cfg.poll_interval  # default end-of-iter pause
            try:
                token = await tm.get(session)
                async with session.get(
                    cfg.decisions_url,
                    headers={"Authorization": f"Bearer {token}"},
                    params={"status": "pending", "limit": 100},
                    timeout=ClientTimeout(total=10),
                ) as r:
                    if r.status == 401:
                        consec_401 += 1
                        stats.record_decisions_401()
                        # On first 401, invalidate token and try again next normal iter.
                        # On repeated 401, back off heavily so we don't burn SA login quota.
                        if consec_401 == 1:
                            tm.invalidate()
                            log.warning("GET 401 — invalidating token, normal retry")
                        else:
                            sleep_after = min(60.0 * consec_401, 600.0)
                            log.warning("GET 401 (%dx in a row) — backing off %ss",
                                        consec_401, sleep_after)
                    elif r.status == 429:
                        retry = float(r.headers.get("Retry-After", "30"))
                        log.warning("rate limited (decisions GET), sleeping %ss", retry)
                        sleep_after = retry
                    elif r.status != 200:
                        log.warning("GET decisions %s: %s", r.status, await r.text())
                        sleep_after = min(backoff, 60.0)
                        backoff = min(backoff * 2, 60.0)
                    else:
                        consec_401 = 0
                        backoff = 1.0
                        j = await r.json()
                        decisions = j.get("decisions", [])
                        if decisions:
                            log.info("got %d pending decisions", len(decisions))
                            await asyncio.gather(
                                *(process_decision(session, token, cfg, d) for d in decisions),
                                return_exceptions=True,
                            )
            except RuntimeError as e:
                msg = str(e)
                if "429" in msg:
                    stats.record_sa_login(False)
                    sleep_after = 90.0
                    log.warning("SA login rate-limited; sleeping %ss", sleep_after)
                else:
                    sleep_after = min(backoff, 60.0)
                    backoff = min(backoff * 2, 60.0)
                    log.warning("SA login error: %s; sleeping %ss", e, sleep_after)
                stats.record_executor_iter(error=msg[:200])
            except Exception as e:
                log.exception("executor loop error: %s", e)
                sleep_after = min(backoff, 60.0)
                backoff = min(backoff * 2, 60.0)
                stats.record_executor_iter(error=str(e)[:200])
            else:
                stats.record_executor_iter()
            await asyncio.sleep(sleep_after)
