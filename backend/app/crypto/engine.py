"""
AES-256-GCM 加解密引擎

所有加密操作的底層實作。不處理金鑰管理，只負責加解密。
"""
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# AES-256 key size
KEY_SIZE = 32
# GCM nonce size (96 bits, NIST recommended)
NONCE_SIZE = 12


def generate_key() -> bytes:
    """產生隨機 AES-256 金鑰 (32 bytes)"""
    return os.urandom(KEY_SIZE)


def generate_nonce() -> bytes:
    """產生隨機 GCM nonce (12 bytes)"""
    return os.urandom(NONCE_SIZE)


def encrypt_data(key: bytes, plaintext: bytes) -> tuple[bytes, bytes]:
    """
    AES-256-GCM 加密

    Args:
        key: 32-byte AES key
        plaintext: 明文資料

    Returns:
        (ciphertext_with_tag, nonce)
        ciphertext_with_tag 包含 GCM auth tag (最後 16 bytes)
    """
    if len(key) != KEY_SIZE:
        raise ValueError(f'金鑰長度必須為 {KEY_SIZE} bytes')

    nonce = generate_nonce()
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return ciphertext, nonce


def decrypt_data(key: bytes, ciphertext: bytes, nonce: bytes) -> bytes:
    """
    AES-256-GCM 解密

    Args:
        key: 32-byte AES key
        ciphertext: 密文 (含 GCM auth tag)
        nonce: 加密時使用的 nonce

    Returns:
        明文資料

    Raises:
        cryptography.exceptions.InvalidTag: 密文被竄改或金鑰錯誤
    """
    if len(key) != KEY_SIZE:
        raise ValueError(f'金鑰長度必須為 {KEY_SIZE} bytes')

    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)


def wrap_key(wrapping_key: bytes, key_to_wrap: bytes) -> tuple[bytes, bytes]:
    """
    用一把金鑰包裝另一把金鑰 (AES-256-GCM key wrapping)

    Returns:
        (wrapped_key_with_tag, nonce)
    """
    return encrypt_data(wrapping_key, key_to_wrap)


def unwrap_key(wrapping_key: bytes, wrapped_key: bytes, nonce: bytes) -> bytes:
    """
    解包金鑰

    Returns:
        原始金鑰 bytes
    """
    return decrypt_data(wrapping_key, wrapped_key, nonce)
