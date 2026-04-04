"""
BeakSeal Vault Service
封裝 VaultClient 供 BeakPlatform 各模組使用
"""
import logging
import os
from typing import Optional

from ..utils.vault_client import VaultClient, VaultError

logger = logging.getLogger(__name__)

# Singleton client instance
_client: Optional[VaultClient] = None


def get_client() -> VaultClient:
    """Get or create the VaultClient singleton."""
    global _client
    if _client is None:
        socket_path = os.getenv('BEAKSEAL_SOCKET',
                                '/opt/BeakSeal/beakseal.sock')
        _client = VaultClient(socket_path=socket_path)
    return _client


class VaultService:
    """
    Vault 服務層 - 供 BeakPlatform API handlers 使用。

    自動以組織 org_code 作為 BeakSeal 的 org_id，
    以使用者 secure_code 作為 user_id。
    """

    @staticmethod
    def is_available() -> bool:
        """Check if BeakSeal service is reachable and unsealed."""
        try:
            status = get_client().get_status()
            return not status.get('sealed', True)
        except Exception:
            return False

    @staticmethod
    def get_status() -> dict:
        """Get vault status."""
        return get_client().get_status()

    @staticmethod
    def ensure_org_registered(org_code: str) -> None:
        """Ensure an organization is registered in BeakSeal."""
        client = get_client()
        try:
            client.get_current_key(org_code)
        except VaultError:
            try:
                client.register_org(org_code)
                logger.info("組織 %s 已在 BeakSeal 註冊", org_code)
            except VaultError as e:
                if '已存在' not in str(e):
                    raise

    @staticmethod
    def encrypt_file(org_code: str, user_code: str,
                     file_data: bytes, filename: str) -> dict:
        """
        Encrypt a file via BeakSeal.

        Returns:
            dict with 'file_id' and 'status'

        Raises:
            VaultError on failure
        """
        return get_client().encrypt_file(
            org_id=org_code,
            user_id=user_code,
            file_data=file_data,
            filename=filename)

    @staticmethod
    def decrypt_file(file_id: str, org_code: str = '',
                     user_code: str = '') -> bytes:
        """
        Decrypt a file from BeakSeal.

        Returns:
            Raw file bytes

        Raises:
            VaultError on failure
        """
        return get_client().decrypt_file(
            file_id=file_id,
            org_id=org_code,
            user_id=user_code)

    @staticmethod
    def delete_file(file_id: str, org_code: str = '',
                    user_code: str = '') -> dict:
        """Secure-delete an encrypted file."""
        return get_client().delete_file(
            file_id=file_id,
            org_id=org_code,
            user_id=user_code)

    @staticmethod
    def get_file_meta(file_id: str) -> dict:
        """Get file metadata without decryption."""
        return get_client().get_file_meta(file_id)

    @staticmethod
    def rotate_key(org_code: str) -> dict:
        """Trigger key rotation."""
        return get_client().rotate_key(org_code)

    @staticmethod
    def get_key_generations(org_code: str) -> list:
        """List key generations."""
        return get_client().get_key_generations(org_code)

    @staticmethod
    def get_audit_logs(**kwargs) -> list:
        """Query audit logs."""
        return get_client().get_audit_logs(**kwargs)

    @staticmethod
    def verify_audit_chain(from_id: int = 0, to_id: int = 0) -> dict:
        """Verify audit chain integrity."""
        return get_client().verify_audit_chain(from_id, to_id)
