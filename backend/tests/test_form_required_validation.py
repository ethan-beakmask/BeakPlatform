import json
import os
import sys
import time
from datetime import timedelta
from pathlib import Path

from flask import session
from flask_login import login_user

os.environ.setdefault("SYSTEM_ORG_CODE", "system.local")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db  # noqa: E402
from app.models.api_key import ApiKey  # noqa: E402
from app.models.contract import Contract, ContractStatus  # noqa: E402
from app.security.hmac_verifier import compute_signature  # noqa: E402
from modules.form_workflow.api.fc_fill import submit_form  # noqa: E402
from modules.form_workflow.models import (  # noqa: E402
    FwFormTemplate,
    FwFormWorkflowMapping,
    FwMappingPermission,
    FwPublishedFormWorkflow,
    FwWorkflowTemplate,
)
from modules.form_workflow.services.form_submit_service import (  # noqa: E402
    extract_schema_field_keys,
    validate_required_fields,
)


ORG_SC = 'test_org_00000000001'


def _required_schema():
    return {
        'display': 'form',
        'components': [
            {
                'type': 'textfield',
                'key': 'expires_at',
                'label': 'Expires At',
                'input': True,
                'validate': {'required': True},
            },
        ],
    }


def _workflow_graph():
    return {'nodes': [{'id': 'node-Start-1', 'type': 'Start'}], 'edges': []}


def _published_form(*, org_sc=ORG_SC, suffix='required', schema=None):
    schema = schema or _required_schema()
    template = FwFormTemplate(
        secure_code=f'tmpl_{suffix}',
        org_secure_code=org_sc,
        code=f'FORM_{suffix}',
        name='Required Form',
        category_secure_code=f'CAT_GENERAL_{suffix}',
        schema=schema,
        version='AA',
        revision=1,
        is_published=True,
        is_active=True,
        is_deleted=False,
    )
    workflow = FwWorkflowTemplate(
        secure_code=f'wf_{suffix}',
        org_secure_code=org_sc,
        form_template_secure_code=template.secure_code,
        code=f'WF_{suffix}',
        name='Required Workflow',
        graph=_workflow_graph(),
        version='AA',
        revision=1,
        is_active=True,
        is_deleted=False,
    )
    db.session.add_all([template, workflow])
    db.session.flush()

    mapping = FwFormWorkflowMapping(
        secure_code=f'map_{suffix}',
        org_secure_code=org_sc,
        form_template_id=template.id,
        form_template_secure_code=template.secure_code,
        form_template_code=template.code,
        form_template_version=template.version,
        workflow_template_id=workflow.id,
        workflow_template_secure_code=workflow.secure_code,
        workflow_template_code=workflow.code,
        workflow_template_version=workflow.version,
        is_active=True,
        is_deleted=False,
    )
    db.session.add(mapping)
    db.session.flush()

    published = FwPublishedFormWorkflow(
        secure_code=f'pub_{suffix}',
        org_secure_code=org_sc,
        source_mapping_id=mapping.id,
        source_mapping_secure_code=mapping.secure_code,
        source_form_template_id=template.id,
        source_form_template_secure_code=template.secure_code,
        source_form_version=template.version,
        source_form_revision=template.revision,
        source_workflow_template_id=workflow.id,
        source_workflow_template_secure_code=workflow.secure_code,
        source_workflow_version=workflow.version,
        source_workflow_revision=workflow.revision,
        publish_version=1,
        name='Published Required Form',
        form_snapshot={
            'name': template.name,
            'code': template.code,
            'schema': schema,
            'builder_config': {},
        },
        workflow_snapshot={'name': workflow.name, 'graph': _workflow_graph()},
        status='Published',
        is_deleted=False,
    )
    db.session.add(published)
    db.session.commit()
    return template, mapping, published


def _api_key_fixture(monkeypatch, published):
    secret = b'0123456789abcdef0123456789abcdef'
    key = ApiKey(
        secure_code='api_key_required_test',
        org_secure_code=ORG_SC,
        key_id='ak_required_test',
        name='Required Test',
        secret_ciphertext=b'x',
        secret_file_nonce=b'x',
        secret_wrapped_dek='x',
        secret_dek_nonce='x',
        secret_encryption_key_sc='x',
        scopes={'form': [published.secure_code]},
        status='active',
    )
    db.session.add(key)
    db.session.commit()

    from app.services import api_key_service
    monkeypatch.setattr(api_key_service, 'decrypt_secret', lambda record: secret)
    return key, secret


def _trigger_client(app):
    endpoint = 'form_workflow_external_trigger.trigger_form'
    if endpoint not in app.view_functions:
        from modules.form_workflow.api.external_trigger import external_trigger_bp
        app.register_blueprint(external_trigger_bp)
    if endpoint in app.view_functions:
        app.view_functions[endpoint]._public_route = True
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


def _grant_form_workflow_contract(org):
    today = org.local_today()
    contract = Contract(
        secure_code=f'contract_fw_{org.secure_code[-8:]}',
        org_secure_code=org.secure_code,
        contract_number=f'CTR-FW-{org.secure_code[-8:]}',
        name='Form Workflow Test Contract',
        start_date=today - timedelta(days=1),
        end_date=today + timedelta(days=30),
        status=ContractStatus.ACTIVE,
        modules_config=json.dumps(['form_workflow']),
        is_deleted=False,
    )
    db.session.add(contract)
    db.session.commit()
    return contract


def _grant_user(org_sc, mapping_sc, user_sc):
    perm = FwMappingPermission(
        secure_code=f'perm_{mapping_sc}',
        org_secure_code=org_sc,
        mapping_secure_code=mapping_sc,
        grant_type='user',
        grant_target=user_sc,
        include_children=False,
        is_deleted=False,
    )
    db.session.add(perm)
    db.session.commit()
    return perm


def _login_in_request(user, org):
    login_user(user)
    session['org_secure_code'] = org.secure_code
    session['org_domain'] = org.domain_name


def _json_from_response(result):
    response = result[0] if isinstance(result, tuple) else result
    status = result[1] if isinstance(result, tuple) else response.status_code
    return status, response.get_json()


def _field(**overrides):
    data = {
        'type': 'textfield',
        'key': 'field_a',
        'label': 'Field A',
        'input': True,
        'validate': {'required': True},
    }
    data.update(overrides)
    return data


def test_required_textfield_missing_blank_and_present_values():
    schema = {'components': [_field()]}

    assert validate_required_fields(schema, {}) == [{'key': 'field_a', 'label': 'Field A'}]
    assert validate_required_fields(schema, {'field_a': ''}) == [{'key': 'field_a', 'label': 'Field A'}]
    assert validate_required_fields(schema, {'field_a': '  '}) == [{'key': 'field_a', 'label': 'Field A'}]
    assert validate_required_fields(schema, {'field_a': 'ok'}) == []


def test_required_empty_value_rules():
    schema = {'components': [
        _field(key='none_value'),
        _field(key='empty_list'),
        _field(key='empty_dict'),
        _field(key='zero_value'),
    ]}

    assert validate_required_fields(schema, {
        'none_value': None,
        'empty_list': [],
        'empty_dict': {},
        'zero_value': 0,
    }) == [
        {'key': 'none_value', 'label': 'Field A'},
        {'key': 'empty_list', 'label': 'Field A'},
        {'key': 'empty_dict', 'label': 'Field A'},
    ]


def test_required_checkbox_and_selectboxes_rules():
    schema = {'components': [
        _field(type='checkbox', key='agree'),
        _field(type='selectboxes', key='choices'),
    ]}

    assert validate_required_fields(schema, {
        'agree': False,
        'choices': {'a': False, 'b': False},
    }) == [
        {'key': 'agree', 'label': 'Field A'},
        {'key': 'choices', 'label': 'Field A'},
    ]
    assert validate_required_fields(schema, {
        'agree': True,
        'choices': {'a': False, 'b': True},
    }) == []


def test_non_required_and_conditional_or_hidden_fields_are_ignored():
    schema = {'components': [
        _field(key='optional', validate={}),
        _field(key='hidden_required', hidden=True),
        _field(key='conditional_required', conditional={'when': 'kind', 'eq': 'x'}),
        _field(key='custom_conditional_required', customConditional='show = false;'),
    ]}

    assert validate_required_fields(schema, {}) == []


def test_required_fields_in_layouts_but_not_input_containers():
    schema = {'components': [
        {'type': 'panel', 'components': [_field(key='panel_field')]},
        {'type': 'columns', 'columns': [
            {'components': [_field(key='column_field')]},
        ]},
        {'type': 'tabs', 'tabs': [
            {'components': [_field(key='tab_field')]},
        ]},
        {
            'type': 'datagrid',
            'key': 'items',
            'input': True,
            'components': [_field(key='nested_field')],
        },
    ]}

    assert validate_required_fields(schema, {}) == [
        {'key': 'panel_field', 'label': 'Field A'},
        {'key': 'column_field', 'label': 'Field A'},
        {'key': 'tab_field', 'label': 'Field A'},
    ]


def test_label_fallback_and_schema_order_are_preserved():
    schema = {'components': [
        _field(key='first', label='First'),
        _field(key='second', label=''),
    ]}

    assert validate_required_fields(schema, {}) == [
        {'key': 'first', 'label': 'First'},
        {'key': 'second', 'label': 'second'},
    ]


def test_extract_schema_field_keys_includes_tabs():
    schema = {'components': [
        {'type': 'tabs', 'tabs': [
            {'components': [_field(key='tab_key')]},
        ]},
    ]}

    assert extract_schema_field_keys(schema) == {'tab_key'}


def test_trigger_form_rejects_missing_required_field_and_accepts_present_value(
        app, db_session, monkeypatch):
    _template, _mapping, published = _published_form(suffix='trigger_required')
    key, secret = _api_key_fixture(monkeypatch, published)

    missing_response = _signed_post(app, key, secret, {
        'published_secure_code': published.secure_code,
        'subject': 'Trigger required test',
        'form_data': {},
    })
    assert missing_response.status_code == 400
    missing_body = missing_response.get_json()
    assert missing_body['error'] == 'missing_required_fields'
    assert missing_body['details']['missing_keys'] == ['expires_at']

    ok_response = _signed_post(app, key, secret, {
        'published_secure_code': published.secure_code,
        'subject': 'Trigger required test',
        'form_data': {'expires_at': '2026-12-31'},
    })
    assert ok_response.status_code == 201
    assert ok_response.get_json()['success'] is True
    assert ok_response.get_json()['data']['form_instance_secure_code']


def test_fc_fill_rejects_missing_required_field_before_serial_allocation(
        app, test_org, test_admin):
    _grant_form_workflow_contract(test_org)
    _template, mapping, published = _published_form(
        org_sc=test_org.secure_code,
        suffix='fc_required',
    )
    _grant_user(test_org.secure_code, mapping.secure_code, test_admin.secure_code)

    with app.test_request_context('/api/form-center/submit', method='POST', json={
        'published_secure_code': published.secure_code,
        'subject': 'FC required test',
        'form_data': {},
    }):
        _login_in_request(test_admin, test_org)
        status, body = _json_from_response(submit_form())

    assert status == 400
    assert body['error_code'] == 'missing_required_fields'
    assert body['details']['missing_keys'] == ['expires_at']

    with app.test_request_context('/api/form-center/submit', method='POST', json={
        'published_secure_code': published.secure_code,
        'subject': 'FC required test',
        'form_data': {'expires_at': '2026-12-31'},
    }):
        _login_in_request(test_admin, test_org)
        status, body = _json_from_response(submit_form())

    assert not (
        status == 400 and body.get('error_code') == 'missing_required_fields'
    )
