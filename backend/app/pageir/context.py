"""Page IR render context stored on Flask request globals."""
from __future__ import annotations

from flask import g


_VALID_WORLDS = {"platform", "portal"}


def set_render_context(world, sub_system_sc=None, portal_user=None) -> None:
    """Set the server-side Page IR render context for the current request."""
    if world not in _VALID_WORLDS:
        raise ValueError(f"Invalid Page IR render world: {world}")
    ctx = {"world": world}
    if sub_system_sc is not None:
        ctx["sub_system_sc"] = sub_system_sc
    if portal_user is not None:
        ctx["portal_user"] = portal_user
    g.pageir_render_context = ctx


def get_render_context() -> dict:
    """Return the current Page IR render context; default is platform."""
    try:
        return dict(getattr(g, "pageir_render_context", None) or {"world": "platform"})
    except RuntimeError:
        return {"world": "platform"}


def clear_render_context() -> None:
    """Clear the current Page IR render context."""
    try:
        if hasattr(g, "pageir_render_context"):
            delattr(g, "pageir_render_context")
    except RuntimeError:
        return
