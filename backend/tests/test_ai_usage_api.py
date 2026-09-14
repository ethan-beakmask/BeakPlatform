# -*- coding: utf-8 -*-
"""
AiAgent usage and quota administration API tests.
"""
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import create_app, db
from app.models import Organization
from app.models.contract import Contract, ContractStatus
from app.models.system_setting import SystemSetting
from modules.form_workflow.models import FwAiUsageRecord
from modules.form_workflow.services import ai_usage_service


API_PREFIX = '/beakplatform/api/form-workflow/ai-usage'
CONFIG_KEYS = set(ai_usage_service.HARDCODED_DEFAULTS.keys())


@pytest.fixture(scope='function')
def app():
    from app.module_loader import module_loader

    previous_skip = os.environ.get('SKIP_MODULE_SYNC')
    os.environ['SKIP_MODULE_SYNC'] = '1'
    module_loader._loaded = False
    module_loader.modules = {}
    for name in list(sys.modules):
        if name == 'modules.form_workflow.api' or name.startswith('modules.form_workflow.api.'):
            sys.modules.pop(name, None)
        if name == 'modules.form_workflow.web' or name.startswith('modules.form_workflow.web.'):
            sys.modules.pop(name, None)
    app = create_app('testing')

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

    module_loader._loaded = False
    module_loader.modules = {}
    if previous_skip is None:
        os.environ.pop('SKIP_MODULE_SYNC', None)
    else:
        os.environ['SKIP_MODULE_SYNC'] = previous_skip


def _seed_contract(org_code):
    contract = Contract(
        org_secure_code=org_code,
        contract_number=f'CTR-TEST-{org_code[-4:]}',
        name='Form workflow test contract',
        start_date=date.today() - timedelta(days=1),
        end_date=date.today() + timedelta(days=30),
        status=ContractStatus.ACTIVE,
        modules_config=json.dumps(['form_workflow']),
    )
    db.session.add(contract)
    db.session.commit()
    return contract


def _seed_system_defaults(**overrides):
    data = dict(ai_usage_service.HARDCODED_DEFAULTS)
    data.update(overrides)
    setting = SystemSetting(
        key=ai_usage_service.SYSTEM_SETTING_KEY,
        value=json.dumps(data),
        value_type='json',
        description='test',
        category='ai_node',
    )
    db.session.add(setting)
    db.session.commit()
    return setting


def _usage(org_code, *, status=FwAiUsageRecord.STATUS_SUCCESS, queue='q_api',
           started_at=None, cost='0.10'):
    rec = FwAiUsageRecord(
        org_secure_code=org_code,
        workflow_instance_secure_code=f'wi_{queue}',
        form_instance_secure_code=f'fi_{queue}',
        node_id='ai1',
        node_name='AI node',
        node_queue_secure_code=queue,
        model='claude-sonnet-5',
        status=status,
        input_tokens=12,
        output_tokens=7,
        cost_usd=cost,
        started_at=started_at or datetime.utcnow(),
        finished_at=started_at or datetime.utcnow(),
    )
    db.session.add(rec)
    db.session.commit()
    return rec


def _second_org():
    org = Organization(
        secure_code='test_org_00000000002',
        code='TEST_ORG_B',
        name='Test Organization B',
        domain_name='test-b.local',
        is_active=True,
        is_deleted=False,
    )
    db.session.add(org)
    db.session.commit()
    return org


@pytest.fixture
def ai_api_admin(admin_client, test_org):
    _seed_contract(test_org.secure_code)
    _seed_system_defaults()
    return admin_client


def test_ai_usage_api_requires_login(client):
    endpoints = [
        ('GET', f'{API_PREFIX}/config'),
        ('PUT', f'{API_PREFIX}/config'),
        ('GET', f'{API_PREFIX}/summary'),
        ('GET', f'{API_PREFIX}/records'),
    ]

    statuses = []
    for method, url in endpoints:
        resp = client.open(url, method=method, json={} if method == 'PUT' else None)
        statuses.append(resp.status_code)

    assert statuses
    assert all(code in (401, 403) for code in statuses)


def test_admin_get_config_returns_all_keys(ai_api_admin):
    resp = ai_api_admin.get(f'{API_PREFIX}/config')

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert set(data['config'].keys()) == CONFIG_KEYS
    assert {item['key'] for item in data['items']} == CONFIG_KEYS


def test_put_config_sets_org_source(ai_api_admin):
    resp = ai_api_admin.put(f'{API_PREFIX}/config', json={
        'enabled': True,
        'daily_max_runs': 9,
    })

    assert resp.status_code == 200
    data = resp.get_json()['data']
    sources = {item['key']: item['source'] for item in data['items']}
    assert data['config']['daily_max_runs'] == 9
    assert sources['daily_max_runs'] == 'org'


def test_put_config_clear_returns_to_system(ai_api_admin):
    ai_api_admin.put(f'{API_PREFIX}/config', json={'daily_max_cost_usd': 2.5})

    resp = ai_api_admin.put(f'{API_PREFIX}/config', json={'clear': ['daily_max_cost_usd']})

    assert resp.status_code == 200
    data = resp.get_json()['data']
    row = next(item for item in data['items'] if item['key'] == 'daily_max_cost_usd')
    assert row['source'] == 'system'
    assert data['config']['daily_max_cost_usd'] == row['system_default']


@pytest.mark.parametrize('payload', [
    {'daily_max_runs': -1},
    {'monthly_max_cost_usd': '1.25'},
])
def test_put_config_rejects_invalid_values_without_writing(ai_api_admin, payload):
    ok = ai_api_admin.put(f'{API_PREFIX}/config', json={'daily_max_runs': 7})
    assert ok.status_code == 200

    resp = ai_api_admin.put(f'{API_PREFIX}/config', json=payload)
    after = ai_api_admin.get(f'{API_PREFIX}/config').get_json()['data']

    assert resp.status_code == 400
    assert resp.get_json()['error'] == 'invalid_value'
    assert after['config']['daily_max_runs'] == 7


def test_records_per_page_is_capped_at_100(ai_api_admin, test_org):
    _usage(test_org.secure_code)

    resp = ai_api_admin.get(f'{API_PREFIX}/records?per_page=500')

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['per_page'] == 100
    assert data['total'] == 1


def test_records_are_isolated_by_current_org(ai_api_admin, test_org):
    own = _usage(test_org.secure_code, queue='qa')
    org_b = _second_org()
    _seed_contract(org_b.secure_code)
    _usage(org_b.secure_code, queue='qb')

    resp = ai_api_admin.get(f'{API_PREFIX}/records')

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['total'] == 1
    assert [item['secure_code'] for item in data['items']] == [own.secure_code]
    assert all('org_secure_code' not in item for item in data['items'])


def test_summary_counts_recent_blocked(ai_api_admin, test_org):
    _usage(test_org.secure_code, status=FwAiUsageRecord.STATUS_BLOCKED, queue='blocked_a')
    _usage(test_org.secure_code, status=FwAiUsageRecord.STATUS_BLOCKED, queue='blocked_b')
    _usage(test_org.secure_code, status=FwAiUsageRecord.STATUS_SUCCESS, queue='success')

    resp = ai_api_admin.get(f'{API_PREFIX}/summary')

    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['recent_blocked'] == 2
    assert data['daily']['runs'] == 1
    assert data['monthly']['runs'] == 1
