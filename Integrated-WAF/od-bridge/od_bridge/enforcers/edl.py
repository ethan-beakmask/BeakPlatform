"""EDL enforcer — materializes OpenDefense decisions into PAN-OS External
Dynamic Lists.

Why this is a *reconciler*, not an appender
-------------------------------------------
A PAN-OS EDL is a plain-text file the firewall re-fetches on a schedule, and
whatever the file says at fetch time IS the policy.  There is no per-entry TTL
in the format.  So an append-only writer can never drop an expired entry — that
is exactly how a blocklist grows until the firewall refuses to load it.

Instead we keep the authoritative set in `state.json` (each entry carrying its
own expires_at) and re-render the whole file after every mutation and on a
periodic prune.  Additions accumulate; expiries fall out on their own.

Two lists are produced, matching the block/allow control we expose:
  blocklist.txt  <- action=block     (deny rule source)
  allowlist.txt  <- action=allow     (allow rule source, placed above the deny)
`unblock` removes the target from both lists — it is the generic "stop acting
on this target" signal, and removal is idempotent.

Served over HTTP by web.py at /edl and /edl/allow, because PAN-OS can only
consume an EDL from a URL.
"""
import json
import logging
import os
import tempfile
import time
from typing import Any, Dict, Optional

log = logging.getLogger("enforce.edl")

SUPPORTED_TARGETS = {"ip", "cidr"}

BLOCK_FILE = "blocklist.txt"
ALLOW_FILE = "allowlist.txt"
STATE_FILE = "state.json"

_LIST_FOR_ACTION = {"block": "block", "allow": "allow"}


def _paths(cfg) -> Dict[str, str]:
    d = cfg.edl_dir
    return {
        "dir": d,
        "block": os.path.join(d, BLOCK_FILE),
        "allow": os.path.join(d, ALLOW_FILE),
        "state": os.path.join(d, STATE_FILE),
    }


def _load_state(path: str) -> Dict[str, Dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {"block": {}, "allow": {}}
    except (OSError, ValueError) as exc:
        # A corrupt state file must not wedge enforcement forever; start clean
        # and say so loudly — the next decisions will repopulate it.
        log.error("edl state unreadable (%s), starting empty: %s", path, exc)
        return {"block": {}, "allow": {}}
    for key in ("block", "allow"):
        if not isinstance(data.get(key), dict):
            data[key] = {}
    return data


def _atomic_write(path: str, text: str) -> None:
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-", suffix=".swap")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _prune(entries: Dict[str, Dict[str, Any]], now: float) -> int:
    """Drop entries whose expires_at has passed. Returns how many were dropped."""
    dead = [
        target for target, meta in entries.items()
        if meta.get("expires_at") is not None and float(meta["expires_at"]) <= now
    ]
    for target in dead:
        del entries[target]
    return len(dead)


def _render(entries: Dict[str, Dict[str, Any]], title: str, now: float,
            *, header: bool = False) -> str:
    """Render one list file.

    Default output is bare addresses, one per line — that is the only shape
    PAN-OS documents for an IP list.  Its syntax is
    `[address][space][comment]`: a comment has to sit on the same line as an
    address, so a standalone `#` line is outside the documented format and a
    firewall is free to reject it.  (Before PAN-OS 6.1 any line carrying a
    comment was dropped entirely.)

    `header=True` prepends a `#` block for humans reading it over curl.  Keep
    it off for anything a firewall actually fetches.
    """
    lines = []
    if header:
        lines += [
            f"# OpenDefense EDL — {title}",
            f"# generated {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now))} UTC",
            f"# entries {len(entries)}",
            "#",
            "# Rendered from od-bridge state; entries disappear when their TTL lapses.",
            "# Do not edit by hand — the next reconcile overwrites this file.",
        ]
    # Sorted so a diff between fetches is readable by a human on-call.
    for target in sorted(entries):
        lines.append(target)
    lines.append("")
    return "\n".join(lines)


def _write_lists(p: Dict[str, str], state: Dict[str, Dict[str, Any]],
                 now: float, header: bool) -> None:
    _atomic_write(p["block"], _render(state["block"], "blocklist", now, header=header))
    _atomic_write(p["allow"], _render(state["allow"], "allowlist", now, header=header))
    _atomic_write(p["state"], json.dumps(state, indent=2, sort_keys=True))


def reconcile(cfg, *, now: Optional[float] = None) -> Dict[str, Any]:
    """Prune expired entries and re-render both list files. Safe to call often."""
    now = time.time() if now is None else now
    p = _paths(cfg)
    os.makedirs(p["dir"], exist_ok=True)

    state = _load_state(p["state"])
    dropped = _prune(state["block"], now) + _prune(state["allow"], now)

    _write_lists(p, state, now, cfg.edl_header)

    return {
        "ok": True,
        "block_entries": len(state["block"]),
        "allow_entries": len(state["allow"]),
        "expired_dropped": dropped,
    }


async def apply(decision: dict, cfg) -> dict:
    action = decision.get("action")
    target_type = decision.get("target_type")
    target = decision.get("target_value")
    ttl = decision.get("ttl_seconds")

    if target_type not in SUPPORTED_TARGETS:
        return {"ok": False, "error": f"unsupported_target_type:{target_type}"}
    if not target:
        return {"ok": False, "error": "empty_target"}

    now = time.time()
    p = _paths(cfg)
    os.makedirs(p["dir"], exist_ok=True)
    state = _load_state(p["state"])

    if action in _LIST_FOR_ACTION:
        which = _LIST_FOR_ACTION[action]
        expires_at = (now + float(ttl)) if ttl else None
        state[which][target] = {
            "expires_at": expires_at,
            "added_at": now,
            "ttl_seconds": ttl,
            "severity": decision.get("severity"),
            "reason": decision.get("reason"),
            "decision_secure_code": decision.get("secure_code"),
            "case_secure_code": decision.get("case_secure_code"),
        }
        note = None
    elif action == "unblock":
        # Generic removal: drop the target from whichever lists hold it.
        removed = [w for w in ("block", "allow") if state[w].pop(target, None) is not None]
        note = "already_absent" if not removed else ",".join(removed)
    else:
        return {"ok": False, "error": f"unsupported_action:{action}"}

    _prune(state["block"], now)
    _prune(state["allow"], now)

    try:
        _write_lists(p, state, now, cfg.edl_header)
    except OSError as exc:
        log.exception("edl write failed")
        return {"ok": False, "error": f"write_failed:{exc}"}

    result = {
        "ok": True,
        "block_entries": len(state["block"]),
        "allow_entries": len(state["allow"]),
        "file": p["block"] if action != "allow" else p["allow"],
    }
    if note:
        result["note"] = note
    log.info("edl %s %s → block=%d allow=%d",
             action, target, result["block_entries"], result["allow_entries"])
    return result


async def run_prune_loop(cfg) -> None:
    """Periodic reconcile so entries expire even when no decisions arrive."""
    import asyncio
    while True:
        await asyncio.sleep(cfg.edl_prune_interval)
        try:
            r = reconcile(cfg)
            if r["expired_dropped"]:
                log.info("edl prune dropped %d expired entr%s (block=%d allow=%d)",
                         r["expired_dropped"],
                         "y" if r["expired_dropped"] == 1 else "ies",
                         r["block_entries"], r["allow_entries"])
        except Exception:
            log.exception("edl prune failed")
