#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PF-252 B5a 批次：node展覽館 —— FormAdapter（簽核）第一批：簽核者是怎麼決定的。

FormAdapter 是全平台最複雜的節點，拆成兩批：B5a 只講「assignee_type 怎麼解析出
簽核者」，自訂決策出線配對與簽核逾時留給 B5b。

    NT-19 FormAdapter 示範（發起人自簽）      assignee_type=INITIATOR：誰送單誰簽核。
    NT-19 FormAdapter 示範（指定人員）        assignee_type=USER：不論誰送單，簽核者
                                              永遠是設定裡寫死的那個人（demo-manager）。
    NT-19 FormAdapter 示範（角色＠單位）      assignee_type=ROLE，同一個角色
                                              DEPT_MANAGER 接兩個節點，分別示範
                                              unit_scope=APPLICANT_UNIT（只認申請人
                                              所屬單位的主管）與 unit_scope=GLOBAL
                                              （全企業任一該角色持有者皆可）。
    NT-19 FormAdapter 示範（找不到簽核人時）  用 Branch 依表單欄位分流到兩個刻意讓
                                              assignee_type=DYNAMIC 解析成空清單的
                                              節點，對照 no_assignee_action 的
                                              'return'（退回申請人、REJECTED 終態）
                                              與 'fallback_role'（改派 ORG_ADMIN，
                                              正常進入等待簽核）兩種行為。

目標企業固定是系統預設企業（Organization.code='SYSTEM'），分類固定是「node展覽館」
（fw_categories.secure_code='J1ygL6zexauKlLM0_Ktoaw'）。用到 B0 佈建的示範人資結構
（demo-staff／demo-manager／demo-director，示範部／示範處兩層部門，見
/opt/tmp/verify/20260907-nodedemo-briefing.md 附錄 A）。

冪等：重跑會沿用既有表單／流程（依 code 找），bump revision 並重新發行（會停用
舊的已發行版本並建立新版）。填寫權限授予企業內所有非 EXTERNAL 的在職帳號。

用法：
    cd /opt/BeakPlatform-dev
    set -a && source .env && set +a
    venv/bin/python scripts/examples/provision_nodedemo_approval_assignee.py --dry-run
    venv/bin/python scripts/examples/provision_nodedemo_approval_assignee.py --apply

節點 config 欄位依 handler 原始碼確認：
    modules/form_workflow/services/node_handlers/formadapter_handler.py
    modules/form_workflow/services/node_handlers/branch_handler.py
    modules/form_workflow/services/task_authorizer.py（執行時授權判定）
    modules/form_workflow/services/role_holding_service.py（角色@單位持有者解析）
權威對照表：/opt/tmp/verify/20260907-node-config-reference.md（FormAdapter／Branch 節）
設計文件：dev-notes/ROLE_UNIT_APPROVAL_DESIGN.md
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

# 示範人資帳號（B0 佈建，見 briefing 附錄 A）
DEMO_STAFF_EMAIL = 'demo-staff@system.local'
DEMO_MANAGER_EMAIL = 'demo-manager@system.local'
DEMO_DIRECTOR_EMAIL = 'demo-director@system.local'


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
# NT-19 FormAdapter：發起人自簽（INITIATOR）
# ---------------------------------------------------------------------------

def build_initiator_graph():
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 340, 200,
              '流程入口，不需要任何前置設定。'),
        _node('node-Approve', 'FormAdapter', '簽核（發起人自簽）', {
            'assignee_type': 'INITIATOR',
            'selection_mode': 'single',
            'output_variable': 'nt19_initiator_decision',
            'allow_comment': True, 'require_comment': False,
            'use_custom_decisions': True, 'input_variables': [],
            'decision_options': [
                {'id': 'opt-approve', 'label': '核准（我同意）', 'value': 'approved',
                 'style': 'primary', 'target_edges': ['edge-approve']},
                {'id': 'opt-reject', 'label': '駁回（我不同意，結束流程）', 'value': 'rejected',
                 'style': 'danger', 'target_edges': []},
            ],
        }, 620, 200,
            'assignee_type=INITIATOR：不論這個流程實例是誰送出的，簽核者永遠是'
            '「這個實例的申請人本人」。示範中由 demo-staff 送單、也由 demo-staff'
            '自己完成簽核，不牽涉任何角色或部門。'),
        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 900, 200,
              '簽核核准後正常結束，記為 COMPLETED。'),
    ]
    edges = [
        _edge('edge-start', 'node-Start', 'node-Approve'),
        _edge('edge-approve', 'node-Approve', 'node-End', '核准'),
    ]
    return _graph(nodes, edges)


NT19_INITIATOR_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'FormAdapter（簽核）是流程裡負責等待人工核決的節點：流程執行到這裡會暫停，'
    '直到指定的簽核者透過表單中心送出決定，才依決定選擇後續路徑推進。誰是'
    '「指定的簽核者」由 assignee_type 決定——這是本節點最容易混淆的設定，'
    'node展覽館用四個示範分別講清楚 INITIATOR／USER／ROLE＠單位／找不到簽核人時'
    '這四種情況，本流程講第一種、也是最單純的一種。\n\n'
    '【本流程的設定重點】\n'
    '- assignee_type=\'INITIATOR\'：簽核者永遠是「這個流程實例的申請人」，'
    '與角色、部門、職等完全無關。誰送單，誰簽核；換一個人送單，簽核者就換成'
    '那個人，不需要另外設定任何對象。\n'
    '- use_custom_decisions=True 搭配兩個決策選項（核准／駁回）：駁回選項的'
    ' target_edges 刻意留空——空陣列代表這個決策是終態，選了駁回會直接把案件'
    '記成 REJECTED、流程立即結束，不會走到 End 節點。\n'
    '- output_variable=\'nt19_initiator_decision\'：簽核者選擇的 value'
    '（\'approved\'／\'rejected\'）會寫進這個流程變數，供後續節點或稽核查閱。\n\n'
    '【怎麼看結果】\n'
    '用 demo-staff 送單後，待簽任務只會出現在 demo-staff 自己的表單中心待辦裡'
    '（不是主管、不是任何角色持有者）。用同一個帳號簽核「核准」，流程走到 End'
    '正常結束；查 fw_workflow_variables 的 nt19_initiator_decision 應為'
    ' approved，fw_approval_records 該筆的簽核者就是申請人自己'
    '（acted_as_kind／acted_as_role_code 皆為空，因為這是本人身分直接簽核，'
    '不涉及代理）。'
)

FORM_INITIATOR_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-19 FormAdapter 示範表單（發起人自簽）'),
        _hint('送出後這張單的簽核者就是「你自己」——不論你是誰送單，簽核任務'
              '都只會出現在你自己的待辦。用 demo-staff 送單並用 demo-staff 完成簽核，'
              '就是本示範要驗證的行為。'),
        _text('applicant_note', '申請事由（非必填）'),
        _submit_button(),
    ],
}


# ---------------------------------------------------------------------------
# NT-19 FormAdapter：指定人員（USER）
# ---------------------------------------------------------------------------

def build_user_graph(demo_manager_sc):
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 340, 200,
              '流程入口，不需要任何前置設定。'),
        _node('node-Approve', 'FormAdapter', '簽核（固定指定 demo-manager）', {
            'assignee_type': 'USER',
            'assignee_value': demo_manager_sc,
            'selection_mode': 'single',
            'output_variable': 'nt19_user_decision',
            'allow_comment': True, 'require_comment': False,
            'use_custom_decisions': True, 'input_variables': [],
            'decision_options': [
                {'id': 'opt-approve', 'label': '核准', 'value': 'approved',
                 'style': 'primary', 'target_edges': ['edge-approve']},
                {'id': 'opt-reject', 'label': '駁回', 'value': 'rejected',
                 'style': 'danger', 'target_edges': []},
            ],
        }, 620, 200,
            'assignee_type=USER，assignee_value 寫死 demo-manager 的 secure_code：'
            '不管誰送單，簽核者永遠是這個固定的人。'),
        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 900, 200,
              '簽核核准後正常結束，記為 COMPLETED。'),
    ]
    edges = [
        _edge('edge-start', 'node-Start', 'node-Approve'),
        _edge('edge-approve', 'node-Approve', 'node-End', '核准'),
    ]
    return _graph(nodes, edges)


NT19_USER_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'FormAdapter（簽核）等待指定的簽核者送出決定才會繼續推進。本流程示範第二種'
    'assignee_type：USER。\n\n'
    '【本流程的設定重點】\n'
    '- assignee_type=\'USER\'，assignee_value 直接寫死 demo-manager@system.local'
    ' 的 secure_code：不管誰送單，簽核者永遠是這個固定的人，與申請人、角色、'
    '部門完全無關。這是最不「動態」的一種，適合「這張表單本來就該給某個特定'
    '窗口審」的場景（例如「所有請款單一律由財務窗口審」）。\n'
    '- assignee_value 支援逗號分隔多個 secure_code（多人皆可簽，任一人簽核即'
    '推進），本示範只放一個人。\n'
    '- 對照 INITIATOR：INITIATOR 是「誰送就誰簽」，USER 是「誰送都給同一個人'
    '簽」，是兩個相反的極端；ROLE＠單位（見另一個示範）則是介於兩者之間的'
    '「依身分動態找人」。\n\n'
    '【怎麼看結果】\n'
    '用 demo-staff（或任何人）送單，待簽任務只會出現在 demo-manager 的表單中心'
    '待辦，demo-staff 自己看不到、也簽不了。用 demo-manager 簽核「核准」後查'
    ' fw_workflow_variables 的 nt19_user_decision 應為 approved。'
)

FORM_USER_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-19 FormAdapter 示範表單（指定人員）'),
        _hint('送出後不論你是誰，簽核任務都只會指派給固定的 demo-manager'
              '（assignee_type=USER，寫死一個 secure_code）。'),
        _text('applicant_note', '申請事由（非必填）'),
        _submit_button(),
    ],
}


# ---------------------------------------------------------------------------
# NT-19 FormAdapter：角色＠單位（ROLE + unit_scope）
# ---------------------------------------------------------------------------

def build_role_unit_graph(dept_manager_role_sc):
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 340, 200,
              '流程入口，申請人是誰決定了 APPLICANT_UNIT 範圍解析出哪個單位。'),
        _node('node-ApproveUnit', 'FormAdapter', '部門主管簽核（申請人單位）', {
            'assignee_type': 'ROLE',
            'assignee_value': dept_manager_role_sc,
            'unit_scope': 'APPLICANT_UNIT',
            'self_target_action': 'escalate_or_return',
            'selection_mode': 'single',
            'output_variable': 'nt19_unit_decision',
            'allow_comment': True, 'require_comment': False,
            'use_custom_decisions': True, 'input_variables': [],
            'decision_options': [
                {'id': 'opt-approve', 'label': '核准（申請人部門主管）', 'value': 'approved',
                 'style': 'primary', 'target_edges': ['edge-unit-approve']},
                {'id': 'opt-reject', 'label': '駁回', 'value': 'rejected',
                 'style': 'danger', 'target_edges': []},
            ],
        }, 620, 200,
            'unit_scope=APPLICANT_UNIT：只認「申請人自己所屬單位」的 DEPT_MANAGER'
            '持有者。申請人是 demo-staff（示範部成員），所以只有示範部的主管'
            '（demo-manager）算數；示範處的主管（demo-director）不算——DEPT_MANAGER'
            '是 POSITION 型角色，不會往祖先單位套圈。'),
        _node('node-ApproveGlobal', 'FormAdapter', '部門主管簽核（全企業）', {
            'assignee_type': 'ROLE',
            'assignee_value': dept_manager_role_sc,
            'unit_scope': 'GLOBAL',
            'self_target_action': 'escalate_or_return',
            'selection_mode': 'single',
            'output_variable': 'nt19_global_decision',
            'allow_comment': True, 'require_comment': False,
            'use_custom_decisions': True, 'input_variables': [],
            'decision_options': [
                {'id': 'opt-approve', 'label': '核准（任一部門主管）', 'value': 'approved',
                 'style': 'primary', 'target_edges': ['edge-global-approve']},
                {'id': 'opt-reject', 'label': '駁回', 'value': 'rejected',
                 'style': 'danger', 'target_edges': []},
            ],
        }, 900, 200,
            'unit_scope=GLOBAL（預設值）：不限單位，全企業任何一個持有'
            ' DEPT_MANAGER 的人都算，示範部與示範處的主管都可以簽。'),
        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 1180, 200,
              '兩層核准都完成後正常結束，記為 COMPLETED。'),
    ]
    edges = [
        _edge('edge-start', 'node-Start', 'node-ApproveUnit'),
        _edge('edge-unit-approve', 'node-ApproveUnit', 'node-ApproveGlobal', '核准'),
        _edge('edge-global-approve', 'node-ApproveGlobal', 'node-End', '核准'),
    ]
    return _graph(nodes, edges)


NT19_ROLEUNIT_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'FormAdapter 的簽核者除了固定的一個人，也可以是「一個角色，在某個單位範圍'
    '內」——assignee_type=\'ROLE\' 搭配 unit_scope，這是四種簽核者裡最複雜、'
    '也是本批次的重點。\n\n'
    '【本流程的設定重點】\n'
    '- 兩個節點用同一個角色 DEPT_MANAGER（部門正主管），差別只在 unit_scope：\n'
    '  第一個節點 unit_scope=\'APPLICANT_UNIT\'——範圍是「申請人自己所屬的'
    '單位」。申請人是 demo-staff、所屬單位是示範部，這個節點只認示範部的'
    ' DEPT_MANAGER 持有者（demo-manager）。\n'
    '  第二個節點 unit_scope=\'GLOBAL\'——不限單位，全企業任何一個持有'
    ' DEPT_MANAGER 的人都算，包含示範處的主管 demo-director。\n'
    '- 授權判定不是看「進關卡當下的快照」，是看「簽核當下即時的身分」：'
    ' demo-manager 若在簽核前被撤了 DEPT_MANAGER，即使他還在待簽清單裡'
    '也簽不了。\n'
    '- DEPT_MANAGER 是 POSITION 型角色（「位子」的概念），不會往祖先單位'
    '套圈——示範處是示範部的上一層，但示範處的主管不會因為單位是祖先關係'
    '就自動對示範部的 APPLICANT_UNIT 節點有權限。這正是本示範刻意用'
    ' demo-director 當「不該有權限」反例的原因：他持有 DEPT_MANAGER，'
    '但持有的單位不對。\n'
    '- self_target_action 保持預設 \'escalate_or_return\'：如果申請人自己'
    '就是目標單位的主管本人，會往上一層升級或退回。本示範用 demo-staff'
    '（非主管）送單，避免觸發這個機制，讓兩個節點的差異單純呈現。\n\n'
    '【怎麼看結果】\n'
    '用 demo-staff 送單後，第一個節點的待簽任務只會出現在 demo-manager 的'
    '待辦；用 demo-director 或 ORG_ADMIN 嘗試簽核會被擋下（見驗收記錄的實際'
    'HTTP 狀態碼與錯誤內容）。demo-manager 核准後，第二個節點換成 GLOBAL'
    '範圍，這次 demo-director 也簽得動（他持有的 DEPT_MANAGER＠示範處在'
    ' GLOBAL 範圍內一樣算數）。查 fw_workflow_variables 的'
    ' nt19_unit_decision／nt19_global_decision，以及 fw_approval_records'
    '兩筆記錄的簽核者是否符合預期。'
)

FORM_ROLEUNIT_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-19 FormAdapter 示範表單（角色＠單位）'),
        _hint('送出後會先指派給你所屬單位（示範部）的主管，主管核准後第二關'
              '換成「全企業任一部門主管都可簽」。'),
        _text('applicant_note', '申請事由（非必填）'),
        _submit_button(),
    ],
}


# ---------------------------------------------------------------------------
# NT-19 FormAdapter：找不到簽核人時（no_assignee_action）
# ---------------------------------------------------------------------------

def build_noassignee_graph(org_admin_role_sc):
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 260, 200,
              '流程入口，依表單欄位 no_assignee_mode 決定要示範哪一種行為。'),
        _node('node-Branch', 'Branch', '依 no_assignee_mode 分流', {
            'rules': [
                {'name': '退回模式',
                 'conditions': [{'variable': '${f.no_assignee_mode}', 'operator': '==',
                                  'value': 'return'}],
                 'target_edges': ['edge-branch-return']},
                {'name': '改派角色模式',
                 'conditions': [{'variable': '${f.no_assignee_mode}', 'operator': '==',
                                  'value': 'fallback_role'}],
                 'target_edges': ['edge-branch-fallback']},
            ],
            'fallback': {'action': 'route', 'target_edge': 'edge-branch-return',
                         'log_message': 'no_assignee_mode 非 return/fallback_role，預設走退回模式'},
        }, 500, 200,
            '純粹用來讓同一個流程模板可以送兩種不同的示範，不是本流程要介紹的重點'
            '（Branch 節點本身在 NT-05 有專門的示範）。'),
        _node('node-Return', 'FormAdapter', '簽核（刻意解析不到人・退回模式）', {
            'assignee_type': 'DYNAMIC',
            'assignee_value': 'nt19_ghost_approver_return',
            'selection_mode': 'single',
            'output_variable': 'nt19_noassignee_return_decision',
            'allow_comment': True, 'require_comment': False,
            'no_assignee_action': 'return',
            'use_custom_decisions': True, 'input_variables': [],
            'decision_options': [
                {'id': 'opt-approve', 'label': '核准（示範用，實際上不會被走到）',
                 'value': 'approved', 'style': 'default', 'target_edges': ['edge-return-approve']},
            ],
        }, 780, 80,
            'assignee_type=DYNAMIC 指向一個從頭到尾沒有被設值的流程變數'
            '（nt19_ghost_approver_return），保證簽核者一定解析成空清單。'
            ' no_assignee_action=\'return\'（預設值）：找不到簽核人就直接把案件'
            '結束、記為 REJECTED，不會真的進入等待簽核，因此上面設定的決策選項'
            '實際上永遠不會被使用到。'),
        _node('node-EndReturn', 'End', 'End（示範用，實際上不會被走到）',
              {'finish_mode': 'detach'}, 1020, 80,
              '結構完整性用途：因為 return 模式一定在到達這裡之前就已經'
              ' complete_workflow，這個節點不會真的被執行到。'),
        _node('node-Fallback', 'FormAdapter', '簽核（刻意解析不到人・改派角色模式）', {
            'assignee_type': 'DYNAMIC',
            'assignee_value': 'nt19_ghost_approver_fallback',
            'selection_mode': 'single',
            'output_variable': 'nt19_noassignee_fallback_decision',
            'allow_comment': True, 'require_comment': False,
            'no_assignee_action': 'fallback_role',
            'no_assignee_role_secure_code': org_admin_role_sc,
            'use_custom_decisions': True, 'input_variables': [],
            'decision_options': [
                {'id': 'opt-approve', 'label': '核准', 'value': 'approved',
                 'style': 'primary', 'target_edges': ['edge-fallback-approve']},
                {'id': 'opt-reject', 'label': '駁回', 'value': 'rejected',
                 'style': 'danger', 'target_edges': []},
            ],
        }, 780, 320,
            '同樣用一個永遠沒被設值的流程變數（nt19_ghost_approver_fallback）'
            '保證解析成空清單，但 no_assignee_action=\'fallback_role\'：改派給'
            ' no_assignee_role_secure_code 指定的角色（本示範指定 ORG_ADMIN，'
            '一個保證隨時有人持有的全域角色）。流程會正常進入等待簽核狀態，'
            '不會直接結束。'),
        _node('node-EndFallback', 'End', 'End', {'finish_mode': 'detach'}, 1020, 320,
              '改派角色的持有者核准後正常結束，記為 COMPLETED。'),
    ]
    edges = [
        _edge('edge-start-branch', 'node-Start', 'node-Branch'),
        _edge('edge-branch-return', 'node-Branch', 'node-Return', '退回模式'),
        _edge('edge-branch-fallback', 'node-Branch', 'node-Fallback', '改派角色模式'),
        _edge('edge-return-approve', 'node-Return', 'node-EndReturn', '核准（不會被走到）'),
        _edge('edge-fallback-approve', 'node-Fallback', 'node-EndFallback', '核准'),
    ]
    return _graph(nodes, edges)


NT19_NOASSIGNEE_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'FormAdapter 解析簽核者時不保證一定找得到人——DYNAMIC 變數可能是空的、'
    ' USER 指定的可能是空字串、角色底下可能沒有可用的持有者。'
    ' no_assignee_action 決定「找不到簽核人時」怎麼辦，這是 FormAdapter 的'
    ' fail-safe 機制。\n\n'
    '【本流程的設定重點】\n'
    '本流程用 Branch 依表單欄位 no_assignee_mode 分流到兩個節點，兩個節點都'
    '刻意讓 assignee_type=\'DYNAMIC\' 指向一個從頭到尾都沒有被設值的流程變數'
    '（保證解析結果一定是空清單），藉此對照 no_assignee_action 的兩種行為：\n'
    '- no_assignee_action=\'return\'（預設值）：找不到簽核人時，直接把案件'
    '結束、記為 REJECTED，簽核者顯示「系統（找不到簽核人）」，流程不會走到'
    ' End 節點——因為在還沒進入等待簽核狀態之前就已經結束了。這是最安全的'
    '預設：沒人可簽的案件不會無限期卡住，會退回讓申請人知道要重送或找人'
    '補位。\n'
    '- no_assignee_action=\'fallback_role\'：找不到簽核人時，改派給'
    ' no_assignee_role_secure_code 指定的角色（本示範指定 ORG_ADMIN）。流程'
    '正常進入等待簽核狀態，等該角色的持有者簽核。即使改派的角色當下也沒有'
    '人持有，也只是停在等待中（管理員之後補人即可簽），不會像 return 模式'
    '一樣直接判死。\n'
    '- 兩個節點都設了 decision_options，但 return 模式的那組實際上永遠不會'
    '被用到——它在到達決策階段前就已經結束了；設定它只是為了讓圖保持結構'
    '完整（FormAdapter 節點沒有出線會直接回 error）。\n\n'
    '【怎麼看結果】\n'
    '送單時 no_assignee_mode 填 \'return\'：流程立刻以 REJECTED 結束，查'
    ' fw_approval_records 會看到一筆 action=\'no_assignee\'、簽核者是「系統'
    '（找不到簽核人）」。另外送一次 no_assignee_mode 填 \'fallback_role\'：'
    '流程進入等待簽核，待簽任務出現在 ORG_ADMIN 持有者的待辦，用 ORG_ADMIN'
    '簽核後流程正常走到 End，查 fw_workflow_variables 的'
    ' nt19_noassignee_fallback_decision 應為 approved。'
)

FORM_NOASSIGNEE_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-19 FormAdapter 示範表單（找不到簽核人時）'),
        _hint('填 no_assignee_mode = \'return\'：流程會立刻結束並標記已退回'
              '（因為刻意讓簽核者解析不到人）。填 \'fallback_role\'：流程會改派給'
              ' ORG_ADMIN 繼續等待簽核。'),
        _text('no_assignee_mode', 'no_assignee_mode（填 return 或 fallback_role）',
              '本示範刻意讓簽核者解析永遠是空的，這個欄位只決定要示範'
              ' no_assignee_action 的哪一種行為。'),
        _submit_button(),
    ],
}


FULL_DEMOS_STATIC = [
    {
        'form_code': 'NODEDEMO_NT19_INITIATOR_FORM',
        'form_name': 'NT-19 FormAdapter 示範表單（發起人自簽）',
        'form_schema': FORM_INITIATOR_SCHEMA,
        'workflow_code': 'NODEDEMO_NT19_INITIATOR_FLOW',
        'workflow_name': 'NT-19 FormAdapter 示範（發起人自簽）',
        'description': NT19_INITIATOR_DESCRIPTION,
        'graph': lambda ctx: build_initiator_graph(),
    },
]


def build_full_demos(ctx):
    demos = list(FULL_DEMOS_STATIC)
    demos.append({
        'form_code': 'NODEDEMO_NT19_USER_FORM',
        'form_name': 'NT-19 FormAdapter 示範表單（指定人員）',
        'form_schema': FORM_USER_SCHEMA,
        'workflow_code': 'NODEDEMO_NT19_USER_FLOW',
        'workflow_name': 'NT-19 FormAdapter 示範（指定人員）',
        'description': NT19_USER_DESCRIPTION,
        'graph': lambda c: build_user_graph(c['demo_manager_sc']),
    })
    demos.append({
        'form_code': 'NODEDEMO_NT19_ROLEUNIT_FORM',
        'form_name': 'NT-19 FormAdapter 示範表單（角色＠單位）',
        'form_schema': FORM_ROLEUNIT_SCHEMA,
        'workflow_code': 'NODEDEMO_NT19_ROLEUNIT_FLOW',
        'workflow_name': 'NT-19 FormAdapter 示範（角色＠單位）',
        'description': NT19_ROLEUNIT_DESCRIPTION,
        'graph': lambda c: build_role_unit_graph(c['dept_manager_role_sc']),
    })
    demos.append({
        'form_code': 'NODEDEMO_NT19_NOASSIGNEE_FORM',
        'form_name': 'NT-19 FormAdapter 示範表單（找不到簽核人時）',
        'form_schema': FORM_NOASSIGNEE_SCHEMA,
        'workflow_code': 'NODEDEMO_NT19_NOASSIGNEE_FLOW',
        'workflow_name': 'NT-19 FormAdapter 示範（找不到簽核人時）',
        'description': NT19_NOASSIGNEE_DESCRIPTION,
        'graph': lambda c: build_noassignee_graph(c['org_admin_role_sc']),
    })
    result = []
    for d in demos:
        graph_fn = d['graph']
        d = dict(d)
        d['graph'] = (lambda fn=graph_fn: (lambda: fn(ctx)))()
        result.append(d)
    return result


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
            created_by_name='provision_nodedemo_approval_assignee',
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
        description='佈建 node展覽館的 FormAdapter 簽核者示範（B5a：assignee_type 解析）')
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
        from app.models.role import Role
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

        demo_manager = User.query.filter_by(
            org_secure_code=osc, email=DEMO_MANAGER_EMAIL, is_deleted=False).first()
        if not demo_manager:
            log(f'找不到示範帳號：{DEMO_MANAGER_EMAIL}（B0 應已建立，請確認）')
            return 1
        dept_manager_role = Role.query.filter_by(
            org_secure_code=osc, code='DEPT_MANAGER', is_deleted=False, is_active=True).first()
        if not dept_manager_role:
            log('找不到角色 DEPT_MANAGER（系統企業，B0 部門結構應已建立此角色）')
            return 1
        org_admin_role = Role.query.filter_by(
            org_secure_code=osc, code='ORG_ADMIN', is_deleted=False, is_active=True).first()
        if not org_admin_role:
            log('找不到角色 ORG_ADMIN（系統企業出廠角色，理論上必存在）')
            return 1

        ctx = {
            'demo_manager_sc': demo_manager.secure_code,
            'dept_manager_role_sc': dept_manager_role.secure_code,
            'org_admin_role_sc': org_admin_role.secure_code,
        }
        log(f'  demo-manager secure_code = {ctx["demo_manager_sc"]}')
        log(f'  DEPT_MANAGER role secure_code = {ctx["dept_manager_role_sc"]}'
            f'（role_type={dept_manager_role.role_type}）')
        log(f'  ORG_ADMIN role secure_code = {ctx["org_admin_role_sc"]}')

        publisher = User.query.filter_by(
            org_secure_code=osc, user_type='ORG_ADMIN',
            is_deleted=False, is_active=True).first()

        full_demos = build_full_demos(ctx)

        log('\n=== FormAdapter 簽核者示範（表單／流程／配對／發行） ===')
        full_results = {}
        for demo in full_demos:
            log(f"\n--- {demo['workflow_name']} ---")
            full_results[demo['workflow_code']] = apply_full_demo(
                db, models, org, demo, publisher, args.apply)

        if args.apply:
            db.session.commit()
            log('\n已寫入。到 /forms/center 的「填寫表單」就看得到這四張單。')
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
