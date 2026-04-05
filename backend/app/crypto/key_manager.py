"""
金鑰管理器

負責 Master Key 載入、Org Key 生命週期、檔案加解密的完整流程。
"""
import base64
import logging
import os
from typing import Optional

from . import engine

logger = logging.getLogger(__name__)

# Master Key 快取 (process 生命週期)
_master_key: Optional[bytes] = None


def _get_master_key() -> bytes:
    """
    從環境變數載入 Master Key。

    ENCRYPTION_MASTER_KEY 格式: base64url 編碼的 32-byte key
    產生方式: python3 -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
    """
    global _master_key
    if _master_key is not None:
        return _master_key

    key_b64 = os.getenv('ENCRYPTION_MASTER_KEY')
    if not key_b64:
        raise RuntimeError(
            '未設定 ENCRYPTION_MASTER_KEY 環境變數。'
            '請執行: python3 -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())" '
            '產生金鑰並加入 .env'
        )

    try:
        key = base64.urlsafe_b64decode(key_b64)
    except Exception:
        raise RuntimeError('ENCRYPTION_MASTER_KEY 格式錯誤，必須為 base64url 編碼')

    if len(key) != engine.KEY_SIZE:
        raise RuntimeError(
            f'ENCRYPTION_MASTER_KEY 長度錯誤: {len(key)} bytes，需要 {engine.KEY_SIZE} bytes'
        )

    _master_key = key
    return _master_key


class KeyManager:
    """
    金鑰管理器

    兩層架構:
    - Master Key (env) → 包裝 Org Key
    - Org Key (DB) → 包裝 File DEK
    - File DEK (per-file random) → 加密檔案
    """

    @staticmethod
    def get_or_create_org_key(org_sc: str) -> tuple:
        """
        取得企業的 Org Key，不存在則建立。

        Returns:
            (org_key_bytes, org_key_record)
        """
        from ..models.org_encryption_key import OrgEncryptionKey
        from .. import db

        master_key = _get_master_key()

        # 找現有的 active key
        record = OrgEncryptionKey.query.filter_by(
            org_secure_code=org_sc,
            is_active=True,
            is_deleted=False,
        ).first()

        if record:
            # 解包 Org Key
            wrapped = base64.urlsafe_b64decode(record.wrapped_key)
            nonce = base64.urlsafe_b64decode(record.key_nonce)
            org_key = engine.unwrap_key(master_key, wrapped, nonce)
            return org_key, record

        # 建立新的 Org Key
        org_key = engine.generate_key()
        wrapped, nonce = engine.wrap_key(master_key, org_key)

        from ..utils.security import generate_secure_code
        record = OrgEncryptionKey(
            secure_code=generate_secure_code(),
            org_secure_code=org_sc,
            wrapped_key=base64.urlsafe_b64encode(wrapped).decode(),
            key_nonce=base64.urlsafe_b64encode(nonce).decode(),
            algorithm='AES-256-GCM',
            is_active=True,
        )
        db.session.add(record)
        db.session.flush()

        logger.info("為企業 %s 建立加密金鑰", org_sc)
        return org_key, record

    @staticmethod
    def encrypt_file(org_sc: str, plaintext: bytes) -> dict:
        """
        加密檔案完整流程。

        Args:
            org_sc: 企業 secure_code
            plaintext: 檔案明文

        Returns:
            {
                'ciphertext': bytes,        # 密文 (含 GCM tag)
                'file_nonce': bytes,         # 檔案加密 nonce
                'wrapped_dek': str,          # base64 包裝後的 DEK
                'dek_nonce': str,            # base64 DEK 包裝 nonce
                'encryption_key_sc': str,    # Org Key 的 secure_code
            }
        """
        org_key, key_record = KeyManager.get_or_create_org_key(org_sc)

        # 產生隨機 DEK
        dek = engine.generate_key()

        # 用 DEK 加密檔案
        ciphertext, file_nonce = engine.encrypt_data(dek, plaintext)

        # 用 Org Key 包裝 DEK
        wrapped_dek, dek_nonce = engine.wrap_key(org_key, dek)

        return {
            'ciphertext': ciphertext,
            'file_nonce': file_nonce,
            'wrapped_dek': base64.urlsafe_b64encode(wrapped_dek).decode(),
            'dek_nonce': base64.urlsafe_b64encode(dek_nonce).decode(),
            'encryption_key_sc': key_record.secure_code,
        }

    @staticmethod
    def decrypt_file(org_sc: str, ciphertext: bytes,
                     file_nonce: bytes, wrapped_dek_b64: str,
                     dek_nonce_b64: str, encryption_key_sc: str) -> bytes:
        """
        解密檔案完整流程。

        Args:
            org_sc: 企業 secure_code
            ciphertext: 密文 (含 GCM tag)
            file_nonce: 檔案加密 nonce
            wrapped_dek_b64: base64 包裝後的 DEK
            dek_nonce_b64: base64 DEK 包裝 nonce
            encryption_key_sc: 使用的 Org Key secure_code

        Returns:
            明文 bytes
        """
        from ..models.org_encryption_key import OrgEncryptionKey

        master_key = _get_master_key()

        # 取得 Org Key
        key_record = OrgEncryptionKey.query.filter_by(
            secure_code=encryption_key_sc,
            org_secure_code=org_sc,
            is_deleted=False,
        ).first()

        if not key_record:
            raise RuntimeError(f'找不到加密金鑰: {encryption_key_sc}')

        # 解包 Org Key
        wrapped_org = base64.urlsafe_b64decode(key_record.wrapped_key)
        org_nonce = base64.urlsafe_b64decode(key_record.key_nonce)
        org_key = engine.unwrap_key(master_key, wrapped_org, org_nonce)

        # 解包 DEK
        wrapped_dek = base64.urlsafe_b64decode(wrapped_dek_b64)
        dek_nonce = base64.urlsafe_b64decode(dek_nonce_b64)
        dek = engine.unwrap_key(org_key, wrapped_dek, dek_nonce)

        # 解密檔案
        return engine.decrypt_data(dek, ciphertext, file_nonce)
