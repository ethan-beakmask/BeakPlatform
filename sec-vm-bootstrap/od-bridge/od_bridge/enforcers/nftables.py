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

SUPPORTED_TARGETS = {"ip", "cidr"}


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
