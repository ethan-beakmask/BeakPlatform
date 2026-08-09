import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from modules.open_defense.services.payload_profile_service import (
    build_native_form_data,
    extract_details,
    flatten_payload,
    normalize_axis_fields,
    resolve_correlation_id,
    validate_profile_payload,
)


SAMPLE_PAYLOAD = {
    'DataSource': 'SPLUNK',
    'Summary': {
        'AlertSource': '192.0.2.1:0',
        'CustomerName': 'SAMPLECORP',
        'RawIdentifier': 'AV-017A-202608090025-1',
        'RuleId': 'AV-017A',
        'Severity': 2,
        'AlertDate': '2026-08-08T16:25:38Z',
        'SrcIP': '',
        'DestIP': '192.0.2.10,192.0.2.11',
        'DeviceName': 'SAMPLE-00000-0000',
        'Action': 'allowed',
        'EventCount': 1,
        'IncidentRemedy': 'Review endpoint and isolate if needed.',
        'SignatureList': [],
        'OpenTicketFlag': True,
        'Parameter': 'Long analysis parameter text.',
    },
    'EventContents': [
        {
            'Content': {
                'EventDate': '2026-08-08T16:25:38Z',
                'EventName': 'Local Analysis Malware',
                'SeverityID': 4,
                'SrcIPStr': '',
                'DestIPStr': '192.0.2.10,192.0.2.11',
                'EventDirection': 0,
            },
        },
    ],
    'Extensions': [
        {
            'PropertyName': 'RxFileName',
            'PropertyValue': '20260809@002553{sample}.sdr',
        },
        {
            'PropertyName': 'RxFileTime',
            'PropertyValue': '2026-08-08T16:25:53Z',
        },
    ],
}


def _profile(**overrides):
    data = {
        'code': 'soc_native',
        'source_system': 'SPLUNK',
        'correlation_id_path': 'Summary.RawIdentifier',
        'field_map': {
            'severity_id': 'Summary.Severity',
            'actor_ip': 'Summary.SrcIP',
            'target_host': 'Summary.DeviceName',
            'source_system': '',
            'finding_rule_id': 'Summary.RuleId',
            'occurred_at': 'Summary.AlertDate',
        },
        'severity_map': {'1': 5, '2': 4, '3': 3},
        'detail_path': 'EventContents',
        'detail_item_key': 'Content',
        'kv_expansions': [
            {
                'path': 'Extensions',
                'key_field': 'PropertyName',
                'value_field': 'PropertyValue',
                'prefix': 'Extensions',
            },
        ],
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_flatten_payload_keeps_summary_keys_and_skips_detail_path(app):
    flat = flatten_payload(SAMPLE_PAYLOAD, detail_path='EventContents')

    assert flat['Summary.RuleId'] == 'AV-017A'
    assert 'EventContents' not in flat


def test_kv_expansions_emit_extension_keys(app):
    flat = flatten_payload(
        SAMPLE_PAYLOAD,
        kv_expansions=_profile().kv_expansions,
        detail_path='EventContents',
    )

    assert flat['Extensions.RxFileName'] == '20260809@002553{sample}.sdr'
    assert 'Extensions' not in flat


def test_extract_details_unwraps_event_content(app):
    details = extract_details(SAMPLE_PAYLOAD, 'EventContents', 'Content')

    assert details[0]['EventName'] == 'Local Analysis Malware'


def test_normalize_axis_fields_maps_severity_and_empty_actor_ip(app):
    axis = normalize_axis_fields(SAMPLE_PAYLOAD, _profile())

    assert axis['severity_id'] == 4
    assert axis['actor_ip'] is None
    assert axis['source_system'] == 'SPLUNK'


def test_resolve_correlation_id_normal_missing_and_long_hash(app):
    profile = _profile()

    assert resolve_correlation_id(SAMPLE_PAYLOAD, profile) == 'AV-017A-202608090025-1'
    assert resolve_correlation_id(SAMPLE_PAYLOAD, _profile(correlation_id_path='Summary.Missing')) is None

    payload = {'Summary': {'RawIdentifier': 'x' * 100}}
    value = resolve_correlation_id(payload, profile)
    assert value.startswith('h:')
    assert len(value) == 34


def test_build_native_form_data_reserved_axis_wins_over_flat_key(app):
    payload = dict(SAMPLE_PAYLOAD)
    payload['severity_id'] = 'flat-value'

    form_data = build_native_form_data(payload, _profile())

    assert form_data['severity_id'] == 4
    assert form_data['Summary.RuleId'] == 'AV-017A'
    assert form_data['EventContents'][0]['EventName'] == 'Local Analysis Malware'
    assert form_data['od_payload_profile'] == 'soc_native'


def test_validate_profile_payload_rejects_unknown_axis_key(app):
    body = {
        'code': 'soc_native',
        'name': 'SOC Native',
        'source_system': 'SPLUNK',
        'correlation_id_path': 'Summary.RawIdentifier',
        'field_map': {
            'severity_id': 'Summary.Severity',
            'actor_ip': 'Summary.SrcIP',
            'target_host': 'Summary.DeviceName',
            'source_system': '',
            'finding_rule_id': 'Summary.RuleId',
            'occurred_at': 'Summary.AlertDate',
            'extra_key': 'Summary.Action',
        },
    }

    ok, message = validate_profile_payload(body)
    assert not ok
    assert 'field_map' in message
