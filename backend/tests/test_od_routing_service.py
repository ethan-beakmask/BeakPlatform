import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db
from modules.open_defense.models import OdFormTemplateMapping
from modules.open_defense.services.routing_service import (
    resolve_form_template,
    validate_match_rules,
)


ORG_SC = 'test_org_00000000001'


def _body(**overrides):
    body = {
        'correlation_id': 'corr-1',
        'source_system': 'suricata',
        'event_class': 'network_activity',
        'occurred_at': '2026-08-09T00:00:00Z',
        'severity_id': 4,
        'confidence': 80,
        'finding': {
            'title': 'ET MALWARE',
            'rule_id': '2013504',
        },
        'actor': {
            'ip': '198.51.100.10',
            'country': 'TW',
            'user_agent': 'curl/8.0',
        },
        'target': {
            'host': 'db.internal',
            'url': '/login.php',
            'service': 'mysql',
        },
        'evidence': {},
        'detector_hint': {},
    }
    body.update(overrides)
    return body


def _rule(
    *,
    org_secure_code=ORG_SC,
    event_class=None,
    form_template_secure_code='tmpl_default',
    priority=0,
    match_rules=None,
    is_active=True,
    name='rule',
):
    record = OdFormTemplateMapping(
        org_secure_code=org_secure_code,
        event_class=event_class,
        form_template_secure_code=form_template_secure_code,
        priority=priority,
        match_rules=match_rules,
        is_active=is_active,
        name=name,
        is_deleted=False,
    )
    db.session.add(record)
    db.session.flush()
    return record


def test_legacy_event_class_mapping_still_matches(app, db_session):
    _rule(
        event_class='network_activity',
        form_template_secure_code='tmpl_network',
        match_rules=None,
        priority=0,
    )
    _rule(
        event_class='web_activity',
        form_template_secure_code='tmpl_web',
        match_rules=None,
        priority=0,
    )

    assert resolve_form_template(ORG_SC, _body()) == 'tmpl_network'


def test_priority_then_id_order(app, db_session):
    first = _rule(form_template_secure_code='tmpl_first', priority=5)
    second = _rule(form_template_secure_code='tmpl_second', priority=5)
    high = _rule(form_template_secure_code='tmpl_high', priority=10)

    assert first.id < second.id < high.id
    assert resolve_form_template(ORG_SC, _body()) == 'tmpl_high'

    high.is_active = False
    db.session.flush()
    assert resolve_form_template(ORG_SC, _body()) == 'tmpl_first'


@pytest.mark.parametrize(
    ('condition', 'matched_body', 'unmatched_body'),
    [
        ({'field': 'source_system', 'op': 'eq', 'value': 'SURICATA'}, _body(), _body(source_system='coraza')),
        ({'field': 'source_system', 'op': 'ne', 'value': 'coraza'}, _body(), _body(source_system='coraza')),
        ({'field': 'target.service', 'op': 'in', 'value': ['postgres', 'MYSQL']}, _body(), _body(target={'service': 'redis'})),
        ({'field': 'target.service', 'op': 'not_in', 'value': ['redis']}, _body(), _body(target={'service': 'redis'})),
        ({'field': 'severity_id', 'op': 'gt', 'value': 3}, _body(), _body(severity_id=3)),
        ({'field': 'severity_id', 'op': 'gte', 'value': 4}, _body(), _body(severity_id=3)),
        ({'field': 'severity_id', 'op': 'lt', 'value': 5}, _body(), _body(severity_id=5)),
        ({'field': 'severity_id', 'op': 'lte', 'value': 4}, _body(), _body(severity_id=5)),
        ({'field': 'finding.title', 'op': 'contains', 'value': 'malware'}, _body(), _body(finding={'title': 'Benign', 'rule_id': '2013504'})),
        ({'field': 'finding.rule_id', 'op': 'startswith', 'value': '2013'}, _body(), _body(finding={'title': 'ET MALWARE', 'rule_id': '9999'})),
        ({'field': 'target.url', 'op': 'endswith', 'value': '.PHP'}, _body(), _body(target={'url': '/index.html', 'service': 'mysql'})),
        ({'field': 'actor.ip', 'op': 'exists', 'value': True}, _body(), _body(actor={'ip': '', 'country': 'TW'})),
        ({'field': 'actor.asn', 'op': 'exists', 'value': False}, _body(), _body(actor={'ip': '198.51.100.10', 'asn': 64512})),
    ],
)
def test_supported_ops_match_and_do_not_match(app, db_session, condition, matched_body, unmatched_body):
    _rule(
        form_template_secure_code='tmpl_match',
        match_rules=[condition],
    )

    assert resolve_form_template(ORG_SC, matched_body) == 'tmpl_match'
    assert resolve_form_template(ORG_SC, unmatched_body) is None


def test_numeric_ops_fail_closed_for_non_numbers(app, db_session):
    _rule(
        form_template_secure_code='tmpl_number',
        match_rules=[{'field': 'severity_id', 'op': 'gte', 'value': 4}],
    )

    assert resolve_form_template(ORG_SC, _body(severity_id='4')) is None


def test_missing_field_condition_fails_closed(app, db_session):
    _rule(
        form_template_secure_code='tmpl_missing',
        match_rules=[{'field': 'target.database.name', 'op': 'eq', 'value': 'prod'}],
    )

    assert resolve_form_template(ORG_SC, _body()) is None


def test_inactive_rule_is_not_considered(app, db_session):
    _rule(
        form_template_secure_code='tmpl_inactive',
        match_rules=[{'field': 'source_system', 'op': 'eq', 'value': 'suricata'}],
        is_active=False,
    )

    assert resolve_form_template(ORG_SC, _body()) is None


def test_invalid_db_match_rules_do_not_raise(app, db_session, caplog):
    _rule(
        form_template_secure_code='tmpl_bad',
        match_rules={'field': 'source_system', 'op': 'eq', 'value': 'suricata'},
    )

    assert resolve_form_template(ORG_SC, _body()) is None
    assert 'od routing rule invalid' in caplog.text


def test_validate_match_rules_rejects_unknown_op_and_regex(app):
    ok, message = validate_match_rules([
        {'field': 'source_system', 'op': 'unknown', 'value': 'suricata'},
    ])
    assert not ok
    assert '不支援' in message

    ok, message = validate_match_rules([
        {'field': 'finding.title', 'op': 'regex', 'value': '.*'},
    ])
    assert not ok
    assert '不支援' in message
