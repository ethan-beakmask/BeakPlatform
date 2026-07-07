"""
Platform HMAC Verifier (Pure Functions)

平台級 API Key 簽章驗證(規格: docs/API_KEY_TRIGGER_SPEC.md §2):
    canonical_string = f"{timestamp}\n{body_raw}"
    signature = hex(HMAC-SHA256(secret, canonical_string))
    header X-BP-Signature: "sha256=" + signature

與 modules/open_defense/services/hmac_verifier.py 同規格(該模組為此實作的前身,
P2 遷移後由本檔為唯一實作)。純函式不依賴 Flask / DB,方便單元測試。
"""
import hmac
import hashlib
import time
from typing import Union


SIGNATURE_PREFIX = 'sha256='
TIMESTAMP_TOLERANCE_SEC = 300  # ±5 分鐘


def compute_signature(secret: bytes, timestamp: str, body: bytes) -> str:
    """
    計算簽章。

    Args:
        secret: 32-byte HMAC 共用密鑰
        timestamp: Unix 秒(字串,header 原值)
        body: 原始 request body bytes(不重序列化)

    Returns:
        "sha256=<hex>" 完整 header 值
    """
    canonical = timestamp.encode('ascii') + b'\n' + body
    digest = hmac.new(secret, canonical, hashlib.sha256).hexdigest()
    return SIGNATURE_PREFIX + digest


def verify_signature(secret: bytes, timestamp: str, body: bytes,
                     header_value: str) -> bool:
    """
    驗證簽章。使用 hmac.compare_digest 防 timing attack。
    任何錯誤(格式不符、計算不符)回 False。
    """
    if not header_value or not header_value.startswith(SIGNATURE_PREFIX):
        return False
    expected = compute_signature(secret, timestamp, body)
    return hmac.compare_digest(expected.encode('ascii'),
                               header_value.encode('ascii'))


def is_timestamp_valid(timestamp: str,
                       tolerance_sec: int = TIMESTAMP_TOLERANCE_SEC,
                       now: Union[int, float, None] = None) -> bool:
    """檢查 timestamp 是否在容忍範圍內(防 replay)。"""
    if not timestamp:
        return False
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    current = int(now if now is not None else time.time())
    return abs(current - ts) <= tolerance_sec
