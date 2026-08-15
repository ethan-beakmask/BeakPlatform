"""nftables enforcer — manages a named set in inet/secstack/blocklist.

Bootstrap (run once on host or via init container):

  nft add table inet secstack
  nft add set inet secstack blocklist '{ type ipv4_addr; flags interval,timeout; }'
  nft add set inet secstack blocklist6 '{ type ipv6_addr; flags interval,timeout; }'
  nft add chain inet secstack input '{ type filter hook input priority -100; }'
  nft add rule inet secstack input ip  saddr @blocklist  drop
  nft add rule inet secstack input ip6 saddr @blocklist6 drop

This enforcer just adds/removes elements with optional timeout.
"""
import asyncio
import ipaddress
import json

SUPPORTED_TARGETS = {"ip", "cidr"}
STATE_SETS = ("blocklist", "blocklist6", "allowlist")


def _set_for(value: str) -> str:
    try:
        net = ipaddress.ip_network(value, strict=False)
        return "blocklist6" if net.version == 6 else "blocklist"
    except ValueError:
        return "blocklist"


async def _nft(*args: str) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        "nft", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    return proc.returncode, out.decode(errors="replace")


def _elem_value(elem) -> str | None:
    if isinstance(elem, str):
        return elem
    if not isinstance(elem, dict):
        return None
    if "elem" in elem:
        return _elem_value(elem["elem"])
    if "val" in elem:
        return _elem_value(elem["val"])
    if "prefix" in elem and isinstance(elem["prefix"], dict):
        prefix = elem["prefix"]
        addr = prefix.get("addr")
        length = prefix.get("len")
        if addr is not None and length is not None:
            return f"{addr}/{length}"
    if "addr" in elem:
        return str(elem["addr"])
    return None


def _elem_expires(elem) -> int | None:
    if not isinstance(elem, dict):
        return None
    if "expires" in elem:
        try:
            return int(elem["expires"])
        except (TypeError, ValueError):
            return None
    if isinstance(elem.get("elem"), dict):
        return _elem_expires(elem["elem"])
    return None


def _extract_set(payload: dict, set_name: str):
    for item in payload.get("nftables") or []:
        set_data = item.get("set") if isinstance(item, dict) else None
        if isinstance(set_data, dict) and set_data.get("name") == set_name:
            return set_data.get("elem") or []
    return []


async def list_sets() -> tuple[bool, dict]:
    state = {"blocklist": {}, "blocklist6": {}, "allowlist": []}
    for set_name in STATE_SETS:
        rc, out = await _nft("-j", "list", "set", "inet", "secstack", set_name)
        if rc != 0:
            return False, {"error": out.strip()[:300] or f"nft_list_failed:{set_name}"}
        try:
            payload = json.loads(out)
        except json.JSONDecodeError:
            return False, {"error": f"nft_json_invalid:{set_name}"}
        elems = _extract_set(payload, set_name)
        for elem in elems:
            value = _elem_value(elem)
            if not value:
                continue
            if set_name == "allowlist":
                state["allowlist"].append(value)
            else:
                state[set_name][value] = _elem_expires(elem)
    state["allowlist"].sort()
    return True, state


async def apply(decision: dict, cfg) -> dict:
    action = decision.get("action")
    target_type = decision.get("target_type")
    target = decision.get("target_value")
    ttl = decision.get("ttl_seconds")

    if target_type not in SUPPORTED_TARGETS:
        return {"ok": False, "error": f"unsupported_target_type:{target_type}"}
    if not target:
        return {"ok": False, "error": "empty_target"}

    set_name = _set_for(target)
    elem = f"{target} timeout {ttl}s" if ttl else target

    if action == "block":
        rc, out = await _nft("add", "element", "inet", "secstack", set_name, "{", elem, "}")
        return {"ok": rc == 0, "set": set_name, "element": elem, "stdout": out.strip()[:300]}
    if action == "unblock":
        rc, out = await _nft("delete", "element", "inet", "secstack", set_name, "{", target, "}")
        # idempotent: element already gone (kernel TTL expired or never blocked) → ok
        out_l = out.lower()
        if rc != 0 and ("does not exist" in out_l or "no such file" in out_l):
            return {"ok": True, "note": "already_absent"}
        return {"ok": rc == 0, "set": set_name, "element": target, "stdout": out.strip()[:300]}
    return {"ok": False, "error": f"unsupported_action:{action}"}
