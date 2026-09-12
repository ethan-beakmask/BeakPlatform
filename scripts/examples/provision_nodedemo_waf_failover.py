#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
node展覽館 —— WAF 節點熱備切換（OsExecutor 實務應用）。

這張範本表單示範一個真的會有副作用的維運流程：發現 WAF 故障的人送單，
寫明故障現象與切換原因；決策關卡留下人員簽核意見做為決策記錄；OsExecutor
在管理機上執行 ITHome2026-WAF/failover.sh；結果寫回表單，再依 ok /
exception / timeout 分流。成功直接結束，失敗進人工確認關卡後結束。

目標企業預設是系統預設企業（Organization.code='SYSTEM'），分類固定是
「node展覽館」（fw_categories.secure_code='J1ygL6zexauKlLM0_Ktoaw'）。

冪等：重跑會沿用既有表單／流程（依 code 找），bump revision 並重新發行
（會停用舊的已發行版本並建立新版）。填寫權限授予企業內所有非 EXTERNAL
的在職帳號。

用法：
    cd /opt/BeakPlatform-dev
    set -a && source .env && set +a
    venv/bin/python scripts/examples/provision_nodedemo_waf_failover.py --dry-run --node "現役主機=sec-vm" --node "備援主機=ubuntu24"
    venv/bin/python scripts/examples/provision_nodedemo_waf_failover.py --apply  --node "現役主機=sec-vm" --node "備援主機=ubuntu24"

節點 config 欄位依 handler 原始碼確認：
    modules/form_workflow/services/node_handlers/os_executor_handler.py
    modules/form_workflow/services/node_handlers/formadapter_handler.py
    modules/form_workflow/services/node_handlers/branch_handler.py
    modules/form_workflow/services/node_handlers/fieldwrite_handler.py
    modules/form_workflow/services/node_handlers/end_handler.py
權威對照表：/opt/tmp/verify/20260907-node-config-reference.md（OsExecutor／
FormAdapter／Branch／OpFieldWrite／End 各節）
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'backend'))

ORG_CODE = 'SYSTEM'
CATEGORY_NAME = 'node展覽館'
CATEGORY_SECURE_CODE = 'J1ygL6zexauKlLM0_Ktoaw'
ICON_BASE = '/static/modules/form_workflow/icons/workflow'

FORM_CODE = 'NODEDEMO_WAF_FAILOVER'
FORM_NAME = 'WAF 節點熱備切換申請'
WORKFLOW_CODE = 'NODEDEMO_WAF_FAILOVER_FLOW'
WORKFLOW_NAME = 'WAF 節點熱備切換（OsExecutor 實務）'

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


def _graph(nodes, edges):
    return {'nodes': nodes, 'edges': edges, 'relayPoints': [],
            'canvasSettings': _canvas(), 'fieldReadConfig': {}}


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


def _select(key, label, options, description=''):
    comp = {
        'key': key, 'type': 'select', 'input': True, 'label': label, 'tableView': True,
        'dataSrc': 'values',
        'data': {'values': [{'label': label, 'value': value} for label, value in options]},
        'validate': {'required': True},
    }
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


def _approve_config(output_variable, label, target_edge):
    """單一決策的自簽關卡：assignee_type=INITIATOR，一個人就能走完全程。"""
    return {
        'assignee_type': 'INITIATOR',
        'selection_mode': 'single',
        'output_variable': output_variable,
        'allow_comment': True, 'require_comment': False,
        'use_custom_decisions': True, 'input_variables': [],
        'decision_options': [
            {'id': 'opt-continue', 'label': label, 'value': 'continue',
             'style': 'primary', 'target_edges': [target_edge]},
        ],
    }


def _decision_config(assignee_config):
    config = dict(assignee_config)
    config.update({
        'selection_mode': 'single',
        'output_variable': 'waf_failover_decision',
        'allow_comment': True,
        'require_comment': True,
        'use_custom_decisions': True,
        'input_variables': [],
        'decision_options': [
            {'id': 'opt-run', 'label': '執行切換', 'value': 'run',
             'style': 'primary', 'target_edges': ['edge-decision-os']},
            {'id': 'opt-cancel', 'label': '取消', 'value': 'cancel',
             'style': 'danger', 'target_edges': []},
        ],
    })
    return config


def _manual_confirm_config(assignee_config):
    config = _approve_config('waf_failover_manual_confirm', '已人工處置', 'edge-manual-end')
    config.update(assignee_config)
    return config


def _disabled(comp):
    comp['disabled'] = True
    return comp


def build_waf_schema(node_options):
    symptom = _textarea('symptom', '故障現象／切換原因',
                        '請描述偵測到的 WAF 異常、影響範圍，以及為什麼需要切換。',
                        rows=6)
    symptom['validate'] = {'required': True}
    return {
        'display': 'form',
        'components': [
            _title(FORM_NAME),
            _hint('這張單會真的執行 WAF 節點熱備切換。決策關卡的簽核意見就是'
                  '人員決策記錄；執行約 20 秒；failover.sh 的判定結果與輸出'
                  '會寫回本單，成功直接結束，失敗會進人工確認關卡。'),
            _select('target_node', '目標節點', node_options,
                    '選擇要切換到的 WAF 節點。選項值會原樣傳給 failover.sh 的 to 參數。'),
            symptom,
            _disabled(_text('failover_result', '執行結果（由流程寫回）',
                            'ok／exception／timeout，由 OsExecutor 寫入。')),
            _disabled(_textarea('failover_output', 'failover.sh 輸出（由流程寫回）',
                                'stdout 與 stderr 會由流程寫回，方便直接在表單中心留存。',
                                rows=12)),
            _submit_button(),
        ],
    }


def build_waf_graph(failover_dir, config_path, timeout_seconds, assignee_config):
    command = f'bash {os.path.join(failover_dir, "failover.sh")} --config {config_path} to ${{f.target_node}} --yes'
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 180, 220,
              '流程入口。送單者已在表單寫明故障現象、切換原因與目標節點。'),
        _node('node-Decision', 'FormAdapter', '切換決策',
              _decision_config(assignee_config), 460, 220,
              '人員決策關卡。簽核意見就是本次 WAF 熱備切換的人員決策留證；'
              '按「執行切換」才會進入 OsExecutor，按「取消」會成為 REJECTED 終態。'),
        _node('node-OsFailover', 'OsExecutor', '執行 failover.sh', {
            'command': command,
            'result_var': 'failover',
            'timeout_seconds': timeout_seconds,
            'expect_exit_codes': [0],
            'wait_for_result': True,
            'kill_on_timeout': 'group',
            'notify_on_exception': True,
        }, 740, 220,
            '在管理機上執行 WAF 熱備切換工具。這是有副作用的維運命令，'
            'OsExecutor 不會因 exception 或 timeout 自動重試；真正結果要看'
            ' failover_result 與 failover_stdout / failover_stderr。'),
        _node('node-WriteResult', 'OpFieldWrite', '寫回執行結果', {
            'target_field': 'failover_result',
            'content': '${v.failover_result}',
            'content_type': 'text',
        }, 1020, 120,
            '把 OsExecutor 四分法結果寫回 failover_result 欄位：ok、exception、timeout'
            '或 dispatched。'),
        _node('node-WriteOutput', 'OpFieldWrite', '寫回命令輸出', {
            'target_field': 'failover_output',
            'content': '【stdout】\n${v.failover_stdout}\n\n【stderr】\n${v.failover_stderr}',
            'content_type': 'text',
        }, 1020, 320,
            '把 failover.sh 的 stdout 與 stderr 寫回表單，包含失敗時 stdout 印出的'
            '手動回退指令。'),
        _node('node-Branch', 'Branch', '切換成功？', {
            'rules': [
                {'name': '切換成功',
                 'conditions': [{'variable': '${v.failover_result}', 'operator': '==',
                                  'value': 'ok'}],
                 'target_edges': ['edge-branch-success']},
            ],
            'fallback': {'action': 'route', 'target_edge': 'edge-branch-manual',
                         'log_message': 'failover.sh 未回報 ok，轉人工確認'},
        }, 1300, 220,
            '依 OsExecutor 的 failover_result 分流：ok 直接結束；exception 或 timeout'
            '走人工確認。Branch fallback 明確設定 route，確保失敗路徑會推進。'),
        _node('node-EndSuccess', 'End', '完成', {'finish_mode': 'detach'}, 1580, 120,
              '切換成功，流程正常結束。'),
        _node('node-Manual', 'FormAdapter', '切換失敗，人工確認',
              _manual_confirm_config(assignee_config), 1580, 320,
              '切換失敗或逾時時停在人工確認關卡，由人員確認現場狀態、必要時依'
              ' failover.sh 輸出中的手動回退指令處置。'),
        _node('node-EndManual', 'End', '結束', {'finish_mode': 'detach'}, 1860, 320,
              '人工確認後結束流程，表單保留決策記錄與命令輸出。'),
    ]
    edges = [
        _edge('edge-start-decision', 'node-Start', 'node-Decision'),
        _edge('edge-decision-os', 'node-Decision', 'node-OsFailover', '執行切換'),
        _edge('edge-os-write-result', 'node-OsFailover', 'node-WriteResult'),
        _edge('edge-write-result-output', 'node-WriteResult', 'node-WriteOutput'),
        _edge('edge-write-output-branch', 'node-WriteOutput', 'node-Branch'),
        _edge('edge-branch-success', 'node-Branch', 'node-EndSuccess', 'ok'),
        _edge('edge-branch-manual', 'node-Branch', 'node-Manual', '失敗或逾時'),
        _edge('edge-manual-end', 'node-Manual', 'node-EndManual', '已人工處置'),
    ]
    return _graph(nodes, edges)


WAF_DESCRIPTION = (
    '【這個流程示範什麼】\n'
    '這是 OsExecutor 的實務應用：流程在平台主機上執行有副作用的 WAF 熱備切換'
    '命令。送單者填寫故障現象與目標節點後，先進人員決策關卡；簽核意見即是'
    '決策留證。核准後才由 OsExecutor 執行 failover.sh，並把 ok / exception /'
    ' timeout 等四分法結果與命令輸出寫回表單。\n\n'
    '【本流程的設定重點】\n'
    '- FormAdapter「切換決策」使用自訂決策：「執行切換」接出線到 OsExecutor，'
    '「取消」不接出線，成為 REJECTED 終態。\n'
    '- OsExecutor 使用 wait_for_result=true，expect_exit_codes=[0]，'
    'kill_on_timeout=group；命令中的 ${f.target_node} 使用預設引號化，避免表單'
    '輸入被 shell 當成額外命令。\n'
    '- OpFieldWrite 會把 failover_result 與 stdout/stderr 寫回本單。\n'
    '- Branch 判斷 ${v.failover_result} == ok 時直接到完成；fallback 明確 route'
    '到人工確認，避免失敗時停在分支節點。\n\n'
    '【怎麼看結果】\n'
    '成功時 failover_result 會是 ok，流程走到「完成」。若是 exception 或 timeout，'
    '流程會停在「切換失敗，人工確認」；請查看 failover_output 的 stdout/stderr，'
    '必要時依工具輸出的手動回退指令處置。'
)


def build_demo(node_options, failover_dir, config_path, timeout_seconds, assignee_config):
    return {
        'form_code': FORM_CODE,
        'form_name': FORM_NAME,
        'form_schema': build_waf_schema(node_options),
        'workflow_code': WORKFLOW_CODE,
        'workflow_name': WORKFLOW_NAME,
        'description': WAF_DESCRIPTION,
        'graph': lambda: build_waf_graph(
            failover_dir, config_path, timeout_seconds, assignee_config),
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
            created_by_name='provision_nodedemo_waf_failover',
        ))
        added += 1
    if added:
        log(f'  {"[預演] 會新增" if not apply else "已新增"}填寫授權 {added} 筆'
            f'（共 {len(users)} 個帳號）')
    else:
        log(f'  填寫授權已存在（{len(users)} 個帳號）')


def apply_full_demo(db, models, org, demo, publisher, apply):
    from app.utils.security import generate_secure_code

    FwFormTemplate = models['FwFormTemplate']
    FwWorkflowTemplate = models['FwWorkflowTemplate']
    FwFormWorkflowMapping = models['FwFormWorkflowMapping']
    FwPublishedFormWorkflow = models['FwPublishedFormWorkflow']

    osc = org.secure_code

    form = FwFormTemplate.query.filter_by(
        org_secure_code=osc, code=demo['form_code'], is_deleted=False).first()
    is_new_form = form is None
    if is_new_form:
        form = FwFormTemplate(
            secure_code=generate_secure_code(), org_secure_code=osc, code=demo['form_code'],
            version='AA', revision=1, name=demo['form_name'],
            description=demo['form_name'], category=CATEGORY_NAME,
            category_secure_code=CATEGORY_SECURE_CODE, schema=demo['form_schema'],
            builder_config={}, is_published=False, is_active=True,
            is_protected=False, permission_type='org')
    else:
        form.name = demo['form_name']
        form.schema = demo['form_schema']
        form.revision = (form.revision or 0) + 1

    wf = FwWorkflowTemplate.query.filter_by(
        org_secure_code=osc, code=demo['workflow_code'], is_deleted=False).first()
    is_new_wf = wf is None
    graph = demo['graph']()
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
        # graph 與 cytoscape_config 兩欄都要寫（設計器讀後者，引擎讀前者）；
        # 直接改 graph 不會自動 bump revision，publish 判斷有無變更靠 version+revision。
        wf.graph = graph
        wf.cytoscape_config = graph
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
            description=f"node展覽館：{demo['workflow_name']}")
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
        existing.status = 'Suspended'  # 不呼叫 suspend()：它內部會 commit，會打斷這支腳本的交易

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


def repo_root():
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))


def default_failover_dir():
    return os.path.join(repo_root(), 'ITHome2026-WAF')


def parse_node_option(raw):
    if '=' not in raw:
        raise argparse.ArgumentTypeError('--node 格式必須是「顯示名稱=節點識別」')
    label, value = raw.split('=', 1)
    label = label.strip()
    value = value.strip()
    if not label or not value:
        raise argparse.ArgumentTypeError('--node 的顯示名稱與節點識別都不可空白')
    return label, value


def build_parser():
    parser = argparse.ArgumentParser(
        description='佈建 node展覽館的 WAF 節點熱備切換範本',
        formatter_class=argparse.RawTextHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--dry-run', action='store_true', help='只列出會做什麼，不寫入')
    group.add_argument('--apply', action='store_true', help='實際寫入資料庫')
    parser.add_argument('--org', default=ORG_CODE, help=f'企業 code（預設 {ORG_CODE}）')
    parser.add_argument('--failover-dir', default=default_failover_dir(),
                        help='failover.sh 所在目錄（預設為本 repo 的 ITHome2026-WAF）')
    parser.add_argument('--config', default=None,
                        help='failover.conf 路徑（預設 <failover-dir>/failover.conf）')
    parser.add_argument('--node', action='append', type=parse_node_option, default=[],
                        help='目標節點選項，可重複。格式：「顯示名稱=節點識別」')
    parser.add_argument('--approver-role', default=None,
                        help='決策關卡角色 code；未給則指派送單者自己決策')
    parser.add_argument('--timeout-seconds', type=int, default=240,
                        help='OsExecutor timeout_seconds（預設 240）')
    return parser


def resolve_role_secure_code(Role, org_sc, role_code):
    if not role_code:
        return None
    role = Role.query.filter_by(
        org_secure_code=org_sc, code=role_code, is_deleted=False, is_active=True).first()
    if not role:
        raise SystemExit(f'找不到角色：{role_code}（企業內 roles.code）')
    return role.secure_code


def main():
    parser = build_parser()
    if len(sys.argv) == 1:
        parser.print_help()
        return 0
    args = parser.parse_args()

    if len(args.node) < 2:
        parser.error('--node 至少要提供 2 個')
    if args.timeout_seconds < 1 or args.timeout_seconds > 3600:
        parser.error('--timeout-seconds 必須介於 1 到 3600')

    failover_dir = os.path.abspath(args.failover_dir)
    config_path = os.path.abspath(args.config or os.path.join(failover_dir, 'failover.conf'))

    from app import create_app, db

    # modules 套件要等 create_app() 跑過 module_loader 才會被插進 sys.path。
    app = create_app('development')
    with app.app_context():
        from app.models import Organization, Role, User
        from modules.form_workflow.models import (
            FwFormTemplate, FwFormWorkflowMapping, FwMappingPermission,
            FwPublishedFormWorkflow, FwWorkflowTemplate, WorkflowNodeDefinition,
        )

        models = {
            'FwFormTemplate': FwFormTemplate,
            'FwFormWorkflowMapping': FwFormWorkflowMapping,
            'FwMappingPermission': FwMappingPermission,
            'FwPublishedFormWorkflow': FwPublishedFormWorkflow,
            'FwWorkflowTemplate': FwWorkflowTemplate,
            'WorkflowNodeDefinition': WorkflowNodeDefinition,
        }

        db.session.execute(db.text("SET LOCAL app.is_system_admin = 'true'"))

        org = Organization.query.filter_by(code=args.org, is_deleted=False).first()
        if not org:
            log(f'找不到企業：{args.org}')
            return 1
        osc = org.secure_code
        log(f'企業：{org.name}（{osc}）')
        load_node_icons(models)

        role_sc = resolve_role_secure_code(Role, osc, args.approver_role)
        if role_sc:
            assignee_config = {'assignee_type': 'ROLE', 'assignee_value': role_sc,
                               'unit_scope': 'GLOBAL'}
            log(f'決策關卡角色：{args.approver_role}（{role_sc}）')
        else:
            assignee_config = {'assignee_type': 'INITIATOR'}
            log('決策關卡：INITIATOR（送單者自己決策）')

        publisher = User.query.filter_by(
            org_secure_code=osc, user_type='ORG_ADMIN',
            is_deleted=False, is_active=True).first()

        log(f'failover-dir：{failover_dir}')
        log(f'config：{config_path}')
        log('目標節點：')
        for label, value in args.node:
            log(f'  {label} = {value}')

        demo = build_demo(args.node, failover_dir, config_path,
                          args.timeout_seconds, assignee_config)

        log('\n=== WAF 節點熱備切換（表單／流程／配對／發行） ===')
        result = apply_full_demo(db, models, org, demo, publisher, args.apply)

        if args.apply:
            db.session.commit()
            log('\n已寫入。到 /forms/center 的「填寫表單」就看得到這張單。')
            if result:
                log(f"\n{WORKFLOW_CODE}: form_sc={result['form_sc']} "
                    f"wf_sc={result['wf_sc']} published_sc={result['published_sc']}")
        else:
            db.session.rollback()
            log('\n[預演] 未寫入任何資料')
    return 0


if __name__ == '__main__':
    sys.exit(main())
