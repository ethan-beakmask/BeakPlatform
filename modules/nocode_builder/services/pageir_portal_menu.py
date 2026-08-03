"""Page IR NoCode portal menu provider."""
from __future__ import annotations

import logging
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flask import request
from flask_babel import gettext as _

from app.pageir.registry import register_menu_provider

from ..models.site_map_node import DcSiteMapNode
from . import portal_auth_service, portal_access_service

logger = logging.getLogger(__name__)
_MENU_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


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

        node_by_sc = {node.secure_code: node for node in nodes}
        entries = [
            entry
            for item in items or []
            if (entry := _build_item_entry(item, node_by_sc, sub_system_sc, portal_user, path_id, ctx)) is not None
        ]
        return entries
    except Exception:
        logger.exception("Page IR portal menu provider failed")
        return []


def _build_item_entry(
    item: dict,
    node_by_sc: dict[str, object],
    sub_system_sc: str,
    portal_user: dict,
    path_id: str,
    ctx: dict,
) -> dict | None:
    kind = item.get("kind")
    if kind == "system":
        return _system_entry_for_item(item, sub_system_sc, portal_user, path_id)
    if kind != "node":
        return None

    node = node_by_sc.get(item.get("node"))
    if node is None:
        return None

    children = [
        entry
        for child in item.get("children") or []
        if (entry := _build_item_entry(
            child,
            node_by_sc,
            sub_system_sc,
            portal_user,
            path_id,
            ctx,
        )) is not None
    ]

    url = None
    if (
        node.node_type == "page"
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
            if ctx.get("menu_nav_source") == "self":
                url = _url_with_nav(
                    url,
                    ctx.get("menu_nav_key"),
                    node.secure_code,
                    ctx.get("menu_nav_keys"),
                )

    if not url and not children:
        return None
    return {
        "label": node.name or "",
        "url": url,
        "icon": node.icon or None,
        "node": node.secure_code,
        "children": children,
    }


def _system_entry_for_item(item: dict, sub_system_sc: str, portal_user: dict, path_id: str) -> dict | None:
    user_id = portal_user.get("user_id")
    script_root = request.script_root
    link = item.get("link")
    if link == "login" and user_id is None:
        return _system_entry(_("登入"), f"{script_root}/public/portal/{path_id}/login")
    if (
        link == "register"
        and user_id is None
        and portal_auth_service.is_registration_allowed(sub_system_sc)
    ):
        return _system_entry(_("註冊"), f"{script_root}/public/portal/{path_id}/register")
    if link == "logout" and user_id is not None:
        return _system_entry(_("登出"), f"{script_root}/public/portal/{path_id}/logout")
    return None


def _system_entry(label: str, url: str) -> dict:
    return {
        "label": label,
        "url": url,
        "icon": None,
        "node": None,
        "children": [],
    }


def _url_with_nav(url: str, nav_key: str | None, node_sc: str, nav_keys=None) -> str:
    if not _valid_menu_token(nav_key) or not _valid_menu_token(node_sc):
        return url
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    # 只沿用本頁其他 menu 的 nav 參數（讓多組聯動的選擇並存）。
    # 不可整包複製 request.args——表格的分頁／排序參數會被帶到別頁，
    # 撞上目標頁同 id 的 widget。
    for key in nav_keys or []:
        if key != nav_key and _valid_menu_token(key) and _valid_menu_token(request.args.get(key)):
            query[key] = request.args.get(key)
    query[nav_key] = node_sc
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _valid_menu_token(value) -> bool:
    return isinstance(value, str) and bool(_MENU_TOKEN_RE.fullmatch(value))
