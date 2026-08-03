"""Page IR NoCode portal menu provider."""
from __future__ import annotations

import logging
from collections import defaultdict

from flask import request
from flask_babel import gettext as _

from app.pageir.registry import register_menu_provider

from ..models.site_map_node import DcSiteMapNode
from . import portal_auth_service, portal_access_service

logger = logging.getLogger(__name__)


def init_portal_pageir_menu() -> None:
    """Register portal Page IR menu provider."""
    register_menu_provider("portal", _build_portal_menu)


def _build_portal_menu(items: list[dict], ctx: dict) -> list[dict]:
    try:
        sub_system_sc = ctx.get("sub_system_sc")
        portal_user = ctx.get("portal_user")
        path_id = ctx.get("path_id")
        if not sub_system_sc or portal_user is None or not path_id:
            return []

        nodes = DcSiteMapNode.query.filter_by(
            sub_system_secure_code=sub_system_sc,
            is_deleted=False,
            is_active=True,
        ).all()

        selected = {
            item.get("node")
            for item in items
            if item.get("kind") == "node" and item.get("node")
        }
        node_by_sc = {node.secure_code: node for node in nodes}
        children_by_parent: dict[str | None, list] = defaultdict(list)
        for node in nodes:
            parent_sc = node.parent_secure_code if node.parent_secure_code in node_by_sc else None
            children_by_parent[parent_sc].append(node)
        for siblings in children_by_parent.values():
            siblings.sort(key=lambda node: (node.display_order or 0, node.name or ""))

        entries = [
            entry
            for node in children_by_parent.get(None, [])
            if (entry := _build_node_entry(
                node,
                children_by_parent,
                selected,
                sub_system_sc,
                portal_user,
                path_id,
            )) is not None
        ]
        entries.extend(_system_entries(items, sub_system_sc, portal_user, path_id))
        return entries
    except Exception:
        logger.exception("Page IR portal menu provider failed")
        return []


def _build_node_entry(
    node,
    children_by_parent: dict[str | None, list],
    selected: set[str],
    sub_system_sc: str,
    portal_user: dict,
    path_id: str,
) -> dict | None:
    children = [
        entry
        for child in children_by_parent.get(node.secure_code, [])
        if (entry := _build_node_entry(
            child,
            children_by_parent,
            selected,
            sub_system_sc,
            portal_user,
            path_id,
        )) is not None
    ]

    url = None
    if (
        node.secure_code in selected
        and node.node_type == "page"
        and node.page_layout_secure_code
    ):
        allowed, _reason = portal_access_service.check_page_access(
            sub_system_sc,
            node.page_layout_secure_code,
            portal_user,
        )
        if allowed:
            url = (
                f"{request.script_root}/public/portal/{path_id}/p/"
                f"{node.page_layout_secure_code}"
            )

    if not url and not children:
        return None
    return {
        "label": node.name or "",
        "url": url,
        "icon": node.icon or None,
        "children": children,
    }


def _system_entries(items: list[dict], sub_system_sc: str, portal_user: dict, path_id: str) -> list[dict]:
    entries = []
    user_id = portal_user.get("user_id")
    script_root = request.script_root
    for item in items:
        if item.get("kind") != "system":
            continue
        link = item.get("link")
        if link == "login" and user_id is None:
            entries.append(_system_entry(_("登入"), f"{script_root}/public/portal/{path_id}/login"))
        elif (
            link == "register"
            and user_id is None
            and portal_auth_service.is_registration_allowed(sub_system_sc)
        ):
            entries.append(_system_entry(_("註冊"), f"{script_root}/public/portal/{path_id}/register"))
        elif link == "logout" and user_id is not None:
            entries.append(_system_entry(_("登出"), f"{script_root}/public/portal/{path_id}/logout"))
    return entries


def _system_entry(label: str, url: str) -> dict:
    return {
        "label": label,
        "url": url,
        "icon": None,
        "children": [],
    }
