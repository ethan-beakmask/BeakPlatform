import json
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import inspect

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db
from app.models.api_key import ApiKey
from app.security.hmac_verifier import compute_signature
from modules.form_workflow.models import (
    FwFormInstance,
    FwFormTemplate,
    FwPublishedFormWorkflow,
    FwWorkflowInstance,
)
from modules.open_defense.models import OdIntakeEvent
from modules.open_defense.services.case_aggregation_service import (
    DEFAULT_AGGREGATION,
    append_event,
    build_event_summary,
    effective_config,
    find_mergeable_case,
    merge_event,
    resolve_group_key,
)
from modules.open_defense.services.intake_service import AGGREGATION_WINDOW_MINUTES
from modules.open_defense.services.routing_service import validate_aggregation


ORG_SC = 'test_org_00000000001'
TEMPLATE_SC = 'tmpl_sec_aggregation'


def _require_od_aggregation_tables():
    required = {
        'od_intake_events',
        'fw_workflow_instances',
        'fw_form_instances',
    }
    inspector = inspect(db.engine)
    missing = sorted(table for table in required if not inspector.has_table(table))
    if missing:
        pytest.skip(
            'PF-46: pytest app fixture did not create module tables required for '
            f'OpenDefense aggregation integration tests: {", ".join(missing)}'
        )


def _axis(**overrides):
    data = {
        'severity_id': 4,
        'actor_ip': '198.51.100.10',
        'target_host': 'host-1',
        'source_system': 'SPLUNK',
        'finding_rule_id': 'AV-017A',
        'occurred_at': '2026-08-10T00:00:00Z',
    }
    data.update(overrides)
    return data


def _group_key(payload_kind='native', source_system='SPLUNK', rule_secure_code='rule_test', axis=None, config=None):
    return resolve_group_key(
        rule_secure_code=rule_secure_code,
        axis=axis or _axis(source_system=source_system),
        client_key=None,
        config=config or effective_config(None),
        payload_kind=payload_kind,
        source_system=source_system,
    )


def _case_record(
    *,
    case_sc,
    form_sc,
    correlation_id,
    event_class,
    source_system,
    actor_ip='198.51.100.10',
    rule_id='AV-017A',
    received_at=None,
    created_at=None,
    org_secure_code=ORG_SC,
    status='RUNNING',
    severity_id=4,
    template_sc=TEMPLATE_SC,
    group_key=None,
    od_last_seen='2026-08-10T00:00:00Z',
):
    axis = _axis(
        severity_id=severity_id,
        actor_ip=actor_ip,
        source_system=source_system,
        finding_rule_id=rule_id,
    )
    payload_kind = 'native' if event_class == 'native' else 'ocsf'
    group_key = group_key or _group_key(payload_kind, source_system, axis=axis)
    form = FwFormInstance(
        secure_code=form_sc,
        org_secure_code=org_secure_code,
        form_template_secure_code=template_sc,
        serial_number=f'SN-{form_sc}',
        form_data={
            **axis,
            'od_group_key': group_key,
            'od_event_count': 1,
            'od_last_seen': od_last_seen,
            'od_repeat_count': 0,
            'od_history_block_count': 0,
            'od_events': [],
            'od_actor_ips': [actor_ip] if actor_ip else [],
        },
        status='INITIAL',
        source_type='WEBHOOK_OD',
        created_at=created_at,
    )
    workflow = FwWorkflowInstance(
        secure_code=case_sc,
        org_secure_code=org_secure_code,
        form_instance_secure_code=form_sc,
        workflow_template_secure_code=f'wf_{case_sc}',
        execution_code=f'OD-{case_sc}',
        status=status,
        started_at=datetime.utcnow(),
    )
    event = OdIntakeEvent(
        secure_code=f'event_{case_sc}',
        org_secure_code=org_secure_code,
        correlation_id=correlation_id,
        intake_key_secure_code=f'key_{case_sc}',
        source_system=source_system,
        event_class=event_class,
        severity_id=severity_id,
        raw_body={'native' if event_class == 'native' else 'ocsf': True},
        signature_verified=True,
        case_secure_code=case_sc,
        received_at=received_at or datetime.utcnow(),
    )
    db.session.add_all([form, workflow, event])
    db.session.flush()
    return workflow


def _find(payload_kind='native', source_system='SPLUNK', severity_id=4, axis=None, config=None, template_sc=TEMPLATE_SC):
    config = config or effective_config(None)
    key = resolve_group_key(
        rule_secure_code='rule_test',
        axis=axis or _axis(source_system=source_system, severity_id=severity_id),
        client_key=None,
        config=config,
        payload_kind=payload_kind,
        source_system=source_system,
    )
    return find_mergeable_case(
        org_secure_code=ORG_SC,
        form_template_secure_code=template_sc,
        group_key=key,
        severity_id=severity_id,
        config=config,
    )


def test_resolve_group_key_fail_closed_for_invalid_payload_kind(caplog):
    caplog.set_level(logging.WARNING)

    result = resolve_group_key(
        rule_secure_code='rule_test',
        axis=_axis(),
        client_key=None,
        config=effective_config(None),
        payload_kind='unexpected',
        source_system='SPLUNK',
    )

    assert result is None
    assert 'invalid payload_kind' in caplog.text


def test_resolve_group_key_fail_closed_for_native_missing_source_system(caplog):
    caplog.set_level(logging.WARNING)

    result = resolve_group_key(
        rule_secure_code='rule_test',
        axis=_axis(),
        client_key=None,
        config=effective_config(None),
        payload_kind='native',
        source_system=None,
    )

    assert result is None
    assert 'missing source_system' in caplog.text


@pytest.mark.parametrize(
    ('actor_ip', 'rule_id'),
    [
        (None, 'AV-017A'),
        ('', 'AV-017A'),
        ('198.51.100.10', None),
        ('198.51.100.10', ''),
    ],
)
def test_resolve_group_key_skips_missing_axis(actor_ip, rule_id):
    assert resolve_group_key(
        rule_secure_code='rule_test',
        axis=_axis(actor_ip=actor_ip, finding_rule_id=rule_id),
        client_key=None,
        config=effective_config(None),
        payload_kind='native',
        source_system='SPLUNK',
    ) is None


def test_native_same_source_same_axis_finds_case(app, db_session):
    _require_od_aggregation_tables()
    workflow = _case_record(
        case_sc='case_native_same',
        form_sc='form_native_same',
        correlation_id='corr-native-same',
        event_class='native',
        source_system='SPLUNK',
    )

    result = _find('native', 'SPLUNK')

    assert result.secure_code == workflow.secure_code


def test_native_different_source_system_does_not_match(app, db_session):
    _require_od_aggregation_tables()
    _case_record(
        case_sc='case_native_other_source',
        form_sc='form_native_other_source',
        correlation_id='corr-native-other-source',
        event_class='native',
        source_system='SPLUNK',
    )

    assert _find('native', 'OTHER_SOC') is None


def test_native_payload_does_not_match_ocsf_case(app, db_session):
    _require_od_aggregation_tables()
    _case_record(
        case_sc='case_ocsf_only',
        form_sc='form_ocsf_only',
        correlation_id='corr-ocsf-only',
        event_class='network_activity',
        source_system='suricata',
    )

    assert _find('native', 'suricata') is None


def test_ocsf_payload_does_not_match_native_case(app, db_session):
    _require_od_aggregation_tables()
    _case_record(
        case_sc='case_native_only',
        form_sc='form_native_only',
        correlation_id='corr-native-only',
        event_class='native',
        source_system='SPLUNK',
    )

    assert _find('ocsf', 'SPLUNK') is None


def test_ocsf_same_axis_still_finds_ocsf_case(app, db_session):
    _require_od_aggregation_tables()
    workflow = _case_record(
        case_sc='case_ocsf_same',
        form_sc='form_ocsf_same',
        correlation_id='corr-ocsf-same',
        event_class='network_activity',
        source_system='suricata',
    )

    result = _find('ocsf', 'suricata')

    assert result.secure_code == workflow.secure_code


def test_outside_aggregation_window_does_not_match(app, db_session):
    _require_od_aggregation_tables()
    outside_window = datetime.utcnow() - timedelta(
        minutes=AGGREGATION_WINDOW_MINUTES + 1
    )
    _case_record(
        case_sc='case_outside_window',
        form_sc='form_outside_window',
        correlation_id='corr-outside-window',
        event_class='native',
        source_system='SPLUNK',
        created_at=outside_window,
    )

    assert _find('native', 'SPLUNK') is None


def test_effective_config_defaults_and_partial_override():
    assert effective_config(None) == DEFAULT_AGGREGATION

    config = effective_config({'window_minutes': 5, 'group_by': ['target_host']})

    assert config['window_minutes'] == 5
    assert config['group_by'] == ['target_host']
    assert config['enabled'] is True
    assert config['window_from'] == 'first_seen'


@pytest.mark.parametrize(
    'value',
    [
        {'enabled': True, 'group_by': ['actor_ip'], 'window_minutes': 1, 'window_from': 'last_seen', 'merge_closed_max_severity': -1},
        None,
    ],
)
def test_validate_aggregation_accepts_valid(value):
    assert validate_aggregation(value)[0] is True


@pytest.mark.parametrize(
    'value',
    [
        {'unknown': True},
        {'group_by': ['occurred_at']},
        {'window_minutes': 0},
        {'window_from': 'created'},
    ],
)
def test_validate_aggregation_rejects_invalid_shapes(value):
    ok, message = validate_aggregation(value)
    assert not ok
    assert message


def test_resolve_group_key_client_precedence_disabled_hash_and_kind_suffixes():
    axis = _axis()
    config = effective_config({'group_by': ['actor_ip']})

    assert resolve_group_key(
        rule_secure_code='rule_test',
        axis=axis,
        client_key=' client-1 ',
        config=config,
        payload_kind='ocsf',
        source_system='SPLUNK',
    ) == 'client:client-1'
    assert resolve_group_key(
        rule_secure_code='rule_test',
        axis=_axis(actor_ip=''),
        client_key=None,
        config=config,
        payload_kind='ocsf',
        source_system='SPLUNK',
    ) is None
    assert resolve_group_key(
        rule_secure_code='rule_test',
        axis=axis,
        client_key=None,
        config=effective_config({'enabled': False}),
        payload_kind='ocsf',
        source_system='SPLUNK',
    ) is None

    hashed = resolve_group_key(
        rule_secure_code='rule_test',
        axis=axis,
        client_key='x' * 129,
        config=config,
        payload_kind='ocsf',
        source_system='SPLUNK',
    )
    assert hashed.startswith('client:h:')
    assert len(hashed) == len('client:h:') + 32

    native = resolve_group_key(
        rule_secure_code='rule_test',
        axis=axis,
        client_key=None,
        config=config,
        payload_kind='native',
        source_system='SPLUNK',
    )
    ocsf = resolve_group_key(
        rule_secure_code='rule_test',
        axis=axis,
        client_key=None,
        config=config,
        payload_kind='ocsf',
        source_system='SPLUNK',
    )
    trigger = resolve_group_key(
        rule_secure_code='rule_test',
        axis=axis,
        client_key=None,
        config=config,
        payload_kind='trigger',
        source_system='SPLUNK',
    )
    assert '\x1fsrc=SPLUNK' in native
    assert len({native, ocsf, trigger}) == 3


def test_find_mergeable_case_last_seen_window_extends_case(app, db_session):
    _require_od_aggregation_tables()
    old = datetime.utcnow() - timedelta(minutes=61)
    _case_record(
        case_sc='case_last_seen_recent',
        form_sc='form_last_seen_recent',
        correlation_id='corr-last-seen',
        event_class='native',
        source_system='SPLUNK',
        created_at=old,
        od_last_seen=(datetime.utcnow() - timedelta(minutes=5)).isoformat() + 'Z',
    )

    assert _find('native', 'SPLUNK', config=effective_config({'window_from': 'last_seen'})) is not None
    assert _find('native', 'SPLUNK', config=effective_config({'window_from': 'first_seen'})) is None


def test_find_mergeable_case_completed_threshold(app, db_session):
    _require_od_aggregation_tables()
    _case_record(
        case_sc='case_completed',
        form_sc='form_completed',
        correlation_id='corr-completed',
        event_class='native',
        source_system='SPLUNK',
        status='COMPLETED',
    )

    assert _find('native', 'SPLUNK', severity_id=3) is None
    assert _find('native', 'SPLUNK', severity_id=2) is not None
    assert _find('native', 'SPLUNK', severity_id=2, config=effective_config({'merge_closed_max_severity': -1})) is None


def test_merge_event_updates_jsonb_and_flush_persists(app, db_session):
    _require_od_aggregation_tables()
    workflow = _case_record(
        case_sc='case_merge_updates',
        form_sc='form_merge_updates',
        correlation_id='corr-merge-updates',
        event_class='native',
        source_system='SPLUNK',
        severity_id=2,
    )
    summary = build_event_summary(
        event_sc='event-new',
        received_at=datetime.utcnow(),
        axis=_axis(severity_id=5, actor_ip='203.0.113.8'),
        finding_title='Escalated',
        source_system='SPLUNK',
    )

    merge_event(
        workflow_instance=workflow,
        event_summary=summary,
        axis=_axis(severity_id=5, actor_ip='203.0.113.8'),
    )
    db.session.flush()
    db.session.expire_all()

    form = FwFormInstance.query.filter_by(secure_code='form_merge_updates').first()
    assert form.form_data['od_event_count'] == 2
    assert form.form_data['severity_id'] == 5
    assert form.form_data['od_events'][-1]['event_sc'] == 'event-new'
    assert form.form_data['od_actor_ips'] == ['198.51.100.10', '203.0.113.8']


def test_append_event_keeps_earliest_and_latest_with_truncation_count():
    form_data = {'od_events': [{'n': n} for n in range(249)]}
    append_event(form_data, {'n': 249})

    assert len(form_data['od_events']) == 200
    assert [item['n'] for item in form_data['od_events'][:100]] == list(range(100))
    assert [item['n'] for item in form_data['od_events'][100:]] == list(range(150, 250))
    assert form_data['od_events_truncated'] == 50


def _schema():
    keys = [
        'severity_id',
        'actor_ip',
        'target_host',
        'source_system',
        'finding_rule_id',
        'occurred_at',
        'finding_title',
    ]
    return {'components': [{'type': 'textfield', 'key': key, 'input': True} for key in keys]}


def _published_fixture(category_sc):
    suffix = category_sc.replace('CAT_', '').lower()
    template = FwFormTemplate(
        secure_code=f'tmpl_{suffix}',
        org_secure_code=ORG_SC,
        code=f'FORM_{suffix}',
        name='Trigger Form',
        category_secure_code=category_sc,
        schema=_schema(),
        version='AA',
        is_published=True,
        is_active=True,
    )
    db.session.add(template)
    db.session.flush()
    published = FwPublishedFormWorkflow(
        secure_code=f'pub_{suffix}',
        org_secure_code=ORG_SC,
        source_mapping_id=1,
        source_mapping_secure_code=f'map_{suffix}',
        source_form_template_id=template.id,
        source_form_template_secure_code=template.secure_code,
        source_form_version='AA',
        source_form_revision=1,
        source_workflow_template_id=1,
        source_workflow_template_secure_code=f'wf_tmpl_{suffix}',
        source_workflow_version='AA',
        source_workflow_revision=1,
        publish_version=1,
        name='Published Trigger Form',
        form_snapshot={'name': template.name, 'code': template.code, 'schema': _schema(), 'builder_config': {}},
        workflow_snapshot={'name': 'WF', 'graph': {'nodes': [{'id': 'node-Start-1', 'type': 'Start'}], 'edges': []}},
        status='Published',
    )
    db.session.add(published)
    db.session.flush()
    return template, published


def _api_key_fixture(monkeypatch):
    secret = b'0123456789abcdef0123456789abcdef'
    key = ApiKey(
        secure_code='api_key_trigger_test',
        org_secure_code=ORG_SC,
        key_id='ak_trigger_test',
        name='Trigger Test',
        secret_ciphertext=b'x',
        secret_file_nonce=b'x',
        secret_wrapped_dek='x',
        secret_dek_nonce='x',
        secret_encryption_key_sc='x',
        scopes={'form_category': ['CAT_SECURITY_testcase', 'CAT_GENERAL_testcase']},
        status='active',
    )
    db.session.add(key)
    db.session.flush()

    from app.services import api_key_service
    monkeypatch.setattr(api_key_service, 'decrypt_secret', lambda record: secret)
    return key, secret


def _trigger_client(app):
    endpoint = 'form_workflow_external_trigger.trigger_form'
    if endpoint not in app.view_functions:
        from modules.form_workflow.api.external_trigger import external_trigger_bp
        app.register_blueprint(external_trigger_bp)
    for name in (
        'form_workflow_external_trigger.trigger_form',
        'form_workflow_external_trigger.list_triggerable_forms',
    ):
        if name in app.view_functions:
            app.view_functions[name]._public_route = True
    return app.test_client()


def _signed_post(app, key, secret, payload):
    body = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    ts = str(int(time.time()))
    return _trigger_client(app).post(
        '/beakplatform/api/trigger/form',
        data=body,
        headers={
            'Content-Type': 'application/json',
            'X-BP-Key-Id': key.key_id,
            'X-BP-Timestamp': ts,
            'X-BP-Signature': compute_signature(secret, ts, body),
        },
    )


def _trigger_payload(form_code, actor_ip='198.51.100.10', case_group_key=None):
    payload = {
        'form_code': form_code,
        'subject': 'Trigger aggregation',
        'form_data': {
            'severity_id': 3,
            'actor_ip': actor_ip,
            'target_host': 'host-1',
            'source_system': 'manual',
            'finding_rule_id': 'RULE-1',
            'occurred_at': '2026-09-25T00:00:00Z',
            'finding_title': 'Manual finding',
        },
    }
    if case_group_key is not None:
        payload['case_group_key'] = case_group_key
    return payload


def test_trigger_security_form_merges_but_general_form_creates_each_time(app, db_session, monkeypatch):
    key, secret = _api_key_fixture(monkeypatch)
    security_template, _security_published = _published_fixture('CAT_SECURITY_testcase')
    general_template, _general_published = _published_fixture('CAT_GENERAL_testcase')

    first = _signed_post(app=app, key=key, secret=secret, payload=_trigger_payload(security_template.code))
    second = _signed_post(app=app, key=key, secret=secret, payload=_trigger_payload(security_template.code))

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.get_json()['merged'] is True
    assert second.get_json()['data']['merged_into']['od_event_count'] == 2

    general_first = _signed_post(app=app, key=key, secret=secret, payload=_trigger_payload(general_template.code))
    general_second = _signed_post(app=app, key=key, secret=secret, payload=_trigger_payload(general_template.code))

    assert general_first.status_code == 201
    assert general_second.status_code == 201


def test_trigger_case_group_key_non_string_is_rejected(app, db_session, monkeypatch):
    key, secret = _api_key_fixture(monkeypatch)
    security_template, _published = _published_fixture('CAT_SECURITY_testcase')
    payload = _trigger_payload(security_template.code, case_group_key={'bad': True})

    response = _signed_post(app=app, key=key, secret=secret, payload=payload)

    assert response.status_code == 400
    assert response.get_json()['error'] == 'invalid_case_group_key'
