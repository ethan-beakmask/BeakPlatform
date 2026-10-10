# -*- coding: utf-8 -*-
"""HttpRequest 節點的白名單、SSRF 防護與結果變數測試。"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db  # noqa: E402
from app.models import SystemSetting  # noqa: E402
from modules.form_workflow.services.node_handlers import http_request_handler as h  # noqa: E402
from modules.form_workflow.services.node_handlers.http_request_handler import (  # noqa: E402
    HttpRequestHandler,
    collect_response_headers,
    is_destination_allowed,
    mask_sensitive_headers,
    read_response_body,
    sanitize_request_headers,
)

ORG_A = 'ORG_AAAAAAAAAAAAAAAAAAAA'


def make_handler(config):
    queue_item = SimpleNamespace(
        org_secure_code=ORG_A,
        node_id='n_http_1',
        node_type='HttpRequest',
        node_config=config,
        secure_code='QUEUE_HTTP',
        status='PENDING',
        id=1,
        retry_count=0,
        started_at=None,
        process_id=None,
        workflow_instance_secure_code='WI_HTTP',
    )
    handler = HttpRequestHandler(queue_item)
    flow_vars = {}
    logs = []
    handler.report_running = lambda: None
    handler.log_info = lambda msg, details=None: logs.append(('INFO', msg, details))
    handler.log_warning = lambda msg, details=None: logs.append(('WARNING', msg, details))
    handler.log_error = lambda msg, details=None: logs.append(('ERROR', msg, details))
    handler.set_flow_var = lambda name, value: flow_vars.__setitem__(name, value)
    handler.replace_variables = lambda text, **kw: str(text).replace('${f.url}', 'http://api.example.com/ping')
    return handler, flow_vars, logs


@pytest.mark.parametrize('hostname,port,ips,entries,expected', [
    ('api.example.com', 443, ['93.184.216.34'], ['api.example.com'], True),
    ('api.example.com', 8443, ['93.184.216.34'], ['api.example.com:443'], False),
    ('foo.example.com', 443, ['93.184.216.34'], ['*.example.com'], True),
    ('example.com', 443, ['93.184.216.34'], ['*.example.com'], False),
    ('x.example.com', 443, ['93.184.216.34'], ['93.184.216.0/24'], True),
    ('x.example.com', 443, ['93.184.216.34'], ['93.184.216.34:80'], False),
    ('api.example.com', 80, ['10.0.0.5'], ['api.example.com'], False),
    ('api.example.com', 80, ['10.0.0.5'], ['api.example.com', '10.0.0.0/8'], True),
    ('localhost', 8089, ['127.0.0.1'], ['127.0.0.1:8089'], True),
    ('localhost', 8089, ['127.0.0.1'], ['localhost:8089'], False),
    ('api.example.com', 443, ['169.254.10.1'], ['api.example.com'], False),
    ('api.example.com', 443, ['::1'], ['api.example.com'], False),
    ('api.example.com', 443, ['93.184.216.34'], [], False),
])
def test_destination_allowlist_rules(hostname, port, ips, entries, expected):
    allowed, _reason = is_destination_allowed(hostname, port, ips, entries)
    assert allowed is expected


def test_org_allowlist_is_intersection(app, monkeypatch):
    SystemSetting.set('http_request_allowed_hosts', ['api.example.com'], value_type='json')
    SystemSetting.set('http_request_org_allowed_hosts', {ORG_A: ['other.example.com']}, value_type='json')
    handler, _vars, _logs = make_handler({
        'url': 'http://api.example.com/ping',
        'result_var': 'http',
    })
    monkeypatch.setattr(h, 'resolve_hostname', lambda host, port: ['93.184.216.34'])

    allowed, reason = handler._check_destination(handler._load_runtime_config())

    assert allowed is False
    assert reason == 'destination_not_in_allowlist'


def test_sanitize_headers_ignores_invalid_blocked_and_truncates():
    raw = [{'name': f'X-{i}', 'value': str(i)} for i in range(25)]
    raw += [
        {'name': 'Bad Header', 'value': 'x'},
        {'name': 'Host', 'value': 'evil.example'},
        {'name': 'Content-Length', 'value': '999'},
    ]
    headers = sanitize_request_headers(raw, replace_func=lambda text: text + '!')

    assert headers['User-Agent'] == h.USER_AGENT
    assert headers['X-0'] == '0!'
    assert headers['X-19'] == '19!'
    assert 'X-20' not in headers
    assert 'Host' not in headers
    assert 'Content-Length' not in headers
    assert 'Bad Header' not in headers


def test_mask_sensitive_headers():
    masked = mask_sensitive_headers({
        'Authorization': 'Bearer secret',
        'X-Api-Key': 'abc',
        'X-Trace': 'visible',
    })
    assert masked['Authorization'] == '<已遮蔽>'
    assert masked['X-Api-Key'] == '<已遮蔽>'
    assert masked['X-Trace'] == 'visible'


def test_json_body_config_error_returns_success(monkeypatch):
    handler, flow_vars, _logs = make_handler({
        'url': 'http://api.example.com/ping',
        'method': 'POST',
        'body_mode': 'json',
        'body': '{bad json',
        'result_var': 'http',
    })
    monkeypatch.setattr(h, 'is_node_allowed', lambda node_type, org: True)
    monkeypatch.setattr(h, 'resolve_hostname', lambda host, port: ['93.184.216.34'])
    monkeypatch.setattr(SystemSetting, 'get', lambda key, default=None: ['api.example.com'] if key == 'http_request_allowed_hosts' else {})
    called = {'request': False}
    monkeypatch.setattr(h.requests, 'request', lambda *a, **kw: called.__setitem__('request', True))

    resp = handler.handle()

    assert resp['status'] == 'success'
    assert flow_vars['http_result'] == 'config_error'
    assert flow_vars['http_ok'] is False
    assert called['request'] is False


class FakeResponse:
    def __init__(self, status_code=200, chunks=None, headers=None, encoding='utf-8'):
        self.status_code = status_code
        self._chunks = chunks if chunks is not None else [b'{"pong": true}']
        self.headers = headers or {'Content-Type': 'application/json', 'Set-Cookie': 'secret'}
        self.encoding = encoding
        self.closed = False

    def iter_content(self, chunk_size=8192):
        yield from self._chunks

    def close(self):
        self.closed = True


def test_handler_200_json_sets_result_vars(monkeypatch):
    handler, flow_vars, _logs = make_handler({
        'url': '${f.url}',
        'method': 'GET',
        'result_var': 'http',
    })
    monkeypatch.setattr(h, 'is_node_allowed', lambda node_type, org: True)
    monkeypatch.setattr(h, 'resolve_hostname', lambda host, port: ['93.184.216.34'])
    monkeypatch.setattr(SystemSetting, 'get', lambda key, default=None: ['api.example.com'] if key == 'http_request_allowed_hosts' else {})
    monkeypatch.setattr(h.requests, 'request', lambda *a, **kw: FakeResponse())

    resp = handler.handle()

    assert resp['status'] == 'success'
    assert flow_vars['http_result'] == 'ok'
    assert flow_vars['http_ok'] is True
    assert flow_vars['http_status'] == 200
    assert flow_vars['http_json'] == {'pong': True}
    assert 'set-cookie' not in flow_vars['http_headers']


@pytest.mark.parametrize('status', [302, 500])
def test_handler_non_2xx_is_http_error_and_no_redirect(monkeypatch, status):
    handler, flow_vars, _logs = make_handler({
        'url': 'http://api.example.com/status',
        'method': 'GET',
        'result_var': 'http',
    })
    monkeypatch.setattr(h, 'is_node_allowed', lambda node_type, org: True)
    monkeypatch.setattr(h, 'resolve_hostname', lambda host, port: ['93.184.216.34'])
    monkeypatch.setattr(SystemSetting, 'get', lambda key, default=None: ['api.example.com'] if key == 'http_request_allowed_hosts' else {})
    calls = []

    def fake_request(*args, **kwargs):
        calls.append(kwargs)
        return FakeResponse(status_code=status, chunks=[b'nope'], headers={'Location': 'http://elsewhere/'})

    monkeypatch.setattr(h.requests, 'request', fake_request)

    resp = handler.handle()

    assert resp['status'] == 'success'
    assert flow_vars['http_result'] == 'http_error'
    assert flow_vars['http_ok'] is False
    assert flow_vars['http_status'] == status
    assert flow_vars['http_headers']['location'] == 'http://elsewhere/'
    assert calls[0]['allow_redirects'] is False


@pytest.mark.parametrize('exc,expected', [
    (requests.exceptions.Timeout('slow'), 'timeout'),
    (requests.exceptions.ConnectionError('down'), 'connection_error'),
])
def test_handler_request_exceptions(monkeypatch, exc, expected):
    handler, flow_vars, _logs = make_handler({
        'url': 'http://api.example.com/ping',
        'result_var': 'http',
    })
    monkeypatch.setattr(h, 'is_node_allowed', lambda node_type, org: True)
    monkeypatch.setattr(h, 'resolve_hostname', lambda host, port: ['93.184.216.34'])
    monkeypatch.setattr(SystemSetting, 'get', lambda key, default=None: ['api.example.com'] if key == 'http_request_allowed_hosts' else {})
    monkeypatch.setattr(h.requests, 'request', lambda *a, **kw: (_ for _ in ()).throw(exc))

    resp = handler.handle()

    assert resp['status'] == 'success'
    assert flow_vars['http_result'] == expected


def test_allowlist_missing_does_not_call_request(monkeypatch):
    handler, flow_vars, _logs = make_handler({
        'url': 'http://api.example.com/ping',
        'result_var': 'http',
    })
    monkeypatch.setattr(h, 'is_node_allowed', lambda node_type, org: True)
    monkeypatch.setattr(h, 'resolve_hostname', lambda host, port: ['93.184.216.34'])
    monkeypatch.setattr(SystemSetting, 'get', lambda key, default=None: [] if key == 'http_request_allowed_hosts' else {})
    called = {'request': False}
    monkeypatch.setattr(h.requests, 'request', lambda *a, **kw: called.__setitem__('request', True))

    resp = handler.handle()

    assert resp['status'] == 'success'
    assert flow_vars['http_result'] == 'not_allowed'
    assert called['request'] is False


def test_response_truncation_skips_json():
    response = FakeResponse(chunks=[b'{"pong": ', b'true, "extra": 1}'])
    body, truncated = read_response_body(response, 12)

    assert truncated is True
    assert body == b'{"pong": tru'


def test_collect_response_headers_limits_and_skips_cookie():
    headers = {'Set-Cookie': 'secret'}
    headers.update({f'X-{i}': 'v' * 1200 for i in range(55)})

    collected = collect_response_headers(headers)

    assert 'set-cookie' not in collected
    assert len(collected) == 50
    assert len(collected['x-0']) == 1000


def test_validate_required_fields():
    with pytest.raises(ValueError):
        HttpRequestHandler(SimpleNamespace(node_config={'result_var': 'http'}, workflow_instance_secure_code='WI')).validate()
    with pytest.raises(ValueError):
        HttpRequestHandler(SimpleNamespace(node_config={'url': 'http://x', 'result_var': 'bad-name'}, workflow_instance_secure_code='WI')).validate()
    with pytest.raises(ValueError):
        HttpRequestHandler(SimpleNamespace(node_config={'url': 'http://x', 'result_var': 'ok', 'method': 'TRACE'}, workflow_instance_secure_code='WI')).validate()
