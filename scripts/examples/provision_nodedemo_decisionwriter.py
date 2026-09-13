#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PF-252 B14 批次：node展覽館 —— DecisionWriter（NT-23）示範（寫入防禦決策）。

本檔佈建一個流程：核准後把使用者填的 IP 寫成一筆防禦決策（block），
示範這個節點怎麼把「一個 IP」變成「一筆能被外部執行端拉走的封鎖決策」，
以及兩個最容易出事的地方：

    1) decided_via 的自動推斷（_infer_decided_via()）是看
       workflow_instance.last_completed_node_type 是否為 FormAdapter，
       在並行分支下不可靠（後完成的節點蓋過真正做決策的那個）。
       本示範一律在節點 config 明寫 decided_via='human'，不依賴推斷。

    2) target_value 經 replace_variables() 之後如果是空字串，
       DecisionWriter 會直接回 error（見 decision_writer_handler.py:44-51）。
       所以本流程在 DecisionWriter 之前放一個 Branch，先判斷
       ${f.target_ip} 是否為空：有值才走 DecisionWriter，留空則走另一條
       只寫說明文字的路徑，讓流程照樣正常結束，不會卡住。

阻擋目標一律使用 123.123.0.0/16 這個 Ethan 指定的安全測試網段
（不是 RFC1918 私有網段、不是 TEST-NET、不在任何內建/設定保護清單內），
不會誤傷任何真實或內網位址。

反向測試（保護清單命中）刻意不透過完整流程送單：DecisionWriter 遇到
ProtectedTargetError 時，若 on_protected（本流程沒有設，預設 'error'）
不是 'skip'，節點會回傳一般的 status='error'，這會讓 queue_item 進入
傳統二元制的 fail() 重試（3 次後 FAILED），流程實例會停在 RUNNING
不會結束——這與「流程必須真的跑完才算完成」的硬性要求衝突。改用
標準測試手法：在系統企業的封鎖保護清單暫時新增一筆 custom 項目
（範圍限定在 123.123.99.0/24，仍在 Ethan 指定的安全測試網段內），
直接呼叫 decision_writer 底層真正呼叫的
modules.open_defense.services.decision_service.create_decision()，
確認 123.123.99.50 這個落在該保護網段內的目標會被 ProtectedTargetError
擋下、資料庫完全不寫入任何決策，測完立刻刪除這筆暫時的保護清單項目。
這與流程節點呼叫的是同一支函式，驗證的是同一套判定邏輯。

目標企業固定是系統預設企業（Organization.code='SYSTEM'），分類固定是
「node展覽館」。。
DecisionWriter 不是受限節點（org_restricted=false），不需要企業授權，
但需要 open_defense 模組已載入（handler 內部 import
modules.open_defense.services.decision_service）。

冪等：重跑會沿用既有表單／流程（依 code 找），bump revision 並重新發行
（會停用舊的已發行版本並建立新版）。填寫權限授予企業內所有非 EXTERNAL
的在職帳號。

用法：
    cd <repo>
    set -a && source .env && set +a
    venv/bin/python scripts/examples/provision_nodedemo_decisionwriter.py --dry-run
    venv/bin/python scripts/examples/provision_nodedemo_decisionwriter.py --apply

節點 config 欄位依 handler 原始碼確認：
    modules/form_workflow/services/node_handlers/decision_writer_handler.py
    modules/form_workflow/services/node_handlers/formadapter_handler.py（見 fc_pending.py::approve_task()）
    modules/form_workflow/services/node_handlers/branch_handler.py
    modules/form_workflow/services/node_handlers/fieldwrite_handler.py
    modules/open_defense/services/decision_service.py
    modules/open_defense/services/protected_target_service.py
    modules/open_defense/models/defense_decision.py（VALID_ACTIONS／VALID_TARGET_TYPES／VALID_SEVERITIES）
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

# 安全測試網段（Ethan 指定）：阻擋目標一律落在這個範圍，不用任何真實或內網 IP。
SAFE_TEST_RANGE_NOTE = '123.123.0.0/16（Ethan 指定的安全測試網段，非真實或內網位址）'
DEFAULT_TARGET_IP = '123.123.45.67'
# 反向測試用的自訂保護清單網段（同樣落在安全測試網段內，測完即刪除）。
REVERSE_TEST_PROTECTED_CIDR = '123.123.99.0/24'
REVERSE_TEST_TARGET_IP = '123.123.99.50'

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


def _text(key, label, description='', default_value=None):
    comp = {'key': key, 'type': 'textfield', 'input': True, 'label': label, 'tableView': True}
    if description:
        comp['description'] = description
    if default_value is not None:
        comp['defaultValue'] = default_value
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


def _decision_config(output_variable, options):
    """自訂決策的簽核設定：assignee_type=INITIATOR，一個人就能走完全程。

    options: [{id, label, value, style, target_edge}, ...]
    """
    return {
        'assignee_type': 'INITIATOR',
        'selection_mode': 'single',
        'output_variable': output_variable,
        'allow_comment': True, 'require_comment': False,
        'use_custom_decisions': True, 'input_variables': [],
        'decision_options': [
            {'id': o['id'], 'label': o['label'], 'value': o['value'],
             'style': o['style'], 'target_edges': [o['target_edge']]}
            for o in options
        ],
    }


# ---------------------------------------------------------------------------
# 流程：NT-23 DecisionWriter 示範（寫入防禦決策）
# ---------------------------------------------------------------------------

def build_decisionwriter_graph():
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 100, 220,
              '流程入口，不需要任何前置設定。'),

        _node('node-Approve', 'FormAdapter', '核准是否阻擋',
              _decision_config('block_decision', [
                  {'id': 'opt-approve', 'label': '核准，執行阻擋', 'value': 'approved',
                   'style': 'danger', 'target_edge': 'edge-approve-branch'},
                  {'id': 'opt-reject', 'label': '駁回，不執行任何處置', 'value': 'rejected',
                   'style': 'default', 'target_edge': 'edge-reject-end'},
              ]),
              360, 120,
              '簽核者固定是發起人自己（assignee_type=INITIATOR），代表'
              '「核准這筆封鎖」的把關動作——正式資安流程通常會換成資安人員'
              '或主管角色（參考 scripts/examples/od_workflow_graphs.py 的'
              '一線／二線簽核）。核准才會進入下一步的空值防呆判斷；'
              '駁回直接收尾，DecisionWriter 完全不會被呼叫，'
              ' od_defense_decisions 不會新增任何記錄。'),

        _node('node-Branch-empty', 'Branch', '目標是否留空',
              {
                  'rules': [
                      {
                          'name': '有填目標，才走封鎖',
                          'conditions': [{'variable': '${f.target_ip}', 'operator': 'not_empty',
                                          'value': '', 'logic': 'AND'}],
                          'target_edges': ['edge-hasvalue-decision'],
                      },
                      {
                          'name': '留空，跳過封鎖',
                          'conditions': [{'variable': '${f.target_ip}', 'operator': 'empty',
                                          'value': '', 'logic': 'AND'}],
                          'target_edges': ['edge-empty-skip'],
                      },
                  ],
                  'fallback': {
                      'action': 'route',
                      'target_edge': 'edge-empty-skip',
                      'log_message': '無法判定 target_ip 是否為空，保守地不寫入封鎖決策',
                  },
              },
              620, 120,
              'DecisionWriter 的 target_value 經變數替換後若為空字串會直接'
              '回 error（節點失敗、進入 3 次自動重試），流程可能因此卡住。'
              '這個 Branch 是自動封鎖前的必要防呆：只有 target_ip 真的有值'
              '才會走到 DecisionWriter，留空的案件改走右下角只寫說明文字'
              '的路徑，流程照樣正常結束。兩條規則互斥（not_empty／empty'
              '正好覆蓋所有情況），fallback 保守地一律導向「跳過」，不會'
              '誤觸發封鎖。'),

        _node('node-Decision', 'DecisionWriter', '寫入封鎖決策', {
            'action': 'block',
            'target_type': 'ip',
            'target_value': '${f.target_ip}',
            'severity': 'high',
            'ttl_seconds': 3600,
            'decided_via': 'human',
            'enforcement_points': ['nftables', 'edl'],
            'reason_template':
                '[node展覽館示範] NT-23 送單 ${wi.exec_code} 核准阻擋 ${f.target_ip}'
                '（示範用途，測試網段 123.123.0.0/16）',
        }, 900, 40,
            'decided_via 明確標 human，不依賴「看上一個完成節點是不是'
            ' FormAdapter」的自動推斷——並行分支下最後完成的節點可能不是'
            '真正做決策的那個，推斷會失準。action=block／target_type=ip'
            '／severity=high／ttl_seconds=3600（1 小時後過期，'
            ' expires_at 由 handler 自動算好）。enforcement_points 列了'
            ' nftables 與 edl 兩個執行點：外部執行端各自依這個清單篩選'
            '要不要拉走這筆決策；本示範特別加 edl 是因為平台端 EDL 黑名單'
            '（modules/open_defense/services/edl_service.py）只看'
            '「該企業所有有效 block」不看 enforcement_points，而 .20 的'
            ' od-bridge 執行端只收標了 edl 的決策——兩份清單本來就不同，'
            '不是同步失敗。reason_template 帶 [node展覽館示範] 標記，'
            '方便事後從 od_defense_decisions 表辨識並清理。'),

        _node('node-Write-ok', 'OpFieldWrite', '寫回封鎖結果', {
            'target_field': 'decision_result',
            'content': (
                '[已寫入封鎖決策]\n'
                '目標：${f.target_ip}\n'
                '決策 secure_code：DecisionWriter 不寫流程變數，只能查'
                ' fw_node_execution_logs.log_data 或 od_defense_decisions 表。\n'
                '嚴重度：high，TTL：3600 秒（1 小時後過期）\n'
                '執行點：nftables, edl\n'
                '流程執行代碼：${wi.exec_code}\n\n'
                '這筆決策已寫進 od_defense_decisions 表，外部執行端（nftables／'
                ' EDL）會依 enforcement_points 篩選後拉走實施；平台端 EDL 黑名單'
                '每分鐘由 scripts/cron/od_render_edl.py 重新渲染一次。'
            ),
        }, 1180, 40,
            '把封鎖結果的重點欄位寫回表單，方便送單者不必再去查資料庫就能'
            '確認這次到底寫了什麼。DecisionWriter 本身不寫任何流程變數'
            '給後續節點用（見權威對照表），只有 data 欄位，所以這裡改用'
            ' OpFieldWrite 直接把說明文字寫回表單。'),

        _node('node-Write-skip', 'OpFieldWrite', '寫回跳過原因', {
            'target_field': 'decision_result',
            'content': (
                '[已跳過，未寫入任何封鎖決策]\n'
                '原因：target_ip 欄位留空。\n'
                '這是 Branch 防呆生效的證明——如果沒有這個 Branch，'
                ' DecisionWriter 會因為 target_value 替換後為空而回 error，'
                '流程會卡在這個節點反覆重試。改走這條路徑後流程照樣正常'
                '結束，沒有任何決策記錄被寫入。\n'
                '流程執行代碼：${wi.exec_code}'
            ),
        }, 900, 260,
            '示範「防呆生效」時使用者實際看到的畫面：清楚說明為什麼沒有'
            '執行封鎖，而不是讓流程默默卡住或報一個看不懂的錯誤。'),

        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 1440, 150,
              '流程正常結束（finish_mode=detach）。不論走哪一條路徑'
              '（核准且有值／核准但留空／駁回）最後都會走到這裡，'
              '流程實例的 status 都會是 COMPLETED。'),
    ]
    edges = [
        _edge('edge-start-approve', 'node-Start', 'node-Approve'),
        _edge('edge-approve-branch', 'node-Approve', 'node-Branch-empty', label='核准'),
        _edge('edge-reject-end', 'node-Approve', 'node-End', label='駁回'),
        _edge('edge-hasvalue-decision', 'node-Branch-empty', 'node-Decision', label='有填目標'),
        _edge('edge-empty-skip', 'node-Branch-empty', 'node-Write-skip', label='留空'),
        _edge('edge-decision-write', 'node-Decision', 'node-Write-ok'),
        _edge('edge-write-ok-end', 'node-Write-ok', 'node-End'),
        _edge('edge-write-skip-end', 'node-Write-skip', 'node-End'),
    ]
    return _graph(nodes, edges)


NT23_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'DecisionWriter 把「一個處置決定」寫成一筆 OdDefenseDecision 記錄'
    '（od_defense_decisions 表）。這是平台端的通用防禦決策廣播機制'
    '（開源、廠牌中性版的「寫 PA/CrowdSec/Cloudflare 黑名單」）：外部'
    '執行端（nftables、CrowdSec、Cloudflare 等）各自依 enforcement_points'
    '篩選後拉走這筆決策去實施，DecisionWriter 本身不直接連任何防火牆。\n\n'
    '【本流程的設定重點】\n'
    '- **action＝block／target_type＝ip**：合法值清單不在 handler 裡，'
    '在 modules/open_defense/models/defense_decision.py 的'
    ' VALID_ACTIONS=(block, unblock, allow, escalate, observe) 與'
    ' VALID_TARGET_TYPES=(ip, ipv6, cidr, domain, url, asn, country,'
    ' user_agent, jwt_sub)，實際驗證在 decision_service.py::_validate()。'
    'handler 自己只檢查 action／target_type 是否為空字串，不合法的值'
    '會在呼叫 decision_service 時才被擋下（一樣是 error，只是拒絕點'
    '在下一層）。\n'
    '- **target_value＝${f.target_ip}**：一律引用表單欄位，不寫死。'
    '本示範的預設值與允許範圍是 123.123.0.0/16（Ethan 指定的安全測試'
    '網段），不是任何真實或內網位址。\n'
    '- **decided_via 明確標 human，不依賴自動推斷**：不填這個欄位時'
    ' handler 會用 _infer_decided_via() 猜——看'
    ' workflow_instance.last_completed_node_type 是不是 FormAdapter，'
    '是就猜 human，否則猜 auto。這個推斷在並行分支下不可靠：如果'
    ' DecisionWriter 跟另一條分支的節點並行執行，「最後完成的節點」'
    '不一定是真正做出這個決策的那個 FormAdapter，猜出來的 decided_via'
    '可能完全是錯的。**只要這個節點在流程裡有任何可能與別的分支並行，'
    '一律在 config 明寫 human 或 auto，不要賭自動推斷猜得準。**\n'
    '- **severity＝high／ttl_seconds＝3600**：severity 只是分級標記'
    '（VALID_SEVERITIES=info/low/medium/high/critical），不影響是否'
    '寫入成功；ttl_seconds 決定 expires_at（此例 1 小時後過期），留空'
    '（或 <=0）代表永久，過期後只影響「平台端 EDL 黑名單」還收不收這筆'
    '（依 expires_at 判斷，不看 status）。\n'
    '- **enforcement_points＝[nftables, edl]**：這不是「真的去設定'
    ' nftables／EDL」，只是給外部執行端篩選用的標籤。留空的話任何執行端'
    '都不會主動拉走這筆決策（除了平台端 EDL 黑名單——它刻意看「該企業'
    '所有有效 block」不看這個欄位）。\n'
    '- **target_value 替換後為空會讓節點回 error，流程可能卡住**：本流程'
    '在 DecisionWriter 前面放了一個 Branch，先判斷 ${f.target_ip} 是否'
    '為空——有值才進 DecisionWriter，留空改走另一條只寫說明文字的路徑。'
    '這是任何「會自動封鎖」的流程都該有的防呆，不要指望 DecisionWriter'
    '自己會優雅地處理空值（它只會回 error，讓 queue_item 進入 3 次'
    '自動重試，重試完仍是 FAILED，而流程實例會停在 RUNNING 不會結束）。\n'
    '- **命中封鎖保護清單會被拒絕寫入**：action=block 且'
    ' target_type 屬 ip／ipv6／cidr 時，create_decision() 會先查'
    '「封鎖保護清單」（企業出廠 16 筆內建網段 ∪ 平台設定 ∪ 企業自訂），'
    '命中就丟 ProtectedTargetError，除非節點 config 設'
    ' allow_protected_target=true（會在 decision_metadata 留稽核痕跡）'
    '或 on_protected=skip（視為成功但不寫入）。本示範沒有設定這兩個'
    '欄位，所以命中保護清單就是預設行為：拒絕寫入、節點回 error。\n\n'
    '【怎麼看結果】\n'
    '1) 回填的表單欄位 decision_result（由 OpFieldWrite 寫入）能看到'
    '這次到底寫了封鎖決策還是跳過了。\n'
    '2) 查資料庫：SELECT secure_code, action, target_type, target_value,'
    ' severity, ttl_seconds, expires_at, decided_via, status,'
    ' enforcement_points, reason FROM od_defense_decisions WHERE'
    " reason LIKE '%node展覽館示範%' ORDER BY id DESC;\n"
    '3) 到「資安案件處置中心」（/open-defense/security-cases，需'
    ' SECURITY_STAFF 或 SOC_SUPERVISOR 等資安角色）——但本示範走的是'
    ' node展覽館專屬分類，不是 CAT_SECURITY_ 開頭的案件分類，所以'
    '**不會**出現在處置中心的案件清單裡，這是刻意的區隔（避免示範資料'
    '混進真實資安案件），只能透過上面的 SQL 或流程管理頁查看。\n'
    '4) EDL 黑名單：若這筆決策仍在有效期內（ttl_seconds 未過期）且'
    '狀態允許，下一次手動或排程執行'
    ' scripts/cron/od_render_edl.py 會把它渲染進'
    ' /srv/beakshare/edl/系統預設企業網域/blocklist.txt（.env 的'
    ' OD_EDL_OUTPUT_DIR）。這份黑名單收的是「該企業所有有效 block」，'
    '不看 enforcement_points 有沒有列 edl。'
)

FORM_DECISIONWRITER_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-23 DecisionWriter 示範表單（寫入防禦決策）'),
        _hint('送出後先經過一個自簽的核准關卡，核准後由 Branch 判斷下面的'
              '目標 IP 是否留空：有填才會呼叫 DecisionWriter 寫入封鎖決策，'
              '留空則安全地跳過並說明原因，流程都會正常結束。阻擋目標一律'
              '使用 123.123.0.0/16（Ethan 指定的安全測試網段），不會是'
              '任何真實或內網位址。'),
        _text('target_ip', '要阻擋的來源 IP（target_value）',
              '預設值落在安全測試網段 123.123.0.0/16。若想示範「留空時的'
              '防呆路徑」，送單前把這欄清空即可——流程不會卡住，只會'
              '改走「跳過」路徑並在下方欄位說明原因。',
              default_value=DEFAULT_TARGET_IP),
        _textarea('decision_result', '處置結果（由流程自動填寫）',
                   '由流程的 OpFieldWrite 節點自動寫入，送單者不需輸入。',
                   rows=8, disabled=True),
        _submit_button(),
    ],
}


FULL_DEMOS_STATIC = [
    {
        'form_code': 'NODEDEMO_NT23_DECISIONWRITER_FORM',
        'form_name': 'NT-23 DecisionWriter 示範表單（寫入防禦決策）',
        'form_schema': FORM_DECISIONWRITER_SCHEMA,
        'workflow_code': 'NODEDEMO_NT23_DECISIONWRITER_FLOW',
        'workflow_name': 'NT-23 DecisionWriter 示範（寫入防禦決策）',
        'description': NT23_DESCRIPTION,
        'graph': lambda: build_decisionwriter_graph(),
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
            created_by_name='provision_nodedemo_decisionwriter',
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
    for demo in FULL_DEMOS_STATIC:
        log(f"\n--- {demo['workflow_name']} ---")
        results[demo['workflow_code']] = apply_full_demo(
            db, models, org, demo, publisher, apply)
    return {'results': results, 'category_secure_code': SHOWCASE_CATEGORY_SECURE_CODE}

def main():
    parser = argparse.ArgumentParser(description='佈建 node展覽館的 DecisionWriter 示範（B14）')
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
            log('\n已寫入。到 /forms/center 的「填寫表單」就看得到這些單。')
            log('\n完整示範：')
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
