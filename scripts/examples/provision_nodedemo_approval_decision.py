#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PF-252 B5b 批次：node展覽館 —— FormAdapter（簽核）第二批：簽核者按下按鈕之後
會發生什麼，以及沒人按時會怎樣。

B5a 已經講完「assignee_type 怎麼解析出簽核者」，本批次接著講兩件事：

    NT-19 FormAdapter 示範（自訂決策配對出線）    三個按鈕：核准／退回補件／駁回，
                                                  示範 target_edges 怎麼把按鈕接到
                                                  不同出線，以及「未配對出線＝
                                                  REJECTED 終態」這條規則。
    NT-19 FormAdapter 示範（決策結果驅動後續分支） 兩個決策（核准／需要補充資料）
                                                  刻意接到「同一條出線、同一個
                                                  Branch 節點」，示範圖形結構本身
                                                  分不出兩者，必須靠 output_variable
                                                  寫入的流程變數讓下游 Branch 做
                                                  二次判斷才分得出來。
    NT-19 FormAdapter 示範（簽核逾時自動改道）     timeout_enabled + timeout_minutes +
                                                  timeout_mode=ABSOLUTE + timeout_path_id：
                                                  送單後刻意不簽核，等它自己逾時改道。

目標企業固定是系統預設企業（Organization.code='SYSTEM'），分類固定是「node展覽館」
（fw_categories.secure_code='J1ygL6zexauKlLM0_Ktoaw'）。三個流程的簽核者一律用
assignee_type='INITIATOR'（發起人自簽，本批次全部用系統企業 ORG_ADMIN 送單兼簽核），
這批的重點不是簽核者怎麼解析（B5a 已經講過），是簽核之後的路由與逾時行為。

冪等：重跑會沿用既有表單／流程（依 code 找），bump revision 並重新發行（會停用
舊的已發行版本並建立新版）。填寫權限授予企業內所有非 EXTERNAL 的在職帳號。

用法：
    cd /opt/BeakPlatform-dev
    set -a && source .env && set +a
    venv/bin/python scripts/examples/provision_nodedemo_approval_decision.py --dry-run
    venv/bin/python scripts/examples/provision_nodedemo_approval_decision.py --apply

節點 config 欄位依 handler 原始碼確認：
    modules/form_workflow/services/node_handlers/formadapter_handler.py
    modules/form_workflow/services/node_handlers/branch_handler.py
    modules/form_workflow/api/fc_pending.py::approve_task()（決策提交的真正執行路徑）
    modules/form_workflow/static/modules/form_workflow/js/fc-approval.js（決策提交時
    decision 欄位怎麼算出來——這是本批次最重要的一段程式碼，見檔尾備忘）
權威對照表：/opt/tmp/verify/20260907-node-config-reference.md（FormAdapter 節）
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


def _graph(nodes, edges):
    return {'nodes': nodes, 'edges': edges, 'relayPoints': [],
            'canvasSettings': _canvas(), 'fieldReadConfig': {}}


# ---------------------------------------------------------------------------
# NT-19 FormAdapter：自訂決策配對出線（核准／退回補件／駁回）
# ---------------------------------------------------------------------------

def build_decisionedge_graph():
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 260, 220,
              '流程入口，不需要任何前置設定。'),
        _node('node-Approve', 'FormAdapter', '簽核（三個決策按鈕）', {
            'assignee_type': 'INITIATOR',
            'selection_mode': 'single',
            'output_variable': 'nt19_decision_edge_value',
            'allow_comment': True, 'require_comment': False,
            'use_custom_decisions': True, 'input_variables': [],
            'decision_options': [
                {'id': 'opt-approve', 'label': '核准', 'value': 'approved',
                 'style': 'primary', 'target_edges': ['edge-approve']},
                {'id': 'opt-return', 'label': '退回補件（回到本關卡再簽一次）',
                 'value': 'return_for_revision', 'style': 'warning',
                 'target_edges': ['edge-return']},
                {'id': 'opt-reject', 'label': '駁回（結束流程，不再重簽）',
                 'value': 'rejected', 'style': 'danger', 'target_edges': []},
            ],
        }, 620, 220,
            '三個決策按鈕分別接到三種不同的出線設定：「核准」接單一出線走向正常'
            '結束；「退回補件」接一條迴圈出線繞回本節點自己，形成真正的重簽迴圈；'
            '「駁回」刻意不接任何出線（target_edges 為空陣列），依規則直接判定為'
            '流程終態。'),
        _node('node-Revise', 'OpFieldWrite', '記錄退回補件', {
            'target_field': 'revision_note',
            'content': '簽核者選擇退回補件，已寫回表單，請確認內容後由原申請人'
                       '再次簽核（本節點只是留痕，不會擋下重新簽核）。',
            'content_type': 'text',
        }, 620, 420,
            '被「退回補件」選中時先經過這裡寫一筆表單欄位留痕，再繞回'
            'node-Approve 重新進入等待簽核狀態。'),
        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 980, 220,
              '「核准」選項的出線終點，正常結束記為 COMPLETED。'),
    ]
    edges = [
        _edge('edge-start', 'node-Start', 'node-Approve'),
        _edge('edge-approve', 'node-Approve', 'node-End', '核准'),
        _edge('edge-return', 'node-Approve', 'node-Revise', '退回補件'),
        _edge('edge-revise-loop', 'node-Revise', 'node-Approve', '重新進入簽核'),
    ]
    return _graph(nodes, edges)


NT19_DECISIONEDGE_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'FormAdapter（簽核）等待簽核者送出決定後才會繼續推進。use_custom_decisions=True'
    '時可以自訂任意數量的按鈕，每個按鈕各自透過 target_edges 決定「選了這個按鈕之後'
    '流程要走哪條路」。本流程示範三個按鈕分別接到三種不同的出線設定。\n\n'
    '【本流程的設定重點】\n'
    '- 「核准」（value=approved，target_edges=[edge-approve]）：接單一出線，走向'
    ' End 節點，流程正常結束（COMPLETED）。\n'
    '- 「退回補件」（value=return_for_revision，target_edges=[edge-return]）：'
    '接到 OpFieldWrite 節點再繞回 node-Approve 自己，形成一個真正的迴圈——選這個'
    '按鈕流程不會結束，會重新產生一筆等待簽核的任務，可以重複簽核任意次。\n'
    '- 「駁回」（value=rejected，style=danger，target_edges=[]）：**刻意不配對任何'
    '出線**。依規則「未配對出線的決策＝REJECTED 終態」，選這個按鈕流程立刻結束、'
    '記為 REJECTED，不會走到任何節點。\n'
    '- 三個按鈕的 output_variable 都寫進同一個流程變數'
    ' nt19_decision_edge_value，值是按鈕的 value（approved／return_for_revision／'
    ' rejected），不受「有沒有配對出線」影響——即使駁回是終態，這個變數一樣會'
    '被寫入，只是流程已經結束、後面沒有節點會再讀它。\n\n'
    '【反直覺的地方，也是本流程最重要的一個發現】\n'
    '簽核記錄 fw_approval_records.action 只有兩種可能值：\'approved\' 或'
    ' \'rejected\'，而且**不是照按鈕的 value 或按鈕的語意決定**——決定權在前端'
    '（fc-approval.js::submitApproval()）的這段邏輯：只有當「該按鈕的'
    ' target_edges 是空的」且「該按鈕的 style 是 danger」兩個條件同時成立，才會'
    '送出 decision=\'rejected\'；只要按鈕接了任何出線（不論按鈕語意上是核准還是'
    '退回補件），一律送出 decision=\'approved\'。也就是說本流程的「退回補件」'
    '按鈕，雖然語意上明顯是一種否定／退回，但因為它接了出線，'
    ' fw_approval_records.action 記的仍然是 \'approved\'，不是想像中的某種'
    '「退回」專屬代碼。要知道簽核者實際選了哪個按鈕，唯一可靠的方法是查'
    ' output_variable 寫入的流程變數（本例 nt19_decision_edge_value）或'
    ' fw_approval_records.comment，不能只看 action 欄位。\n\n'
    '【怎麼看結果】\n'
    '用 ORG_ADMIN 送單三次，分別在待簽任務裡按「核准」「退回補件」「駁回」，'
    '每次都查一次 fw_workflow_instances.status（流程終態）與'
    ' fw_approval_records.action（簽核記錄），對照下表：核准→COMPLETED／'
    'approved；退回補件→流程不結束（RUNNING，回到等待簽核）／approved；'
    '駁回→REJECTED／rejected。'
)

FORM_DECISIONEDGE_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-19 FormAdapter 示範表單（自訂決策配對出線）'),
        _hint('送出後待簽任務會出現在你自己的表單中心待辦（assignee_type=INITIATOR）。'
              '按「退回補件」流程不會結束，會回到同一關卡再簽一次；按「駁回」流程'
              '立刻以 REJECTED 結束；按「核准」流程正常結束。'),
        _text('applicant_note', '申請事由（非必填）'),
        _submit_button(),
    ],
}


# ---------------------------------------------------------------------------
# NT-19 FormAdapter：決策結果驅動後續分支
# ---------------------------------------------------------------------------

def build_decisionbranch_graph():
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 220, 220,
              '流程入口，不需要任何前置設定。'),
        _node('node-Approve', 'FormAdapter', '簽核（核准／需要補充資料，同一條出線）', {
            'assignee_type': 'INITIATOR',
            'selection_mode': 'single',
            'output_variable': 'nt19_decision_branch_value',
            'allow_comment': True, 'require_comment': False,
            'use_custom_decisions': True, 'input_variables': [],
            'decision_options': [
                {'id': 'opt-approve', 'label': '核准', 'value': 'approved',
                 'style': 'primary', 'target_edges': ['edge-to-branch']},
                {'id': 'opt-needinfo', 'label': '需要補充資料', 'value': 'need_info',
                 'style': 'default', 'target_edges': ['edge-to-branch']},
                {'id': 'opt-reject', 'label': '駁回', 'value': 'rejected',
                 'style': 'danger', 'target_edges': []},
            ],
        }, 500, 220,
            '刻意讓「核准」與「需要補充資料」兩個決策都指向同一條出線'
            '（edge-to-branch），圖形結構本身完全分不出簽核者選了哪一個——'
            '要分辨必須讀 output_variable 寫入的流程變數。'),
        _node('node-Branch', 'Branch', '依決策結果二次分流', {
            'rules': [
                {'name': '已核准',
                 'conditions': [{'variable': '${v.nt19_decision_branch_value}',
                                  'operator': '==', 'value': 'approved'}],
                 'target_edges': ['edge-branch-approved']},
                {'name': '需要補充資料',
                 'conditions': [{'variable': '${v.nt19_decision_branch_value}',
                                  'operator': '==', 'value': 'need_info'}],
                 'target_edges': ['edge-branch-needinfo']},
            ],
            'fallback': {'action': 'log',
                         'log_message': 'nt19_decision_branch_value 非預期值'},
        }, 800, 220,
            '讀取 FormAdapter 寫入的 nt19_decision_branch_value 流程變數，'
            '依值分流到兩個完全不同的後續處理節點。這一步才是真正決定「核准」與'
            '「需要補充資料」兩種決策實際上會發生什麼事的地方——上一個節點的'
            ' target_edges 只負責「先送到這裡集中處理」。'),
        _node('node-NeedInfoNote', 'OpFieldWrite', '記錄需要補充資料', {
            'target_field': 'followup_note',
            'content': '簽核者要求補充資料，已通知申請人；本節點只做記錄，'
                       '不會建立第二個簽核任務。',
            'content_type': 'text',
        }, 1080, 340,
            '「需要補充資料」這條路徑專屬的處理節點，「核准」不會走到這裡。'),
        _node('node-EndApproved', 'End', 'End（核准）', {'finish_mode': 'detach'},
              1080, 100, '「核准」這條路徑的終點，COMPLETED。'),
        _node('node-EndNeedInfo', 'End', 'End（需要補充資料）', {'finish_mode': 'detach'},
              1360, 340, '「需要補充資料」這條路徑的終點，同樣是 COMPLETED——'
              '流程終態本身分不出兩者的差異，差異只留在流程變數與'
              ' followup_note 欄位裡。'),
    ]
    edges = [
        _edge('edge-start', 'node-Start', 'node-Approve'),
        _edge('edge-to-branch', 'node-Approve', 'node-Branch', '核准／需要補充資料'),
        _edge('edge-branch-approved', 'node-Branch', 'node-EndApproved', '已核准'),
        _edge('edge-branch-needinfo', 'node-Branch', 'node-NeedInfoNote', '需要補充資料'),
        _edge('edge-needinfo-end', 'node-NeedInfoNote', 'node-EndNeedInfo'),
    ]
    return _graph(nodes, edges)


NT19_DECISIONBRANCH_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'FormAdapter 的 output_variable 會把簽核者選擇的決策值寫進流程變數。本流程'
    '示範一個容易被忽略的用法：當兩個決策的 target_edges 刻意指向同一個下游節點'
    '時，流程圖的連線本身完全無法分辨簽核者選了哪一個，唯一能分辨的方法就是讀'
    ' output_variable 寫入的那個流程變數，交給下游的 Branch 節點做二次判斷。\n\n'
    '【本流程的設定重點】\n'
    '- 「核准」（value=approved）與「需要補充資料」（value=need_info）兩個決策'
    '的 target_edges 都是 [edge-to-branch]——同一條出線、同一個下一個節點'
    '（node-Branch）。「駁回」（value=rejected）維持與另一個示範一樣的空'
    ' target_edges，直接進入 REJECTED 終態。\n'
    '- output_variable=\'nt19_decision_branch_value\'：這是本流程能夠分辨兩種'
    '決策的唯一依據。\n'
    '- node-Branch 讀 ${v.nt19_decision_branch_value}，依值分流到兩個完全不同的'
    '節點：「已核准」直接結束；「需要補充資料」先經過 OpFieldWrite 寫一筆'
    ' followup_note 才結束。\n'
    '- 對照另一個示範（自訂決策配對出線）：那個示範是「用出線本身區分決策」，'
    '本流程是「用流程變數＋下游 Branch 區分決策」——後者適合「不同決策其實要走'
    '差不多的後續流程、只有少數地方要分流」的情境，可以少畫很多條重複的線。\n\n'
    '【怎麼看結果】\n'
    '送單兩次，一次按「核准」、一次按「需要補充資料」，兩次都會走到'
    ' node-Branch 再各自分流。查 fw_workflow_variables 的'
    ' nt19_decision_branch_value（兩次分別是 approved／need_info），並比對'
    '兩次流程各自走到哪個 End 節點（可從 fw_node_execution_queue 的'
    ' node_id 看出來），以及第二次送單的 form_data.followup_note 是否真的'
    '被 OpFieldWrite 寫入。'
)

FORM_DECISIONBRANCH_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-19 FormAdapter 示範表單（決策結果驅動後續分支）'),
        _hint('「核准」與「需要補充資料」兩個決策接的是同一條出線，流程圖本身'
              '分不出差異；下游的 Branch 節點會讀簽核時寫入的流程變數再分流。'),
        _text('applicant_note', '申請事由（非必填）'),
        _submit_button(),
    ],
}


# ---------------------------------------------------------------------------
# NT-19 FormAdapter：簽核逾時自動改道
# ---------------------------------------------------------------------------

def build_timeout_graph():
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 220, 220,
              '流程入口，不需要任何前置設定。'),
        _node('node-Approve', 'FormAdapter', '簽核（1 分鐘內不簽就逾時改道）', {
            'assignee_type': 'INITIATOR',
            'selection_mode': 'single',
            'allow_comment': True, 'require_comment': False,
            'use_custom_decisions': False,
            'timeout_enabled': True,
            'timeout_minutes': 1,
            'timeout_mode': 'ABSOLUTE',
            'timeout_path_id': 'edge-timeout',
        }, 520, 220,
            '本節點刻意不用自訂決策（use_custom_decisions=False），出線本身就是'
            '可選路徑。timeout_enabled=True、timeout_minutes=1、'
            'timeout_mode=ABSOLUTE：從進入本關卡那一刻起算，1 分鐘內沒人簽核，'
            '系統會自動走 timeout_path_id 指定的出線（edge-timeout），不需要'
            '任何人動作。'),
        _node('node-EndNormal', 'End', 'End（正常簽核）', {'finish_mode': 'detach'},
              800, 100, '如果有人在逾時之前簽核並選擇這條出線，流程正常結束。'
              '本示範刻意不簽核，這個節點不會被走到。'),
        _node('node-TimeoutNote', 'OpFieldWrite', '記錄逾時改道', {
            'target_field': 'timeout_note',
            'content': '本案已逾時，系統自動判定為逾時並改走此路徑，'
                       '未經任何人工簽核。',
            'content_type': 'text',
        }, 800, 340,
            '逾時路徑專屬的處理節點，寫一筆表單欄位留痕，證明流程走到這裡不是'
            '因為有人簽核，而是逾時自動改道。'),
        _node('node-EndTimeout', 'End', 'End（逾時改道）', {'finish_mode': 'detach'},
              1080, 340, '逾時改道路徑的終點，COMPLETED——與正常簽核一樣是'
              '正常結束，差異只留在 fw_approval_records（action=timeout）與'
              ' timeout_note 欄位。'),
    ]
    edges = [
        _edge('edge-start', 'node-Start', 'node-Approve'),
        _edge('edge-approve', 'node-Approve', 'node-EndNormal', '正常簽核'),
        _edge('edge-timeout', 'node-Approve', 'node-TimeoutNote', '逾時改道'),
        _edge('edge-timeout-end', 'node-TimeoutNote', 'node-EndTimeout'),
    ]
    return _graph(nodes, edges)


NT19_TIMEOUT_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'FormAdapter 可以設定簽核逾時：從進入關卡那一刻起算，超過指定時間沒人簽核，'
    '系統會自動採用指定的逾時路徑繼續推進，不需要任何人介入。這是避免流程因為'
    '沒人簽核而無限期卡住的機制。\n\n'
    '【本流程的設定重點】\n'
    '- timeout_enabled=True、timeout_minutes=1、timeout_mode=\'ABSOLUTE\'：'
    '不論簽核者有沒有班表，一律從進入關卡起算滿 1 分鐘就視為逾時（ABSOLUTE＝'
    '絕對時間，不考慮工作時間）。\n'
    '- timeout_path_id=\'edge-timeout\'：本節點刻意不使用自訂決策'
    '（use_custom_decisions=False），可選路徑就是節點自己的出線，逾時要走的'
    '路徑用出線的 edge id 指定，不是決策選項的 id。\n'
    '- 逾時真的發生時，系統會在 fw_approval_records 寫一筆'
    ' action=\'timeout\'、簽核者顯示「系統（逾時自動處理）」的記錄，效果與'
    '人工選擇該路徑相同——流程繼續往下走，不會卡住也不會報錯。\n\n'
    '【關於 timeout_mode=\'WORKING\'（本流程沒有實際示範，原因見下）】\n'
    'WORKING 模式只在簽核者的班表工作時間內倒數（下班、假日不計時），沒有班表'
    '就自動退回 ABSOLUTE。本示範刻意不做 WORKING 對照組：佈建當下系統企業'
    '（system.local）一張班表都沒有（work_schedules 0 筆），會後兩者都退回'
    ' ABSOLUTE、看不出差異；而現在是深夜，若臨時建一張日間班表，WORKING 模式'
    '的倒數會在下班時段暫停、逾時永遠不會在這次驗收的時間內到期，反而讓流程'
    '卡住跑不完。因此本示範只做 ABSOLUTE 模式的完整實測，WORKING 模式的行為'
    '差異用這段文字說明，之後若要做對照組，建議另外建一張涵蓋當下時間的班表'
    '再測。\n\n'
    '【怎麼看結果】\n'
    '送單後刻意不簽核，等待約 1 分鐘以上（送單到 executor 真正輪詢到還有數秒'
    '延遲），查 fw_workflow_instances.status 應變為 COMPLETED、'
    ' fw_node_execution_queue 該節點的 status 應為 SUCCESS 且已不在 WAITING，'
    ' fw_approval_records 會多一筆 action=\'timeout\'，'
    ' form_data.timeout_note 應為 OpFieldWrite 寫入的內容。'
)

FORM_TIMEOUT_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-19 FormAdapter 示範表單（簽核逾時自動改道）'),
        _hint('送出後請不要簽核這張單，等待約 1 分鐘以上，系統會自動判定逾時並'
              '改走指定路徑。'),
        _text('applicant_note', '申請事由（非必填）'),
        _submit_button(),
    ],
}


FULL_DEMOS_STATIC = [
    {
        'form_code': 'NODEDEMO_NT19_DECISIONEDGE_FORM',
        'form_name': 'NT-19 FormAdapter 示範表單（自訂決策配對出線）',
        'form_schema': FORM_DECISIONEDGE_SCHEMA,
        'workflow_code': 'NODEDEMO_NT19_DECISIONEDGE_FLOW',
        'workflow_name': 'NT-19 FormAdapter 示範（自訂決策配對出線）',
        'description': NT19_DECISIONEDGE_DESCRIPTION,
        'graph': lambda: build_decisionedge_graph(),
    },
    {
        'form_code': 'NODEDEMO_NT19_DECISIONBRANCH_FORM',
        'form_name': 'NT-19 FormAdapter 示範表單（決策結果驅動後續分支）',
        'form_schema': FORM_DECISIONBRANCH_SCHEMA,
        'workflow_code': 'NODEDEMO_NT19_DECISIONBRANCH_FLOW',
        'workflow_name': 'NT-19 FormAdapter 示範（決策結果驅動後續分支）',
        'description': NT19_DECISIONBRANCH_DESCRIPTION,
        'graph': lambda: build_decisionbranch_graph(),
    },
    {
        'form_code': 'NODEDEMO_NT19_TIMEOUT_FORM',
        'form_name': 'NT-19 FormAdapter 示範表單（簽核逾時自動改道）',
        'form_schema': FORM_TIMEOUT_SCHEMA,
        'workflow_code': 'NODEDEMO_NT19_TIMEOUT_FLOW',
        'workflow_name': 'NT-19 FormAdapter 示範（簽核逾時自動改道）',
        'description': NT19_TIMEOUT_DESCRIPTION,
        'graph': lambda: build_timeout_graph(),
    },
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
            created_by_name='provision_nodedemo_approval_decision',
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


def main():
    parser = argparse.ArgumentParser(
        description='佈建 node展覽館的 FormAdapter 決策路由與逾時示範（B5b）')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--dry-run', action='store_true', help='只列出會做什麼，不寫入')
    group.add_argument('--apply', action='store_true', help='實際寫入資料庫')
    parser.add_argument('--org', default=ORG_CODE, help=f'企業 code（預設 {ORG_CODE}）')
    args = parser.parse_args()

    from app import create_app, db

    # modules 套件要等 create_app() 跑過 module_loader 才會被插進 sys.path。
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
        osc = org.secure_code
        log(f'企業：{org.name}（{osc}）')
        load_node_icons(models)

        publisher = User.query.filter_by(
            org_secure_code=osc, user_type='ORG_ADMIN',
            is_deleted=False, is_active=True).first()

        log('\n=== FormAdapter 決策路由與逾時示範（表單／流程／配對／發行） ===')
        full_results = {}
        for demo in FULL_DEMOS_STATIC:
            log(f"\n--- {demo['workflow_name']} ---")
            full_results[demo['workflow_code']] = apply_full_demo(
                db, models, org, demo, publisher, args.apply)

        if args.apply:
            db.session.commit()
            log('\n已寫入。到 /forms/center 的「填寫表單」就看得到這三張單。')
            log('\n完整示範：')
            for code, r in full_results.items():
                if r:
                    log(f"  {code}: form_sc={r['form_sc']} wf_sc={r['wf_sc']} "
                        f"published_sc={r['published_sc']}")
        else:
            db.session.rollback()
            log('\n[預演] 未寫入任何資料')
    return 0


if __name__ == '__main__':
    sys.exit(main())
