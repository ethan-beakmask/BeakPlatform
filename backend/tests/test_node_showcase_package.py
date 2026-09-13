import importlib.util
import os
import re
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app import db  # noqa: E402
from app.models import Organization  # noqa: E402
from modules.form_workflow.models import FwWorkflowTemplate, WorkflowNodeDefinition  # noqa: E402
from modules.form_workflow.services.node_grant_service import grant_node_to_org  # noqa: E402
from scripts.examples.node_showcase import SHOWCASE_ITEMS, ensure_showcase_category, plan_showcase_items  # noqa: E402


RESTRICTED_TYPES = {
    'OsExecutor',
    'OsFileRead',
    'OsFileWrite',
    'SysSqlExecutor',
    'SysTelegram',
    'SysEmailRelay',
}


def _source_for_module(module_name):
    spec = importlib.util.find_spec(module_name)
    assert spec and spec.origin
    with open(spec.origin, encoding='utf-8') as handle:
        return handle.read()


def _quoted(source, value):
    return bool(re.search(rf"(['\"]){re.escape(value)}\1", source))


def test_showcase_item_metadata_matches_demo_sources(app):
    del app
    for name, module_name, _defaults, metadata in SHOWCASE_ITEMS:
        source = _source_for_module(module_name)
        declared = set(metadata['node_types'])

        for node_type in declared:
            assert _quoted(source, node_type), f'{name} 宣告了不存在於原始碼的 node_type: {node_type}'

        for node_type in RESTRICTED_TYPES:
            assert not _quoted(source, node_type) or node_type in declared, (
                f'{name} 原始碼使用受限 node_type 但 metadata 未宣告: {node_type}'
            )


def _org(secure_code, code, domain, is_system_org=False):
    org = Organization(
        secure_code=secure_code,
        code=code,
        name=code,
        domain_name=domain,
        is_active=True,
        is_deleted=False,
        is_system_org=is_system_org,
    )
    db.session.add(org)
    return org


def _node_def(node_type, restricted=False):
    db.session.add(WorkflowNodeDefinition(
        node_type=node_type,
        is_active=True,
        scope='SYSTEM',
        category='test',
        display_name=node_type,
        execution_handler='test.Handler',
        org_restricted=restricted,
        is_deleted=False,
    ))


def _plan_by_code(plan):
    return {item['code']: item for item in plan}


def test_plan_showcase_items_skips_unauthorized_restricted_nodes(app):
    del app
    system_org = _org('sys_org_sc', 'SYSTEM', 'system.local', is_system_org=True)
    enterprise_org = _org('ent_org_sc', 'ENT', 'ent.local')

    for node_type in RESTRICTED_TYPES:
        _node_def(node_type, restricted=True)
    for node_type in ['Start', 'End', 'OpSet', 'OpFieldRead', 'OpFieldWrite', 'Branch', 'FormAdapter']:
        _node_def(node_type, restricted=False)
    db.session.commit()

    for node_type in RESTRICTED_TYPES:
        grant_node_to_org(node_type, system_org.secure_code)

    system_plan = plan_showcase_items(system_org)
    assert {item['action'] for item in system_plan} == {'run'}

    enterprise_plan = _plan_by_code(plan_showcase_items(enterprise_org))
    for code in ['B6', 'B7', 'B8', 'B11', 'B12', 'waf_failover', 'waf_monitor']:
        assert enterprise_plan[code]['action'] == 'skip'
        assert any(node_type in enterprise_plan[code]['reason'] for node_type in RESTRICTED_TYPES)
    assert enterprise_plan['B1']['action'] == 'run'
    assert enterprise_plan['B3']['action'] == 'run'

    only_plan = plan_showcase_items(enterprise_org, only=['B8'])
    assert [item['code'] for item in only_plan] == ['B8']


def test_plan_showcase_items_marks_existing_workflows(app):
    org = _org('exist_org_sc', 'EXIST', 'exist.local')
    db.session.flush()
    category = ensure_showcase_category(org)
    db.session.add(FwWorkflowTemplate(
        org_secure_code=org.secure_code,
        category_secure_code=category.secure_code,
        code='NODEDEMO_NT22_OPSET_FLOW',
        name='existing',
        graph={'nodes': [{'type': 'Start'}], 'edges': []},
        is_deleted=False,
    ))
    db.session.commit()

    plan = _plan_by_code(plan_showcase_items(org, only=['B1']))
    assert plan['B1']['exists'] is True
