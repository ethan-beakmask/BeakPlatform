#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PF-252 B1 批次：node展覽館 —— 三個變數類節點的示範流程。

    NT-22 OpSet 示範        設定流程變數：固定值 / 表單欄位取值 / 字串串接 / 四則運算
    NT-20 OpFieldRead 示範  把表單欄位讀進流程變數（與 OpSet 的差別：讀表單 vs 設值）
    NT-21 OpFieldWrite 示範 把流程變數寫回表單欄位（效果最直觀：送出後表單欄位真的被填上）

三個流程各自只有一個主角節點，配角一律是 Start / End / FormAdapter（發起人自己簽核，
assignee_type=INITIATOR，一個帳號就能跑完全程）/ OpSet（NT-21 示範裡用來準備一個
流程變數給 OpFieldWrite 用）。

目標企業固定是系統預設企業（Organization.code='SYSTEM'），分類固定是「node展覽館」
。。

冪等：重跑會沿用既有表單／流程（依 code 找），bump revision 並重新發行（會停用
舊的已發行版本並建立新版）。填寫權限授予企業內所有非 EXTERNAL 的在職帳號。

用法：
    cd <repo>
    set -a && source .env && set +a
    venv/bin/python scripts/examples/provision_nodedemo_vars.py --dry-run
    venv/bin/python scripts/examples/provision_nodedemo_vars.py --apply

節點 config 欄位依 handler 原始碼確認（node-config-reference 尚未產出時的替代做法）：
    modules/form_workflow/services/node_handlers/opset_handler.py
    modules/form_workflow/services/node_handlers/fieldread_handler.py
    modules/form_workflow/services/node_handlers/fieldwrite_handler.py
"""
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

# 座標刻意落在 x 340~1200 / y 落在單一水平線 200（三個流程都是線性 5 節點以內，
# 不需要分岔，維持單排最不容易重疊）。橫向間距 160~220，符合
# WORKFLOW_DESIGNER_NOTES.md 的建議範圍。

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


def _number(key, label, description=''):
    comp = {'key': key, 'type': 'number', 'input': True, 'label': label,
            'tableView': True, 'delimiter': False}
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
# NT-22 OpSet 示範
# ---------------------------------------------------------------------------

FORM_OPSET_CODE = 'NODEDEMO_NT22_OPSET_FORM'
WF_OPSET_CODE = 'NODEDEMO_NT22_OPSET_FLOW'
FORM_OPSET_NAME = 'NT-22 OpSet 示範表單'
WF_OPSET_NAME = 'NT-22 OpSet 示範'

WF_OPSET_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'OpSet（設定變數）用來在流程執行中設定一個或多個流程變數。它不呼叫任何外部服務、'
    '也不會動表單本身，純粹是流程內部的資料處理節點；設定完的變數可以在後面的 Branch '
    '條件、簽核任務內容、或其他節點的 config 裡用 ${v.變數名} 取用。流程變數不會憑空存在，'
    '一定要有節點實際設定過才查得到——OpSet 是最基本、最直接的設定方式。\n\n'
    '【本流程的設定重點】\n'
    '- config.operations 是一個陣列，逐項依序執行，同一個節點可以一次做好幾件事。\n'
    '- fixed_note：operation=set，value 寫死一段中文字，示範「跟表單內容無關的固定值」——'
    '不管誰送單、填什麼，這一項永遠一樣。\n'
    '- amount_from_form：operation=set，value=${f.base_amount}，示範「從表單欄位取值」；'
    'handler 會先做變數替換拿到表單值的字串，再嘗試轉成數字，轉得成就存成 int/float，'
    '轉不成才原樣保留成字串。\n'
    '- greeting：先用 operation=set 給一個固定基底值「您好，」，再用 operation=concat 把 '
    '${f.applicant_name} 接上去，示範「把已有的值和新值串起來」——concat 是「取出 target_var '
    '現有值再加上新值」，不是取代；如果把這一步改成 set，效果會變成整個覆蓋掉「您好，」，'
    '不會有串接效果。\n'
    '- amount_doubled：operation=expr，value=${f.base_amount} * 2，示範四則運算；expr 只認得'
    '基本數學運算子（+ - * / // % **），運算元必須能轉成數字。如果表單欄位填的是文字'
    '（例如「abc」），這一步會失敗，但只記一條錯誤、不會讓整個節點失敗（其餘 operations 仍照跑，'
    '失敗清單在節點日誌 log_data.errors 裡）。\n\n'
    '【怎麼看結果】\n'
    '查 fw_workflow_variables（依該次流程實例的 workflow_instance_secure_code），應該看到 '
    'fixed_note、amount_from_form、greeting、amount_doubled 四個變數，其中 greeting 的值是'
    '「您好，」加上送單時填的申請人姓名。'
)

FORM_OPSET_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-22 OpSet 示範表單'),
        _hint('送出後流程會用 OpSet 節點做四種變數設定：寫死的固定值、讀表單欄位轉存、'
              '字串串接、以及用 expr 做乘法運算。跑完後查 fw_workflow_variables 看結果。'),
        _text('applicant_name', '申請人姓名', '會被串接進 greeting 變數，示範「串值」。'),
        _number('base_amount', '基本金額', '填數字。會被原樣轉存、也會被乘以 2；'
                '故意填文字可以看 expr 那一步「失敗但不中斷節點」的行為。'),
        _submit_button(),
    ],
}


def build_opset_graph():
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 340, 200),
        _node(
            'node-OpSet', 'OpSet', '設定示範變數',
            {
                'operations': [
                    {'target_var': 'fixed_note', 'operation': 'set',
                     'value': '這是流程設計時寫死的固定字串，任何人送單、不管表單內容是什麼，'
                              '這一項永遠一樣'},
                    {'target_var': 'amount_from_form', 'operation': 'set',
                     'value': '${f.base_amount}'},
                    {'target_var': 'greeting', 'operation': 'set', 'value': '您好，'},
                    {'target_var': 'greeting', 'operation': 'concat',
                     'value': '${f.applicant_name}'},
                    {'target_var': 'amount_doubled', 'operation': 'expr',
                     'value': '${f.base_amount} * 2'},
                ],
            },
            560, 200,
            '示範四種設定來源：set 固定值（fixed_note）、set 表單欄位（amount_from_form）、'
            'set + concat 串接兩個值（greeting）、expr 四則運算（amount_doubled）。'
            '五個 operation 依序執行，同一個節點一次做完。',
        ),
        _approve_node(
            'node-Form-approve', '確認變數設定結果', 800, 200,
            'opset_decision', '確認無誤', 'edge-ok', '有問題', 'edge-ng',
            'assignee_type=INITIATOR：示範用，送單的人自己就會在待辦看到這張單。'
            '簽核本身不影響變數，只是讓流程能走到 End。',
        ),
        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 1040, 200),
    ]
    edges = [
        _edge('edge-start-opset', 'node-Start', 'node-OpSet'),
        _edge('edge-opset-form', 'node-OpSet', 'node-Form-approve'),
        _edge('edge-ok', 'node-Form-approve', 'node-End', '確認無誤'),
        _edge('edge-ng', 'node-Form-approve', 'node-End', '有問題'),
    ]
    return {'nodes': nodes, 'edges': edges, 'relayPoints': [],
            'canvasSettings': _canvas(), 'fieldReadConfig': {}}


# ---------------------------------------------------------------------------
# NT-20 OpFieldRead 示範
# ---------------------------------------------------------------------------

FORM_FIELDREAD_CODE = 'NODEDEMO_NT20_FIELDREAD_FORM'
WF_FIELDREAD_CODE = 'NODEDEMO_NT20_FIELDREAD_FLOW'
FORM_FIELDREAD_NAME = 'NT-20 OpFieldRead 示範表單'
WF_FIELDREAD_NAME = 'NT-20 OpFieldRead 示範'

WF_FIELDREAD_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'OpFieldRead（讀取欄位）把發起這次流程的那張表單裡、指定欄位的值抄一份存成流程變數，'
    '讓後面的節點（Branch 條件判斷、OpFieldWrite 寫回別的地方等）可以取用，不必每次都重新'
    '解析表單內容。\n\n'
    '【本流程的設定重點】\n'
    '- config.fields 是一個字串陣列，本示範寫死 ["visitor_note", "urgency"]，只讀這兩個欄位。\n'
    '- 如果把 fields 留空，節點會依序退而求其次：先看流程模板 graph.fieldReadConfig 有沒有'
    '針對這張表單設定要讀哪些欄位；還是沒有，就自動抓表單全部欄位（排除底線開頭的系統鍵、'
    '以及 submit / data）——代表留空不是「不讀」，而是「讀更多」，欄位一多容易讀進不必要的雜訊。\n'
    '- 每個被讀到的欄位會同時產生兩個流程變數：一個是「{表單模板 secure_code}_{欄位 key}」'
    '（例如 xxxxxxxx_visitor_note），一個是欄位 key 本身（visitor_note）。兩個值完全一樣，'
    '只是命名習慣不同，後面的節點通常直接用短名 ${v.visitor_note}。\n'
    '- 和 OpSet 的差別：OpSet 是「設定」一個值，來源可以是寫死的常數、四則運算、或字串串接，'
    '不必然跟表單有關；OpFieldRead 是「原封不動地把表單資料謄進流程變數」，不做任何運算或'
    '型別轉換，一次可以抄好幾個欄位。\n\n'
    '【怎麼看結果】\n'
    '查 fw_workflow_variables，應該看到 visitor_note、urgency 兩個變數（值與送單時填的表單'
    '內容一致），以及另外兩個帶表單 secure_code 前綴、值相同的變數。'
)

FORM_FIELDREAD_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-20 OpFieldRead 示範表單'),
        _hint('送出後流程會用 OpFieldRead 節點把「訪客留言」與「急迫程度」兩個欄位讀進'
              '流程變數（config.fields 寫死這兩個 key）。跑完後查 fw_workflow_variables 看結果。'),
        _text('visitor_note', '訪客留言', '會被 OpFieldRead 讀進流程變數 visitor_note。', rows=3),
        _number('urgency', '急迫程度（1~5）', '會被 OpFieldRead 讀進流程變數 urgency。'),
        _submit_button(),
    ],
}


def build_fieldread_graph():
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 340, 200),
        _node(
            'node-FieldRead', 'OpFieldRead', '讀取表單欄位',
            {'fields': ['visitor_note', 'urgency']},
            560, 200,
            '把送單表單的 visitor_note 與 urgency 兩個欄位讀進流程變數。'
            '留空 config.fields 的話會退而求其次：先看 fieldReadConfig，再退到自動抓全部欄位。',
        ),
        _approve_node(
            'node-Form-approve', '確認讀取結果', 800, 200,
            'fieldread_decision', '確認無誤', 'edge-ok', '有問題', 'edge-ng',
            'assignee_type=INITIATOR：示範用，送單的人自己就會在待辦看到這張單。',
        ),
        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 1040, 200),
    ]
    edges = [
        _edge('edge-start-read', 'node-Start', 'node-FieldRead'),
        _edge('edge-read-form', 'node-FieldRead', 'node-Form-approve'),
        _edge('edge-ok', 'node-Form-approve', 'node-End', '確認無誤'),
        _edge('edge-ng', 'node-Form-approve', 'node-End', '有問題'),
    ]
    return {'nodes': nodes, 'edges': edges, 'relayPoints': [],
            'canvasSettings': _canvas(), 'fieldReadConfig': {}}


# ---------------------------------------------------------------------------
# NT-21 OpFieldWrite 示範
# ---------------------------------------------------------------------------

FORM_FIELDWRITE_CODE = 'NODEDEMO_NT21_FIELDWRITE_FORM'
WF_FIELDWRITE_CODE = 'NODEDEMO_NT21_FIELDWRITE_FLOW'
FORM_FIELDWRITE_NAME = 'NT-21 OpFieldWrite 示範表單'
WF_FIELDWRITE_NAME = 'NT-21 OpFieldWrite 示範'

WF_FIELDWRITE_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'OpFieldWrite（寫入欄位）把一段文字（可以混合流程變數、表單欄位、時間戳記）寫回'
    '這次流程本身的表單實例——是三個變數類節點裡效果最直觀的一個：跑完之後使用者去'
    '表單中心打開這張單，指定欄位就已經被填上內容了。\n\n'
    '【本流程的設定重點】\n'
    '- target_field 只填欄位 key（本示範是 process_result）；也接受 ${form.欄位key} 這種'
    '變數語法格式，handler 會自動解析出真正的 key 再寫入，兩種寫法效果一樣。\n'
    '- content 是一段字串，寫入前會先做變數替換：本示範同時用了 ${t.now}（節點執行當下的'
    '時間，UTC，格式 YYYY-MM-DD HH:MM:SS）、${f.reason}（讀送單時的表單欄位）、'
    '${v.reviewer_note}（讀前一個 OpSet 節點設定的流程變數），示範三種前綴可以混在同一段'
    '內容裡一起替換。\n'
    '- content_type 預設 text，本示範沒有特別設定；若改成 html，內容裡字面的 \\n 會轉成 <br>'
    '而不是真正換行，適合寫進會被當 HTML 渲染的欄位。\n'
    '- target_field 或 content 只要有一項留空，節點不會報錯，只會在執行紀錄標記 skipped=true'
    ' 並跳過——畫面上看起來一切正常（節點是綠的），但表單完全沒有被改動，這是最容易被忽略的'
    '「靜默沒生效」狀態。\n\n'
    '【怎麼看結果】\n'
    '送單並簽核完成後，到表單中心打開這張單，「系統處理結果」欄位應該已經被自動填上一段文字。'
    '也可以直接查 fw_form_instances.form_data（該實例的 secure_code）確認 JSON 裡 '
    'process_result 的值真的改了；同時 fw_workflow_variables 也會多出同名的 process_result '
    '流程變數（以及帶表單 secure_code 前綴的版本），這是 handler 執行完寫入後順便同步的。'
)

FORM_FIELDWRITE_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-21 OpFieldWrite 示範表單'),
        _hint('送出後流程會先用 OpSet 準備一個流程變數，再用 OpFieldWrite 把混合三種來源'
              '（固定文字、表單欄位、流程變數、時間戳記）的內容寫回「系統處理結果」欄位。'),
        _text('reason', '申請原因', '會被 OpFieldWrite 的 content 讀進去（${f.reason}）。'),
        _text('process_result', '系統處理結果（送單時免填）',
              '送單時留空即可，流程跑完後這裡會被 OpFieldWrite 節點自動填上內容。', rows=4),
        _submit_button(),
    ],
}


def build_fieldwrite_graph():
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 340, 200),
        _node(
            'node-OpSet-note', 'OpSet', '準備附註變數',
            {'operations': [
                {'target_var': 'reviewer_note', 'operation': 'set',
                 'value': '系統自動處理（示範用固定字串）'},
            ]},
            520, 200,
            '只是配角：先準備一個流程變數 reviewer_note，給下一個 OpFieldWrite 節點的 '
            'content 引用（示範 ${v.xxx} 前綴），不是本流程的示範重點。',
        ),
        _node(
            'node-FieldWrite', 'OpFieldWrite', '寫回處理結果',
            {
                'target_field': 'process_result',
                'content': '[自動處理 ${t.now}] 原因：${f.reason}。附註：${v.reviewer_note}',
                'content_type': 'text',
            },
            740, 200,
            '把 content 做完變數替換後寫進表單的 process_result 欄位，同時同步一份到'
            '流程變數 process_result。target_field 或 content 任一留空都會被跳過（skipped=true）'
            '而不是報錯。',
        ),
        _approve_node(
            'node-Form-approve', '確認寫回結果', 980, 200,
            'fieldwrite_decision', '確認無誤', 'edge-ok', '有問題', 'edge-ng',
            'assignee_type=INITIATOR：示範用，送單的人自己就會在待辦看到這張單，'
            '打開時應該已經能看到「系統處理結果」欄位被填好了。',
        ),
        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 1220, 200),
    ]
    edges = [
        _edge('edge-start-opset', 'node-Start', 'node-OpSet-note'),
        _edge('edge-opset-write', 'node-OpSet-note', 'node-FieldWrite'),
        _edge('edge-write-form', 'node-FieldWrite', 'node-Form-approve'),
        _edge('edge-ok', 'node-Form-approve', 'node-End', '確認無誤'),
        _edge('edge-ng', 'node-Form-approve', 'node-End', '有問題'),
    ]
    return {'nodes': nodes, 'edges': edges, 'relayPoints': [],
            'canvasSettings': _canvas(), 'fieldReadConfig': {}}


DEMOS = [
    {
        'form_code': FORM_OPSET_CODE, 'form_name': FORM_OPSET_NAME,
        'form_schema': FORM_OPSET_SCHEMA,
        'workflow_code': WF_OPSET_CODE, 'workflow_name': WF_OPSET_NAME,
        'description': WF_OPSET_DESCRIPTION,
        'graph': build_opset_graph,
    },
    {
        'form_code': FORM_FIELDREAD_CODE, 'form_name': FORM_FIELDREAD_NAME,
        'form_schema': FORM_FIELDREAD_SCHEMA,
        'workflow_code': WF_FIELDREAD_CODE, 'workflow_name': WF_FIELDREAD_NAME,
        'description': WF_FIELDREAD_DESCRIPTION,
        'graph': build_fieldread_graph,
    },
    {
        'form_code': FORM_FIELDWRITE_CODE, 'form_name': FORM_FIELDWRITE_NAME,
        'form_schema': FORM_FIELDWRITE_SCHEMA,
        'workflow_code': WF_FIELDWRITE_CODE, 'workflow_name': WF_FIELDWRITE_NAME,
        'description': WF_FIELDWRITE_DESCRIPTION,
        'graph': build_fieldwrite_graph,
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
            created_by_name='provision_nodedemo_vars',
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
            category_secure_code=SHOWCASE_CATEGORY_SECURE_CODE, schema=demo['form_schema'],
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
            category_secure_code=SHOWCASE_CATEGORY_SECURE_CODE,
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
    osc = org.secure_code
    log(f'企業：{org.name}（{osc}）')
    load_node_icons(models)

    publisher = User.query.filter_by(
        org_secure_code=osc, user_type='ORG_ADMIN',
        is_deleted=False, is_active=True).first()

    results = {}
    for demo in DEMOS:
        log(f"\n--- {demo['workflow_name']} ---")
        results[demo['workflow_code']] = apply_demo(
            db, models, org, demo, publisher, apply)
    return {'results': results, 'category_secure_code': SHOWCASE_CATEGORY_SECURE_CODE}

def main():
    parser = argparse.ArgumentParser(description='佈建 node展覽館的 OpSet / OpFieldRead / OpFieldWrite 三個示範流程')
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
            log('\n已寫入。到 /forms/center 的「填寫表單」就看得到這三張單。')
            log('\n示範：')
            for code, r in result['results'].items():
                if r:
                    log(f"  {code}: form_sc={r['form_sc']} wf_sc={r['wf_sc']} "
                        f"published_sc={r['published_sc']}")
        else:
            db.session.rollback()
            log('\n[預演] 未寫入任何資料')
    return 0

if __name__ == '__main__':
    sys.exit(main())
