# -*- coding: utf-8 -*-
"""ExternalWait node service, handler, and public callback tests."""
from datetime import datetime, timedelta
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db
from app.models import SystemSetting
from modules.form_workflow.models import FwNodeExecutionQueue, FwWorkflowInstance
from modules.form_workflow.services import external_wait_service as svc
from modules.form_workflow.services.node_handlers import base as base_handler
from modules.form_workflow.services.node_handlers import external_wait_handler as h
from modules.form_workflow.services.node_handlers.external_wait_handler import ExternalWaitHandler

ORG = 'ORG_EXTWAIT_000000000001'
INSTANCE = 'WI_EXTWAIT_000000000001'
NODE_ID = 'node-Wait'


@pytest.fixture(autouse=True)
def _clear_variable_cache():
    from app.module_loader import module_loader

    module_loader._loaded = False
    svc.VariableService.clear_cache()
    yield
    svc.VariableService.clear_cache()


def _instance(status='RUNNING', code=INSTANCE):
    wi = FwWorkflowInstance(
        secure_code=code,
        org_secure_code=ORG,
        workflow_template_secure_code='WT_EXTWAIT',
        workflow_name='ExternalWait Test',
        status=status,
        execution_code='EXEC-EXTWAIT',
    )
    db.session.add(wi)
    db.session.commit()
    return wi


def _queue(status='WAITING', code='Q_EXTWAIT', instance_code=INSTANCE, node_id=NODE_ID):
    q = FwNodeExecutionQueue(
        secure_code=code,
        org_secure_code=ORG,
        workflow_instance_secure_code=instance_code,
        node_id=node_id,
        node_type='ExternalWait',
        node_name='Wait',
        node_config={'result_var': 'cb', 'timeout_enabled': True, 'timeout_minutes': 2},
        status=status,
        scheduled_at=datetime.utcnow() + timedelta(minutes=2),
        result={},
    )
    db.session.add(q)
    db.session.commit()
    return q


def _handler(config=None, result=None):
    q = SimpleNamespace(
        org_secure_code=ORG,
        node_id=NODE_ID,
        node_type='ExternalWait',
        node_name='Wait',
        node_config=config or {'result_var': 'cb', 'timeout_enabled': True, 'timeout_minutes': 2},
        secure_code='Q_HANDLER',
        status='PENDING',
        id=1,
        retry_count=0,
        started_at=None,
        process_id=None,
        scheduled_at=None,
        result=result,
        workflow_instance_secure_code=INSTANCE,
    )
    handler = ExternalWaitHandler(q)
    flow_vars = {}
    logs = []
    handler.report_running = lambda: None
    handler.log_warning = lambda msg, details=None: logs.append(('WARNING', msg, details))
    handler.set_flow_var = lambda name, value: flow_vars.__setitem__(name, value)
    return handler, flow_vars, logs


def test_token_is_stable_and_bound_to_instance_and_node(app):
    token = svc.callback_token(INSTANCE, NODE_ID)

    assert token == svc.callback_token(INSTANCE, NODE_ID)
    assert token != svc.callback_token(INSTANCE + 'X', NODE_ID)
    assert token != svc.callback_token(INSTANCE, NODE_ID + 'X')
    assert svc.verify_token(INSTANCE, NODE_ID, token) is True
    assert svc.verify_token(INSTANCE, NODE_ID, '0' * 32) is False


def test_build_callback_url_uses_system_base_url_and_app_prefix(app, monkeypatch):
    SystemSetting.set('system_base_url', 'https://forms.example.com/', value_type='string')
    monkeypatch.setenv('APP_PREFIX', '/beakplatform')

    url = svc.build_callback_url(INSTANCE, NODE_ID)

    assert url.startswith('https://forms.example.com/beakplatform/api/external-wait/callback/')
    assert f'/{INSTANCE}/{NODE_ID}/' in url


def test_build_callback_url_returns_none_without_base_url(app):
    assert svc.build_callback_url(INSTANCE, NODE_ID) is None


@pytest.mark.parametrize('payload,depth', [
    ({}, 1),
    ({'a': {'b': [1]}}, 4),
])
def test_json_depth(payload, depth):
    assert svc.json_depth(payload) == depth


def test_receive_callback_404_cases_match(app):
    _instance()
    token = svc.callback_token(INSTANCE, NODE_ID)

    missing_status, missing_body = svc.receive_callback('WI_MISSING_0000000001', NODE_ID, token, b'{}', '127.0.0.1')
    bad_status, bad_body = svc.receive_callback(INSTANCE, NODE_ID, '0' * 32, b'{}', '127.0.0.1')

    assert (missing_status, missing_body) == (404, {'error': 'not_found'})
    assert (bad_status, bad_body) == (404, {'error': 'not_found'})


def test_receive_callback_rejects_non_running_and_completed(app):
    _instance(status='COMPLETED')
    token = svc.callback_token(INSTANCE, NODE_ID)

    status, body = svc.receive_callback(INSTANCE, NODE_ID, token, b'{}', '127.0.0.1')

    assert status == 409
    assert body['error'] == 'workflow_not_running'


def test_receive_callback_rejects_completed_queue(app):
    _instance()
    _queue(status='SUCCESS')
    token = svc.callback_token(INSTANCE, NODE_ID)

    status, body = svc.receive_callback(INSTANCE, NODE_ID, token, b'{}', '127.0.0.1')

    assert status == 409
    assert body['error'] == 'already_completed'


def test_receive_callback_writes_vars_and_wakes_waiting_queue(app):
    _instance()
    q = _queue(status='WAITING')
    token = svc.callback_token(INSTANCE, NODE_ID)

    status, body = svc.receive_callback(INSTANCE, NODE_ID, token, b'{"status":"closed"}', '127.0.0.1')

    db.session.refresh(q)
    assert status == 202
    assert body == {'accepted': True, 'state': 'woken'}
    assert q.scheduled_at <= datetime.utcnow()
    assert svc.VariableService.get_flow_var(INSTANCE, svc.payload_var_name(NODE_ID)) == {'status': 'closed'}
    meta = svc.VariableService.get_flow_var(INSTANCE, svc.meta_var_name(NODE_ID))
    assert meta['source_ip'] == '127.0.0.1'
    assert meta['consumed'] is False


def test_receive_callback_wakes_running_queue_too(app):
    """處理器讀完變數、尚未寫回 WAITING 的那一瞬間收到回呼，也要把 scheduled_at 推到現在"""
    _instance()
    q = _queue(status='RUNNING')
    q.scheduled_at = datetime(9999, 12, 31)
    db.session.commit()
    token = svc.callback_token(INSTANCE, NODE_ID)

    status, body = svc.receive_callback(INSTANCE, NODE_ID, token, b'{}', '127.0.0.1')

    db.session.refresh(q)
    assert (status, body) == (202, {'accepted': True, 'state': 'woken'})
    assert q.scheduled_at <= datetime.utcnow()


def test_receive_callback_buffers_before_queue_exists(app):
    _instance()
    token = svc.callback_token(INSTANCE, NODE_ID)

    status, body = svc.receive_callback(INSTANCE, NODE_ID, token, b'{}', '127.0.0.1')

    assert status == 202
    assert body == {'accepted': True, 'state': 'buffered'}
    assert svc.VariableService.get_flow_var(INSTANCE, svc.payload_var_name(NODE_ID)) == {}


def test_receive_callback_input_limits(app):
    _instance()
    token = svc.callback_token(INSTANCE, NODE_ID)

    assert svc.receive_callback(INSTANCE, NODE_ID, token, b'x' * (svc.MAX_PAYLOAD_BYTES + 1), 'ip')[0] == 413
    assert svc.receive_callback(INSTANCE, NODE_ID, token, b'{bad', 'ip') == (400, {'error': 'invalid_json'})
    deep = b'{"a":{"b":{"c":{"d":{"e":{"f":{"g":{"h":{"i":{"j":{"k":1}}}}}}}}}}}'
    assert svc.receive_callback(INSTANCE, NODE_ID, token, deep, 'ip') == (400, {'error': 'payload_too_deep'})


def test_receive_callback_duplicate_is_409(app):
    _instance()
    token = svc.callback_token(INSTANCE, NODE_ID)

    assert svc.receive_callback(INSTANCE, NODE_ID, token, b'{}', 'ip')[0] == 202
    status, body = svc.receive_callback(INSTANCE, NODE_ID, token, b'{}', 'ip')

    assert status == 409
    assert body['error'] == 'already_received'


def test_handler_first_entry_waits_and_sets_scheduled_at(app, monkeypatch):
    monkeypatch.setattr(h, 'build_callback_url', lambda instance, node: 'https://forms.example.com/cb')
    handler, _vars, _logs = _handler()

    result = handler.handle()

    assert result['status'] == 'waiting'
    assert handler.queue_item.scheduled_at is not None
    assert result['data']['callback_url'] == 'https://forms.example.com/cb'
    assert result['data']['timeout_at'] is not None
    assert result['data']['waiting_since'] is not None


def test_handler_no_timeout_sets_far_future_sentinel(app, monkeypatch):
    monkeypatch.setattr(h, 'build_callback_url', lambda instance, node: 'https://forms.example.com/cb')
    handler, _vars, _logs = _handler({'result_var': 'cb', 'timeout_enabled': False})

    result = handler.handle()

    assert result['status'] == 'waiting'
    assert handler.queue_item.scheduled_at == svc.NO_TIMEOUT_SENTINEL
    assert result['data']['timeout_at'] is None


def test_handler_consumes_callback_and_sets_result_vars(app, monkeypatch):
    store = {
        svc.meta_var_name(NODE_ID): {
            'received_at': '2026-10-10T01:02:03',
            'source_ip': '127.0.0.1',
            'consumed': False,
        },
        svc.payload_var_name(NODE_ID): {'status': 'closed'},
    }
    monkeypatch.setattr(h.VariableService, 'get_flow_var', lambda instance, name: store.get(name))
    monkeypatch.setattr(h.VariableService, 'set_flow_var', lambda instance, name, value, org, node: store.__setitem__(name, value))
    handler, flow_vars, _logs = _handler(result={'data': {
        'callback_url': 'https://forms.example.com/cb',
        'waiting_since': (datetime.utcnow() - timedelta(seconds=5)).isoformat(),
    }})

    result = handler.handle()

    assert result['status'] == 'success'
    assert flow_vars['cb_result'] == 'received'
    assert flow_vars['cb_payload'] == {'status': 'closed'}
    assert flow_vars['cb_received_at'] == '2026-10-10T01:02:03'
    assert flow_vars['cb_source_ip'] == '127.0.0.1'
    assert flow_vars['cb_callback_url'] == 'https://forms.example.com/cb'
    assert flow_vars['cb_waited_seconds'] >= 3
    assert store[svc.meta_var_name(NODE_ID)]['consumed'] is True


def test_handler_timeout_sets_timeout_result(app):
    handler, flow_vars, _logs = _handler(result={'data': {
        'callback_url': 'https://forms.example.com/cb',
        'waiting_since': (datetime.utcnow() - timedelta(seconds=10)).isoformat(),
        'timeout_at': (datetime.utcnow() - timedelta(seconds=1)).isoformat(),
    }})

    result = handler.handle()

    assert result['status'] == 'success'
    assert flow_vars['cb_result'] == 'timeout'
    assert flow_vars['cb_payload'] is None
    assert flow_vars['cb_received_at'] is None
    assert flow_vars['cb_source_ip'] is None


def test_replace_variables_cb_prefix(app, monkeypatch):
    SystemSetting.set('system_base_url', 'https://forms.example.com', value_type='string')
    q = SimpleNamespace(
        workflow_instance_secure_code=INSTANCE,
        node_config={},
        org_secure_code=ORG,
        node_id='node-Http',
        node_type='HttpRequest',
    )

    class FakeHandler(base_handler.BaseNodeHandler):
        def handle(self):
            return {}

    handler = FakeHandler(q)
    handler.get_all_vars = lambda: {}

    value = handler.replace_variables('${cb.node-Wait}')

    assert value.startswith('https://forms.example.com/beakplatform/api/external-wait/callback/')
    assert handler.replace_variables('${cb.bad/node}') == ''


def test_public_api_accepts_without_login_and_is_csrf_exempt(client, app):
    _instance()
    token = svc.callback_token(INSTANCE, NODE_ID)

    resp = client.post(
        f'/beakplatform/api/external-wait/callback/{INSTANCE}/{NODE_ID}/{token}',
        data=b'{}',
        content_type='application/json',
    )
    bad = client.post(
        f'/beakplatform/api/external-wait/callback/{INSTANCE}/{NODE_ID}/{"0" * 32}',
        data=b'{}',
        content_type='application/json',
    )

    assert resp.status_code == 202
    assert bad.status_code == 404
    assert resp.status_code != 400
