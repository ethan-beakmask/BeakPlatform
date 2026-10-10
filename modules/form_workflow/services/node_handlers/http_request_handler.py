"""
FormWorkflow Module - HttpRequest Handler
HTTP 呼叫節點處理器

HttpRequest 會對外送出 HTTP(S) 請求，屬於有副作用的整合節點。為避免平台
自動重試造成重複副作用，所有執行期結果都回 success，真實結果寫入
`<result_var>_*` 流程變數供後續 Branch/FieldWrite 判斷。
"""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import time
import traceback
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

import requests
from flask_babel import gettext as _

from app.models import SystemSetting
from modules.form_workflow.services.node_grant_service import is_node_allowed

from .base import BaseNodeHandler

NODE_TYPE = 'HttpRequest'
VAR_NAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
HEADER_NAME_RE = re.compile(r'^[A-Za-z0-9-]+$')
ALLOWED_METHODS = {'GET', 'POST', 'PUT', 'PATCH', 'DELETE'}
BODY_MODES = {'none', 'json', 'raw'}
BLOCKED_REQUEST_HEADERS = {'host', 'content-length', 'transfer-encoding'}
SENSITIVE_HEADER_RE = re.compile(
    r'(authorization|cookie|proxy-authorization|token|secret|key|password)',
    re.IGNORECASE,
)
DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_MAX_RESPONSE_BYTES = 262144
USER_AGENT = 'BeakPlatform-HttpRequest/1'


@dataclass(frozen=True)
class AllowEntry:
    raw: str
    kind: str
    value: Any
    port: Optional[int] = None


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes', 'y', 'on')
    return bool(value)


def _coerce_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _normalize_method(value: Any) -> str:
    method = str(value or 'GET').strip().upper()
    return method if method in ALLOWED_METHODS else 'GET'


def _normalize_body_mode(value: Any) -> str:
    mode = str(value or 'none').strip().lower()
    return mode if mode in BODY_MODES else 'none'


def _is_special_ip(ip: ipaddress._BaseAddress) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _parse_port(raw_port: str) -> Optional[int]:
    try:
        port = int(raw_port)
    except (TypeError, ValueError):
        return None
    if 1 <= port <= 65535:
        return port
    return None


def _split_host_port(entry: str) -> Tuple[str, Optional[int]]:
    value = entry.strip().lower()
    if not value:
        return '', None
    if value.startswith('['):
        end = value.find(']')
        if end == -1:
            return value, None
        host = value[1:end]
        rest = value[end + 1:]
        if rest.startswith(':'):
            return host, _parse_port(rest[1:])
        return host, None
    if '/' in value:
        network_part, _, port_part = value.rpartition(':')
        if port_part.isdigit() and network_part.count(':') == 0:
            return network_part, _parse_port(port_part)
        return value, None
    if value.count(':') == 1:
        host, raw_port = value.rsplit(':', 1)
        if raw_port.isdigit():
            return host, _parse_port(raw_port)
    return value, None


def _parse_allow_entries(entries: Any) -> List[AllowEntry]:
    if not isinstance(entries, list):
        return []
    parsed: List[AllowEntry] = []
    for item in entries:
        if not isinstance(item, str) or not item.strip():
            continue
        raw = item.strip()
        host, port = _split_host_port(raw)
        if not host:
            continue
        if host.startswith('*.') and len(host) > 2:
            parsed.append(AllowEntry(raw=raw, kind='wildcard', value=host[2:], port=port))
            continue
        try:
            if '/' in host:
                parsed.append(AllowEntry(raw=raw, kind='network', value=ipaddress.ip_network(host, strict=False), port=port))
            else:
                parsed.append(AllowEntry(raw=raw, kind='ip', value=ipaddress.ip_address(host), port=port))
            continue
        except ValueError:
            parsed.append(AllowEntry(raw=raw, kind='host', value=host.rstrip('.'), port=port))
    return parsed


def _entry_port_matches(entry: AllowEntry, port: int) -> bool:
    return entry.port is None or entry.port == port


def _host_matches(hostname: str, entry: AllowEntry) -> bool:
    host = (hostname or '').lower().rstrip('.')
    if entry.kind == 'host':
        return host == entry.value
    if entry.kind == 'wildcard':
        suffix = '.' + entry.value
        return host.endswith(suffix) and host != entry.value and len(host) > len(suffix)
    return False


def _ip_matches(ip: ipaddress._BaseAddress, entry: AllowEntry) -> bool:
    if entry.kind == 'ip':
        return ip == entry.value
    if entry.kind == 'network':
        return ip in entry.value
    return False


def is_destination_allowed(
    hostname: str,
    port: int,
    resolved_ips: Sequence[str],
    entries: Any,
) -> Tuple[bool, str]:
    parsed_entries = _parse_allow_entries(entries)
    if not parsed_entries:
        return False, 'allowlist_empty'

    ips: List[ipaddress._BaseAddress] = []
    for raw_ip in resolved_ips:
        try:
            ips.append(ipaddress.ip_address(raw_ip))
        except ValueError:
            return False, 'resolved_ip_invalid'
    if not ips:
        return False, 'no_resolved_ip'

    prelim = False
    for entry in parsed_entries:
        if not _entry_port_matches(entry, port):
            continue
        if _host_matches(hostname, entry) or any(_ip_matches(ip, entry) for ip in ips):
            prelim = True
            break
    if not prelim:
        return False, 'destination_not_in_allowlist'

    ip_entries = [entry for entry in parsed_entries if entry.kind in ('ip', 'network') and _entry_port_matches(entry, port)]
    for ip in ips:
        if _is_special_ip(ip) and not any(_ip_matches(ip, entry) for entry in ip_entries):
            return False, 'special_ip_requires_ip_allowlist'

    return True, 'allowed'


def resolve_hostname(hostname: str, port: int) -> List[str]:
    infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    return sorted({info[4][0] for info in infos})


def sanitize_request_headers(headers_config: Any, replace_func=None) -> Dict[str, str]:
    headers: Dict[str, str] = {'User-Agent': USER_AGENT}
    if not isinstance(headers_config, list):
        return headers
    for item in headers_config[:20]:
        if not isinstance(item, dict):
            continue
        name = str(item.get('name') or '').strip()
        if not HEADER_NAME_RE.match(name):
            continue
        if name.lower() in BLOCKED_REQUEST_HEADERS:
            continue
        value = str(item.get('value') or '')
        if replace_func:
            value = replace_func(value)
        headers[name] = value
    return headers


def mask_sensitive_headers(headers: Dict[str, str]) -> Dict[str, str]:
    return {
        name: '<已遮蔽>' if SENSITIVE_HEADER_RE.search(name) else value
        for name, value in headers.items()
    }


def collect_response_headers(headers: Any) -> Dict[str, str]:
    collected: Dict[str, str] = {}
    for name, value in headers.items():
        if len(collected) >= 50:
            break
        lower = str(name).lower()
        if lower == 'set-cookie':
            continue
        collected[lower] = str(value)[:1000]
    return collected


def read_response_body(response: Any, max_bytes: int) -> Tuple[bytes, bool]:
    chunks: List[bytes] = []
    total = 0
    truncated = False
    for chunk in response.iter_content(chunk_size=8192):
        if not chunk:
            continue
        remaining = max_bytes - total
        if remaining <= 0:
            truncated = True
            break
        if len(chunk) > remaining:
            chunks.append(chunk[:remaining])
            total += remaining
            truncated = True
            break
        chunks.append(chunk)
        total += len(chunk)
    return b''.join(chunks), truncated


class HttpRequestHandler(BaseNodeHandler):
    """HTTP 呼叫節點。"""

    def validate(self) -> bool:
        url = self.get_config_value('url')
        if not isinstance(url, str) or not url.strip():
            raise ValueError(_('url 為必填'))

        method = str(self.get_config_value('method', 'GET') or '').strip().upper()
        if method and method not in ALLOWED_METHODS:
            raise ValueError(_('method 必須是 GET/POST/PUT/PATCH/DELETE'))

        result_var = self.get_config_value('result_var')
        if not isinstance(result_var, str) or not VAR_NAME_RE.match(result_var.strip()):
            raise ValueError(_('result_var 格式不合法'))
        return True

    def handle(self) -> Dict[str, Any]:
        self.report_running()
        start = time.monotonic()
        result_var = str(self.get_config_value('result_var') or '').strip()
        result = self._empty_result()
        response = None

        try:
            if not is_node_allowed(NODE_TYPE, self.queue_item.org_secure_code):
                result.update({'_result': 'not_allowed', '_error': 'node_not_allowed'})
                self.log_warning('HttpRequest 節點未授權', {'node_type': NODE_TYPE})
                return self._finish(result_var, result, start)

            config = self._load_runtime_config()
            result_var = config['result_var']
            result['_url'] = config['url']

            allowed, reason = self._check_destination(config)
            if not allowed:
                result.update({'_result': 'not_allowed', '_error': reason})
                self.log_warning('HttpRequest 目的地不在白名單內', {
                    'url': config['url'],
                    'reason': reason,
                })
                return self._finish(result_var, result, start)

            headers = sanitize_request_headers(
                config['headers'],
                replace_func=lambda text: self.replace_variables(text, include_form=True, include_workflow=True),
            )
            if config['body_mode'] == 'raw' and not any(name.lower() == 'content-type' for name in headers):
                headers['Content-Type'] = config['content_type']
            data, json_body = self._prepare_body(config, result)
            if result['_result'] == 'config_error':
                return self._finish(result_var, result, start)

            if not config['verify_tls']:
                self.log_warning('HttpRequest 已關閉 TLS 憑證驗證', {'url': config['url']})

            self.log_info('HttpRequest 即將送出', {
                'method': config['method'],
                'url': config['url'],
                'headers': mask_sensitive_headers(headers),
            })

            response = requests.request(
                config['method'],
                config['url'],
                headers=headers,
                data=data,
                json=json_body,
                timeout=(min(5, config['timeout_seconds']), config['timeout_seconds']),
                verify=config['verify_tls'],
                allow_redirects=False,
                stream=True,
            )
            body_bytes, truncated = read_response_body(response, config['max_response_bytes'])
            response.close()
            body_text = body_bytes.decode(response.encoding or 'utf-8', errors='replace')

            result.update({
                '_status': response.status_code,
                '_body': body_text,
                '_headers': collect_response_headers(response.headers),
                '_truncated': truncated,
                '_result': 'ok' if 200 <= response.status_code < 300 else 'http_error',
                '_error': '' if 200 <= response.status_code < 300 else f'HTTP {response.status_code}',
            })
            result['_ok'] = result['_result'] == 'ok'
            if config['expect_json'] and not truncated and body_text:
                try:
                    result['_json'] = json.loads(body_text)
                except ValueError:
                    result['_json'] = None

            self.log_info('HttpRequest 呼叫完成', {
                'result': result['_result'],
                'status': result['_status'],
                'duration_ms': int((time.monotonic() - start) * 1000),
                'body_preview': body_text[:500],
            })

        except HttpRequestConfigError as e:
            result.update({'_result': 'config_error', '_error': str(e)})
            self.log_warning('HttpRequest 設定錯誤', {'error': str(e)})
        except requests.exceptions.Timeout as e:
            result.update({'_result': 'timeout', '_error': str(e)})
        except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
            result.update({'_result': 'connection_error', '_error': str(e)})
        except Exception as e:
            result.update({'_result': 'exception', '_error': str(e)})
            self.log_error('HttpRequest 執行例外', {
                'error': str(e),
                'traceback': traceback.format_exc(),
            })
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass

        return self._finish(result_var, result, start)

    def _load_runtime_config(self) -> Dict[str, Any]:
        url = self.replace_variables(
            str(self.get_config_value('url') or '').strip(),
            include_form=True,
            include_workflow=True,
        )
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname:
            raise HttpRequestConfigError('url 必須是 http:// 或 https:// 開頭')

        result_var = str(self.get_config_value('result_var') or '').strip()
        if not VAR_NAME_RE.match(result_var):
            raise HttpRequestConfigError('result_var 格式不合法')

        return {
            'url': url,
            'parsed': parsed,
            'result_var': result_var,
            'method': _normalize_method(self.get_config_value('method', 'GET')),
            'headers': self.get_config_value('headers', []),
            'body_mode': _normalize_body_mode(self.get_config_value('body_mode', 'none')),
            'body': str(self.get_config_value('body') or ''),
            'content_type': str(self.get_config_value('content_type') or 'text/plain').strip() or 'text/plain',
            'timeout_seconds': _coerce_int(self.get_config_value('timeout_seconds'), DEFAULT_TIMEOUT_SECONDS, 1, 120),
            'verify_tls': _coerce_bool(self.get_config_value('verify_tls'), True),
            'expect_json': _coerce_bool(self.get_config_value('expect_json'), True),
            'max_response_bytes': _coerce_int(
                self.get_config_value('max_response_bytes'),
                DEFAULT_MAX_RESPONSE_BYTES,
                1024,
                2097152,
            ),
        }

    def _check_destination(self, config: Dict[str, Any]) -> Tuple[bool, str]:
        parsed = config['parsed']
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)

        # 白名單為空就直接拒絕，連 DNS 都不查：避免設計者填的主機名在平台尚未開放前就外洩到解析器
        platform_entries = SystemSetting.get('http_request_allowed_hosts', [])
        if not _parse_allow_entries(platform_entries):
            return False, 'allowlist_empty'

        try:
            resolved_ips = resolve_hostname(parsed.hostname, port)
        except socket.gaierror as e:
            raise requests.exceptions.ConnectionError(f'DNS 解析失敗: {e}')

        allowed, reason = is_destination_allowed(parsed.hostname, port, resolved_ips, platform_entries)
        if not allowed:
            return False, reason

        org_map = SystemSetting.get('http_request_org_allowed_hosts', {})
        if isinstance(org_map, dict) and self.queue_item.org_secure_code in org_map:
            return is_destination_allowed(parsed.hostname, port, resolved_ips, org_map.get(self.queue_item.org_secure_code))
        return True, 'allowed'

    def _prepare_body(self, config: Dict[str, Any], result: Dict[str, Any]) -> Tuple[Optional[str], Any]:
        mode = config['body_mode']
        if mode == 'none':
            return None, None

        body = self.replace_variables(config['body'], include_form=True, include_workflow=True)
        if mode == 'json':
            if not body.strip():
                result.update({'_result': 'config_error', '_error': 'JSON body 不可為空'})
                return None, None
            try:
                return None, json.loads(body)
            except ValueError as e:
                result.update({'_result': 'config_error', '_error': f'JSON body 格式錯誤: {e}'})
                return None, None

        return body, None

    def _empty_result(self) -> Dict[str, Any]:
        return {
            '_result': 'exception',
            '_ok': False,
            '_status': None,
            '_body': '',
            '_json': None,
            '_headers': {},
            '_duration_ms': 0,
            '_error': '',
            '_truncated': False,
            '_url': '',
        }

    def _finish(self, result_var: str, result: Dict[str, Any], start: float) -> Dict[str, Any]:
        if result.get('_result') == 'config_error':
            self.log_warning('HttpRequest 設定錯誤', {'error': result.get('_error')})
        elif result.get('_result') not in ('ok', 'http_error', 'not_allowed'):
            self.log_error('HttpRequest 呼叫異常', {
                'result': result.get('_result'),
                'error': result.get('_error'),
                'url': result.get('_url'),
            })

        result['_duration_ms'] = int((time.monotonic() - start) * 1000)
        result['_ok'] = result.get('_result') == 'ok'
        if VAR_NAME_RE.match(result_var or ''):
            for key, value in result.items():
                self.set_flow_var(f'{result_var}{key}', value)

        return {
            'status': 'success',
            'message': f"HttpRequest: {result.get('_result')}",
            'data': {
                'result': result.get('_result'),
                'status': result.get('_status'),
                'duration_ms': result.get('_duration_ms'),
                'url': result.get('_url'),
            },
        }


class HttpRequestConfigError(Exception):
    """執行期設定錯誤。"""
