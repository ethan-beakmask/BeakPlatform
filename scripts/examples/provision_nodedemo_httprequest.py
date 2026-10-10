#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""佈建 node展覽館的 HttpRequest 示範流程。"""
from __future__ import annotations

import argparse
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
BACKEND_DIR = os.path.join(REPO_ROOT, 'backend')
sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, REPO_ROOT)

from scripts.examples.node_showcase import ensure_showcase_category

ORG_CODE = 'SYSTEM'
CATEGORY_NAME = 'node展覽館'
SHOWCASE_CATEGORY_SECURE_CODE = None
ICON_BASE = '/static/modules/form_workflow/icons/workflow'
_NODE_ICONS: dict = {}
_EDGE_STYLE = {
    'width': 2,
    'line-color': 'rgb(149,165,166)',
    'arrow-scale': 1,
    'curve-style': 'straight',
    'target-arrow-color': 'rgb(149,165,166)',
    'target-arrow-shape': 'triangle',
}


def log(msg):
    print(msg, flush=True)


def load_node_icons(models):
    WorkflowNodeDefinition = models['WorkflowNodeDefinition']
    for d in WorkflowNodeDefinition.query.filter_by(is_deleted=False).all():
        if d.icon:
            _NODE_ICONS[d.node_type] = d.icon


def _node(node_id, node_type, label, config=None, x=0, y=0, description=''):
    return {
        'id': node_id,
        'type': node_type,
        'label': label,
        'icon': _NODE_ICONS.get(node_type) or f'{ICON_BASE}/{node_type.lower()}.svg',
        'config': config or {},
        'position': {'x': x, 'y': y},
        'description': description,
    }


def _edge(edge_id, source, target, label=''):
    return {
        'id': edge_id,
        'label': label,
        'style': dict(_EDGE_STYLE),
        'source': source,
        'target': target,
        'hasRelays': False,
    }


def _graph(nodes, edges):
    return {
        'nodes': nodes,
        'edges': edges,
        'relayPoints': [],
        'canvasSettings': {
            'gridStyle': 'dots', 'paperType': 'none', 'paperWidth': 0,
            'gridEnabled': True, 'gridSpacing': 25, 'paperHeight': 0,
            'backgroundId': None, 'backgroundColor': '#fafafa',
            'globalNodeBorder': True,
        },
        'fieldReadConfig': {},
    }


def _text(key, label, description=''):
    comp = {'key': key, 'type': 'textfield', 'input': True, 'label': label, 'tableView': True}
    if description:
        comp['description'] = description
    return comp


def _textarea(key, label, description='', rows=6):
    comp = {'key': key, 'type': 'textarea', 'input': True, 'label': label,
            'tableView': True, 'rows': rows, 'autoExpand': True}
    if description:
        comp['description'] = description
    return comp


def _title(text):
    return {
        'key': 'formTitle', 'tag': 'h3', 'type': 'htmlelement',
        'input': False, 'label': 'HTML', 'tableView': False,
        'attrs': [{'attr': 'style', 'value': 'text-align:center; margin:0 0 0.5rem 0;'}],
        'content': text,
    }


def _hint(text):
    return {
        'key': 'formHint', 'tag': 'p', 'type': 'htmlelement',
        'input': False, 'label': 'HTML', 'tableView': False,
        'attrs': [{'attr': 'style',
                   'value': 'color:#555; background:#f5f5f5; padding:8px; '
                            'border-radius:4px; margin:0 0 1rem 0;'}],
        'content': text,
    }


def _submit_button():
    return {'key': 'submit', 'type': 'button', 'input': True, 'label': '送出',
            'action': 'submit', 'disableOnInvalid': True}


def build_graph():
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 160, 220),
        _node('node-Http', 'HttpRequest', '呼叫表單填入的 URL', {
            'url': '${f.url}',
            'method': 'GET',
            'headers': [],
            'body_mode': 'none',
            'timeout_seconds': 15,
            'verify_tls': True,
            'expect_json': True,
            'max_response_bytes': 262144,
            'result_var': 'http',
        }, 420, 220, '呼叫表單欄位 url 指定的 HTTP(S) 目的地，結果寫進 http_* 流程變數。'),
        _node('node-Branch', 'Branch', '依 http_ok 分流', {
            'rules': [{
                'name': 'HTTP 成功',
                'conditions': [{
                    'variable': '${v.http_ok}',
                    'operator': '==',
                    'value': 'True',
                    'logic': 'AND',
                }],
                'target_edges': ['edge-branch-ok'],
            }],
            'fallback': {'action': 'route', 'target_edge': 'edge-branch-fail'},
        }, 660, 220),
        _node('node-WriteOk', 'OpFieldWrite', '寫入成功回應', {
            'target_field': 'result',
            'content': 'result=${v.http_result}\nstatus=${v.http_status}\nbody=${v.http_body}',
        }, 900, 120),
        _node('node-WriteFail', 'OpFieldWrite', '寫入失敗原因', {
            'target_field': 'result',
            'content': 'result=${v.http_result}\nstatus=${v.http_status}\nerror=${v.http_error}',
        }, 900, 320),
        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 1140, 220),
    ]
    edges = [
        _edge('edge-start-http', 'node-Start', 'node-Http'),
        _edge('edge-http-branch', 'node-Http', 'node-Branch'),
        _edge('edge-branch-ok', 'node-Branch', 'node-WriteOk', '成功'),
        _edge('edge-branch-fail', 'node-Branch', 'node-WriteFail', '失敗'),
        _edge('edge-ok-end', 'node-WriteOk', 'node-End'),
        _edge('edge-fail-end', 'node-WriteFail', 'node-End'),
    ]
    return _graph(nodes, edges)


FORM_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-32 HttpRequest 示範表單'),
        _hint('填入要呼叫的 URL。目的地必須已由系統管理員加入 HttpRequest 白名單；送出後流程會把 http_* 結果變數寫回結果欄。'),
        _text('url', 'URL', '例如 http://127.0.0.1:8089/ping'),
        _textarea('result', 'HTTP 呼叫結果（由流程自動填入）', rows=8),
        _submit_button(),
    ],
}

DEMO = {
    'form_code': 'NODEDEMO_HTTPREQUEST',
    'form_name': 'NT-32 HttpRequest 示範表單',
    'workflow_code': 'NODEDEMO_HTTPREQUEST',
    'workflow_name': 'NT-32 HttpRequest 示範流程',
    'description': 'Start → HttpRequest → Branch → OpFieldWrite → End；用於驗證 HTTP 呼叫節點與白名單行為。',
    'form_schema': FORM_SCHEMA,
    'graph': build_graph,
}


def ensure_fill_permissions(db, models, org_sc, mapping, apply):
    FwMappingPermission = models['FwMappingPermission']
    from app.models import User

    users = User.query.filter(
        User.org_secure_code == org_sc,
        User.is_deleted.is_(False),
        User.is_active.is_(True),
        User.user_type != 'EXTERNAL',
    ).all()
    existing = {
        (p.grant_type, p.grant_target)
        for p in FwMappingPermission.query.filter_by(
            mapping_secure_code=mapping.secure_code, is_deleted=False).all()
    }
    added = 0
    for user in users:
        if ('user', user.secure_code) in existing:
            continue
        if apply:
            db.session.add(FwMappingPermission(
                org_secure_code=org_sc,
                mapping_secure_code=mapping.secure_code,
                grant_type='user',
                grant_target=user.secure_code,
                grant_target_name=user.display_name or user.username,
                include_children=False,
                created_by_name='provision_nodedemo_httprequest',
            ))
        added += 1
    log(f'  {"[預演] 會新增" if not apply else "已新增"}填寫授權 {added} 筆（共 {len(users)} 個帳號）')


def apply_demo(db, models, org, publisher, apply):
    from app.utils.security import generate_secure_code

    FwFormTemplate = models['FwFormTemplate']
    FwWorkflowTemplate = models['FwWorkflowTemplate']
    FwFormWorkflowMapping = models['FwFormWorkflowMapping']
    FwPublishedFormWorkflow = models['FwPublishedFormWorkflow']

    osc = org.secure_code
    form = FwFormTemplate.query.filter_by(org_secure_code=osc, code=DEMO['form_code'], is_deleted=False).first()
    if not form:
        form = FwFormTemplate(
            secure_code=generate_secure_code(), org_secure_code=osc, code=DEMO['form_code'],
            version='AA', revision=1, name=DEMO['form_name'], description=DEMO['form_name'],
            category=CATEGORY_NAME, category_secure_code=SHOWCASE_CATEGORY_SECURE_CODE,
            schema=DEMO['form_schema'], builder_config={}, is_published=False,
            is_active=True, is_protected=False, permission_type='org')
    else:
        form.name = DEMO['form_name']
        form.schema = DEMO['form_schema']
        form.revision = (form.revision or 0) + 1

    graph = DEMO['graph']()
    wf = FwWorkflowTemplate.query.filter_by(org_secure_code=osc, code=DEMO['workflow_code'], is_deleted=False).first()
    if not wf:
        wf = FwWorkflowTemplate(
            secure_code=generate_secure_code(), org_secure_code=osc, code=DEMO['workflow_code'],
            version='AA', revision=1, name=DEMO['workflow_name'], description=DEMO['description'],
            category=CATEGORY_NAME, category_secure_code=SHOWCASE_CATEGORY_SECURE_CODE,
            graph=graph, cytoscape_config=graph, is_published=False, is_active=True,
            is_protected=False, permission_type='org', is_subprocess=False)
    else:
        wf.name = DEMO['workflow_name']
        wf.description = DEMO['description']
        wf.graph = graph
        wf.cytoscape_config = graph
        wf.revision = (wf.revision or 0) + 1

    log(f"  流程 {DEMO['workflow_code']} + 表單 {DEMO['form_code']}")
    if not apply:
        log('  [預演] 會寫入表單 schema 與流程 graph，並重新發行')
        return None

    db.session.add(form)
    db.session.flush()
    db.session.add(wf)
    db.session.flush()

    mapping = FwFormWorkflowMapping.query.filter_by(
        org_secure_code=osc, form_template_secure_code=form.secure_code, is_deleted=False).first()
    if not mapping:
        mapping = FwFormWorkflowMapping(
            secure_code=generate_secure_code(), org_secure_code=osc,
            form_template_id=form.id, form_template_secure_code=form.secure_code,
            form_template_code=form.code, form_template_version=form.version,
            workflow_template_id=wf.id, workflow_template_secure_code=wf.secure_code,
            workflow_template_code=wf.code, workflow_template_version=wf.version,
            is_active=True, is_published=False, priority=0,
            description=f"node展覽館：{DEMO['workflow_name']}")
        db.session.add(mapping)
    else:
        mapping.form_template_version = form.version
        mapping.workflow_template_version = wf.version
        mapping.is_active = True
    db.session.flush()

    ensure_fill_permissions(db, models, osc, mapping, apply)
    for existing in FwPublishedFormWorkflow.query.filter_by(
            org_secure_code=osc, source_mapping_secure_code=mapping.secure_code,
            status='Published', is_deleted=False).all():
        existing.status = 'Suspended'

    published = FwPublishedFormWorkflow.create_from_mapping(
        mapping=mapping, form_template=form, workflow_template=wf,
        published_by=publisher.secure_code if publisher else None,
        published_by_name=(publisher.display_name or publisher.username) if publisher else None)
    mapping.is_published = True
    db.session.add(published)
    db.session.flush()
    log(f'  已發行 v{published.publish_version}：{published.secure_code}')
    log(f'  published_secure_code={published.secure_code}')
    return {'form_sc': form.secure_code, 'wf_sc': wf.secure_code, 'published_sc': published.secure_code}


def _workflow_models():
    from modules.form_workflow.models import (
        FwFormTemplate, FwFormWorkflowMapping, FwMappingPermission,
        FwPublishedFormWorkflow, FwWorkflowTemplate, WorkflowNodeDefinition,
    )
    return {
        'FwFormTemplate': FwFormTemplate,
        'FwFormWorkflowMapping': FwFormWorkflowMapping,
        'FwMappingPermission': FwMappingPermission,
        'FwPublishedFormWorkflow': FwPublishedFormWorkflow,
        'FwWorkflowTemplate': FwWorkflowTemplate,
        'WorkflowNodeDefinition': WorkflowNodeDefinition,
    }


def provision(org, apply=True, **opts):
    from app import db
    from app.models import User

    del opts
    db.session.execute(db.text("SET LOCAL app.is_system_admin = 'true'"))
    global SHOWCASE_CATEGORY_SECURE_CODE
    SHOWCASE_CATEGORY_SECURE_CODE = ensure_showcase_category(org).secure_code
    models = _workflow_models()
    load_node_icons(models)
    publisher = User.query.filter_by(
        org_secure_code=org.secure_code, user_type='ORG_ADMIN',
        is_deleted=False, is_active=True).first()
    result = apply_demo(db, models, org, publisher, apply)
    return {'result': result, 'category_secure_code': SHOWCASE_CATEGORY_SECURE_CODE}


def main():
    parser = argparse.ArgumentParser(description='佈建 node展覽館的 HttpRequest 示範（NT-32）')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--dry-run', action='store_true', help='只列出會做什麼，不寫入')
    group.add_argument('--apply', action='store_true', help='實際寫入資料庫')
    parser.add_argument('--org', default=ORG_CODE, help=f'企業 code（預設 {ORG_CODE}）')
    args = parser.parse_args()

    from app import create_app, db

    app = create_app('development')
    with app.app_context():
        from app.models import Organization

        org = Organization.query.filter_by(code=args.org, is_deleted=False).first()
        if not org:
            log(f'找不到企業：{args.org}')
            return 1
        result = provision(org, apply=args.apply)
        if args.apply:
            db.session.commit()
            published = result['result']['published_sc'] if result.get('result') else ''
            log(f'\n已寫入。published_secure_code={published}')
        else:
            db.session.rollback()
            log('\n[預演] 未寫入任何資料')
    return 0


if __name__ == '__main__':
    sys.exit(main())
