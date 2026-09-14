import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db
from app.defaults.proxy_request_defaults import (
    MAPPING_PERMISSION_SPECS,
    build_graph,
    seed_org_proxy_request_flow,
    validate_graph,
)

from modules.form_workflow.models import (
    FwFormTemplate,
    FwFormWorkflowMapping,
    FwMappingPermission,
    FwPublishedFormWorkflow,
    FwWorkflowTemplate,
)  # noqa: E402


def test_proxy_request_graph_is_valid_and_dynamic_assignee_is_wired():
    graph = build_graph('/static/modules/form_workflow/icons/workflow/opproxygrant.svg')

    assert validate_graph(graph) == []
    consent = next(node for node in graph['nodes'] if node['id'] == 'node-FormAdapter-consent')
    assert consent['config']['assignee_type'] == 'DYNAMIC'
    assert consent['config']['assignee_value'] == 'delegate'
    options = consent['config']['decision_options']
    assert {option['value'] for option in options} == {'approved', 'rejected'}
    assert all(option['target_edges'] for option in options)


def test_seed_org_proxy_request_flow_is_idempotent(test_org):
    first = seed_org_proxy_request_flow(test_org.secure_code)
    db.session.commit()
    second = seed_org_proxy_request_flow(test_org.secure_code)
    db.session.commit()

    assert first['ok'] is True
    assert first['created']['form'] is True
    assert first['created']['workflow'] is True
    assert first['created']['mapping'] is True
    assert first['created']['published'] is True
    assert sorted(first['created']['permissions']) == ['role:EMPLOYEE', 'role:ORG_ADMIN']
    assert second['ok'] is True
    assert second['created'] == {
        'form': False,
        'workflow': False,
        'mapping': False,
        'published': False,
        'permissions': [],
    }

    form = FwFormTemplate.query.filter_by(
        org_secure_code=test_org.secure_code,
        code='PROXY_REQUEST',
        is_deleted=False,
    ).one()
    workflow = FwWorkflowTemplate.query.filter_by(
        org_secure_code=test_org.secure_code,
        code='PROXY_REQUEST_FLOW',
        is_deleted=False,
    ).one()
    mapping = FwFormWorkflowMapping.query.filter_by(
        org_secure_code=test_org.secure_code,
        form_template_secure_code=form.secure_code,
        is_deleted=False,
    ).one()
    published = FwPublishedFormWorkflow.query.filter_by(
        org_secure_code=test_org.secure_code,
        source_mapping_secure_code=mapping.secure_code,
        status='Published',
        is_deleted=False,
    ).one()
    permissions = FwMappingPermission.query.filter_by(
        org_secure_code=test_org.secure_code,
        mapping_secure_code=mapping.secure_code,
        is_deleted=False,
    ).all()

    assert form.schema['components'][1]['defaultToCurrentUser'] is False
    assert workflow.graph
    assert workflow.cytoscape_config
    assert mapping.workflow_template_secure_code == workflow.secure_code
    assert published.secure_code == first['published_secure_code']
    assert {
        (item.grant_type, item.grant_target, item.grant_target_name, item.include_children)
        for item in permissions
    } == set(MAPPING_PERMISSION_SPECS)
