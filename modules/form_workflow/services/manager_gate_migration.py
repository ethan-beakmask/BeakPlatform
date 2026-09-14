"""PF-251 manager gate migration helpers."""

from sqlalchemy.orm.attributes import flag_modified


_FALSE_VALUES = (False, 'false', '0', 'no')


def _node_data(node: dict) -> dict:
    data = node.get('data')
    return data if isinstance(data, dict) else node


def _node_config(node: dict) -> dict:
    data = _node_data(node)
    config = data.get('config')
    return config if isinstance(config, dict) else {}


def _is_false_fallback(value) -> bool:
    if value is False:
        return True
    if isinstance(value, str) and value.strip().lower() in _FALSE_VALUES:
        return True
    return False


def _rewrite_label(config: dict, head_role_name: str) -> None:
    label = config.get('assignee_label')
    if not isinstance(label, str) or not label:
        return
    if '@' in label:
        _, suffix = label.split('@', 1)
        config['assignee_label'] = f'{head_role_name}@{suffix}'
    else:
        config['assignee_label'] = head_role_name


def migrate_gate_nodes(nodes: list, manager_role_sc: str, head_role_sc: str, head_role_name: str) -> int:
    """就地改寫一個 nodes 陣列，回傳改了幾個節點。"""
    changed = 0
    for node in nodes or []:
        if not isinstance(node, dict):
            continue
        data = _node_data(node)
        if data.get('type') != 'FormAdapter':
            continue
        config = _node_config(node)
        if config.get('assignee_type') != 'ROLE':
            continue
        if config.get('assignee_value') != manager_role_sc:
            continue
        if _is_false_fallback(config.get('absence_fallback')):
            continue

        config['assignee_value'] = head_role_sc
        config.pop('absence_fallback', None)
        _rewrite_label(config, head_role_name)
        changed += 1
    return changed


def _roles_for_org(org_secure_code: str, Role):
    roles = Role.query.filter(
        Role.org_secure_code == org_secure_code,
        Role.code.in_(('DEPT_MANAGER', 'DEPT_HEAD')),
        Role.is_deleted == False,  # noqa: E712
    ).all()
    by_code = {role.code: role for role in roles}
    return by_code.get('DEPT_MANAGER'), by_code.get('DEPT_HEAD')


def migrate_org_manager_gates(org, ctx) -> dict:
    """對該企業改寫既有主管缺席順位關卡為 DEPT_HEAD。"""
    Role = ctx.get('Role')
    FwWorkflowTemplate = ctx.get('FwWorkflowTemplate')
    FwPublishedFormWorkflow = ctx.get('FwPublishedFormWorkflow')
    if Role is None or FwWorkflowTemplate is None or FwPublishedFormWorkflow is None:
        from app.models import Role as Role
        from modules.form_workflow.models import FwPublishedFormWorkflow, FwWorkflowTemplate

    manager_role, head_role = _roles_for_org(org.secure_code, Role)
    if manager_role is None or head_role is None:
        return {'gate_skipped_no_role': 1}

    counts = {
        'gate_templates': 0,
        'gate_template_nodes': 0,
        'gate_snapshots': 0,
        'gate_snapshot_nodes': 0,
    }

    templates = FwWorkflowTemplate.query.filter(
        FwWorkflowTemplate.org_secure_code == org.secure_code,
        FwWorkflowTemplate.is_deleted == False,  # noqa: E712
    ).all()
    for template in templates:
        graph = template.graph if isinstance(template.graph, dict) else {}
        graph_changed = migrate_gate_nodes(
            graph.get('nodes') or [],
            manager_role.secure_code,
            head_role.secure_code,
            head_role.name,
        )
        if graph_changed:
            flag_modified(template, 'graph')

        cytoscape = template.cytoscape_config if isinstance(template.cytoscape_config, dict) else {}
        cytoscape_changed = migrate_gate_nodes(
            cytoscape.get('nodes') or [],
            manager_role.secure_code,
            head_role.secure_code,
            head_role.name,
        )
        if cytoscape_changed:
            flag_modified(template, 'cytoscape_config')

        changed_nodes = max(graph_changed, cytoscape_changed)
        if changed_nodes:
            counts['gate_templates'] += 1
            counts['gate_template_nodes'] += changed_nodes

    snapshots = FwPublishedFormWorkflow.query.filter(
        FwPublishedFormWorkflow.org_secure_code == org.secure_code,
        FwPublishedFormWorkflow.is_deleted == False,  # noqa: E712
    ).all()
    for published in snapshots:
        snapshot = published.workflow_snapshot if isinstance(published.workflow_snapshot, dict) else {}
        graph = snapshot.get('graph') if isinstance(snapshot.get('graph'), dict) else {}
        graph_changed = migrate_gate_nodes(
            graph.get('nodes') or [],
            manager_role.secure_code,
            head_role.secure_code,
            head_role.name,
        )
        cytoscape = snapshot.get('cytoscape_config') if isinstance(snapshot.get('cytoscape_config'), dict) else {}
        cytoscape_changed = migrate_gate_nodes(
            cytoscape.get('nodes') or [],
            manager_role.secure_code,
            head_role.secure_code,
            head_role.name,
        )
        changed_nodes = max(graph_changed, cytoscape_changed)
        if changed_nodes:
            flag_modified(published, 'workflow_snapshot')
            counts['gate_snapshots'] += 1
            counts['gate_snapshot_nodes'] += changed_nodes

    return counts
