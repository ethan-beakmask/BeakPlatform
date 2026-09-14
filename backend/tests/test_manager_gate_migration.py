"""PF-251 manager gate migration."""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db  # noqa: E402
from app.models import Role, RoleType  # noqa: E402
from modules.form_workflow.models import FwPublishedFormWorkflow, FwWorkflowTemplate  # noqa: E402
from modules.form_workflow.services.manager_gate_migration import (  # noqa: E402
    migrate_gate_nodes,
    migrate_org_manager_gates,
)


def _role(org, code, name):
    role = Role(
        org_secure_code=org.secure_code,
        code=code,
        name=name,
        role_type=RoleType.POSITION,
        scope_type='DEPARTMENT',
        is_active=True,
        is_deleted=False,
    )
    db.session.add(role)
    db.session.commit()
    return role


def _node(node_id, manager_sc, absence_marker='missing', label='部門正主管@申請人所屬單位'):
    config = {
        'assignee_type': 'ROLE',
        'assignee_value': manager_sc,
        'assignee_label': label,
    }
    if absence_marker != 'missing':
        config['absence_fallback'] = absence_marker
    return {
        'id': node_id,
        'type': 'FormAdapter',
        'config': config,
    }


def test_migrate_gate_nodes_conditions_and_idempotency():
    manager_sc = 'mgr_sc'
    head_sc = 'head_sc'
    nodes = [
        _node('missing', manager_sc),
        _node('true', manager_sc, True, '部門主管@申請人所屬單位'),
        _node('false-str', manager_sc, 'false'),
        _node('false-bool', manager_sc, False),
        {'id': 'not-fa', 'type': 'Start', 'config': {'assignee_type': 'ROLE', 'assignee_value': manager_sc}},
        {'id': 'not-role', 'type': 'FormAdapter', 'config': {'assignee_type': 'USER', 'assignee_value': manager_sc}},
        _node('other-role', 'other_sc'),
        _node('label-only-role', manager_sc, True, '部門正主管'),
        {'data': _node('cy', manager_sc, 'yes', '部門正主管@指定單位')},
    ]

    changed = migrate_gate_nodes(nodes, manager_sc, head_sc, '部門主管')

    assert changed == 4
    assert nodes[0]['config']['assignee_value'] == head_sc
    assert nodes[0]['config']['assignee_label'] == '部門主管@申請人所屬單位'
    assert 'absence_fallback' not in nodes[0]['config']
    assert nodes[1]['config']['assignee_label'] == '部門主管@申請人所屬單位'
    assert nodes[2]['config']['assignee_value'] == manager_sc
    assert nodes[3]['config']['assignee_value'] == manager_sc
    assert nodes[7]['config']['assignee_label'] == '部門主管'
    assert nodes[8]['data']['config']['assignee_label'] == '部門主管@指定單位'
    assert migrate_gate_nodes(nodes, manager_sc, head_sc, '部門主管') == 0


def test_migrate_org_manager_gates_flags_json_fields(test_org):
    manager = _role(test_org, 'DEPT_MANAGER', '部門正主管')
    head = _role(test_org, 'DEPT_HEAD', '部門主管')
    graph_node = _node('graph-hit', manager.secure_code, True)
    cy_node = {'data': _node('cy-hit', manager.secure_code, 'yes')}
    template = FwWorkflowTemplate(
        secure_code='mgr_gate_tpl',
        org_secure_code=test_org.secure_code,
        code='MGR_GATE',
        name='Manager Gate',
        graph={'nodes': [graph_node], 'edges': []},
        cytoscape_config={'nodes': [cy_node], 'edges': []},
        is_deleted=False,
    )
    snapshot = {
        'graph': {'nodes': [_node('snap-graph', manager.secure_code, True)], 'edges': []},
        'cytoscape_config': {'nodes': [{'data': _node('snap-cy', manager.secure_code)}], 'edges': []},
    }
    published = FwPublishedFormWorkflow(
        secure_code='mgr_gate_pub',
        org_secure_code=test_org.secure_code,
        source_mapping_id=1,
        source_mapping_secure_code='map_sc',
        source_form_template_id=1,
        source_form_template_secure_code='form_sc',
        source_workflow_template_id=1,
        source_workflow_template_secure_code=template.secure_code,
        name='Published Manager Gate',
        form_snapshot={},
        workflow_snapshot=copy.deepcopy(snapshot),
        status='Published',
        is_deleted=False,
    )
    db.session.add_all([template, published])
    db.session.commit()

    counts = migrate_org_manager_gates(test_org, {
        'Role': Role,
        'FwWorkflowTemplate': FwWorkflowTemplate,
        'FwPublishedFormWorkflow': FwPublishedFormWorkflow,
    })
    db.session.commit()

    assert counts == {
        'gate_templates': 1,
        'gate_template_nodes': 1,
        'gate_snapshots': 1,
        'gate_snapshot_nodes': 1,
    }
    db.session.expire_all()
    reloaded_template = FwWorkflowTemplate.query.filter_by(secure_code='mgr_gate_tpl').one()
    reloaded_published = FwPublishedFormWorkflow.query.filter_by(secure_code='mgr_gate_pub').one()

    for config in [
        reloaded_template.graph['nodes'][0]['config'],
        reloaded_template.cytoscape_config['nodes'][0]['data']['config'],
        reloaded_published.workflow_snapshot['graph']['nodes'][0]['config'],
        reloaded_published.workflow_snapshot['cytoscape_config']['nodes'][0]['data']['config'],
    ]:
        assert config['assignee_value'] == head.secure_code
        assert config['assignee_label'].startswith(head.name)
        assert 'absence_fallback' not in config

    assert migrate_org_manager_gates(test_org, {
        'Role': Role,
        'FwWorkflowTemplate': FwWorkflowTemplate,
        'FwPublishedFormWorkflow': FwPublishedFormWorkflow,
    }) == {
        'gate_templates': 0,
        'gate_template_nodes': 0,
        'gate_snapshots': 0,
        'gate_snapshot_nodes': 0,
    }
