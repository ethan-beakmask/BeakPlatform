#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PF-252 B15 批次：node展覽館 —— OpHrLookup（NT-31）示範（人事資料取值）。

本檔佈建兩個流程：

1. NT-31 OpHrLookup 示範（取得人事資料）
   入門示範：把申請人的職位、職等、職系、部門、直屬主管等人事資料
   整批寫進 hr_* 流程變數，再寫回表單讓人直接看到。不啟用 approver_mode，
   純粹展示「這個節點到底查得到什麼」。

2. NT-31 OpHrLookup 示範（依金額沿主管鏈找核決人）
   本批次的重點：啟用 approver_mode，依申請金額沿主管鏈往上找到第一個
   「核決上限 >= 金額」的主管，再把他設成 FormAdapter 的動態簽核人
   （assignee_type=DYNAMIC，assignee_value='hr_approver'）。

兩個流程都使用系統企業既有的示範人資結構（附錄 A，2026-09-07 已佈建，
本腳本不建立也不修改）：

    示範處 IxAGtnFKrUrXTi4s8okjE8（根）
      └ 示範部 nZhemfe5upQ38diRJ3tKsO（子）
    demo-staff@system.local    L200 示範專員級（申請人，示範部一般成員）
    demo-manager@system.local  L500 示範經理級（示範部正主管，直屬主管）
    demo-director@system.local L700 示範處長級（示範處正主管）
    核決類別 TRAVEL 差旅費 Gjx6BVgZVB4t_RBePJreSv：
      L200 上限 0 ／ L500 上限 300,000 ／ L700 上限 999,999,999
    判定規則「第一個 approval_limit >= amount 的主管即為核決人」，
    所以金額剛好 300,000 由 demo-manager 核，超過才輪到 demo-director。

直屬主管完全由部門角色推導（DEPT_MANAGER@單位持有人），不是任職卡欄位——
demo-manager 卸任或換人，兩個流程都會自動跟著變，不需要改流程或表單。

OpHrLookup 找核決人時只依主管鏈與核決上限比對金額，不檢查主管當下是否
請假（那是 FormAdapter 的 assignee_type=ROLE 搭配單位範圍才有的
absence_fallback 機制，這裡完全沒有這層邏輯，兩者不要混淆）。

目標企業固定是系統預設企業（Organization.code='SYSTEM'），分類固定是
「node展覽館」（fw_categories.secure_code='J1ygL6zexauKlLM0_Ktoaw'）。

冪等：重跑會沿用既有表單／流程（依 code 找），bump revision 並重新發行
（會停用舊的已發行版本並建立新版）。填寫權限授予企業內所有非 EXTERNAL
的在職帳號。

用法：
    cd /opt/BeakPlatform-dev
    set -a && source .env && set +a
    venv/bin/python scripts/examples/provision_nodedemo_hrlookup.py --dry-run
    venv/bin/python scripts/examples/provision_nodedemo_hrlookup.py --apply

節點 config 欄位依 handler 原始碼確認：
    modules/form_workflow/services/node_handlers/hr_lookup_handler.py
    modules/form_workflow/services/node_handlers/formadapter_handler.py（見 fc_pending.py::approve_task()）
    modules/form_workflow/services/node_handlers/fieldwrite_handler.py
規格：dev-notes/HR_LOOKUP_NODE_SPEC.md
權威對照表：/opt/tmp/verify/20260907-node-config-reference.md
範本：scripts/examples/provision_hr_lookup_demo.py（GHTRAVEL 版）、
      scripts/examples/provision_nodedemo_decisionwriter.py（B14，最新腳本模式）
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
APPROVAL_CATEGORY_CODE = 'TRAVEL'

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


def _text(key, label, description='', default_value=None, input_type='textfield', required=False):
    comp = {'key': key, 'type': input_type, 'input': True, 'label': label, 'tableView': True}
    if description:
        comp['description'] = description
    if default_value is not None:
        comp['defaultValue'] = default_value
    if required:
        comp['validate'] = {'required': True}
    return comp


def _textarea(key, label, description='', rows=6, disabled=False):
    comp = {'key': key, 'type': 'textarea', 'input': True, 'label': label,
            'tableView': True, 'rows': rows, 'autoExpand': True}
    if description:
        comp['description'] = description
    if disabled:
        comp['disabled'] = True
        comp['tableView'] = False
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
# 流程 1：NT-31 OpHrLookup 示範（取得人事資料）
# ---------------------------------------------------------------------------

HRINFO_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'OpHrLookup 把一個成員（預設是申請人自己）的職位資料整批查出來，'
    '寫成一組 hr_* 流程變數：職稱、職等、職系、部門，以及由部門角色'
    '推導出來的直屬主管。後續節點只要引用 ${v.hr_xxx} 就能拿到這些值，'
    '不需要自己下 SQL 或組 API。\n\n'
    '【本流程的設定重點】\n'
    '- **target_source=applicant**：目標固定是「發起這張單的人」'
    '（form_instance.applicant_secure_code）。另一種寫法是'
    ' target_source=variable + target_expr，可以查任何人（例如'
    ' ${f.someone_else}），本流程只示範最常用的第一種。\n'
    '- **var_prefix=hr**：所有輸出變數都會加這個前綴，同一流程裡如果要'
    '同時查兩個人（例如申請人與代理人），換一個前綴（如 hr2）就不會'
    '互相覆蓋。\n'
    '- **本流程刻意不設定 approval_category_code，也不開 approver_mode**：'
    '這兩個開關屬於「核決額度查詢」的進階功能，另一個流程'
    '（NT-31 OpHrLookup 示範（依金額沿主管鏈找核決人））會示範它們。'
    '這裡只想單純展示「查得到什麼人事資料」，避免兩個示範互相干擾。\n'
    '- **direct_manager 系列（hr_direct_manager／hr_direct_manager_name'
    '／hr_direct_manager_unit／hr_direct_manager_unit_name）是由部門角色'
    '推導的，不是任職卡上的欄位**（EmployeePosition.direct_manager_'
    'secure_code 已於 2026-09-05 PF-247 第 4 期退役）。推導方式是查申請人'
    '單位是否有 DEPT_MANAGER 持有人，沒有就找不到就往上一層祖先單位找，'
    '本人剛好是主管或該站職缺就跳過往上一層。這代表主管改組、換人，'
    '流程完全不用改，下次執行就會拿到新的主管。\n'
    '- **找不到有效職位時節點仍會成功（success），只是全部欄位回空字串'
    '／hr_found=false**：這個節點設計上永遠不會讓流程失敗，查不到就讓'
    '後面接 Branch 判斷 ${v.hr_found}，不會逼流程卡住重試。\n\n'
    '【怎麼看結果】\n'
    '1) 表單的「人事資料摘要」欄位（由 OpFieldWrite 寫回，唯讀），'
    '會列出這次查到的每一個 hr_* 值。\n'
    '2) 查流程變數：SELECT var_name, var_value FROM fw_workflow_variables'
    " WHERE workflow_instance_secure_code='<實例 sc>' AND var_name LIKE"
    " 'hr_%' ORDER BY var_name;\n"
    '3) 送出後有一個簡單的自我確認關卡（assignee_type=INITIATOR，'
    '發起人自己簽），確認資料無誤即可結案，這一步只是走個形式讓流程'
    '像一個完整的單據，不是這個節點的示範重點。'
)

FORM_HRINFO_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-31 OpHrLookup 示範表單（取得人事資料）'),
        _hint('送出後流程會立刻查出你自己（申請人）的職位、職等、職系、'
              '部門與直屬主管，寫進下方「人事資料摘要」欄位，最後由你'
              '自己確認一次即可結案。不需要填任何欄位，直接送出即可。'),
        _textarea('hr_summary', '人事資料摘要（由流程自動填寫）',
                   '由流程的 OpHrLookup + OpFieldWrite 節點自動寫入，'
                   '送單者不需輸入。',
                   rows=16, disabled=True),
        _submit_button(),
    ],
}


def build_hrinfo_graph():
    hr_summary_content = (
        '【申請人基本資料】\n'
        '是否找到有效職位：${v.hr_found}\n'
        '姓名：${v.hr_user_name}（${v.hr_user_code}）\n'
        '職位型態：${v.hr_position_type}\n\n'
        '【職稱與職等】\n'
        '職稱：${v.hr_job_title}（代碼 ${v.hr_job_title_code}，'
        '簡稱 ${v.hr_job_title_short}）\n'
        '職稱是否主管：${v.hr_is_supervisor}\n'
        '職等：${v.hr_job_level_name}（代碼 ${v.hr_job_level_code}，'
        '排序 ${v.hr_job_level_order}）\n'
        '職等是否管理職：${v.hr_job_level_is_manager}\n\n'
        '【職系】\n'
        '職系：${v.hr_job_family_name}（代碼 ${v.hr_job_family_code}，'
        '類型 ${v.hr_job_family_type}）\n'
        '職系根節點代碼：${v.hr_job_family_root_code}\n\n'
        '【部門】\n'
        '部門：${v.hr_unit_name}（代碼 ${v.hr_unit_code}）\n'
        '是否部門主管：${v.hr_is_unit_head}\n\n'
        '【直屬主管（由部門角色推導，非任職卡指標）】\n'
        '直屬主管：${v.hr_direct_manager_name}（${v.hr_direct_manager}）\n'
        '主管所在單位：${v.hr_direct_manager_unit_name}'
        '（${v.hr_direct_manager_unit}）\n\n'
        '流程執行代碼：${wi.exec_code}'
    )
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 100, 180,
              '流程入口，不需要任何前置設定。'),

        _node('node-HrLookup', 'OpHrLookup', '取申請人人事資料', {
            'target_source': 'applicant',
            'var_prefix': 'hr',
        }, 340, 180,
            '把申請人的職稱、職等、職系、部門與直屬主管整批寫成 hr_* '
            '流程變數。target_source=applicant 固定查發起這張單的人，'
            '沒有設定 approval_category_code，所以不會輸出 hr_approval_'
            'limit（那個要另外設定核決類別才會有值，見另一個示範流程）。'),

        _node('node-Write', 'OpFieldWrite', '寫回人事資料摘要', {
            'target_field': 'hr_summary',
            'content': hr_summary_content,
        }, 580, 180,
            '把上一個節點查到的所有 hr_* 變數整理成一段文字寫回表單的'
            ' hr_summary 欄位，讓送單者不必查資料庫就能直接在表單上'
            '看到完整結果。'),

        _node('node-Confirm', 'FormAdapter', '本人確認', {
            'assignee_type': 'INITIATOR',
            'selection_mode': 'single',
            'allow_comment': True,
            'require_comment': False,
            'use_custom_decisions': False,
        }, 820, 180,
            '簽核者固定是發起人自己（assignee_type=INITIATOR）——這一步'
            '只是讓流程像一張完整單據一樣有始有終，不是 OpHrLookup 的'
            '示範重點。這個節點只有一條出邊（沒有另外設定'
            ' use_custom_decisions 的多重決策），確認即可推進到結束。'),

        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 1060, 180,
              '流程正常結束（finish_mode=detach），流程實例狀態變成'
              ' COMPLETED。'),
    ]
    edges = [
        _edge('edge-start-lookup', 'node-Start', 'node-HrLookup'),
        _edge('edge-lookup-write', 'node-HrLookup', 'node-Write'),
        _edge('edge-write-confirm', 'node-Write', 'node-Confirm'),
        _edge('edge-confirm-end', 'node-Confirm', 'node-End', label='確認'),
    ]
    return _graph(nodes, edges)


# ---------------------------------------------------------------------------
# 流程 2：NT-31 OpHrLookup 示範（依金額沿主管鏈找核決人）
# ---------------------------------------------------------------------------

APPROVER_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'OpHrLookup 開啟 approver_mode 後，會從申請人的直屬主管開始，'
    '沿著部門主管鏈一站一站往上找，找到第一個「核決上限 >= 申請金額」'
    '的主管，把他寫成 hr_approver 變數，交給下一個 FormAdapter 節點當'
    '動態簽核人（assignee_type=DYNAMIC）。這是本節點最主要的用途：'
    '讓簽核關卡的「找誰簽」變成資料驅動，不必為每一種金額寫死一個'
    '簽核流程分支。\n\n'
    '【本流程的設定重點】\n'
    '- **approval_category_code=TRAVEL、approver_mode=true、'
    'amount_expr=${f.amount}**：三者缺一不可——只設 approval_category_'
    'code 不開 approver_mode 只會多輸出申請人自己的核決上限'
    '（hr_approval_limit），不會去找核決人；只開 approver_mode 不設'
    ' approval_category_code 或 amount_expr，核決人變數會全部寫空字串'
    '＋hr_approver_found=false（並記警告），不會讓節點失敗。\n'
    '- **核決人不是「申請人的主管」，而是「沿主管鏈往上第一個額度夠的'
    '人」**：本示範的差旅費核決類別（TRAVEL）三個職等的上限是'
    ' L200=0／L500=300,000／L700=999,999,999。申請人 demo-staff 是'
    ' L200（上限 0，自己不能核決任何金額），他的直屬主管 demo-manager'
    '（示範部正主管，L500，上限 300,000）若額度夠就在第一站直接核決；'
    '若申請金額超過 300,000，就會再往上一站，落到示範部的上層單位'
    '「示範處」的正主管 demo-director（L700，上限 999,999,999）。\n'
    '- **金額剛好等於門檻算低職等那邊**：判定規則是「第一個'
    ' approval_limit >= amount 的主管」，用的是 >=，所以申請金額剛好'
    ' 300,000 時，第一站的 demo-manager（上限剛好 300,000）就會通過'
    '判定、直接核決，不會往上升到 demo-director——這是本示範刻意用來'
    '驗證邊界值的對照組。\n'
    '- **這條主管鏈不檢查缺席／請假**：OpHrLookup 找核決人只比對主管鏈'
    '與核決上限的數字，不會像 FormAdapter 的 assignee_type=ROLE 搭配'
    ' unit_scope 那樣去看主管當下是否請假（absence_fallback 機制）。'
    '如果 demo-manager 剛好請假，這個節點還是會把他選為核決人，簽核'
    '任務照樣落在他身上——這是兩個機制刻意分工不同層面，不要混淆。\n'
    '- **簽核節點 assignee_type=DYNAMIC、assignee_value=hr_approver**：'
    'DYNAMIC 型別是「讀一個流程變數，把它的值當成簽核人 secure_code」，'
    '所以簽核者完全由上一個 OpHrLookup 節點的查詢結果決定，同一張流程'
    '圖不用為「金額 20 萬找經理簽、金額 50 萬找處長簽」畫兩條不同的'
    '簽核分支。\n\n'
    '【怎麼看結果】\n'
    '1) 表單的「核決人資訊」欄位（由 OpFieldWrite 寫回，唯讀），會顯示'
    '這次查到的核決人是誰、他的職等與所在單位。\n'
    '2) 查流程變數確認核決人：SELECT var_name, var_value FROM'
    ' fw_workflow_variables WHERE workflow_instance_secure_code=<實例 sc>'
    " AND var_name LIKE 'hr_approver%' ORDER BY var_name;\n"
    '3) 查簽核任務實際指派給誰、以及後來是誰簽的：SELECT node_type,'
    ' status, result->\'data\'->>\'assignees\' FROM'
    ' fw_node_execution_queue WHERE workflow_instance_secure_code='
    '<實例 sc> AND node_type=\'FormAdapter\'；簽核完成後看'
    ' fw_approval_records.approver_secure_code。\n'
    '4) 三個金額（200,000／300,000／500,000）送單後核決人應分別落在'
    ' demo-manager／demo-manager／demo-director，這是本流程最直接的'
    '證據。'
)

FORM_APPROVER_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-31 OpHrLookup 示範表單（依金額沿主管鏈找核決人）'),
        _hint('填申請金額送出後，流程會依你（申請人）的部門主管鏈與'
              '差旅費核決類別（TRAVEL）的職等上限，自動找到第一個'
              '額度足夠的主管當簽核人。範例上限：示範經理級 300,000／'
              '示範處長級 999,999,999。'),
        _text('amount', '申請金額', '單位新台幣，純數字。', input_type='number', required=True),
        _text('purpose', '出差事由', '', required=False),
        _textarea('approver_summary', '核決人資訊（由流程自動填寫）',
                   '由流程的 OpHrLookup + OpFieldWrite 節點自動寫入，'
                   '送單者不需輸入。',
                   rows=12, disabled=True),
        _submit_button(),
    ],
}


def build_approver_graph():
    approver_summary_content = (
        '【申請人本身核決資料（僅供對照）】\n'
        '申請人：${v.hr_user_name}（職等 ${v.hr_job_level_name}）\n'
        '申請人本身差旅費核決上限：${v.hr_approval_limit}\n'
        '直屬主管：${v.hr_direct_manager_name}'
        '（${v.hr_direct_manager_unit_name}）\n\n'
        '【找到的核決人（沿主管鏈往上，第一個核決上限 >= 申請金額者）】\n'
        '是否找到核決人：${v.hr_approver_found}\n'
        '核決人：${v.hr_approver_name}（${v.hr_approver}）\n'
        '核決人職等：${v.hr_approver_level_code}\n'
        '核決人所在單位：${v.hr_approver_unit_name}\n\n'
        '申請金額：${f.amount}\n'
        '流程執行代碼：${wi.exec_code}'
    )
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 100, 180,
              '流程入口，不需要任何前置設定。'),

        _node('node-HrLookup', 'OpHrLookup', '依金額找核決人', {
            'target_source': 'applicant',
            'var_prefix': 'hr',
            'approval_category_code': APPROVAL_CATEGORY_CODE,
            'approver_mode': True,
            'amount_expr': '${f.amount}',
        }, 340, 180,
            '除了申請人自己的職位資料，額外啟用 approver_mode：依'
            ' TRAVEL 核決類別與 ${f.amount} 的金額，沿部門主管鏈往上找'
            '第一個核決上限足夠的主管，寫成 hr_approver 系列變數。'),

        _node('node-Write', 'OpFieldWrite', '寫回核決人資訊', {
            'target_field': 'approver_summary',
            'content': approver_summary_content,
        }, 580, 180,
            '把 OpHrLookup 查到的核決人資訊整理成文字寫回表單，讓送單者'
            '在簽核前就能看到這張單會被誰簽核，以及為什麼是他（沿主管鏈'
            '往上第一個額度足夠的人）。'),

        _node('node-Approve', 'FormAdapter', '核決人動態簽核', {
            'assignee_type': 'DYNAMIC',
            'assignee_value': 'hr_approver',
            'assignee_label': '依金額找到的核決人',
            'selection_mode': 'single',
            'output_variable': 'approval_decision',
            'allow_comment': True,
            'require_comment': False,
            'use_custom_decisions': True,
            'input_variables': [],
            'decision_options': [
                {'id': 'opt-approve', 'label': '核准', 'value': 'approved',
                 'style': 'primary', 'target_edges': ['edge-approve']},
                {'id': 'opt-reject', 'label': '駁回', 'value': 'rejected',
                 'style': 'danger', 'target_edges': ['edge-reject']},
            ],
        }, 820, 180,
            'assignee_type=DYNAMIC，assignee_value 讀取流程變數'
            ' hr_approver 的值當簽核人 secure_code——也就是上一個'
            ' OpHrLookup 節點依金額找到的那個人，不是寫死某個角色或'
            '某個人。同一張圖不需要為不同金額畫不同的簽核分支。'),

        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 1060, 180,
              '流程正常結束（finish_mode=detach），不論核准或駁回都會走'
              '到這裡，流程實例狀態變成 COMPLETED。'),
    ]
    edges = [
        _edge('edge-start-lookup', 'node-Start', 'node-HrLookup'),
        _edge('edge-lookup-write', 'node-HrLookup', 'node-Write'),
        _edge('edge-write-approve', 'node-Write', 'node-Approve'),
        _edge('edge-approve', 'node-Approve', 'node-End', label='核准'),
        _edge('edge-reject', 'node-Approve', 'node-End', label='駁回'),
    ]
    return _graph(nodes, edges)


FULL_DEMOS_STATIC = [
    {
        'form_code': 'NODEDEMO_NT31_HRINFO_FORM',
        'form_name': 'NT-31 OpHrLookup 示範表單（取得人事資料）',
        'form_schema': FORM_HRINFO_SCHEMA,
        'workflow_code': 'NODEDEMO_NT31_HRINFO_FLOW',
        'workflow_name': 'NT-31 OpHrLookup 示範（取得人事資料）',
        'description': HRINFO_DESCRIPTION,
        'graph': lambda: build_hrinfo_graph(),
    },
    {
        'form_code': 'NODEDEMO_NT31_APPROVER_FORM',
        'form_name': 'NT-31 OpHrLookup 示範表單（依金額沿主管鏈找核決人）',
        'form_schema': FORM_APPROVER_SCHEMA,
        'workflow_code': 'NODEDEMO_NT31_APPROVER_FLOW',
        'workflow_name': 'NT-31 OpHrLookup 示範（依金額沿主管鏈找核決人）',
        'description': APPROVER_DESCRIPTION,
        'graph': lambda: build_approver_graph(),
    },
]


# ---------------------------------------------------------------------------
# 寫入
# ---------------------------------------------------------------------------

def ensure_fill_permissions(db, models, org_sc, mapping, apply):
    """
    給示範表單開填寫權限（表單中心預設只放行 SYSTEM_ADMIN / FLOW_DESIGNER /
    FORM_DESIGNER，ORG_ADMIN 與一般 EMPLOYEE 都不在內，沒有這一步連
    demo-staff／demo-manager／demo-director 都送不了單、簽不了核）。
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
            created_by_name='provision_nodedemo_hrlookup',
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
        description='佈建 node展覽館的 OpHrLookup 示範（B15）')
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

        log('\n=== OpHrLookup 示範（表單／流程／配對／發行） ===')
        full_results = {}
        for demo in FULL_DEMOS_STATIC:
            log(f"\n--- {demo['workflow_name']} ---")
            full_results[demo['workflow_code']] = apply_full_demo(
                db, models, org, demo, publisher, args.apply)

        if args.apply:
            db.session.commit()
            log('\n已寫入。到 /forms/center 的「填寫表單」就看得到這兩張單。')
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
