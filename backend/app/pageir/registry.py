"""Page IR 執行期資源與動作註冊表。"""
from __future__ import annotations

from collections.abc import Callable
from copy import copy
from typing import Any


_RESOURCES: dict[str, dict[str, Any]] = {}
_ACTIONS: dict[str, dict[str, Any]] = {}


def register_resource(code: str, config: dict) -> None:
    """註冊 Page IR 可解析資源；同 code 後註冊者覆蓋前者。"""
    _RESOURCES[code] = copy(config)


def get_resource(code: str) -> dict | None:
    """取得已註冊資源設定；未註冊回 None。"""
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


def register_action(ref: str, config: dict) -> None:
    """註冊 Page IR 動作端點；同 ref 後註冊者覆蓋前者。"""
    _ACTIONS[ref] = copy(config)


def get_action(ref: str) -> dict | None:
    """取得已註冊動作設定；未註冊回 None。"""
    config = _ACTIONS.get(ref)
    return copy(config) if config is not None else None


def list_actions() -> list[str]:
    """列出 Page IR 可設計動作 ref；不暴露動作 callable。"""
    return sorted(
        ref for ref, config in _ACTIONS.items()
        if not isinstance(config, Callable)
    )
