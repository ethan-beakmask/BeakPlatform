#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PF-252 B2 批次：node展覽館 —— Branch（分支）與 Delay（暫停）的示範流程。

    NT-05 Branch 示範（互斥條件）              金額分三段，規則互斥，每次只走一條路徑
    NT-05 Branch 示範（多條命中會全部展開）    金額落在重疊區間時兩條規則同時命中，
                                                Branch 會同時推進兩條出線
    NT-08 Delay 示範                            流程暫停 45 秒，由 executor 輪詢喚醒

三個流程各自只有一個主角節點，配角一律是 Start / End / OpSet /
FormAdapter（發起人自己簽核，assignee_type=INITIATOR，一個帳號就能跑完全程）。

目標企業固定是系統預設企業（Organization.code='SYSTEM'），分類固定是「node展覽館」
（fw_categories.secure_code='J1ygL6zexauKlLM0_Ktoaw'）。

冪等：重跑會沿用既有表單／流程（依 code 找），bump revision 並重新發行（會停用
舊的已發行版本並建立新版）。填寫權限授予企業內所有非 EXTERNAL 的在職帳號。

用法：
    cd /opt/BeakPlatform-dev
    set -a && source .env && set +a
    venv/bin/python scripts/examples/provision_nodedemo_control.py --dry-run
    venv/bin/python scripts/examples/provision_nodedemo_control.py --apply

節點 config 欄位依 handler 原始碼確認：
    modules/form_workflow/services/node_handlers/branch_handler.py
    modules/form_workflow/services/node_handlers/delay_handler.py
    modules/form_workflow/services/node_handlers/opset_handler.py
權威對照表：/opt/tmp/verify/20260907-node-config-reference.md（Branch／Delay 節）
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


def _text(key, label, description='', rows=None):
    comp = {'key': key, 'type': 'textarea' if rows else 'textfield',
            'input': True, 'label': label, 'tableView': True}
    if description:
        comp['description'] = description
    if rows:
        comp['rows'] = rows
    return comp


def _number(key, label, description='', required=False):
    comp = {'key': key, 'type': 'number', 'input': True, 'label': label,
            'tableView': True, 'delimiter': False}
    if description:
        comp['description'] = description
    if required:
        comp['validate'] = {'required': True}
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


def _approve_node(node_id, label, x, y, output_var, ok_label, ok_edge,
                   ng_label, ng_edge, description=''):
    """
    人工簽核節點，assignee_type=INITIATOR：發起人自己簽核。

    示範用刻意這樣設，一個人就能在 /forms/center 走完全程；
    真實流程請改 ROLE 或 DEPARTMENT。
    """
    return _node(
        node_id, 'FormAdapter', label,
        {
            'assignee_type': 'INITIATOR',
            'assignee_label': '發起人（示範用）',
            'assignee_list': [],
            'selection_mode': 'single',
            'output_variable': output_var,
            'allow_comment': True,
            'require_comment': False,
            'use_custom_decisions': True,
            'input_variables': [],
            'decision_options': [
                {'id': f'{node_id}-ok', 'label': ok_label, 'value': 'approved',
                 'style': 'default', 'target_edges': [ok_edge]},
                {'id': f'{node_id}-ng', 'label': ng_label, 'value': 'rejected',
                 'style': 'danger', 'target_edges': [ng_edge]},
            ],
        },
        x, y, description,
    )


# ---------------------------------------------------------------------------
# NT-05 Branch 示範（互斥條件）
# ---------------------------------------------------------------------------

FORM_BRANCH_EXCL_CODE = 'NODEDEMO_NT05_BRANCH_EXCL_FORM'
WF_BRANCH_EXCL_CODE = 'NODEDEMO_NT05_BRANCH_EXCL_FLOW'
FORM_BRANCH_EXCL_NAME = 'NT-05 Branch 示範表單（互斥條件）'
WF_BRANCH_EXCL_NAME = 'NT-05 Branch 示範（互斥條件）'

WF_BRANCH_EXCL_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'Branch（條件分支）依規則對照流程變數或表單欄位目前的值，決定接下來要走哪一條或'
    '哪幾條出線；一條規則都沒命中時走 fallback。它本身不呼叫任何外部服務，純粹是'
    '「評估條件、挑出線」的路由節點。\n\n'
    '【本流程的設定重點】\n'
    '- 三條規則刻意互斥（金額三段：<10000／10000~99999／>=100000），示範最常見、也是'
    '設計時該追求的用法：每次送單只會有一條規則命中，只走一條路徑。\n'
    '- 「中額」規則放了兩個條件（>=10000 且 <100000），兩個條件的 logic 都標 AND：'
    'logic 是「分組符」，只有遇到 OR 或掃到最後一條才收尾成一組，組內是 AND、組間是 OR。'
    '兩個條件都標 AND（或都不填，預設也是 AND）時會被視為同一個 AND 群組，等於'
    '「兩個條件都要成立」。如果誤把其中一個標成 OR，就會被拆成兩個群組（OR 關係）——'
    '「金額 >= 10000」會單獨成立一組，不管上限，中額規則就會在金額 >= 10000 時一律命中，'
    '與高額規則同時成立，變成本示範另一個流程（多條命中會全部展開）的情境，而不是這裡'
    '想要的互斥效果。\n'
    '- fallback.action 設為 \'log\'（預設值）：三條規則已涵蓋所有非負金額，理論上不會落到'
    'fallback；但如果真的沒有規則命中（例如金額是負數，或欄位缺值使比較拋例外），'
    'fallback 為非 route 時會 data.skip_advance=True，流程在 Branch 這一步就安靜停住、'
    '不會走到後面任何節點，也不會報錯——這是刻意示範的安全閥，不是漏設定。想要'
    '「沒命中時還是要走某條路」就要把 fallback.action 改成 \'route\' 並填 target_edge。\n\n'
    '【怎麼看結果】\n'
    '送不同金額（例如 5000／50000／500000）各跑一次，查 fw_workflow_variables 應該'
    '只看到對應那一段的 bracket_result 值，其餘兩段的 OpSet 節點根本不會被建立佇列'
    '項目（查 fw_node_execution_queue 只有一個 node-Set-* 有記錄）。'
)

FORM_BRANCH_EXCL_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-05 Branch 示範表單（互斥條件）'),
        _hint('三條規則互斥：金額 &lt;10000 走低額、10000~99999 走中額、&gt;=100000 走高額。'
              '每次送單只會命中一條規則，跑完查 fw_workflow_variables 的 bracket_result。'),
        _number('amount', '金額', '決定走哪一段分支：<10000 低額／10000~99999 中額／>=100000 高額。',
                required=True),
        _submit_button(),
    ],
}


def build_branch_exclusive_graph():
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 340, 200),
        _node(
            'node-Branch', 'Branch', '金額分段（互斥）',
            {
                'rules': [
                    {
                        'name': '低額（金額 < 10000）',
                        'conditions': [
                            {'variable': '${f.amount}', 'operator': '<', 'value': '10000',
                             'logic': 'AND'},
                        ],
                        'target_edges': ['edge-low'],
                    },
                    {
                        'name': '中額（10000 <= 金額 < 100000）',
                        'conditions': [
                            {'variable': '${f.amount}', 'operator': '>=', 'value': '10000',
                             'logic': 'AND'},
                            {'variable': '${f.amount}', 'operator': '<', 'value': '100000',
                             'logic': 'AND'},
                        ],
                        'target_edges': ['edge-mid'],
                    },
                    {
                        'name': '高額（金額 >= 100000）',
                        'conditions': [
                            {'variable': '${f.amount}', 'operator': '>=', 'value': '100000',
                             'logic': 'AND'},
                        ],
                        'target_edges': ['edge-high'],
                    },
                ],
                'fallback': {
                    'action': 'log',
                    'log_message': '金額不在任何分段內（理論上不會發生，除非是負數或無法解析）',
                },
            },
            560, 200,
            '依 ${f.amount} 判斷落在哪一段：<10000／10000~99999／>=100000，三段互斥，'
            '命中哪一段就只走該段的出線，另外兩段完全不會被推進。',
        ),
        _node(
            'node-Set-Low', 'OpSet', '低額分支',
            {'operations': [{'target_var': 'bracket_result', 'operation': 'set',
                              'value': '低額（<10000）'}]},
            780, 60,
            '命中「低額」規則時才會執行，寫入流程變數 bracket_result=\'低額（<10000）\'。',
        ),
        _node(
            'node-Set-Mid', 'OpSet', '中額分支',
            {'operations': [{'target_var': 'bracket_result', 'operation': 'set',
                              'value': '中額（10000~99999）'}]},
            780, 200,
            '命中「中額」規則時才會執行，寫入流程變數 bracket_result=\'中額（10000~99999）\'。',
        ),
        _node(
            'node-Set-High', 'OpSet', '高額分支',
            {'operations': [{'target_var': 'bracket_result', 'operation': 'set',
                              'value': '高額（>=100000）'}]},
            780, 340,
            '命中「高額」規則時才會執行，寫入流程變數 bracket_result=\'高額（>=100000）\'。',
        ),
        _approve_node(
            'node-Form-approve', '確認分段結果', 1020, 200,
            'branch_decision', '確認無誤', 'edge-ok', '有問題', 'edge-ng',
            'assignee_type=INITIATOR：示範用，送單的人自己就會在待辦看到這張單。'
            '三段分支不管走哪一段，最後都會匯流到這裡再走到 End。',
        ),
        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 1260, 200),
    ]
    edges = [
        _edge('edge-start-branch', 'node-Start', 'node-Branch'),
        _edge('edge-low', 'node-Branch', 'node-Set-Low', '低額'),
        _edge('edge-mid', 'node-Branch', 'node-Set-Mid', '中額'),
        _edge('edge-high', 'node-Branch', 'node-Set-High', '高額'),
        _edge('edge-low-form', 'node-Set-Low', 'node-Form-approve'),
        _edge('edge-mid-form', 'node-Set-Mid', 'node-Form-approve'),
        _edge('edge-high-form', 'node-Set-High', 'node-Form-approve'),
        _edge('edge-ok', 'node-Form-approve', 'node-End', '確認無誤'),
        _edge('edge-ng', 'node-Form-approve', 'node-End', '有問題'),
    ]
    return {'nodes': nodes, 'edges': edges, 'relayPoints': [],
            'canvasSettings': _canvas(), 'fieldReadConfig': {}}


# ---------------------------------------------------------------------------
# NT-05 Branch 示範（多條命中會全部展開）
# ---------------------------------------------------------------------------

FORM_BRANCH_MULTI_CODE = 'NODEDEMO_NT05_BRANCH_MULTI_FORM'
WF_BRANCH_MULTI_CODE = 'NODEDEMO_NT05_BRANCH_MULTI_FLOW'
FORM_BRANCH_MULTI_NAME = 'NT-05 Branch 示範表單（多條命中）'
WF_BRANCH_MULTI_NAME = 'NT-05 Branch 示範（多條命中會全部展開）'

WF_BRANCH_MULTI_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'Branch（條件分支）依規則對照變數值決定要走哪一條或哪幾條出線。這份示範的重點'
    '不是分支本身的用法，而是刻意示範一個最容易被忽略、寫錯不會報錯的行為：'
    '規則之間如果彼此重疊，同一次評估可以有一條以上的規則同時成立，Branch 對此的'
    '處理方式是「全部展開」，不是「先到先贏」。\n\n'
    '【本流程的設定重點】\n'
    '- 兩條規則刻意設計成會重疊：規則 A「金額 >= 50000」與規則 B「金額 <= 200000」。'
    '當金額落在 [50000, 200000] 這個區間（含兩端）時，兩條規則會同時成立。\n'
    '- Branch 對「同時命中多條規則」的行為是把所有命中規則的 target_edges 取聯集'
    '（去重後）逐條推進，不是 first-match-wins，也不會因為某條規則已命中就跳過'
    '其餘規則不評估。所以送 amount=100000 時，Branch 會同時推進 edge-a 與 edge-b'
    '兩條出線，兩條下游各自的 OpSet 節點都會真的被執行——這通常不是設計者原本想要'
    '的結果，是規則沒設計成互斥時最典型的踩坑現場。\n'
    '- edge-a 之後接的 node-Set-A 沒有設定任何出線：這是刻意示範「無出邊節點安全'
    '終止該分支」——執行完就安靜結束，不報錯也不會讓流程卡住，只是這條分支自己'
    '收尾，不會推進到簽核或 End。edge-b 之後才接到簽核與 End，由這條分支負責把'
    '整個流程實例收尾。兩條分支誰先被推進、誰後被推進不影響結果：OpSet 是同步'
    '節點，兩個都會在流程真正走到 FormAdapter 等待簽核之前執行完畢。\n'
    '- fallback.action 設為 \'route\'，指到第三條「都沒命中」路徑（node-Set-Fallback）：'
    '確保萬一送單金額不在重疊區間內、也完全不在任一規則範圍內時，流程仍然收得了尾，'
    '不會卡死——這只是為了讓示範流程好操作，不是本示範要講的重點。\n\n'
    '【怎麼看結果】\n'
    '送 amount=100000（同時滿足兩條規則）之後查 fw_workflow_variables，應該同時看到'
    ' path_a_triggered=\'true\' 與 path_b_triggered=\'true\' 兩個變數都存在，證明兩條路徑'
    '都真的執行了。也可以查 fw_node_execution_queue：node-Set-A 與 node-Set-B 兩個'
    '節點都有各自的 SUCCESS 記錄（node-Set-A 沒有下一步，node-Set-B 才接得到後面的'
    '簽核與 End）。'
)

FORM_BRANCH_MULTI_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-05 Branch 示範表單（多條命中）'),
        _hint('填入 50000~200000（含兩端）之間的金額會同時命中規則A（&gt;=50000）與'
              '規則B（&lt;=200000），兩條路徑都會執行；此範圍外只會命中一條規則，'
              '完全不在任一規則範圍內則走 fallback。跑完查 fw_workflow_variables 的'
              'path_a_triggered 與 path_b_triggered。'),
        _number('amount', '金額', '填 50000~200000 之間可同時觸發規則A與規則B。',
                required=True),
        _submit_button(),
    ],
}


def build_branch_multi_graph():
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 340, 200),
        _node(
            'node-Branch', 'Branch', '重疊規則（示範多條命中）',
            {
                'rules': [
                    {
                        'name': '規則A（金額 >= 50000）',
                        'conditions': [
                            {'variable': '${f.amount}', 'operator': '>=', 'value': '50000',
                             'logic': 'AND'},
                        ],
                        'target_edges': ['edge-a'],
                    },
                    {
                        'name': '規則B（金額 <= 200000）',
                        'conditions': [
                            {'variable': '${f.amount}', 'operator': '<=', 'value': '200000',
                             'logic': 'AND'},
                        ],
                        'target_edges': ['edge-b'],
                    },
                ],
                'fallback': {
                    'action': 'route',
                    'target_edge': 'edge-fallback',
                    'log_message': '兩條規則都沒有命中',
                },
            },
            560, 200,
            '刻意設計成重疊的兩條規則：金額>=50000（規則A）與金額<=200000（規則B）。'
            '金額落在 [50000,200000] 時兩條規則同時成立，Branch 會同時推進兩條出線，'
            '不是只走一條——這就是本示範要講的「多條命中會全部展開」。',
        ),
        _node(
            'node-Set-A', 'OpSet', '規則A分支（無出邊，安全終止）',
            {'operations': [{'target_var': 'path_a_triggered', 'operation': 'set',
                              'value': 'true'}]},
            780, 60,
            '規則A命中時執行，寫入流程變數 path_a_triggered=\'true\'。這個節點刻意'
            '沒有設定任何出線，示範「無出邊節點安全終止該分支」——執行完就安靜結束，'
            '不會報錯，也不會讓流程卡住，只是不會再推進到簽核或 End。',
        ),
        _node(
            'node-Set-B', 'OpSet', '規則B分支',
            {'operations': [{'target_var': 'path_b_triggered', 'operation': 'set',
                              'value': 'true'}]},
            780, 340,
            '規則B命中時執行，寫入流程變數 path_b_triggered=\'true\'，之後接到簽核'
            '與 End，由這條分支負責把整個流程實例收尾。',
        ),
        _node(
            'node-Set-Fallback', 'OpSet', 'fallback 分支',
            {'operations': [{'target_var': 'fallback_triggered', 'operation': 'set',
                              'value': 'true'}]},
            780, 200,
            '只有在兩條規則都沒命中時才會執行（fallback.action=route 導向這裡），'
            '寫入流程變數 fallback_triggered=\'true\'，讓流程即使沒命中也能走到'
            '簽核與 End，不會卡死。不是本示範要講的重點，只是讓流程好操作。',
        ),
        _approve_node(
            'node-Form-approve', '確認執行結果', 1020, 260,
            'branch_decision', '確認無誤', 'edge-ok', '有問題', 'edge-ng',
            'assignee_type=INITIATOR：示範用，送單的人自己就會在待辦看到這張單。'
            '只有規則B分支與 fallback 分支會走到這裡，規則A分支不會。',
        ),
        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 1260, 260),
    ]
    edges = [
        _edge('edge-start-branch', 'node-Start', 'node-Branch'),
        _edge('edge-a', 'node-Branch', 'node-Set-A', '規則A命中'),
        _edge('edge-b', 'node-Branch', 'node-Set-B', '規則B命中'),
        _edge('edge-fallback', 'node-Branch', 'node-Set-Fallback', '都沒命中'),
        _edge('edge-b-form', 'node-Set-B', 'node-Form-approve'),
        _edge('edge-fallback-form', 'node-Set-Fallback', 'node-Form-approve'),
        _edge('edge-ok', 'node-Form-approve', 'node-End', '確認無誤'),
        _edge('edge-ng', 'node-Form-approve', 'node-End', '有問題'),
    ]
    return {'nodes': nodes, 'edges': edges, 'relayPoints': [],
            'canvasSettings': _canvas(), 'fieldReadConfig': {}}


# ---------------------------------------------------------------------------
# NT-08 Delay 示範
# ---------------------------------------------------------------------------

FORM_DELAY_CODE = 'NODEDEMO_NT08_DELAY_FORM'
WF_DELAY_CODE = 'NODEDEMO_NT08_DELAY_FLOW'
FORM_DELAY_NAME = 'NT-08 Delay 示範表單'
WF_DELAY_NAME = 'NT-08 Delay 示範'

WF_DELAY_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'Delay（延遲）讓流程在這個節點暫停一段時間：時間到之前，流程實例就停在這裡不會'
    '繼續往下走；時間到了之後，由背景的 executor 輪詢機制自動把它撿回來繼續執行，'
    '不需要任何人手動介入，也不佔用簽核待辦。\n\n'
    '【本流程的設定重點】\n'
    '- 本示範用 delay_seconds=45（等待 45 秒）。delay_seconds／delay_minutes／'
    'delay_hours 三個是相加關係、不是互斥選項：例如同時填 delay_minutes=5 與'
    'delay_seconds=30，總共會等 5 分 30 秒，不是取其中一個。\n'
    '- 如果填了 delay_until（絕對時間的 ISO 字串），它的優先序高於上面三個相加的'
    '總和，delay_seconds/minutes/hours 會被完全忽略；delay_until 格式錯誤會直接讓'
    '節點失敗（status=error），不會被靜默忽略跳過。如果 delay_until 填的時間已經'
    '過去，節點會判定「已過目標時間」直接回 success，不會真的等待，也不會報錯——'
    '這代表拿舊資料重跑一個含 Delay 的流程時，Delay 有可能完全不會停頓。\n'
    '- 等待期間，流程實例狀態維持 RUNNING，但 Delay 這個節點在'
    'fw_node_execution_queue 的狀態是 WAITING，且 scheduled_at 被設成目標時間；'
    'executor 的輪詢清單（node_type in Delay/End/ParallelJoin/OsExecutor 且'
    'scheduled_at 已到期）每隔一段時間掃一次，掃到就重新執行這個節點，這次因為'
    '已過目標時間所以直接回 success 並照一般規則走全部出邊。\n\n'
    '【怎麼看結果】\n'
    '送單後立刻查 fw_node_execution_queue，Delay 節點應該是 status=WAITING、'
    'scheduled_at 是送單時間 +45 秒左右；流程實例 fw_workflow_instances.status'
    '仍是 RUNNING。等 45 秒以上再查一次，Delay 節點應該變成 SUCCESS，流程繼續'
    '往下走到 OpSet 節點（寫入 delay_wake_note，可看到節點恢復執行的時間戳記）再到'
    '簽核節點；簽核後 End 執行，流程實例最終變成 COMPLETED。'
)

FORM_DELAY_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-08 Delay 示範表單'),
        _hint('送出後流程會先進入 Delay 節點暫停 45 秒，時間到才會被 executor 自動'
              '撿回來繼續執行，接著才會出現待簽核任務。送單後可以立刻查'
              'fw_node_execution_queue 看 Delay 節點的 WAITING 狀態與 scheduled_at。'),
        _text('note', '備註（非必填）', '示範用，內容沒有特別的邏輯用途。'),
        _submit_button(),
    ],
}


def build_delay_graph():
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 340, 200),
        _node(
            'node-Delay', 'Delay', '等待 45 秒',
            {'delay_seconds': 45},
            580, 200,
            '暫停 45 秒（delay_seconds=45）示範最基本用法。改成 delay_minutes/'
            'delay_hours 會與 delay_seconds 相加；填 delay_until 則以絕對時間為準，'
            '並會蓋過前三者。',
        ),
        _node(
            'node-OpSet-wake', 'OpSet', '記錄恢復時間',
            {'operations': [{'target_var': 'delay_wake_note', 'operation': 'set',
                              'value': 'Delay 節點已於 ${t.now}（UTC）恢復執行'}]},
            820, 200,
            'Delay 到期、executor 把節點撿回來繼續執行後，這個節點才會被跑到，'
            '寫入流程變數 delay_wake_note 記錄恢復執行的時間戳記，用來證明流程'
            '真的等到時間到才繼續，不是立刻往下走。',
        ),
        _approve_node(
            'node-Form-approve', '確認流程已恢復', 1060, 200,
            'delay_decision', '確認無誤', 'edge-ok', '有問題', 'edge-ng',
            'assignee_type=INITIATOR：示範用。看到這張待簽核任務時，代表 Delay'
            '已經到期並且流程已經恢復執行。',
        ),
        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 1300, 200),
    ]
    edges = [
        _edge('edge-start-delay', 'node-Start', 'node-Delay'),
        _edge('edge-delay-wake', 'node-Delay', 'node-OpSet-wake'),
        _edge('edge-wake-form', 'node-OpSet-wake', 'node-Form-approve'),
        _edge('edge-ok', 'node-Form-approve', 'node-End', '確認無誤'),
        _edge('edge-ng', 'node-Form-approve', 'node-End', '有問題'),
    ]
    return {'nodes': nodes, 'edges': edges, 'relayPoints': [],
            'canvasSettings': _canvas(), 'fieldReadConfig': {}}


DEMOS = [
    {
        'form_code': FORM_BRANCH_EXCL_CODE, 'form_name': FORM_BRANCH_EXCL_NAME,
        'form_schema': FORM_BRANCH_EXCL_SCHEMA,
        'workflow_code': WF_BRANCH_EXCL_CODE, 'workflow_name': WF_BRANCH_EXCL_NAME,
        'description': WF_BRANCH_EXCL_DESCRIPTION,
        'graph': build_branch_exclusive_graph,
    },
    {
        'form_code': FORM_BRANCH_MULTI_CODE, 'form_name': FORM_BRANCH_MULTI_NAME,
        'form_schema': FORM_BRANCH_MULTI_SCHEMA,
        'workflow_code': WF_BRANCH_MULTI_CODE, 'workflow_name': WF_BRANCH_MULTI_NAME,
        'description': WF_BRANCH_MULTI_DESCRIPTION,
        'graph': build_branch_multi_graph,
    },
    {
        'form_code': FORM_DELAY_CODE, 'form_name': FORM_DELAY_NAME,
        'form_schema': FORM_DELAY_SCHEMA,
        'workflow_code': WF_DELAY_CODE, 'workflow_name': WF_DELAY_NAME,
        'description': WF_DELAY_DESCRIPTION,
        'graph': build_delay_graph,
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
            created_by_name='provision_nodedemo_control',
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
        description='佈建 node展覽館的 Branch（互斥／多條命中）與 Delay 三個示範流程')
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
            log('\n已寫入。到 /forms/center 的「填寫表單」就看得到這三張單。')
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
