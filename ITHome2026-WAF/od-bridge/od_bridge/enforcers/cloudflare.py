"""Cloudflare enforcer — placeholder.

Real implementation needs a Cloudflare API token (with Account.Account WAF Edit
scope) plus account_id, and uses the IP Lists or Custom Rules API.

For now we accept the decision but no-op so executor can still report 'partial'
without crashing on cloudflare-tagged decisions.
"""
import logging
import os

log = logging.getLogger("enforce.cloudflare")


async def apply(decision: dict, cfg) -> dict:
    if not os.environ.get("CLOUDFLARE_API_TOKEN"):
        log.info("cloudflare enforcer no-op (no CLOUDFLARE_API_TOKEN)")
        return {"ok": False, "error": "not_configured"}
    # TODO: implement IP List add/remove via /accounts/{id}/rules/lists/{list_id}/items
    return {"ok": False, "error": "not_implemented_yet"}
