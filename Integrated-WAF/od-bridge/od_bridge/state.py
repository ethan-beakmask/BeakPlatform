"""In-memory operational state for the bridge.

Used by the /stats and /decisions HTTP routes.  Lossy on restart by design —
this is for at-a-glance human inspection, not auditing (BP and ClickHouse
hold the durable record).
"""
from collections import deque
from threading import Lock
from time import time


_MAX = 200


class Stats:
    def __init__(self) -> None:
        self.lock = Lock()
        self.started_at = time()

        # rolling event windows
        self.recent_forwards: deque = deque(maxlen=_MAX)
        self.recent_decisions: deque = deque(maxlen=_MAX)

        self.counters: dict = {
            "intake_total": 0,
            "intake_2xx": 0,
            "intake_4xx": 0,
            "intake_5xx": 0,
            "intake_unreachable": 0,

            "decisions_processed": 0,
            "decisions_applied": 0,
            "decisions_partial": 0,
            "decisions_failed": 0,

            "sa_logins": 0,
            "sa_login_429s": 0,
            "decisions_get_401": 0,
        }

        self.sa_token_expires_at: float = 0.0
        self.last_executor_iter: float = 0.0
        self.last_executor_error: str = ""

    # ----- ingest side -----
    def record_forward(self, cid: str, src: str, upstream_status: int) -> None:
        with self.lock:
            self.recent_forwards.appendleft({
                "ts": time(),
                "cid": cid,
                "src": src,
                "status": upstream_status,
            })
            self.counters["intake_total"] += 1
            if 200 <= upstream_status < 300:
                self.counters["intake_2xx"] += 1
            elif 400 <= upstream_status < 500:
                self.counters["intake_4xx"] += 1
            elif 500 <= upstream_status < 600:
                self.counters["intake_5xx"] += 1
            else:
                self.counters["intake_unreachable"] += 1

    # ----- executor side -----
    def record_decision(self, sc: str, action: str, target: str,
                        eps: list, result_status: str, err: str = "") -> None:
        with self.lock:
            self.recent_decisions.appendleft({
                "ts": time(),
                "sc": sc,
                "action": action,
                "target": target,
                "eps": eps,
                "status": result_status,
                "err": err[:120],
            })
            self.counters["decisions_processed"] += 1
            key = f"decisions_{result_status}"
            if key in self.counters:
                self.counters[key] += 1

    def record_sa_login(self, ok: bool, expires_at: float = 0.0) -> None:
        with self.lock:
            self.counters["sa_logins"] += 1
            if ok:
                self.sa_token_expires_at = expires_at
            else:
                self.counters["sa_login_429s"] += 1

    def record_decisions_401(self) -> None:
        with self.lock:
            self.counters["decisions_get_401"] += 1

    def record_executor_iter(self, error: str = "") -> None:
        with self.lock:
            self.last_executor_iter = time()
            self.last_executor_error = error

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "uptime_sec": int(time() - self.started_at),
                "counters": dict(self.counters),
                "sa_token_valid_for_sec": max(0, int(self.sa_token_expires_at - time())),
                "last_executor_iter_ago_sec": (
                    int(time() - self.last_executor_iter) if self.last_executor_iter else None
                ),
                "last_executor_error": self.last_executor_error,
                "recent_forwards": list(self.recent_forwards)[:50],
                "recent_decisions": list(self.recent_decisions)[:50],
            }


stats = Stats()
