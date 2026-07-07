"""
Platform API Key Service

封裝平台級 ApiKey 的:
  - 建立(產生 32-byte secret -> Org Key 加密 -> 寫 DB,只回傳一次性明文)
  - 反查(by key_id -> active 且未過期 -> 解密還原 secret bytes)
  - 暫停 / 復原 / 撤銷 / 更新
  - allowed_ips 檢查(含 CIDR)

規格: docs/API_KEY_TRIGGER_SPEC.md
"""
import base64
import ipaddress
import logging
import secrets
from datetime import datetime
from typing import List, Optional, Tuple

from app import db
from app.crypto.key_manager import KeyManager
from app.models.api_key import (
    ApiKey, STATUS_ACTIVE, STATUS_SUSPENDED, STATUS_REVOKED,
)
from app.utils.security import generate_secure_code

logger = logging.getLogger(__name__)

KEY_ID_PREFIX = 'ak_'
SECRET_BYTES = 32


class ApiKeyError(Exception):
    """API Key 相關錯誤"""


def generate_key_id() -> str:
    """產生對外公開的 key_id,如 'ak_a3f9c2e1...'(8 hex chars)"""
    return KEY_ID_PREFIX + secrets.token_hex(8)


def _validate_allowed_ips(allowed_ips) -> Optional[List[str]]:
    """驗證 IP 白名單格式,回傳正規化清單;None/空 list 視為不鎖"""
    if not allowed_ips:
        return None
    if not isinstance(allowed_ips, list):
        raise ApiKeyError('allowed_ips 必須為 list')
    normalized = []
    for entry in allowed_ips:
        entry = str(entry).strip()
        if not entry:
            continue
        try:
            if '/' in entry:
                ipaddress.ip_network(entry, strict=False)
            else:
                ipaddress.ip_address(entry)
        except ValueError:
            raise ApiKeyError(f'IP 或 CIDR 格式錯誤: {entry}')
        normalized.append(entry)
    return normalized or None


def create_api_key(
    *,
    org_secure_code: str,
    name: str,
    consumer_label: Optional[str] = None,
    description: Optional[str] = None,
    scopes: Optional[dict] = None,
    allowed_ips: Optional[List[str]] = None,
    applicant_user_secure_code: Optional[str] = None,
    expires_at: Optional[datetime] = None,
    created_by_secure_code: Optional[str] = None,
) -> Tuple[ApiKey, str]:
    """
    建立一筆 API Key。

    Returns:
        (record, plaintext_secret_b64)  -- plaintext 只在建立時顯示一次,後續無法還原
    """
    if not org_secure_code:
        raise ApiKeyError('org_secure_code 必填')
    if not name or not name.strip():
        raise ApiKeyError('name 必填')
    if scopes is not None and not isinstance(scopes, dict):
        raise ApiKeyError('scopes 必須為 dict')

    secret = secrets.token_bytes(SECRET_BYTES)
    encrypted = KeyManager.encrypt_file(org_secure_code, secret)

    record = ApiKey(
        secure_code=generate_secure_code(),
        org_secure_code=org_secure_code,
        key_id=generate_key_id(),
        name=name.strip(),
        consumer_label=(consumer_label or '').strip() or None,
        description=(description or '').strip() or None,
        secret_ciphertext=encrypted['ciphertext'],
        secret_file_nonce=encrypted['file_nonce'],
        secret_wrapped_dek=encrypted['wrapped_dek'],
        secret_dek_nonce=encrypted['dek_nonce'],
        secret_encryption_key_sc=encrypted['encryption_key_sc'],
        status=STATUS_ACTIVE,
        allowed_ips=_validate_allowed_ips(allowed_ips),
        scopes=scopes or {},
        applicant_user_secure_code=applicant_user_secure_code or None,
        expires_at=expires_at,
        created_by_secure_code=created_by_secure_code,
    )
    db.session.add(record)
    db.session.commit()

    plaintext_b64 = base64.urlsafe_b64encode(secret).decode('ascii')

    logger.info('api_key created sc=%s key_id=%s org=%s by=%s',
                record.secure_code, record.key_id, org_secure_code,
                created_by_secure_code)
    return record, plaintext_b64


def lookup_active_key(key_id: str) -> Optional[ApiKey]:
    """
    依 key_id 查詢 active 且未過期的 API Key。
    suspended / revoked / 過期 / 軟刪除 一律回 None。
    """
    if not key_id:
        return None
    record = ApiKey.query.filter_by(
        key_id=key_id,
        status=STATUS_ACTIVE,
        is_deleted=False,
    ).first()
    if record is None:
        return None
    if record.expires_at is not None and record.expires_at < datetime.utcnow():
        return None
    return record


def decrypt_secret(record: ApiKey) -> bytes:
    """
    將 ApiKey 中的密文解密還原為 32-byte HMAC secret。
    解密失敗會拋例外(代表金鑰系統異常,屬不可預期錯誤)。
    """
    return KeyManager.decrypt_file(
        org_sc=record.org_secure_code,
        ciphertext=bytes(record.secret_ciphertext),
        file_nonce=bytes(record.secret_file_nonce),
        wrapped_dek_b64=record.secret_wrapped_dek,
        dek_nonce_b64=record.secret_dek_nonce,
        encryption_key_sc=record.secret_encryption_key_sc,
    )


def check_source_ip(record: ApiKey, source_ip: str) -> bool:
    """
    檢查來源 IP 是否符合 key 的白名單。
    allowed_ips 為 NULL/空 = 不鎖,一律通過。
    """
    allowed = record.allowed_ips
    if not allowed:
        return True
    if not source_ip:
        return False
    try:
        addr = ipaddress.ip_address(source_ip)
    except ValueError:
        return False
    for entry in allowed:
        try:
            if '/' in entry:
                if addr in ipaddress.ip_network(entry, strict=False):
                    return True
            elif addr == ipaddress.ip_address(entry):
                return True
        except ValueError:
            continue
    return False


def touch_last_used(record: ApiKey) -> None:
    """更新 last_used_at(成功驗章後呼叫)"""
    record.last_used_at = datetime.utcnow()
    db.session.commit()


def suspend_key(record: ApiKey, reason: str,
                operator_secure_code: Optional[str] = None) -> None:
    """暫停 key(可復原)。SaaS 場景以暫停 key 取代封鎖 IP。"""
    if record.status == STATUS_REVOKED:
        raise ApiKeyError('已撤銷的 key 不可暫停')
    record.status = STATUS_SUSPENDED
    record.suspended_reason = (reason or '').strip() or None
    record.suspended_at = datetime.utcnow()
    db.session.commit()
    logger.warning('api_key suspended sc=%s key_id=%s reason=%s by=%s',
                   record.secure_code, record.key_id, reason,
                   operator_secure_code)


def resume_key(record: ApiKey,
               operator_secure_code: Optional[str] = None) -> None:
    """復原被暫停的 key"""
    if record.status != STATUS_SUSPENDED:
        raise ApiKeyError('僅暫停中的 key 可復原')
    record.status = STATUS_ACTIVE
    record.suspended_reason = None
    record.suspended_at = None
    db.session.commit()
    logger.info('api_key resumed sc=%s key_id=%s by=%s',
                record.secure_code, record.key_id, operator_secure_code)


def revoke_key(record: ApiKey,
               operator_secure_code: Optional[str] = None) -> None:
    """撤銷 key(不可復原):status=revoked + 軟刪除"""
    record.status = STATUS_REVOKED
    record.is_deleted = True
    record.deleted_at = datetime.utcnow()
    db.session.commit()
    logger.warning('api_key revoked sc=%s key_id=%s by=%s',
                   record.secure_code, record.key_id, operator_secure_code)


def update_key(
    record: ApiKey,
    *,
    name: Optional[str] = None,
    consumer_label: Optional[str] = None,
    description: Optional[str] = None,
    scopes: Optional[dict] = None,
    allowed_ips: Optional[List[str]] = ...,
    applicant_user_secure_code: Optional[str] = ...,
    expires_at: Optional[datetime] = ...,
) -> ApiKey:
    """更新 key 屬性(secret 不可改)。Ellipsis 表示不變更該欄位。"""
    if record.status == STATUS_REVOKED:
        raise ApiKeyError('已撤銷的 key 不可編輯')
    if name is not None:
        if not name.strip():
            raise ApiKeyError('name 不可為空')
        record.name = name.strip()
    if consumer_label is not None:
        record.consumer_label = consumer_label.strip() or None
    if description is not None:
        record.description = description.strip() or None
    if scopes is not None:
        if not isinstance(scopes, dict):
            raise ApiKeyError('scopes 必須為 dict')
        record.scopes = scopes
    if allowed_ips is not ...:
        record.allowed_ips = _validate_allowed_ips(allowed_ips)
    if applicant_user_secure_code is not ...:
        record.applicant_user_secure_code = applicant_user_secure_code or None
    if expires_at is not ...:
        record.expires_at = expires_at
    db.session.commit()
    return record


def list_keys(org_secure_code: str) -> List[ApiKey]:
    """列出企業的所有 key(含 suspended,不含已撤銷/刪除)"""
    return ApiKey.query.filter_by(
        org_secure_code=org_secure_code,
        is_deleted=False,
    ).order_by(ApiKey.created_at.desc()).all()


def get_key_by_sc(secure_code: str, org_secure_code: str) -> Optional[ApiKey]:
    """依 secure_code 取 key(強制租戶隔離)"""
    if not secure_code or not org_secure_code:
        return None
    return ApiKey.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org_secure_code,
        is_deleted=False,
    ).first()
