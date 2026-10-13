#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ISP 機房設備維護示範：同一張表單分四個區段，每個簽核關卡只解鎖該階段欄位。

用法：
    cd <repo>
    set -a && source .env && set +a
    venv/bin/python scripts/examples/provision_isp_maintenance_demo.py --dry-run
    venv/bin/python scripts/examples/provision_isp_maintenance_demo.py --apply
"""
from __future__ import annotations

import argparse
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
BACKEND_DIR = os.path.join(REPO_ROOT, 'backend')
sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, REPO_ROOT)

ORG_CODE = 'DEMOSOC'
CATEGORY_NAME = '設備維護'
CATEGORY_SECURE_CODE = None
ICON_BASE = '/static/modules/form_workflow/icons/workflow'

_EDGE_STYLE = {
    'width': 2,
    'line-color': 'rgb(149,165,166)',
    'arrow-scale': 1,
    'curve-style': 'straight',
    'target-arrow-color': 'rgb(149,165,166)',
    'target-arrow-shape': 'triangle',
}

_NODE_ICONS: dict = {}


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


def _canvas():
    return {
        'gridStyle': 'dots', 'paperType': 'none', 'paperWidth': 0,
        'gridEnabled': True, 'gridSpacing': 25, 'paperHeight': 0,
        'backgroundId': None, 'backgroundColor': '#fafafa',
        'globalNodeBorder': True,
    }


def _text(key, label, description='', required=False):
    comp = {'key': key, 'type': 'textfield', 'input': True, 'label': label, 'tableView': True}
    if description:
        comp['description'] = description
    if required:
        comp['validate'] = {'required': True}
    return comp


def _textarea(key, label, rows=3, description='', required=False):
    comp = {'key': key, 'type': 'textarea', 'input': True, 'label': label,
            'tableView': True, 'rows': rows, 'autoExpand': False}
    if description:
        comp['description'] = description
    if required:
        comp['validate'] = {'required': True}
    return comp


def _select(key, label, options, description='', required=False):
    comp = {'key': key, 'type': 'select', 'input': True, 'label': label, 'tableView': True,
            'dataSrc': 'values', 'widget': 'html5',
            'data': {'values': [{'label': l, 'value': v} for l, v in options]}}
    if description:
        comp['description'] = description
    if required:
        comp['validate'] = {'required': True}
    return comp


def _panel(key, title, components, show_stages=None):
    """show_stages: None＝永遠顯示；否則只在 data.stage 屬於清單時顯示。"""
    comp = {'key': key, 'type': 'panel', 'input': False, 'label': title, 'title': title,
            'tableView': False, 'collapsible': False, 'clearOnHide': False,
            'components': components}
    if show_stages:
        stages = ', '.join(f"'{s}'" for s in show_stages)
        comp['customConditional'] = f"show = [{stages}].indexOf(data.stage) >= 0;"
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


def _graph(nodes, edges):
    return {'nodes': nodes, 'edges': edges, 'relayPoints': [],
            'canvasSettings': _canvas(), 'fieldReadConfig': {}}


S1_FIELDS = [
    'vendor_name', 'maintenance_scope', 'equipment_list', 'planned_date',
    'planned_personnel', 'applicant_note',
]
S2_FIELDS = [
    'actual_personnel', 'personnel_match', 'temp_personnel_handling',
    'isp_registration_ref', 'isp_admitted',
]
S3_FIELDS = [
    'work_summary', 'unauthorized_attempt', 'unauthorized_detail',
    'equipment_status', 'isp_checkout_ref',
]
S4_FIELDS = [
    'deviation_found', 'deviation_detail', 'deviation_resolved',
    'evidence_ref', 'closure_note',
]

FORM_CODE = 'ISP_MAINT_RECORD'
FORM_NAME = 'ISP 機房設備維護申請與執行紀錄單'
FORM_DESCRIPTION = '一張單走完申請、進出控制、維護作業、結案四個階段；每一關只開放該階段的區段'
WORKFLOW_CODE = 'ISP_MAINT_FLOW'
WORKFLOW_NAME = 'ISP 機房設備維護與進出控制'
WORKFLOW_DESCRIPTION = """一張表單四個階段：主管核准 → 現場進出控制 → 維護作業 → 結案。
階段切換靠 OpFieldWrite 把隱藏欄位 stage 改成 S2／S3／S4，表單上的區段用
form.io customConditional 依 stage 顯示；每個簽核關卡再用 field_permissions
只開放該階段的欄位可修改，其餘唯讀。拒絕放行、主管不授權、作業中止都走
End(cancel)，案件記為已取消；駁回與撤回申請不接出線，案件記為已退回。"""

FORM_SCHEMA = {
    'display': 'form',
    'components': [
        _title('ISP 機房設備維護申請與執行紀錄單'),
        _hint('本單分四個區段。送單時只需填「一、維護申請」；其餘區段由各關卡的負責人在簽核畫面填寫，'
              '沒輪到的區段不會顯示。'),
        {'key': 'stage', 'type': 'hidden', 'input': True, 'label': '階段', 'defaultValue': 'S1',
         'tableView': False},
        _panel('sec_apply', '一、維護申請（申請人填寫）', [
            _text('vendor_name', '廠商名稱', required=True),
            _textarea('maintenance_scope', '維護內容與授權範圍', rows=3, required=True,
                      description='只授權這裡寫的項目；現場超出範圍的操作會被制止並記錄'),
            _textarea('equipment_list', '設備清單（型號／資產編號）', rows=2, required=True),
            _text('planned_date', '預計維護日期', required=True, description='格式 YYYY-MM-DD'),
            _textarea('planned_personnel', '預計到場人員', rows=3, required=True,
                      description='一人一行：姓名／所屬公司／證件末四碼。現場只放行這份名單上的人'),
            _textarea('applicant_note', '備註', rows=2),
        ]),
        _panel('sec_onsite', '二、現場進出控制（現場員工填寫）', [
            _textarea('actual_personnel', '實際到場人員', rows=3, description='一人一行，與上方名單逐一核對'),
            _select('personnel_match', '是否符合原申請', [('全部符合', 'match'), ('有臨時人員', 'temp'), ('不符合', 'mismatch')]),
            _textarea('temp_personnel_handling', '臨時人員處理', rows=2,
                      description='現場接受的授權依據與風險邊界；需主管確認時在決策選「向主管升級確認」'),
            _text('isp_registration_ref', 'ISP 進出登記參照', description='ISP 登記單號或登記時間'),
            _select('isp_admitted', 'ISP 准許進入', [('是', 'yes'), ('否', 'no')]),
        ], show_stages=['S2', 'S3', 'S4']),
        _panel('sec_work', '三、維護作業（陪同員工填寫）', [
            _textarea('work_summary', '作業摘要', rows=3, description='只記錄授權範圍內實際執行的項目'),
            _select('unauthorized_attempt', '是否發生非授權操作', [('無', 'none'), ('有（已制止並記錄）', 'blocked')]),
            _textarea('unauthorized_detail', '非授權操作說明', rows=2),
            _textarea('equipment_status', '設備狀態與韌體版本', rows=2),
            _text('isp_checkout_ref', 'ISP 離場登記參照'),
        ], show_stages=['S3', 'S4']),
        _panel('sec_close', '四、紀錄與結案（負責人填寫）', [
            _select('deviation_found', '是否有人員變更或重要偏差', [('否', 'no'), ('是', 'yes')]),
            _textarea('deviation_detail', '偏差說明與廠商回覆', rows=3),
            _select('deviation_resolved', '偏差是否已妥善處理', [('是', 'yes'), ('否', 'no'), ('不適用', 'na')]),
            _textarea('evidence_ref', '證據參照', rows=2, description='核准紀錄、ISP 登記、照片或 log 的存放位置'),
            _textarea('closure_note', '結案備註', rows=2),
        ], show_stages=['S4']),
        _submit_button(),
    ],
}


def ensure_category(org):
    """Return the org-local equipment maintenance category, creating it when missing."""
    from app import db
    from modules.form_workflow.models import FwCategory

    category = FwCategory.query.filter_by(
        org_secure_code=org.secure_code,
        name=CATEGORY_NAME,
        is_deleted=False,
    ).first()
    if category:
        category.description = '機房與設備維護作業'
        category.display_order = 20
        category.is_system = False
        category.show_in_form_design = True
        category.show_in_workflow_design = True
        category.show_in_form_center = True
        return category

    category = FwCategory(
        org_secure_code=org.secure_code,
        name=CATEGORY_NAME,
        description='機房與設備維護作業',
        display_order=20,
        is_system=False,
        show_in_form_design=True,
        show_in_workflow_design=True,
        show_in_form_center=True,
    )
    db.session.add(category)
    db.session.flush()
    return category


def _perm(editable_keys):
    """只開放指定欄位可修改；未列的欄位依平台預設唯讀。"""
    return {'approver': {k: 'editable' for k in editable_keys}, 'reader': {}}


def _fa(node_id, label, x, y, assignee, output_var, decisions, editable=(), description='',
        require_comment=False):
    """assignee: dict，直接展開進 config。"""
    config = {
        **assignee,
        'selection_mode': 'single',
        'output_variable': output_var,
        'allow_comment': True, 'require_comment': require_comment,
        'use_custom_decisions': True, 'input_variables': [],
        'decision_options': decisions,
        'field_permissions': _perm(editable),
    }
    return _node(node_id, 'FormAdapter', label, config, x, y, description)


def _opt(opt_id, label, value, edges, style='primary'):
    return {'id': opt_id, 'label': label, 'value': value, 'style': style, 'target_edges': list(edges)}


def _setstage(node_id, stage, x, y):
    return _node(node_id, 'OpFieldWrite', f'進入階段 {stage}',
                 {'target_field': 'stage', 'content': stage, 'content_type': 'text'}, x, y,
                 f'把隱藏欄位 stage 改成 {stage}，表單上對應的區段從這一刻起才會顯示。')


INITIATOR = {'assignee_type': 'INITIATOR'}


def ROLE(role_sc, scope):
    return {'assignee_type': 'ROLE', 'assignee_value': role_sc, 'unit_scope': scope,
            'self_target_action': 'escalate_or_return'}


def build_graph(dept_manager_sc, security_staff_sc, soc_supervisor_sc):
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 120, 300, '流程入口，不需要任何前置設定。'),
        _fa('node-Approve', '主管核准', 420, 300, ROLE(dept_manager_sc, 'APPLICANT_UNIT'),
            'isp_approve', [
                _opt('opt-approve-ok', '核准', 'approved', ['edge-approve-ok']),
                _opt('opt-approve-return', '退回補件', 'return', ['edge-approve-return'], 'warning'),
                _opt('opt-approve-reject', '駁回', 'rejected', [], 'danger'),
            ], description='申請人所屬單位主管審核維護範圍與日期；此關只檢視申請區段，不開放改欄位。'),
        _fa('node-Revise', '申請人補件或重新排程', 420, 520, INITIATOR,
            'isp_revise', [
                _opt('opt-revise-resubmit', '重新送審', 'resubmit', ['edge-revise-resubmit']),
                _opt('opt-revise-withdraw', '撤回申請', 'withdraw', [], 'danger'),
            ], editable=S1_FIELDS,
            description='原申請人修正維護申請資料後重新送審；只開放第一區段欄位。'),
        _setstage('node-SetS2', 'S2', 720, 300),
        _fa('node-Onsite', '現場核對與進出登記', 1020, 300, ROLE(security_staff_sc, 'GLOBAL'),
            'isp_onsite', [
                _opt('opt-onsite-ok', '放行進入', 'admit', ['edge-onsite-ok']),
                _opt('opt-onsite-escalate', '向主管升級確認', 'escalate', ['edge-onsite-escalate'], 'warning'),
                _opt('opt-onsite-deny', '拒絕放行', 'deny', ['edge-onsite-deny'], 'danger'),
            ], editable=S2_FIELDS,
            description='現場員工核對到場人員與 ISP 登記；只開放第二區段，讓未到階段的作業資料保持唯讀。'),
        _fa('node-Escalate', '主管確認臨時人員', 1020, 80, ROLE(dept_manager_sc, 'APPLICANT_UNIT'),
            'isp_escalate', [
                _opt('opt-escalate-ok', '授權放行', 'authorized', ['edge-escalate-ok']),
                _opt('opt-escalate-deny', '不授權', 'unauthorized', ['edge-escalate-deny'], 'danger'),
            ], editable=['temp_personnel_handling'],
            description='若現場出現臨時人員，由申請單位主管確認授權邊界；只開放臨時人員處理欄位。'),
        _setstage('node-SetS3', 'S3', 1320, 300),
        _fa('node-Work', '維護作業完成確認', 1620, 300, ROLE(security_staff_sc, 'GLOBAL'),
            'isp_work', [
                _opt('opt-work-done', '作業完成並已離場', 'done', ['edge-work-done']),
                _opt('opt-work-abort', '作業中止', 'abort', ['edge-work-abort'], 'danger'),
            ], editable=S3_FIELDS,
            description='陪同員工記錄授權範圍內的實際維護結果；只開放第三區段，避免回填申請與進出控制資料。'),
        _setstage('node-SetS4', 'S4', 1920, 300),
        _fa('node-Close', '負責人結案確認', 2220, 300, ROLE(soc_supervisor_sc, 'GLOBAL'),
            'isp_close', [
                _opt('opt-close-ok', '結案', 'closed', ['edge-close-ok']),
                _opt('opt-close-escalate', '升級主管處理偏差', 'escalate', ['edge-close-escalate'], 'warning'),
            ], editable=S4_FIELDS, require_comment=True,
            description='SOC 負責人檢查偏差、證據與結案紀錄；只開放第四區段，並要求留下簽核意見。'),
        _fa('node-CloseEscalate', '主管處理偏差', 2220, 80, ROLE(dept_manager_sc, 'APPLICANT_UNIT'),
            'isp_close_escalate', [
                _opt('opt-cesc-back', '已處理，回到結案確認', 'handled', ['edge-cesc-back']),
            ], editable=['deviation_detail', 'deviation_resolved'],
            description='重大偏差交由申請單位主管補充處理方式；只開放偏差說明與處理狀態。'),
        _node('node-End', 'End', 'Process 結案', {'finish_mode': 'detach'}, 2520, 300,
              '正常結案，流程以完成狀態結束。'),
        _node('node-EndCancel', 'End', '停止進入或取消維護', {'finish_mode': 'cancel'}, 1620, 520,
              '拒絕放行、主管不授權或作業中止時，流程以取消狀態結束。'),
    ]
    edges = [
        _edge('edge-start', 'node-Start', 'node-Approve'),
        _edge('edge-approve-ok', 'node-Approve', 'node-SetS2', '核准'),
        _edge('edge-approve-return', 'node-Approve', 'node-Revise', '退回補件'),
        _edge('edge-revise-resubmit', 'node-Revise', 'node-Approve', '重新送審'),
        _edge('edge-s2', 'node-SetS2', 'node-Onsite'),
        _edge('edge-onsite-ok', 'node-Onsite', 'node-SetS3', '放行進入'),
        _edge('edge-onsite-escalate', 'node-Onsite', 'node-Escalate', '升級確認'),
        _edge('edge-onsite-deny', 'node-Onsite', 'node-EndCancel', '拒絕放行'),
        _edge('edge-escalate-ok', 'node-Escalate', 'node-SetS3', '授權放行'),
        _edge('edge-escalate-deny', 'node-Escalate', 'node-EndCancel', '不授權'),
        _edge('edge-s3', 'node-SetS3', 'node-Work'),
        _edge('edge-work-done', 'node-Work', 'node-SetS4', '完成並離場'),
        _edge('edge-work-abort', 'node-Work', 'node-EndCancel', '作業中止'),
        _edge('edge-s4', 'node-SetS4', 'node-Close'),
        _edge('edge-close-ok', 'node-Close', 'node-End', '結案'),
        _edge('edge-close-escalate', 'node-Close', 'node-CloseEscalate', '升級處理'),
        _edge('edge-cesc-back', 'node-CloseEscalate', 'node-Close', '已處理'),
    ]
    graph = _graph(nodes, edges)
    _check_graph(graph)
    return graph


def _check_graph(graph):
    node_ids = {n.get('id') for n in graph.get('nodes', [])}
    edge_by_id = {e.get('id'): e for e in graph.get('edges', [])}

    if len(node_ids) != len(graph.get('nodes', [])):
        raise ValueError('graph contains duplicate or empty node ids')
    if len(edge_by_id) != len(graph.get('edges', [])):
        raise ValueError('graph contains duplicate or empty edge ids')

    for edge in graph.get('edges', []):
        if edge.get('source') not in node_ids:
            raise ValueError(f"edge {edge.get('id')} has missing source {edge.get('source')}")
        if edge.get('target') not in node_ids:
            raise ValueError(f"edge {edge.get('id')} has missing target {edge.get('target')}")

    for node in graph.get('nodes', []):
        if node.get('type') != 'FormAdapter':
            continue
        node_id = node.get('id')
        for option in node.get('config', {}).get('decision_options', []):
            for edge_id in option.get('target_edges') or []:
                edge = edge_by_id.get(edge_id)
                if not edge:
                    raise ValueError(f"node {node_id} option {option.get('id')} references missing edge {edge_id}")
                if edge.get('source') != node_id:
                    raise ValueError(
                        f"node {node_id} option {option.get('id')} references edge {edge_id} "
                        f"from {edge.get('source')}"
                    )


DEMO = {
    'form_code': FORM_CODE,
    'form_name': FORM_NAME,
    'form_description': FORM_DESCRIPTION,
    'form_schema': FORM_SCHEMA,
    'workflow_code': WORKFLOW_CODE,
    'workflow_name': WORKFLOW_NAME,
    'description': WORKFLOW_DESCRIPTION,
}


def ensure_fill_permissions(db, models, org_sc, mapping, apply):
    """
    給示範表單開填寫權限（表單中心預設只放行 SYSTEM_ADMIN / FLOW_DESIGNER /
    FORM_DESIGNER，ORG_ADMIN 不在內，沒有這一步連企業管理員都送不了單）。
    逐一授權給企業內非 EXTERNAL 的在職帳號。
    """
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
        if not apply:
            added += 1
            continue
        db.session.add(FwMappingPermission(
            org_secure_code=org_sc,
            mapping_secure_code=mapping.secure_code,
            grant_type='user',
            grant_target=user.secure_code,
            grant_target_name=user.display_name or user.username,
            include_children=False,
            created_by_name='provision_isp_maintenance_demo',
        ))
        added += 1
    if added:
        log(f'  {"[預演] 會新增" if not apply else "已新增"}填寫授權 {added} 筆'
            f'（共 {len(users)} 個帳號）')
    else:
        log(f'  填寫授權已存在（{len(users)} 個帳號）')


def apply_full_demo(db, models, org, demo, publisher, apply, role_secure_codes):
    from app.utils.security import generate_secure_code

    FwFormTemplate = models['FwFormTemplate']
    FwWorkflowTemplate = models['FwWorkflowTemplate']
    FwFormWorkflowMapping = models['FwFormWorkflowMapping']
    FwPublishedFormWorkflow = models['FwPublishedFormWorkflow']

    osc = org.secure_code
    dept_manager_sc = role_secure_codes['DEPT_MANAGER']
    security_staff_sc = role_secure_codes['SECURITY_STAFF']
    soc_supervisor_sc = role_secure_codes['SOC_SUPERVISOR']

    form = FwFormTemplate.query.filter_by(
        org_secure_code=osc, code=demo['form_code'], is_deleted=False).first()
    is_new_form = form is None
    if is_new_form:
        form = FwFormTemplate(
            secure_code=generate_secure_code(), org_secure_code=osc, code=demo['form_code'],
            version='AA', revision=1, name=demo['form_name'],
            description=demo['form_description'], category=CATEGORY_NAME,
            category_secure_code=CATEGORY_SECURE_CODE, schema=demo['form_schema'],
            builder_config={}, is_published=False, is_active=True,
            is_protected=False, permission_type='org')
    else:
        form.name = demo['form_name']
        form.description = demo['form_description']
        form.schema = demo['form_schema']
        form.category = CATEGORY_NAME
        form.category_secure_code = CATEGORY_SECURE_CODE
        form.revision = (form.revision or 0) + 1

    wf = FwWorkflowTemplate.query.filter_by(
        org_secure_code=osc, code=demo['workflow_code'], is_deleted=False).first()
    is_new_wf = wf is None
    graph = build_graph(dept_manager_sc, security_staff_sc, soc_supervisor_sc)
    if is_new_wf:
        wf = FwWorkflowTemplate(
            secure_code=generate_secure_code(), org_secure_code=osc, code=demo['workflow_code'],
            version='AA', revision=1, name=demo['workflow_name'],
            description=demo['description'], category=CATEGORY_NAME,
            category_secure_code=CATEGORY_SECURE_CODE,
            graph=graph, cytoscape_config=graph, is_published=False, is_active=True,
            is_protected=False, permission_type='org', is_subprocess=False)
    else:
        wf.name = demo['workflow_name']
        wf.description = demo['description']
        wf.category = CATEGORY_NAME
        wf.category_secure_code = CATEGORY_SECURE_CODE
        wf.graph = graph
        wf.cytoscape_config = graph
        wf.is_subprocess = False
        wf.revision = (wf.revision or 0) + 1

    log(f"  流程 {demo['workflow_code']}{'（新建）' if is_new_wf else ''} + "
        f"表單 {demo['form_code']}{'（新建）' if is_new_form else ''}")

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
            description=f'{CATEGORY_NAME}：{demo["workflow_name"]}')
        db.session.add(mapping)
    else:
        mapping.form_template_id = form.id
        mapping.form_template_secure_code = form.secure_code
        mapping.form_template_code = form.code
        mapping.form_template_version = form.version
        mapping.workflow_template_id = wf.id
        mapping.workflow_template_secure_code = wf.secure_code
        mapping.workflow_template_code = wf.code
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
    log(f'  已發行 v{published.publish_version}：{published.secure_code}'
        f'（表單 sc={form.secure_code}，流程 sc={wf.secure_code}）')
    return {'form_sc': form.secure_code, 'wf_sc': wf.secure_code,
            'published_sc': published.secure_code}


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


def _required_role_secure_codes(org_sc):
    from app.models import Role

    required = ['DEPT_MANAGER', 'SECURITY_STAFF', 'SOC_SUPERVISOR']
    rows = Role.query.filter(
        Role.org_secure_code == org_sc,
        Role.code.in_(required),
        Role.is_deleted.is_(False),
    ).all()
    found = {role.code: role.secure_code for role in rows}
    missing = [code for code in required if code not in found]
    return found, missing


def provision(org, apply=True, **opts):
    from app import db
    from app.models import User

    del opts
    db.session.execute(db.text("SET LOCAL app.is_system_admin = 'true'"))
    role_secure_codes, missing_roles = _required_role_secure_codes(org.secure_code)
    if missing_roles:
        log('缺少必要角色：' + ', '.join(missing_roles))
        return {'error': 'missing_roles', 'missing_roles': missing_roles}

    global CATEGORY_SECURE_CODE
    CATEGORY_SECURE_CODE = ensure_category(org).secure_code

    models = _workflow_models()
    osc = org.secure_code
    log(f'企業：{org.name}（{osc}）')
    load_node_icons(models)

    publisher = User.query.filter_by(
        org_secure_code=osc, user_type='ORG_ADMIN',
        is_deleted=False, is_active=True).first()

    log(f"\n--- {DEMO['workflow_name']} ---")
    result = apply_full_demo(db, models, org, DEMO, publisher, apply, role_secure_codes)
    return {'result': result, 'category_secure_code': CATEGORY_SECURE_CODE}


def main():
    parser = argparse.ArgumentParser(description='佈建 ISP 機房設備維護申請與執行紀錄示範')
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
        if result.get('error') == 'missing_roles':
            db.session.rollback()
            return 2
        if args.apply:
            db.session.commit()
            log('\n已寫入。到 /forms/center 的「填寫表單」就看得到這張單。')
            r = result['result']
            if r:
                log('\n完整示範：')
                log(f"  {WORKFLOW_CODE}: form_sc={r['form_sc']} wf_sc={r['wf_sc']} "
                    f"published_sc={r['published_sc']}")
        else:
            db.session.rollback()
            log('\n[預演] 未寫入任何資料')
    return 0


if __name__ == '__main__':
    sys.exit(main())
