#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PF-252 B3 批次：node展覽館 —— Start（開始）與 End（結束）的示範流程。

    NT-01 Start 示範                              最小流程：Start -> OpSet -> End，
                                                    示範 Start 的角色（流程唯一入口）
    NT-02 End 示範（detach 直接結束）              並行分支：快分支（自動化）8 秒內
                                                    抵達 End(detach)；慢分支（等人簽核）
                                                    的任務在流程已結束後仍留在待辦
    NT-02 End 示範（cancel 中止）                  同樣的並行分支骨架，End 設 cancel：
                                                    一抵達就把慢分支等待中的簽核任務
                                                    強制作廢（CANCELLED）
    NT-02 End 示範（strict 等待全部完成）          同樣的骨架，End 設 strict：反覆等待，
                                                    直到慢分支的簽核任務真的被簽過，
                                                    流程才會結束

三個 End 示範共用同一份骨架（快分支：Delay(8s) -> OpSet -> 同時推進 End 與一個
「旁支示範」無出邊節點；慢分支：Delay(10s) -> FormAdapter(INITIATOR，等人簽核)），
只有 End 節點的 finish_mode 不同，方便對照三者行為差異。

目標企業固定是系統預設企業（Organization.code='SYSTEM'），分類固定是「node展覽館」
（fw_categories.secure_code='J1ygL6zexauKlLM0_Ktoaw'）。

冪等：重跑會沿用既有表單／流程（依 code 找），bump revision 並重新發行（會停用
舊的已發行版本並建立新版）。填寫權限授予企業內所有非 EXTERNAL 的在職帳號。

用法：
    cd /opt/BeakPlatform-dev
    set -a && source .env && set +a
    venv/bin/python scripts/examples/provision_nodedemo_startend.py --dry-run
    venv/bin/python scripts/examples/provision_nodedemo_startend.py --apply

節點 config 欄位依 handler 原始碼確認：
    modules/form_workflow/services/node_handlers/start_handler.py
    modules/form_workflow/services/node_handlers/end_handler.py
    modules/form_workflow/services/node_handlers/delay_handler.py
    modules/form_workflow/services/node_handlers/opset_handler.py
    modules/form_workflow/services/node_handlers/formadapter_handler.py
權威對照表：/opt/tmp/verify/20260907-node-config-reference.md（Start／End／Delay／
OpSet／FormAdapter 節）
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
    """從 workflow_node_definitions 讀每個節點型別登記的圖示（檔名與型別名不是硬規則對應）"""
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


def _text(key, label, description=''):
    comp = {'key': key, 'type': 'textfield', 'input': True, 'label': label, 'tableView': True}
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


# ---------------------------------------------------------------------------
# NT-01 Start 示範
# ---------------------------------------------------------------------------

FORM_START_CODE = 'NODEDEMO_NT01_START_FORM'
WF_START_CODE = 'NODEDEMO_NT01_START_FLOW'
FORM_START_NAME = 'NT-01 Start 示範表單'
WF_START_NAME = 'NT-01 Start 示範'

WF_START_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'Start（開始）是每一個流程模板唯一的入口節點：使用者在表單中心送出表單、或外部系統'
    '透過 API Key 呼叫 /api/trigger/form 發動流程時，流程引擎一律從 Start 節點開始建立第一筆'
    '執行佇列項目，接著才依 Start 的出線往下推進到其他節點。它與「這張表單」的關係是'
    '一對一：一次送單＝一個流程實例（workflow instance）＝一次從這個 Start 節點重新出發，'
    '不會有兩次送單共用同一個 Start 節點執行紀錄的情況。\n\n'
    '【本流程的設定重點】\n'
    '- Start 節點的 config 目前只有一個欄位 init.variables（設計器面板若讓使用者填寫，'
    '介面上像是「開始時預先設定幾個流程變數」），但這份示範刻意不使用它、config 留空：'
    '目前設計流程時要建立初始流程變數，一律改用後面接的 OpSet（變數設定）節點，'
    '這是本平台目前唯一會真的把值寫進 fw_workflow_variables 的方式。\n'
    '- 流程本身故意做到最小：Start 之後只接一個 OpSet 節點（寫入兩個示範變數），'
    '再接 End(finish_mode=detach) 結束。目的是讓第一次看流程設計器的人，能先看清楚'
    '「一個能跑起來的流程最少要有幾個節點」，不被其他節點的設定分散注意力。\n\n'
    '【怎麼看結果】\n'
    '送單後查 fw_workflow_instances，應該立刻（不需要等待）看到一筆新實例，'
    'execution_code 是這次送單的可辨識代號，狀態很快就會變成 COMPLETED；'
    '查 fw_workflow_variables 可以看到 started_by_flow 與 start_time 兩個變數，'
    '值就是 OpSet 節點寫入的內容，證明流程確實是從 Start 一路推進過來的。'
)

FORM_START_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-01 Start 示範表單'),
        _hint('這是全平台最小的可跑流程：Start -&gt; OpSet -&gt; End。送出後幾乎立刻'
              '完成，跑完查 fw_workflow_variables 的 started_by_flow 與 start_time。'),
        _text('applicant_note', '備註（非必填）', '示範用，內容沒有特別的邏輯用途。'),
        _submit_button(),
    ],
}


def build_start_graph():
    nodes = [
        _node(
            'node-Start', 'Start', 'Start', {}, 340, 200,
            '流程唯一入口。送單當下由流程引擎建立第一筆執行佇列項目，就是從這個節點'
            '開始。config 留空：init.variables 欄位目前不會產生任何流程變數，'
            '這份示範刻意不使用它，初始變數一律改用下一步的 OpSet 節點設定。',
        ),
        _node(
            'node-OpSet-Init', 'OpSet', '設定初始變數',
            {'operations': [
                {'target_var': 'started_by_flow', 'operation': 'set',
                 'value': 'NT-01 Start 示範'},
                {'target_var': 'start_time', 'operation': 'set', 'value': '${t.now}'},
            ]},
            600, 200,
            'Start 之後接的第一個節點，寫入兩個流程變數 started_by_flow 與'
            ' start_time（UTC 時間），證明流程確實從 Start 推進到這裡。這是本平台'
            '目前唯一會把值真的寫進流程變數的方式，取代 Start 的 init.variables。',
        ),
        _node(
            'node-End', 'End', 'End', {'finish_mode': 'detach'}, 860, 200,
            '流程收尾。這份最小示範不需要示範 finish_mode 的差異（那是 NT-02 End'
            ' 三個示範的主題），所以直接用預設值 detach：送單、跑完、結束，越簡單'
            '越能看清楚 Start 的角色。',
        ),
    ]
    edges = [
        _edge('edge-start-opset', 'node-Start', 'node-OpSet-Init'),
        _edge('edge-opset-end', 'node-OpSet-Init', 'node-End'),
    ]
    return {'nodes': nodes, 'edges': edges, 'relayPoints': [],
            'canvasSettings': _canvas(), 'fieldReadConfig': {}}


# ---------------------------------------------------------------------------
# NT-02 End 示範（共用骨架，三種 finish_mode）
# ---------------------------------------------------------------------------

_END_MODE_META = {
    'detach': {
        'suffix': 'DETACH',
        'name': 'NT-02 End 示範（detach 直接結束）',
        'mode_label': 'detach（直接結束）',
        'result_note': (
            '流程實例終態是 COMPLETED；慢分支的簽核任務（FormAdapter-Slow）'
            '仍然停在 WAITING，不會被作廢，會繼續留在發起人的表單中心待簽核清單裡'
            '——這正是「detach 不會作廢還在等待中的簽核任務」的具體樣子。用同一個'
            '任務 secure_code 呼叫簽核 API 仍然會成功（回 200），證明它是真的還'
            '活著、可操作，不是殘影。'
        ),
    },
    'cancel': {
        'suffix': 'CANCEL',
        'name': 'NT-02 End 示範（cancel 中止）',
        'mode_label': 'cancel（中止）',
        'result_note': (
            '流程實例終態是 CANCELLED（不是 COMPLETED）；慢分支的簽核任務'
            '一抵達 End(cancel) 就被立刻強制作廢，狀態變成 CANCELLED——不必等到'
            '它自己的 Delay 或人工簽核。事後再對同一個任務 secure_code 呼叫簽核'
            'API 會得到 404「找不到任務或已處理」，證明它已經被作廢，不能再被簽。'
        ),
    },
    'strict': {
        'suffix': 'STRICT',
        'name': 'NT-02 End 示範（strict 等待全部完成）',
        'mode_label': 'strict（等待全部完成）',
        'result_note': (
            '流程實例不會在快分支抵達 End 時就結束：End 發現慢分支的簽核任務還'
            '沒完成，會回到 WAITING、30 秒後再檢查一次，如此反覆。只有等到有人'
            '真的把慢分支的簽核任務簽掉（本示範由驗收腳本代為簽核），End 才會'
            '偵測到所有節點皆已完成，流程實例終態才會變成 COMPLETED。'
        ),
    },
}


def _end_description(mode):
    meta = _END_MODE_META[mode]
    return (
        '【這個節點做什麼】\n'
        'End（結束）是流程的終點：一旦流程實例裡的某個分支走到 End 並成功執行，'
        '整個流程實例就會被判定結束（complete_workflow），不是只有 End 所在的那條'
        '分支結束——是「整個流程」結束。至於結束當下要怎麼處理流程裡其他還沒跑完的'
        '節點，由 finish_mode 決定，三種模式行為差很多，本示範固定用'
        f'finish_mode={mode}（{meta["mode_label"]}）。\n\n'
        '【本流程的設定重點】\n'
        '- 流程一開始就用 Start 的兩條出線分成快、慢兩條並行分支（不需要'
        'ParallelFork，一個節點接兩條出線就是並行）：快分支是 Delay(8秒) -> OpSet'
        ' -> 同時推進到 End 與一個「旁支示範」節點；慢分支是 Delay(10秒) -> '
        'FormAdapter（指定簽核人＝發起人自己，卻刻意不主動簽，模擬「一個還在等人'
        '處理的任務」）。\n'
        '- 快分支的 OpSet 節點同時接了兩條出線：一條到 End，另一條到「旁支示範」'
        '（node-Sidenote）。node-Sidenote 沒有設定任何出線——示範「無出邊的節點'
        '會安全終止該分支，不報錯也不結束流程」：它只是寫一個流程變數就安靜'
        '結束，不會被誤認成流程的終點，真正讓整個流程結束的只有走到 End 節點'
        '這件事。\n'
        f'- End 節點本身設 finish_mode=\'{mode}\'。{meta["mode_label"]}的效果：'
        f'{meta["result_note"]}\n\n'
        '【怎麼看結果】\n'
        '送單後查 fw_workflow_instances.status 看流程實例最終狀態，查'
        'fw_node_execution_queue（依 node_type / status）比對慢分支的'
        ' FormAdapter 任務下場。三個 finish_mode 示範流程的骨架完全相同，'
        '只有這裡的設定不同，建議三個都跑一次，直接比對三張查詢結果的差異，'
        '比只看單一個流程更容易看懂差別。'
    )


FORM_END_SCHEMA_TEMPLATE = (
    '這是「End 三種 finish_mode」示範之一：{mode_label}。送出後流程立刻分成快、慢'
    '兩條並行分支，快分支約 8 秒後抵達 End；慢分支需要有人簽核才會完成'
    '（示範故意留給驗收腳本决定要不要簽）。跑完後查 fw_workflow_instances.status'
    '與 fw_node_execution_queue，比對三個 finish_mode 示範的差異。'
)


def _end_form_schema(mode):
    meta = _END_MODE_META[mode]
    return {
        'display': 'form',
        'components': [
            _title(f'NT-02 End 示範表單（{meta["mode_label"]}）'),
            _hint(FORM_END_SCHEMA_TEMPLATE.format(mode_label=meta['mode_label'])),
            _text('applicant_note', '備註（非必填）', '示範用，內容沒有特別的邏輯用途。'),
            _submit_button(),
        ],
    }


def build_end_graph(mode):
    nodes = [
        _node(
            'node-Start', 'Start', 'Start', {}, 340, 220,
            '流程入口。兩條出線同時推進，形成快、慢兩條並行分支，不需要'
            ' ParallelFork。',
        ),
        # 快分支
        _node(
            'node-Delay-Fast', 'Delay', '快分支：等待8秒',
            {'delay_seconds': 8}, 580, 80,
            '快分支的起點，只等待 8 秒、不需要任何人動作，示範自動化路徑能多快'
            '抵達 End。',
        ),
        _node(
            'node-OpSet-Fast', 'OpSet', '快分支：標記完成',
            {'operations': [
                {'target_var': 'fast_branch_done', 'operation': 'set', 'value': 'true'},
                {'target_var': 'fast_branch_completed_at', 'operation': 'set',
                 'value': '${t.now}'},
            ]},
            820, 80,
            '快分支的最後一步，寫入 fast_branch_done / fast_branch_completed_at'
            '兩個流程變數。這個節點同時接了兩條出線：一條到 End、一條到'
            '「旁支示範」，兩條都會被推進。',
        ),
        _node(
            'node-Sidenote', 'OpSet', '旁支示範（無出邊）',
            {'operations': [{'target_var': 'bystander_note', 'operation': 'set',
                              'value': '示範：無出邊節點安全終止該分支，不影響 End 的行為'}]},
            1060, -20,
            '刻意沒有設定任何出線：執行完寫一個流程變數就安靜結束，不報錯也不會'
            '讓流程卡住。這個節點不是流程的終點，真正讓整個流程實例結束的只有'
            '走到 End 節點這件事——兩者是不同的收尾方式，不要混為一談。',
        ),
        _node(
            'node-End', 'End', f'結束（finish_mode={mode}）',
            {'finish_mode': mode, 'wait_seconds': 2}, 1060, 140,
            _end_description(mode),
        ),
        # 慢分支
        _node(
            'node-Delay-Slow', 'Delay', '慢分支：等待10秒',
            {'delay_seconds': 10}, 580, 340,
            '慢分支的起點，等待 10 秒後才進入下一步（等人簽核），示範一條'
            '「比快分支慢，且需要人工處理」的分支。',
        ),
        _node(
            'node-FormAdapter-Slow', 'FormAdapter', '慢分支：等待簽核（示範故意不簽）',
            {
                'assignee_type': 'INITIATOR',
                'assignee_label': '發起人（示範用）',
                'selection_mode': 'single',
                'output_variable': 'slow_branch_signed',
                'allow_comment': True,
                'require_comment': False,
                'use_custom_decisions': True,
                'input_variables': [],
                'decision_options': [
                    {'id': 'opt-ok', 'label': '確認（示範用）', 'value': 'approved',
                     'style': 'default', 'target_edges': []},
                ],
            },
            820, 340,
            '指定簽核人＝發起人自己（assignee_type=INITIATOR），但本示範刻意不'
            '主動簽核，模擬「一個還沒被處理完的任務」。決策只有一個選項且'
            ' target_edges 為空陣列，代表這是終態決策：真的被簽核之後，這條分支'
            '也不會再推進到任何節點（用來對照 detach/cancel/strict 三種模式對'
            '這個任務的不同下場）。',
        ),
    ]
    edges = [
        _edge('edge-start-fast', 'node-Start', 'node-Delay-Fast', '快分支'),
        _edge('edge-start-slow', 'node-Start', 'node-Delay-Slow', '慢分支'),
        _edge('edge-fast-opset', 'node-Delay-Fast', 'node-OpSet-Fast'),
        _edge('edge-opset-end', 'node-OpSet-Fast', 'node-End'),
        _edge('edge-opset-side', 'node-OpSet-Fast', 'node-Sidenote'),
        _edge('edge-slow-form', 'node-Delay-Slow', 'node-FormAdapter-Slow'),
    ]
    return {'nodes': nodes, 'edges': edges, 'relayPoints': [],
            'canvasSettings': _canvas(), 'fieldReadConfig': {}}


def _end_demo(mode):
    meta = _END_MODE_META[mode]
    return {
        'form_code': f'NODEDEMO_NT02_END_{meta["suffix"]}_FORM',
        'form_name': f'NT-02 End 示範表單（{meta["mode_label"]}）',
        'form_schema': _end_form_schema(mode),
        'workflow_code': f'NODEDEMO_NT02_END_{meta["suffix"]}_FLOW',
        'workflow_name': meta['name'],
        'description': _end_description(mode),
        'graph': lambda mode=mode: build_end_graph(mode),
    }


DEMOS = [
    {
        'form_code': FORM_START_CODE, 'form_name': FORM_START_NAME,
        'form_schema': FORM_START_SCHEMA,
        'workflow_code': WF_START_CODE, 'workflow_name': WF_START_NAME,
        'description': WF_START_DESCRIPTION,
        'graph': build_start_graph,
    },
    _end_demo('detach'),
    _end_demo('cancel'),
    _end_demo('strict'),
]


# ---------------------------------------------------------------------------
# 寫入
# ---------------------------------------------------------------------------

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
            created_by_name='provision_nodedemo_startend',
        ))
        added += 1
    if added:
        log(f'  {"[預演] 會新增" if not apply else "已新增"}填寫授權 {added} 筆'
            f'（共 {len(users)} 個帳號）')
    else:
        log(f'  填寫授權已存在（{len(users)} 個帳號）')


def apply_demo(db, models, org, demo, publisher, apply):
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


def main():
    parser = argparse.ArgumentParser(
        description='佈建 node展覽館的 Start 與 End（detach/cancel/strict）四個示範流程')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--dry-run', action='store_true', help='只列出會做什麼，不寫入')
    group.add_argument('--apply', action='store_true', help='實際寫入資料庫')
    parser.add_argument('--org', default=ORG_CODE, help=f'企業 code（預設 {ORG_CODE}）')
    args = parser.parse_args()

    from app import create_app, db

    # modules 套件要等 create_app() 跑過 module_loader 才會被插進 sys.path，
    # 所以模組層 import 必須放在 create_app() 之後（CLAUDE.md 的既有教訓）。
    app = create_app('development')
    with app.app_context():
        from app.models import Organization, User
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
        log(f'企業：{org.name}（{org.secure_code}）')
        load_node_icons(models)

        publisher = User.query.filter_by(
            org_secure_code=org.secure_code, user_type='ORG_ADMIN',
            is_deleted=False, is_active=True).first()

        results = {}
        for demo in DEMOS:
            log(f"\n=== {demo['workflow_name']} ===")
            results[demo['workflow_code']] = apply_demo(db, models, org, demo, publisher, args.apply)

        if args.apply:
            db.session.commit()
            log('\n已寫入。到 /forms/center 的「填寫表單」就看得到這四張單。')
            for code, r in results.items():
                if r:
                    log(f"  {code}: form_sc={r['form_sc']} wf_sc={r['wf_sc']} "
                        f"published_sc={r['published_sc']}")
        else:
            db.session.rollback()
            log('\n[預演] 未寫入任何資料')
    return 0


if __name__ == '__main__':
    sys.exit(main())
