"""
OpenDefense Module - od-bridge Client

唯讀查詢 防禦節點 的 od-bridge，供防禦決策頁做「平台 DB / EDL / kernel nft」
三方對帳。od-bridge 的 EDL 與 nftables 狀態沒有 org 概念（TENANT-01），
呼叫端必須先用平台 DB 的 org_secure_code 篩出本企業決策，再只針對那些 target
比對落地狀態；只有系統管理員可看 downstream orphan。

連線失敗（容器停機、逾時、未設定或回應格式異常）一律回 None，呼叫端據此顯示
「只剩平台端記錄」而不是讓整頁 500。決策頁是同步請求，逾時要短，避免卡住 UI。
"""
import logging
import os
from typing import Dict, List, Optional

import requests
from flask import current_app

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5
# 未設定 OD_BRIDGE_URL 時視為 od-bridge 不可用（回 None），不猜測位址
DEFAULT_BRIDGE_URL = ''


def _base_url() -> str:
    return (
        current_app.config.get('OD_BRIDGE_URL')
        or os.getenv('OD_BRIDGE_URL')
        or DEFAULT_BRIDGE_URL
    ).rstrip('/')


def base_url() -> str:
    """回傳目前設定的 od-bridge base URL，供狀態 API 顯示。"""
    return _base_url()


def _get_text(path: str, base_url_override: Optional[str] = None) -> Optional[str]:
    base = (base_url_override or _base_url()).rstrip('/')
    if not base:
        return None
    try:
        resp = requests.get(
            f'{base}{path}',
            timeout=TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning('od-bridge 查詢失敗，對帳資料不可用: %s', exc)
        return None
    return resp.text


def _get_json(path: str, base_url_override: Optional[str] = None) -> Optional[Dict]:
    base = (base_url_override or _base_url()).rstrip('/')
    if not base:
        return None
    try:
        resp = requests.get(
            f'{base}{path}',
            timeout=TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as exc:
        logger.warning('od-bridge 查詢失敗，對帳資料不可用: %s', exc)
        return None
    except ValueError:
        logger.warning('od-bridge 回應非 JSON，對帳資料不可用')
        return None
    if not isinstance(payload, dict):
        logger.warning('od-bridge JSON 格式非物件，對帳資料不可用')
        return None
    return payload


def _parse_edl(text: Optional[str]) -> Optional[List[str]]:
    if text is None:
        return None
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith('#')
    ]


def get_edl_block(base_url_override: Optional[str] = None) -> Optional[List[str]]:
    """回傳 `/edl` 目前內容；不可用時回 None，空清單回 []。"""
    return _parse_edl(_get_text('/edl', base_url_override))


def get_edl_allow(base_url_override: Optional[str] = None) -> Optional[List[str]]:
    """回傳 `/edl/allow` 目前內容；不可用時回 None，空清單回 []。"""
    return _parse_edl(_get_text('/edl/allow', base_url_override))


def get_nft_state(base_url_override: Optional[str] = None) -> Optional[Dict]:
    """回傳 od-bridge `/state/nft` JSON；不可用時回 None。"""
    return _get_json('/state/nft', base_url_override)
