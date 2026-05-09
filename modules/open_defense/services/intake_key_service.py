"""
OpenDefense Module - Intake Key Service

封裝 OdIntakeKey 的:
  - 建立(產生 32-byte secret -> 用 Org Key 加密 -> 寫 DB,只回傳一次性明文)
  - 反查(by key_id -> 解密 -> 還原 secret bytes)
  - 撤銷
"""
import logging
import secrets
from datetime import datetime
from typing import Optional, List, Tuple

from app import db
from app.crypto.key_manager import KeyManager
from app.utils.security import generate_secure_code

from ..models import OdIntakeKey

logger = logging.getLogger(__name__)

KEY_ID_PREFIX = 'ik_'
SECRET_BYTES = 32


class IntakeKeyError(Exception):
    """Intake Key 相關錯誤"""


def generate_key_id() -> str:
    """產生對外公開的 key_id,如 'ik_a3f9c2e1...'(8 hex chars)"""
    return KEY_ID_PREFIX + secrets.token_hex(8)


def create_intake_key(
    *,
    org_secure_code: str,
    name: str,
    allowed_source_systems: List[str],
    created_by_secure_code: Optional[str] = None,
    expires_at: Optional[datetime] = None,
) -> Tuple[OdIntakeKey, str]:
    """
    建立一筆 intake key。

    Returns:
        (record, plaintext_secret_b64)  -- plaintext 只在建立時顯示一次,後續無法還原
    """
    if not org_secure_code:
        raise IntakeKeyError('org_secure_code 必填')
    if not name or not name.strip():
        raise IntakeKeyError('name 必填')
    if not isinstance(allowed_source_systems, list) or not allowed_source_systems:
        raise IntakeKeyError('allowed_source_systems 必須為非空 list')

    secret = secrets.token_bytes(SECRET_BYTES)
    encrypted = KeyManager.encrypt_file(org_secure_code, secret)

    record = OdIntakeKey(
        secure_code=generate_secure_code(),
        org_secure_code=org_secure_code,
        key_id=generate_key_id(),
        name=name.strip(),
        hmac_secret_ciphertext=encrypted['ciphertext'],
        hmac_secret_file_nonce=encrypted['file_nonce'],
        hmac_secret_wrapped_dek=encrypted['wrapped_dek'],
        hmac_secret_dek_nonce=encrypted['dek_nonce'],
        hmac_secret_encryption_key_sc=encrypted['encryption_key_sc'],
        allowed_source_systems=allowed_source_systems,
        is_active=True,
        expires_at=expires_at,
        created_by_secure_code=created_by_secure_code,
    )
    db.session.add(record)
    db.session.commit()

    import base64
    plaintext_b64 = base64.urlsafe_b64encode(secret).decode('ascii')

    logger.info(
        'OpenDefense intake_key created sc=%s key_id=%s org=%s',
        record.secure_code, record.key_id, org_secure_code,
    )
    return record, plaintext_b64


def lookup_active_key(key_id: str) -> Optional[OdIntakeKey]:
    """
    依 key_id 查詢 active 且未過期的 intake key。
    回傳 ORM 物件;查無回 None。
    """
    if not key_id:
        return None
    record = OdIntakeKey.query.filter_by(
        key_id=key_id,
        is_active=True,
        is_deleted=False,
    ).first()
    if record is None:
        return None
    if record.expires_at is not None and record.expires_at < datetime.utcnow():
        return None
    return record


def decrypt_secret(record: OdIntakeKey) -> bytes:
    """
    將 OdIntakeKey 中的密文解密還原為 32-byte HMAC secret。
    解密失敗會拋例外(代表金鑰系統異常,屬不可預期錯誤)。
    """
    return KeyManager.decrypt_file(
        org_sc=record.org_secure_code,
        ciphertext=bytes(record.hmac_secret_ciphertext),
        file_nonce=bytes(record.hmac_secret_file_nonce),
        wrapped_dek_b64=record.hmac_secret_wrapped_dek,
        dek_nonce_b64=record.hmac_secret_dek_nonce,
        encryption_key_sc=record.hmac_secret_encryption_key_sc,
    )


def touch_last_used(record: OdIntakeKey) -> None:
    """更新 last_used_at(成功驗章後呼叫)"""
    record.last_used_at = datetime.utcnow()
    db.session.commit()


def revoke_key(record: OdIntakeKey) -> None:
    """撤銷 key:標記 is_active=False,軟刪除"""
    record.is_active = False
    record.is_deleted = True
    record.deleted_at = datetime.utcnow()
    db.session.commit()
    logger.info('OpenDefense intake_key revoked sc=%s key_id=%s',
                record.secure_code, record.key_id)
