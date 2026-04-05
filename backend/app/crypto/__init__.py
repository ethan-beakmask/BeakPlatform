"""
BeakPlatform 內建檔案加密模組

兩層金鑰架構：
- Master Key: 從環境變數載入，用於加密 Org Key
- Org Key: 每個企業一把，用於加密 File DEK
- File DEK: 每個檔案一把隨機金鑰，用於加密檔案內容

演算法: AES-256-GCM (authenticated encryption)
"""
from .engine import encrypt_data, decrypt_data, generate_key
from .key_manager import KeyManager

__all__ = ['encrypt_data', 'decrypt_data', 'generate_key', 'KeyManager']
