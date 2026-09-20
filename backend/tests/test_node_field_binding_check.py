from modules.form_workflow.services.node_field_binding_check import (
    check_node_field_bindings,
)
from app.defaults.api_key_request_defaults import (
    FORM_SCHEMA as API_KEY_FORM_SCHEMA,
    build_graph as build_api_key_graph,
)
from app.defaults.proxy_request_defaults import (
    FORM_SCHEMA as PROXY_FORM_SCHEMA,
    build_graph as build_proxy_graph,
)


def _schema(components):
    return {'display': 'form', 'components': components}


def _graph(node_type, config=None, label='測試節點'):
    return {'nodes': [{'id': 'node-1', 'type': node_type, 'label': label,
                       'config': config or {}}]}


def test_api_key_issue_binding_accepts_defaults_and_nested_fields():
    schema = _schema([
        {
            'type': 'panel',
            'key': 'panel',
            'components': [
                {'key': 'beneficiary', 'type': 'userPicker'},
                {'key': 'authorized_forms', 'type': 'formPicker',
                 'beneficiaryKey': 'beneficiary'},
            ],
        },
    ])

    assert check_node_field_bindings(schema, _graph('ApiKeyIssue')) == []


def test_api_key_issue_binding_rejects_wrong_beneficiary_key():
    schema = _schema([
        {'key': 'key_owner', 'type': 'userPicker'},
        {'key': 'scope_forms', 'type': 'formPicker'},
    ])
    graph = _graph('ApiKeyIssue', {
        'beneficiary_field': 'key_owner',
        'forms_field': 'scope_forms',
    }, label='核發 API Key')

    errors = check_node_field_bindings(schema, graph)

    assert len(errors) == 1
    assert '核發 API Key' in errors[0]
    assert 'scope_forms' in errors[0]
    assert 'key_owner' in errors[0]


def test_api_key_issue_binding_rejects_missing_or_wrong_types():
    schema = _schema([
        {'key': 'beneficiary', 'type': 'textfield'},
        {'key': 'authorized_forms', 'type': 'proxyFormPicker'},
    ])

    errors = check_node_field_bindings(schema, _graph('ApiKeyIssue'))

    assert len(errors) == 2
    assert any('人員選擇' in err for err in errors)
    assert any('API表單選擇' in err for err in errors)


def test_op_proxy_grant_accepts_optional_missing_forms_field():
    schema = _schema([
        {'key': 'proxy_roles', 'type': 'myRolePicker'},
        {'key': 'delegate', 'type': 'userPicker'},
    ])

    assert check_node_field_bindings(schema, _graph('OpProxyGrant')) == []


def test_op_proxy_grant_rejects_wrong_field_types():
    schema = _schema([
        {'key': 'proxy_roles', 'type': 'textfield'},
        {'key': 'delegate', 'type': 'textfield'},
        {'key': 'authorized_forms', 'type': 'formPicker'},
    ])

    errors = check_node_field_bindings(schema, _graph('OpProxyGrant'))

    assert len(errors) == 3
    assert any('可委任角色選擇' in err for err in errors)
    assert any('人員選擇' in err for err in errors)
    assert any('代理限定表單選擇' in err for err in errors)


def test_default_api_key_proxy_and_nt04_fixed_schemas_pass():
    api_graph = build_api_key_graph('org_admin_role', '/icon.svg')
    proxy_graph = build_proxy_graph('/icon.svg')
    nt04_schema = _schema([
        {'key': 'key_owner', 'type': 'userPicker'},
        {'key': 'scope_forms', 'type': 'formPicker', 'beneficiaryKey': 'key_owner'},
    ])
    nt04_graph = _graph('ApiKeyIssue', {
        'beneficiary_field': 'key_owner',
        'forms_field': 'scope_forms',
    })

    assert check_node_field_bindings(API_KEY_FORM_SCHEMA, api_graph) == []
    assert check_node_field_bindings(PROXY_FORM_SCHEMA, proxy_graph) == []
    assert check_node_field_bindings(nt04_schema, nt04_graph) == []


def test_nt04_old_missing_beneficiary_key_is_caught():
    schema = _schema([
        {'key': 'key_owner', 'type': 'userPicker'},
        {'key': 'scope_forms', 'type': 'formPicker'},
    ])
    graph = _graph('ApiKeyIssue', {
        'beneficiary_field': 'key_owner',
        'forms_field': 'scope_forms',
    })

    errors = check_node_field_bindings(schema, graph)

    assert errors
    assert 'beneficiary_field' in errors[0]
