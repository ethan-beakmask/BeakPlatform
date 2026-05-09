"""
OpenDefense Module - HMAC Verifier (Pure Functions)

簽章規格(對外契約 v1.0):
    canonical_string = f"{timestamp}\n{body_raw}"
    signature = hex(HMAC-SHA256(secret, canonical_string))
    header X-OD-Signature: "sha256=" + signature

純函式不依賴 Flask / DB,純粹 bytes/str 輸入輸出,方便單元測試。
"""
import hmac
import hashlib
import time
from typing import Union


SIGNATURE_PREFIX = 'sha256='
TIMESTAMP_TOLERANCE_SEC = 300  # 對外契約 §3.1 規定 5 分鐘內有效


def compute_signature(secret: bytes, timestamp: str, body: bytes) -> str:
    """
    計算 webhook 簽章。

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
    驗證 webhook 簽章。使用 hmac.compare_digest 防 timing attack。

    Args:
        secret: 32-byte HMAC 共用密鑰
        timestamp: header X-OD-Timestamp 值(字串)
        body: 原始 request body bytes
        header_value: header X-OD-Signature 值(完整 "sha256=<hex>")

    Returns:
        True 表示簽章一致;任何錯誤(格式不符、計算不符)回 False。
    """
    if not header_value or not header_value.startswith(SIGNATURE_PREFIX):
        return False
    expected = compute_signature(secret, timestamp, body)
    return hmac.compare_digest(expected.encode('ascii'),
                               header_value.encode('ascii'))


def is_timestamp_valid(timestamp: str,
                       tolerance_sec: int = TIMESTAMP_TOLERANCE_SEC,
                       now: Union[int, float, None] = None) -> bool:
    """
    檢查 timestamp 是否在容忍範圍內(防 replay)。

    Args:
        timestamp: header X-OD-Timestamp 值
        tolerance_sec: 容忍秒數,預設 300(5 分鐘)
        now: 可注入測試用,預設 time.time()

    Returns:
        True 表 timestamp 合法且在範圍內;否則 False。
    """
    if not timestamp:
        return False
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    current = int(now if now is not None else time.time())
    return abs(current - ts) <= tolerance_sec
