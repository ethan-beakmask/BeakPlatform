"""Page IR 執行期資源與動作註冊表。"""
from __future__ import annotations

import logging
from collections.abc import Callable
from copy import copy
from typing import Any


logger = logging.getLogger(__name__)

_RESOURCES: dict[str, dict[str, Any]] = {}
_ACTIONS: dict[str, dict[str, Any]] = {}
_PORTAL_ACTIONS: dict[str, dict[str, Any]] = {}
_PROVIDERS: dict[str, Callable[[str, dict], dict | None]] = {}
_RESOURCE_LISTERS: list[Callable[[str], list[dict]]] = []
_ACCESS_EVALUATORS: dict[str, Callable[[dict, str, dict], bool]] = {}
_MENU_PROVIDERS: dict[str, Callable[[list[dict], dict], list[dict]]] = {}
_SHARED_COMPONENT_RESOLVERS: dict[str, Callable[[str, dict], dict | None]] = {}


def register_resource(code: str, config: dict) -> None:
    """註冊 Page IR 可解析資源；同 code 後註冊者覆蓋前者。"""
    _RESOURCES[code] = copy(config)


def register_resource_provider(prefix: str, provider: Callable[[str, dict], dict | None]) -> None:
    """註冊 prefix 型 Page IR 資源 provider；同 prefix 後註冊者覆蓋前者。"""
    _PROVIDERS[prefix] = provider


def get_resource(code: str) -> dict | None:
    """取得已註冊資源設定；依 render context fail-closed 解析。"""
    from app.pageir.context import get_render_context

    ctx = get_render_context()
    world = ctx.get("world", "platform")
    if ":" in code:
        prefix = code.split(":", 1)[0]
        if world != "portal":
            return None
        provider = _PROVIDERS.get(prefix)
        if provider is None:
            return None
        config = provider(code, ctx)
        return copy(config) if config is not None else None

    if world == "portal":
        return None
    config = _RESOURCES.get(code)
    return copy(config) if config is not None else None


def list_resources() -> list[dict]:
    """列出 Page IR 可設計資源；不暴露 resolver callable。"""
    resources = []
    for code, config in sorted(_RESOURCES.items()):
        resources.append({
            "code": code,
            "views": list(config.get("views", [])),
            "fields": list(config.get("fields", [])),
            "egress_resource": config.get("egress_resource"),
        })
    return resources


def register_resource_lister(fn: Callable[[str], list[dict]]) -> None:
    """註冊 prefix 型資源 meta lister。"""
    if fn not in _RESOURCE_LISTERS:
        _RESOURCE_LISTERS.append(fn)


def list_prefixed_resources(sub_system_sc: str) -> list[dict]:
    """列出指定子系統可設計的 prefix 型 Page IR 資源。"""
    resources: list[dict] = []
    for lister in list(_RESOURCE_LISTERS):
        try:
            resources.extend(lister(sub_system_sc) or [])
        except Exception:
            logger.exception("Page IR prefixed resource lister failed")
    return resources


def register_access_evaluator(world: str, fn: Callable[[dict, str, dict], bool]) -> None:
    """註冊指定 render world 的 Page IR access_matrix 評估器。"""
    _ACCESS_EVALUATORS[world] = fn


def get_access_evaluator(world: str) -> Callable[[dict, str, dict], bool] | None:
    """取得指定 render world 的 access_matrix 評估器；未註冊回 None。"""
    return _ACCESS_EVALUATORS.get(world)


def register_menu_provider(world: str, fn: Callable[[list[dict], dict], list[dict]]) -> None:
    """註冊指定 render world 的 Page IR menu 樹提供者；同 world 後註冊者覆蓋前者。"""
    _MENU_PROVIDERS[world] = fn


def get_menu_provider(world: str) -> Callable[[list[dict], dict], list[dict]] | None:
    """取得指定 render world 的 menu provider；未註冊回 None。"""
    return _MENU_PROVIDERS.get(world)


def register_shared_component_resolver(world: str, fn: Callable[[str, dict], dict | None]) -> None:
    """註冊指定 render world 的共用元件 resolver；同 world 後註冊者覆蓋前者。"""
    _SHARED_COMPONENT_RESOLVERS[world] = fn


def get_shared_component_resolver(world: str) -> Callable[[str, dict], dict | None] | None:
    """取得指定 render world 的共用元件 resolver；未註冊回 None。"""
    return _SHARED_COMPONENT_RESOLVERS.get(world)


def register_action(ref: str, config: dict) -> None:
    """註冊 Page IR 動作端點；同 ref 後註冊者覆蓋前者。"""
    _ACTIONS[ref] = copy(config)


def get_action(ref: str) -> dict | None:
    """取得已註冊動作設定；未註冊回 None。"""
    from app.pageir.context import get_render_context

    if get_render_context().get("world") == "portal":
        return None
    config = _ACTIONS.get(ref)
    return copy(config) if config is not None else None


def list_actions() -> list[str]:
    """列出 Page IR 可設計動作 ref；不暴露動作 callable。"""
    return sorted(
        ref for ref, config in _ACTIONS.items()
        if not isinstance(config, Callable)
    )


def register_portal_action(ref: str, config: dict) -> None:
    """註冊 portal 世界的 Page IR 動作；同 ref 後註冊者覆蓋前者。"""
    _PORTAL_ACTIONS[ref] = copy(config)


def get_portal_action(ref: str) -> dict | None:
    """取得 portal 動作設定；非 portal 語境或未註冊一律回 None。"""
    from app.pageir.context import get_render_context

    if get_render_context().get("world") != "portal":
        return None
    config = _PORTAL_ACTIONS.get(ref)
    return copy(config) if config is not None else None


def list_portal_actions() -> list[str]:
    """列出 portal 可設計動作 ref。"""
    return sorted(_PORTAL_ACTIONS)
