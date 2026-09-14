#!/usr/bin/env python3
"""佈建「差旅費申請（人事取值示範）」表單＋流程＋配對並發行，示範 OpHrLookup 節點。

流程：Start → 人事資料取值（核決類別 TRAVEL、依金額 ${f.amount} 找核決人）→ 簽核（動態 hr_approver）→ End。
目標企業要先有職位、直屬主管鏈與核決上限（scripts/seed_test_companies.py --run 建的範例企業即可）。
冪等：重跑會沿用既有表單／流程，bump revision 並重新發行。

用法：
    set -a && source .env && set +a
    venv/bin/python scripts/examples/provision_hr_lookup_demo.py --org GHTRAVEL --apply
"""
import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'backend'))
sys.path.insert(0, _REPO_ROOT)

FORM_CODE = 'HR_LOOKUP_TRAVEL_DEMO'
WF_CODE = 'HR_LOOKUP_TRAVEL_DEMO_FLOW'


def build_schema():
    return {'display': 'form', 'components': [
        {'key': 'amount', 'type': 'number', 'input': True, 'label': '申請金額',
         'tableView': True, 'validate': {'required': True}},
        {'key': 'purpose', 'type': 'textfield', 'input': True, 'label': '事由', 'tableView': True},
        {'key': 'submit', 'type': 'button', 'input': True, 'label': '送出',
         'action': 'submit', 'disableOnInvalid': True},
    ]}


def build_graph(_node, _edge):
    return {'nodes': [
        _node('node-Start', 'Start', 'Start', {}, -500, 0),
        _node('node-HrLookup', 'OpHrLookup', '取申請人人事資料', {
            'target_source': 'applicant', 'var_prefix': 'hr',
            'approval_category_code': 'TRAVEL', 'approver_mode': True, 'amount_expr': '${f.amount}',
        }, -260, 0, '把申請人的職等、職稱、職系、直屬主管與差旅費核決上限寫成 hr_* 變數，並依金額沿主管鏈找核決人。'),
        _node('node-Approve', 'FormAdapter', '核決人簽核', {
            'assignee_type': 'DYNAMIC', 'assignee_value': 'hr_approver', 'assignee_label': '依金額找到的核決人',
            'assignee_list': [], 'selection_mode': 'single', 'output_variable': 'approval',
            'allow_comment': True, 'require_comment': False, 'use_custom_decisions': True, 'input_variables': [],
            'decision_options': [
                {'id': 'opt-approve', 'label': '核准', 'value': 'approved', 'style': 'primary',
                 'target_edges': ['edge-approve']},
                {'id': 'opt-reject', 'label': '駁回', 'value': 'rejected', 'style': 'danger',
                 'target_edges': ['edge-reject']},
            ],
        }, 0, 0),
        _node('node-End', 'End', 'End', {'finish_mode': 'detach', 'wait_seconds': 3}, 260, 0),
    ], 'edges': [
        _edge('edge-start', 'node-Start', 'node-HrLookup'),
        _edge('edge-lookup', 'node-HrLookup', 'node-Approve'),
        _edge('edge-approve', 'node-Approve', 'node-End', label='核准'),
        _edge('edge-reject', 'node-Approve', 'node-End', label='駁回'),
    ]}


def run(org_code, apply=True):
    from app import db
    from app.models import Organization, User
    from app.utils.security import generate_secure_code
    from modules.form_workflow.models import (
        FwFormTemplate, FwWorkflowTemplate, FwFormWorkflowMapping,
        FwPublishedFormWorkflow, FwMappingPermission,
    )
    from app.defaults.api_key_request_defaults import (
        _node, _edge, CATEGORY_NAME, CATEGORY_SECURE_CODE, MAPPING_PERMISSION_SPECS, _get_publisher,
    )
    org = Organization.query.filter_by(code=org_code, is_deleted=False).first()
    if not org:
        raise SystemExit(f'找不到企業 {org_code}')
    osc = org.secure_code
    schema = build_schema()
    graph = build_graph(_node, _edge)

    if not apply:
        print(f'{org_code}: 將建立/更新並發行差旅費人事取值示範流程')
        return {
            'org': org,
            'form': None,
            'workflow': None,
            'mapping': None,
            'published': None,
        }

    form = FwFormTemplate.query.filter_by(org_secure_code=osc, code=FORM_CODE, is_deleted=False).first()
    if not form:
        form = FwFormTemplate(
            secure_code=generate_secure_code(), org_secure_code=osc, code=FORM_CODE, version='AA', revision=1,
            name='差旅費申請（人事取值示範）', description='示範 OpHrLookup：依金額沿主管鏈找核決人',
            category=CATEGORY_NAME, category_secure_code=CATEGORY_SECURE_CODE,
            schema=schema, builder_config={}, is_published=False, is_active=True,
            is_protected=False, permission_type='org')
        db.session.add(form)
        db.session.flush()
    wf = FwWorkflowTemplate.query.filter_by(org_secure_code=osc, code=WF_CODE, is_deleted=False).first()
    if not wf:
        wf = FwWorkflowTemplate(
            secure_code=generate_secure_code(), org_secure_code=osc, code=WF_CODE, version='AA', revision=1,
            name='差旅費核決流程（人事取值示範）', description='OpHrLookup → 依金額找核決人 → 動態簽核',
            category=CATEGORY_NAME, category_secure_code=CATEGORY_SECURE_CODE,
            graph=graph, cytoscape_config=graph, is_published=False, is_active=True,
            is_protected=False, permission_type='org', is_subprocess=False)
        db.session.add(wf)
        db.session.flush()
    else:
        wf.graph = graph
        wf.cytoscape_config = graph
        wf.revision = (wf.revision or 0) + 1
    mapping = FwFormWorkflowMapping.query.filter_by(
        org_secure_code=osc, form_template_secure_code=form.secure_code, is_deleted=False).first()
    if not mapping:
        mapping = FwFormWorkflowMapping(
            secure_code=generate_secure_code(), org_secure_code=osc,
            form_template_id=form.id, form_template_secure_code=form.secure_code,
            form_template_code=form.code, form_template_version=form.version,
            workflow_template_id=wf.id, workflow_template_secure_code=wf.secure_code,
            workflow_template_code=wf.code, workflow_template_version=wf.version,
            is_active=True, is_published=False, priority=0, description='OpHrLookup 示範')
        db.session.add(mapping)
        db.session.flush()
    publisher = _get_publisher(User, osc)
    for existing in FwPublishedFormWorkflow.query.filter_by(
            org_secure_code=osc, source_mapping_secure_code=mapping.secure_code,
            status='Published', is_deleted=False).all():
        existing.status = 'Suspended'
    published = FwPublishedFormWorkflow.create_from_mapping(
        mapping=mapping, form_template=form, workflow_template=wf,
        published_by=publisher.secure_code if publisher else None,
        published_by_name=(publisher.display_name if publisher else None))
    mapping.is_published = True
    db.session.add(published)
    db.session.flush()
    for grant_type, grant_target, grant_target_name, include_children in MAPPING_PERMISSION_SPECS:
        exists = FwMappingPermission.query.filter_by(
            org_secure_code=osc, mapping_secure_code=mapping.secure_code,
            grant_type=grant_type, grant_target=grant_target, is_deleted=False).first()
        if not exists:
            db.session.add(FwMappingPermission(
                secure_code=generate_secure_code(), org_secure_code=osc,
                mapping_secure_code=mapping.secure_code, grant_type=grant_type,
                grant_target=grant_target, grant_target_name=grant_target_name,
                include_children=include_children))
    print(f'{org_code}: 已發行 {published.secure_code}（表單 {form.secure_code}，流程 {wf.secure_code}）')
    return {
        'org': org,
        'form': form,
        'workflow': wf,
        'mapping': mapping,
        'published': published,
    }


def main():
    parser = argparse.ArgumentParser(description='佈建 OpHrLookup 示範流程（差旅費申請）')
    parser.add_argument('--org', default='GHTRAVEL', help='目標企業 code（預設 GHTRAVEL）')
    parser.add_argument('--apply', action='store_true', help='實際寫入資料庫；未加此參數只顯示說明')
    args = parser.parse_args()
    if not args.apply:
        parser.print_help()
        return 0
    from app import create_app, db
    app = create_app('development')
    with app.app_context():
        run(args.org, apply=True)
        db.session.commit()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
