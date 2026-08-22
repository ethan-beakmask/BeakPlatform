"""Utilities for building externally reachable platform URLs."""
from flask import has_request_context, request

from ..models.system_setting import SystemSetting


def get_system_base_url() -> str | None:
    """回傳已設定的系統對外 base URL（無尾斜線）；未設定回 None。"""
    value = (SystemSetting.get('system_base_url', '') or '').strip().rstrip('/')
    return value or None


def build_external_url(path: str) -> str | None:
    """組出對外可用的完整網址；系統對外網址未設定時回 None（呼叫端自行處理）。

    path 是 Flask 的應用內路徑（不含 nginx 前綴），例如 '/auth/org/x.com/login'。
    結果 = base_url + request.script_root + path
    """
    base_url = get_system_base_url()
    if not base_url:
        return None

    normalized_path = path or ''
    if not normalized_path.startswith('/'):
        normalized_path = '/' + normalized_path

    script_root = ''
    if has_request_context():
        script_root = (request.script_root or '').rstrip('/')

    # url_for() 在 request context 內產生的相對 URL 已含 SCRIPT_NAME。
    # 若 path 已帶 nginx 前綴，這裡不能再接一次，否則會變成 /beakplatform/beakplatform/...
    if script_root and normalized_path.startswith(script_root + '/'):
        return base_url + normalized_path
    if script_root and normalized_path == script_root:
        return base_url + normalized_path

    return base_url + script_root + normalized_path
