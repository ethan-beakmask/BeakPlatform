"""
BeakSeal Vault Client
透過 Unix socket 與 BeakSeal 通訊的 Python client library
"""
import json
import logging
import socket
from http.client import HTTPConnection
from typing import Optional

logger = logging.getLogger(__name__)

# Default BeakSeal socket path
DEFAULT_SOCKET = '/opt/BeakSeal/beakseal.sock'


class UnixSocketHTTPConnection(HTTPConnection):
    """HTTP connection over Unix socket."""

    def __init__(self, socket_path: str, timeout: int = 30):
        super().__init__('localhost', timeout=timeout)
        self._socket_path = socket_path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self._socket_path)


class VaultError(Exception):
    """BeakSeal API error."""

    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class VaultClient:
    """
    BeakSeal Vault Client.

    Usage:
        client = VaultClient()
        result = client.encrypt_file(org_id, user_id, file_data, 'document.pdf')
        data = client.decrypt_file(file_id, org_id, user_id)
        status = client.get_status()
    """

    def __init__(self, socket_path: str = DEFAULT_SOCKET, timeout: int = 60):
        self._socket_path = socket_path
        self._timeout = timeout

    def _request(self, method: str, path: str, body=None, headers=None,
                 content_type: str = 'application/json') -> dict:
        """Send a request to BeakSeal and return parsed JSON response."""
        conn = UnixSocketHTTPConnection(self._socket_path, self._timeout)
        try:
            all_headers = {}
            if content_type:
                all_headers['Content-Type'] = content_type
            if headers:
                all_headers.update(headers)

            if isinstance(body, dict):
                body = json.dumps(body).encode('utf-8')

            conn.request(method, path, body=body, headers=all_headers)
            resp = conn.getresponse()
            data = resp.read()

            if resp.status >= 400:
                try:
                    err = json.loads(data)
                    msg = err.get('error', data.decode('utf-8', errors='replace'))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    msg = f'HTTP {resp.status}'
                raise VaultError(msg, resp.status)

            return json.loads(data)
        finally:
            conn.close()

    def _request_raw(self, method: str, path: str, headers=None) -> tuple:
        """Send a request and return raw response (status, headers, body)."""
        conn = UnixSocketHTTPConnection(self._socket_path, self._timeout)
        try:
            conn.request(method, path, headers=headers or {})
            resp = conn.getresponse()
            body = resp.read()
            return resp.status, dict(resp.getheaders()), body
        finally:
            conn.close()

    def _multipart_request(self, path: str, file_data: bytes, filename: str,
                           org_id: str, user_id: str,
                           original_name: str = None) -> dict:
        """Send multipart/form-data request for file upload."""
        boundary = '----BeakSealBoundary7ma4d9abcdef'
        if original_name is None:
            original_name = filename

        body_parts = []
        body_parts.append(f'--{boundary}\r\n'.encode())
        body_parts.append(
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f'Content-Type: application/octet-stream\r\n\r\n'.encode())
        body_parts.append(file_data)
        body_parts.append(b'\r\n')
        body_parts.append(f'--{boundary}\r\n'.encode())
        body_parts.append(
            f'Content-Disposition: form-data; name="original_name"\r\n\r\n'
            f'{original_name}\r\n'.encode())
        body_parts.append(f'--{boundary}--\r\n'.encode())

        body = b''.join(body_parts)
        headers = {
            'Content-Type': f'multipart/form-data; boundary={boundary}',
            'X-BeakSeal-Org': org_id,
            'X-BeakSeal-User': user_id,
        }

        conn = UnixSocketHTTPConnection(self._socket_path, self._timeout)
        try:
            conn.request('POST', path, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            result = json.loads(data)

            if resp.status >= 400 or not result.get('success'):
                msg = result.get('error', f'HTTP {resp.status}')
                raise VaultError(msg, resp.status)

            return result
        finally:
            conn.close()

    # --- Vault Control ---

    def get_status(self) -> dict:
        """Get vault status (sealed/unsealed, uptime, loaded keys)."""
        result = self._request('GET', '/v1/vault/status')
        return result.get('data', result)

    def unseal(self, password: str) -> dict:
        """Unseal the vault with the master password."""
        result = self._request('POST', '/v1/vault/unseal',
                               body={'password': password})
        return result.get('data', result)

    def seal(self) -> dict:
        """Seal the vault (clears all keys from memory)."""
        result = self._request('POST', '/v1/vault/seal')
        return result.get('data', result)

    # --- Organization ---

    def register_org(self, org_id: str) -> dict:
        """Register a new organization (creates first key generation)."""
        result = self._request('POST', '/v1/orgs', body={'org_id': org_id})
        return result.get('data', result)

    # --- File Operations ---

    def encrypt_file(self, org_id: str, user_id: str,
                     file_data: bytes, filename: str,
                     original_name: str = None) -> dict:
        """
        Encrypt and store a file.
        Returns dict with 'file_id' and 'status'.
        """
        result = self._multipart_request(
            '/v1/files/encrypt', file_data, filename,
            org_id, user_id, original_name)
        return result.get('data', result)

    def decrypt_file(self, file_id: str,
                     org_id: str = '', user_id: str = '') -> bytes:
        """Decrypt and return file content as raw bytes."""
        headers = {}
        if org_id:
            headers['X-BeakSeal-Org'] = org_id
        if user_id:
            headers['X-BeakSeal-User'] = user_id

        status, resp_headers, body = self._request_raw(
            'POST', f'/v1/files/decrypt/{file_id}', headers=headers)

        if status >= 400:
            try:
                err = json.loads(body)
                msg = err.get('error', f'HTTP {status}')
            except (json.JSONDecodeError, UnicodeDecodeError):
                msg = f'HTTP {status}'
            raise VaultError(msg, status)

        return body

    def delete_file(self, file_id: str,
                    org_id: str = '', user_id: str = '') -> dict:
        """Secure-delete an encrypted file."""
        headers = {}
        if org_id:
            headers['X-BeakSeal-Org'] = org_id
        if user_id:
            headers['X-BeakSeal-User'] = user_id

        result = self._request('DELETE', f'/v1/files/{file_id}',
                               headers=headers, content_type=None)
        return result.get('data', result)

    def get_file_meta(self, file_id: str) -> dict:
        """Get file metadata (no decryption)."""
        result = self._request('GET', f'/v1/files/{file_id}/meta')
        return result.get('data', result)

    # --- File Validation ---

    def validate_file(self, org_id: str, file_data: bytes,
                      filename: str) -> dict:
        """Validate file type without encryption."""
        result = self._multipart_request(
            '/v1/validate/file', file_data, filename,
            org_id, 'system')
        return result.get('data', result)

    def get_allowed_types(self, org_id: str) -> list:
        """Get allowed file types for an organization."""
        result = self._request('GET', f'/v1/validate/types/{org_id}')
        return result.get('data', [])

    def update_allowed_type(self, org_id: str, extension: str,
                            enabled: bool) -> dict:
        """Enable/disable a file type for an organization."""
        result = self._request(
            'PUT', f'/v1/validate/types/{org_id}',
            body={'extension': extension, 'enabled': enabled})
        return result.get('data', result)

    # --- Key Management ---

    def rotate_key(self, org_id: str) -> dict:
        """Trigger key rotation for an organization."""
        result = self._request('POST', f'/v1/keys/rotate/{org_id}')
        return result.get('data', result)

    def get_key_generations(self, org_id: str) -> list:
        """List all key generations for an organization."""
        result = self._request('GET', f'/v1/keys/generations/{org_id}')
        return result.get('data', [])

    def get_current_key(self, org_id: str) -> dict:
        """Get current key generation for an organization."""
        result = self._request('GET', f'/v1/keys/current/{org_id}')
        return result.get('data', result)

    # --- Audit ---

    def get_audit_logs(self, **kwargs) -> list:
        """
        Query audit logs.
        Keyword args: org_id, user_id, action, file_id,
                      from_date, to_date, limit, offset
        """
        params = '&'.join(f'{k}={v}' for k, v in kwargs.items() if v)
        path = f'/v1/audit/logs?{params}' if params else '/v1/audit/logs'
        result = self._request('GET', path)
        return result.get('data', [])

    def verify_audit_chain(self, from_id: int = 0,
                           to_id: int = 0) -> dict:
        """Verify audit log hash chain integrity."""
        params = []
        if from_id:
            params.append(f'from_id={from_id}')
        if to_id:
            params.append(f'to_id={to_id}')
        path = '/v1/audit/verify'
        if params:
            path += '?' + '&'.join(params)
        result = self._request('GET', path)
        return result.get('data', result)
