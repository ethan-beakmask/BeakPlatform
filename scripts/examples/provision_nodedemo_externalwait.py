#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""佈建 node展覽館的 ExternalWait 示範流程。"""
from __future__ import annotations

import argparse
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
BACKEND_DIR = os.path.join(REPO_ROOT, 'backend')
sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, REPO_ROOT)

from scripts.examples.provision_nodedemo_httprequest import (  # noqa: E402
    _EDGE_STYLE,
    _edge,
    _graph,
    _hint,
    _node,
    _submit_button,
    _textarea,
    _text,
    _title,
    apply_demo as _apply_demo_base,
    ensure_fill_permissions,
    load_node_icons,
    log,
)
from scripts.examples.node_showcase import ensure_showcase_category  # noqa: E402

ORG_CODE = 'SYSTEM'
CATEGORY_NAME = 'node展覽館'
SHOWCASE_CATEGORY_SECURE_CODE = None


def build_graph():
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 120, 260),
        _node('node-Http', 'HttpRequest', '送出非同步請求', {
            'url': '${f.mock_url}/callback-later',
            'method': 'POST',
            'headers': [],
            'body_mode': 'json',
            'body': '{"callback_url": "${cb.node-Wait}", "payload": {"ticket": "${fi.serial}", "status": "closed"}, "delay_seconds": ${f.delay_seconds}}',
            'timeout_seconds': 15,
            'verify_tls': True,
            'expect_json': True,
            'max_response_bytes': 262144,
            'result_var': 'http',
        }, 360, 260),
        _node('node-Wait', 'ExternalWait', '等待外部回呼', {
            'result_var': 'cb',
            'timeout_enabled': True,
            'timeout_minutes': 2,
        }, 600, 260),
        _node('node-Branch', 'Branch', '依 cb_result 分流', {
            'rules': [{
                'name': '收到回呼',
                'conditions': [{
                    'variable': '${v.cb_result}',
                    'operator': '==',
                    'value': 'received',
                    'logic': 'AND',
                }],
                'target_edges': ['edge-branch-ok'],
            }],
            'fallback': {'action': 'route', 'target_edge': 'edge-branch-timeout'},
        }, 840, 260),
        _node('node-WriteOk', 'OpFieldWrite', '寫入回呼內容', {
            'target_field': 'result',
            'content': '${v.cb_payload}',
        }, 1080, 160),
        _node('node-WriteTimeout', 'OpFieldWrite', '寫入逾時', {
            'target_field': 'result',
            'content': '逾時',
        }, 1080, 360),
        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 1320, 260),
    ]
    edges = [
        _edge('edge-start-http', 'node-Start', 'node-Http'),
        _edge('edge-http-wait', 'node-Http', 'node-Wait'),
        _edge('edge-wait-branch', 'node-Wait', 'node-Branch'),
        _edge('edge-branch-ok', 'node-Branch', 'node-WriteOk', '收到'),
        _edge('edge-branch-timeout', 'node-Branch', 'node-WriteTimeout', '逾時'),
        _edge('edge-ok-end', 'node-WriteOk', 'node-End'),
        _edge('edge-timeout-end', 'node-WriteTimeout', 'node-End'),
    ]
    return _graph(nodes, edges)


FORM_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-33 ExternalWait 示範表單'),
        _hint('送出後流程會先呼叫 mock server，再等待 mock server 以 callback_url 打回平台。'),
        _text('mock_url', 'Mock server URL', '例如 http://127.0.0.1:8089'),
        _text('delay_seconds', '延遲秒數', '例如 5；mock server 最高等待 300 秒'),
        _textarea('result', '回呼結果（由流程自動填入）', rows=8),
        _submit_button(),
    ],
}

DEMO = {
    'form_code': 'NODEDEMO_EXTERNALWAIT',
    'form_name': 'NT-33 ExternalWait 示範表單',
    'workflow_code': 'NODEDEMO_EXTERNALWAIT',
    'workflow_name': 'NT-33 ExternalWait 示範流程',
    'description': 'Start → HttpRequest → ExternalWait → Branch → OpFieldWrite → End；用於驗證非同步回呼。',
    'form_schema': FORM_SCHEMA,
    'graph': build_graph,
}


def apply_demo(db, models, org, publisher, apply):
    import scripts.examples.provision_nodedemo_httprequest as base

    old_demo = base.DEMO
    old_category = base.CATEGORY_NAME
    old_showcase_sc = base.SHOWCASE_CATEGORY_SECURE_CODE
    base.DEMO = DEMO
    base.CATEGORY_NAME = CATEGORY_NAME
    base.SHOWCASE_CATEGORY_SECURE_CODE = SHOWCASE_CATEGORY_SECURE_CODE
    try:
        return _apply_demo_base(db, models, org, publisher, apply)
    finally:
        base.DEMO = old_demo
        base.CATEGORY_NAME = old_category
        base.SHOWCASE_CATEGORY_SECURE_CODE = old_showcase_sc


def main():
    parser = argparse.ArgumentParser(description='佈建 node展覽館的 ExternalWait 示範（NT-33）')
    parser.add_argument('--org', default=ORG_CODE, help='企業代碼（預設 SYSTEM）')
    parser.add_argument('--apply', action='store_true', help='實際寫入；未加時只預演')
    args = parser.parse_args()

    from app import create_app, db
    from app.models import Organization, User
    from modules.form_workflow.models import (
        FwCategory, FwFormTemplate, FwFormWorkflowMapping, FwMappingPermission, FwPublishedFormWorkflow,
        FwWorkflowTemplate, WorkflowNodeDefinition,
    )

    app = create_app()
    with app.app_context():
        org = Organization.query.filter_by(code=args.org, is_deleted=False).first()
        if not org:
            raise SystemExit(f'找不到企業 code={args.org}')
        publisher = User.query.filter_by(org_secure_code=org.secure_code, is_deleted=False).first()
        if not publisher:
            raise SystemExit(f'企業 {args.org} 找不到可用使用者')

        global SHOWCASE_CATEGORY_SECURE_CODE
        category = ensure_showcase_category(org)
        SHOWCASE_CATEGORY_SECURE_CODE = category.secure_code
        models = {
            'FwCategory': FwCategory,
            'FwFormTemplate': FwFormTemplate,
            'FwWorkflowTemplate': FwWorkflowTemplate,
            'FwFormWorkflowMapping': FwFormWorkflowMapping,
            'FwMappingPermission': FwMappingPermission,
            'FwPublishedFormWorkflow': FwPublishedFormWorkflow,
            'WorkflowNodeDefinition': WorkflowNodeDefinition,
        }
        load_node_icons(models)
        published = apply_demo(db, models, org, publisher, args.apply)
        if args.apply:
            db.session.commit()
        else:
            db.session.rollback()
            log('[預演] 未寫入資料庫；加 --apply 才會佈建')


if __name__ == '__main__':
    main()
