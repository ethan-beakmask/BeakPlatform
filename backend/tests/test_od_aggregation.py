import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import inspect

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db
from modules.form_workflow.models import FwFormInstance, FwWorkflowInstance
from modules.open_defense.models import OdIntakeEvent
from modules.open_defense.services.intake_service import (
    AGGREGATION_WINDOW_MINUTES,
    _find_mergeable_case,
)


ORG_SC = 'test_org_00000000001'


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
    org_secure_code=ORG_SC,
    status='RUNNING',
):
    form = FwFormInstance(
        secure_code=form_sc,
        org_secure_code=org_secure_code,
        form_template_secure_code=f'tmpl_{form_sc}',
        serial_number=f'SN-{form_sc}',
        form_data={
            'actor_ip': actor_ip,
            'finding_rule_id': rule_id,
            'severity_id': 4,
            'source_system': source_system,
            'occurred_at': '2026-08-10T00:00:00Z',
            'target_host': 'host-1',
        },
        status='INITIAL',
        source_type='WEBHOOK_OD',
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
        severity_id=4,
        raw_body={'native' if event_class == 'native' else 'ocsf': True},
        signature_verified=True,
        case_secure_code=case_sc,
        received_at=received_at or datetime.utcnow(),
    )
    db.session.add_all([form, workflow, event])
    db.session.flush()
    return workflow


def test_find_mergeable_case_fail_closed_without_db_for_invalid_payload_kind(caplog):
    caplog.set_level(logging.WARNING)

    result = _find_mergeable_case(
        org_secure_code=ORG_SC,
        actor_ip='198.51.100.10',
        rule_id='AV-017A',
        severity_id=4,
        payload_kind='unexpected',
    )

    assert result is None
    assert 'invalid payload_kind' in caplog.text


def test_find_mergeable_case_fail_closed_without_db_for_native_missing_source_system(caplog):
    caplog.set_level(logging.WARNING)

    result = _find_mergeable_case(
        org_secure_code=ORG_SC,
        actor_ip='198.51.100.10',
        rule_id='AV-017A',
        severity_id=4,
        payload_kind='native',
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
def test_find_mergeable_case_skips_missing_axis_without_db(actor_ip, rule_id):
    assert _find_mergeable_case(
        org_secure_code=ORG_SC,
        actor_ip=actor_ip,
        rule_id=rule_id,
        severity_id=4,
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

    result = _find_mergeable_case(
        ORG_SC, '198.51.100.10', 'AV-017A', 4, 'native', 'SPLUNK'
    )

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

    result = _find_mergeable_case(
        ORG_SC, '198.51.100.10', 'AV-017A', 4, 'native', 'OTHER_SOC'
    )

    assert result is None


def test_native_payload_does_not_match_ocsf_case(app, db_session):
    _require_od_aggregation_tables()
    _case_record(
        case_sc='case_ocsf_only',
        form_sc='form_ocsf_only',
        correlation_id='corr-ocsf-only',
        event_class='network_activity',
        source_system='suricata',
    )

    result = _find_mergeable_case(
        ORG_SC, '198.51.100.10', 'AV-017A', 4, 'native', 'suricata'
    )

    assert result is None


def test_ocsf_payload_does_not_match_native_case(app, db_session):
    _require_od_aggregation_tables()
    _case_record(
        case_sc='case_native_only',
        form_sc='form_native_only',
        correlation_id='corr-native-only',
        event_class='native',
        source_system='SPLUNK',
    )

    result = _find_mergeable_case(
        ORG_SC, '198.51.100.10', 'AV-017A', 4, 'ocsf'
    )

    assert result is None


def test_ocsf_same_axis_still_finds_ocsf_case(app, db_session):
    _require_od_aggregation_tables()
    workflow = _case_record(
        case_sc='case_ocsf_same',
        form_sc='form_ocsf_same',
        correlation_id='corr-ocsf-same',
        event_class='network_activity',
        source_system='suricata',
    )

    result = _find_mergeable_case(
        ORG_SC, '198.51.100.10', 'AV-017A', 4, 'ocsf'
    )

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
        received_at=outside_window,
    )

    result = _find_mergeable_case(
        ORG_SC, '198.51.100.10', 'AV-017A', 4, 'native', 'SPLUNK'
    )

    assert result is None
