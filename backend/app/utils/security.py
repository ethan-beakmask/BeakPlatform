"""
BeakMask Security Utilities
安全相關工具函數
"""
import secrets
import string
import hashlib
import hmac
from typing import Optional


def generate_secure_code(length: int = 22) -> str:
    """
    生成 URL-safe 的安全識別碼。

    使用 secrets 模組生成密碼學安全的隨機 token。
    預設長度 22 字元，約 131 bits 的熵。

    Args:
        length: Token 長度 (預設 22)

    Returns:
        URL-safe token string
    """
    return secrets.token_urlsafe(length)[:length]


def generate_api_key() -> str:
    """
    生成 API Key。

    格式: bm_live_xxxx 或 bm_test_xxxx
    """
    return f"bm_live_{secrets.token_urlsafe(32)}"


def generate_reset_token() -> str:
    """
    生成密碼重設 token。

    有時效性，應與過期時間一起儲存。
    """
    return secrets.token_urlsafe(32)


def hash_token(token: str, salt: str = '') -> str:
    """
    Hash token for storage.

    不應儲存原始 token，應儲存 hash。

    Args:
        token: 原始 token
        salt: 可選的 salt

    Returns:
        Hashed token
    """
    return hashlib.sha256(f"{salt}{token}".encode()).hexdigest()


def verify_token_hash(token: str, hashed: str, salt: str = '') -> bool:
    """
    驗證 token hash。

    使用 hmac.compare_digest 防止 timing attack。
    """
    computed = hash_token(token, salt)
    return hmac.compare_digest(computed, hashed)


def sanitize_filename(filename: str) -> str:
    """
    清理檔案名稱，移除危險字元。

    Args:
        filename: 原始檔案名稱

    Returns:
        清理後的檔案名稱
    """
    # 允許的字元
    allowed = set(string.ascii_letters + string.digits + '._-')

    # 移除路徑分隔符和危險字元
    filename = filename.replace('/', '_').replace('\\', '_')
    filename = filename.replace('..', '_')

    # 只保留允許的字元
    cleaned = ''.join(c if c in allowed else '_' for c in filename)

    # 移除開頭的點（隱藏檔案）
    cleaned = cleaned.lstrip('.')

    # 限制長度
    if len(cleaned) > 255:
        name, ext = cleaned.rsplit('.', 1) if '.' in cleaned else (cleaned, '')
        if ext:
            cleaned = f"{name[:250]}.{ext[:4]}"
        else:
            cleaned = cleaned[:255]

    return cleaned or 'unnamed'


def mask_email(email: str) -> str:
    """
    遮蔽 email 地址用於顯示。

    例: user@example.com -> u***@e***.com
    """
    if '@' not in email:
        return '***'

    local, domain = email.rsplit('@', 1)
    domain_parts = domain.rsplit('.', 1)

    masked_local = local[0] + '***' if local else '***'
    masked_domain = domain_parts[0][0] + '***' if domain_parts[0] else '***'

    if len(domain_parts) > 1:
        return f"{masked_local}@{masked_domain}.{domain_parts[1]}"
    return f"{masked_local}@{masked_domain}"


def mask_ip(ip: str) -> str:
    """
    遮蔽 IP 地址用於日誌。

    例: 192.168.1.100 -> 192.168.x.x
    """
    parts = ip.split('.')
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.x.x"
    return ip  # IPv6 or invalid, return as-is
