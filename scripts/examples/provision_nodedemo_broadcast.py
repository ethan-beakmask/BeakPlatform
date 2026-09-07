#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PF-252 B10 批次：node展覽館 —— AlertBroadcast（NT-24）／NavbarBroadcast（NT-26）示範。

本檔佈建兩個流程：

    NT-24 AlertBroadcast 示範（緊急廣播）
        流程觸發一則全頁強制彈窗廣播（緊急廣播）。刻意在 broadcast_code 裡
        塞一段 ${wi.exec_code}，藉此證明 broadcast_code **不做變數替換**——
        同一個節點的 title／message 會把 ${...} 換成實際值，broadcast_code
        卻原樣保留字面字串。同一 code 重複發動會覆蓋前一則廣播並清除所有人
        的已讀確認，所以它是「最新一則橫幅」不是逐案通知，不能拿來當稽核。

    NT-26 NavbarBroadcast 示範（跑馬燈廣播）
        流程觸發導覽列跑馬燈，並在同一個流程裡示範 mode=start 與 mode=end
        兩種模式：先啟動跑馬燈、等待一段時間讓人看得到，再呼叫 mode=end
        主動關閉；同時設定 duration_minutes 當作保底自動過期，示範「主動
        關閉」與「到期自動失效」兩種收尾方式並存時的實際行為。

兩者的定位差異（描述裡會寫給讀者看）：AlertBroadcast 是全頁強制、必須勾選
才能關閉的高干擾通知，適合「所有人都必須知道且必須確認」的場景；
NavbarBroadcast 是低干擾的背景提示，適合「大家看到就好、不需要停下手邊
工作」的場景。

目標企業固定是系統預設企業（Organization.code='SYSTEM'），分類固定是「node展覽館」
（fw_categories.secure_code='J1ygL6zexauKlLM0_Ktoaw'）。兩個節點都不是受限節點
（org_restricted=false），不需要企業授權、不需要 grant。

**注意（Ethan 派工要求）**：這兩個節點觸發的廣播會影響系統企業所有使用者的畫面。
- 內容一律以「[node展覽館示範]」開頭標示，避免被誤認為真的警報
- NavbarBroadcast 設 duration_minutes=5（短效期，自動失效）
- AlertBroadcast 沒有內建的有效期限欄位，需要手動 SQL 清除
  （UPDATE lookup_items SET is_active=false WHERE org_secure_code=<SYSTEM sc>
  AND category_code='broadcast' AND code LIKE 'NODEDEMO_ALERT_SAMPLE%'），
  詳見回報內文的「清理方式」段落

冪等：重跑會沿用既有表單／流程（依 code 找），bump revision 並重新發行（會停用
舊的已發行版本並建立新版）。填寫權限授予企業內所有非 EXTERNAL 的在職帳號。

用法：
    cd /opt/BeakPlatform-dev
    set -a && source .env && set +a
    venv/bin/python scripts/examples/provision_nodedemo_broadcast.py --dry-run
    venv/bin/python scripts/examples/provision_nodedemo_broadcast.py --apply

節點 config 欄位依 handler 原始碼確認：
    modules/form_workflow/services/node_handlers/alert_broadcast_handler.py
    modules/form_workflow/services/node_handlers/navbar_broadcast_handler.py
    modules/form_workflow/services/node_handlers/delay_handler.py
    modules/form_workflow/services/node_handlers/fieldwrite_handler.py
    modules/form_workflow/services/node_handlers/formadapter_handler.py
權威對照表：/opt/tmp/verify/20260907-node-config-reference.md
前端顯示：backend/app/static/js/broadcast-poller.js、backend/app/api/broadcasts.py
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


# ---------------------------------------------------------------------------
# 流程一：NT-24 AlertBroadcast 示範（緊急廣播）
# ---------------------------------------------------------------------------

# 刻意在 broadcast_code 裡放一段 ${wi.exec_code}：如果 handler 對 broadcast_code
# 做變數替換，這裡應該會變成實際的流程執行代碼（如 WF-20260907-0007）；
# 但 alert_broadcast_handler.py 只對 title／message 呼叫 replace_variables()，
# broadcast_code 原封不動，所以 lookup_items.code 最終會「原樣保留」這串字面文字。
ALERT_BROADCAST_CODE = 'NODEDEMO_ALERT_SAMPLE_${wi.exec_code}'


def build_alert_graph():
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 100, 200,
              '流程入口，不需要任何前置設定。'),

        _node('node-Alert', 'AlertBroadcast', '觸發緊急廣播', {
            'broadcast_code': ALERT_BROADCAST_CODE,
            'title': '${f.alert_headline}',
            'message': '${f.alert_body}',
            'require_ack': True,
            'target_type': 'all',
        }, 380, 200,
            '對系統企業所有使用者觸發一則全頁強制彈窗，必須捲到底並勾選'
            '「已知道」才能關閉。broadcast_code 刻意寫成'
            ' "NODEDEMO_ALERT_SAMPLE_${wi.exec_code}"——這段 ${...} 不會被'
            '替換，會原樣寫進 lookup_items.code；title／message 則會正常'
            '替換成表單內容。同一個 broadcast_code 重複發動會覆蓋前一則'
            '廣播並清除所有人的已讀確認，所以它代表「目前這一則」而不是'
            '逐案累積的通知記錄。'),

        _node('node-Write', 'OpFieldWrite', '寫回觸發結果', {
            'target_field': 'alert_result_display',
            'content': (
                '[緊急廣播已觸發]\n'
                '這個節點自己的 content 也用了流程執行代碼變數，這裡會被'
                '正常替換成本次流程執行代碼：${wi.exec_code}\n'
                '而 AlertBroadcast 節點的 broadcast_code 用了同一種變數'
                '語法接在 NODEDEMO_ALERT_SAMPLE_ 後面，但那個欄位不會被'
                '替換——資料庫裡存的 code 是連同變數語法本身一起、原封不動'
                '寫入（本節點的 content 沒辦法直接示範這點，因為只要在'
                ' content 裡再寫一次同樣的語法，一樣會被替換掉；要看'
                '「原封不動」的實際樣子，請直接查下方的 SQL）。\n\n'
                '請切換到任一頁面，應該會立刻跳出全頁強制彈窗（如果沒有'
                '立刻跳出，等前端下一次 polling 週期，預設最長 1 分鐘），'
                '捲到底、勾選「我已閱讀並知悉以上訊息」後按「已知道」才能'
                '關閉。'
            ),
        }, 660, 200,
            '把本次流程執行代碼寫回表單欄位，同時對照展示「同一個'
            ' ${wi.exec_code} 在 OpFieldWrite 裡會被替換，在 AlertBroadcast'
            ' 的 broadcast_code 裡不會」。'),

        _node('node-Review', 'FormAdapter', '確認已看到緊急廣播',
              _approve_config('ack', '確認已看到緊急廣播彈窗，結束流程', 'edge-approve-end'),
              940, 200,
              '簽核者固定是發起人自己（assignee_type=INITIATOR），純粹作為'
              '流程收尾的關卡，方便一個帳號就能走完全程。'),

        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 1220, 200,
              '流程正常結束（finish_mode=detach）。'),
    ]
    edges = [
        _edge('edge-start-alert', 'node-Start', 'node-Alert'),
        _edge('edge-alert-write', 'node-Alert', 'node-Write'),
        _edge('edge-write-review', 'node-Write', 'node-Review'),
        _edge('edge-approve-end', 'node-Review', 'node-End', label='確認'),
    ]
    return _graph(nodes, edges)


NT24_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'AlertBroadcast 觸發全企業（或指定角色／部門）的全頁強制彈窗，使用者'
    '必須捲到底並勾選「我已閱讀並知悉以上訊息」才能關閉。前端每隔一段'
    '時間（預設最長 1 分鐘，`window.__BROADCAST_POLL_INTERVAL`）輪詢'
    '`/api/broadcasts/active`，一旦查到屬於自己的未確認廣播就立即彈出，'
    '不需要重新整理頁面或重新登入。這是全平台干擾程度最高的通知方式，'
    '設計上就是給「所有人都必須知道、也必須明確表示知道」的場景用的。\n\n'
    '【本流程的設定重點】\n'
    '- broadcast_code 刻意設成 "NODEDEMO_ALERT_SAMPLE_${wi.exec_code}"，'
    '這是本流程的核心示範：這段 ${...} **不會**被替換，寫進資料庫'
    '（lookup_items.code）的就是含有字面 ${wi.exec_code} 的原始字串，'
    '可以直接查 DB 對照。同一個節點的 title／message 卻**會**被替換——'
    '兩者處理方式不同，是因為 handler（alert_broadcast_handler.py）只對'
    ' title／message 呼叫 replace_variables()，broadcast_code 純粹當成'
    '識別碼原樣使用，設計上就不打算讓它變動。\n'
    '- title／message 分別填 ${f.alert_headline}／${f.alert_body}，示範'
    '把表單內容直接餵給廣播文字，讓送單者能自訂看到的內容。\n'
    '- require_ack=true（也是預設值）：必須捲到底＋勾選才能關閉；設成'
    ' false 的話彈窗只有一個「關閉」按鈕，可以直接點掉不必捲動確認——'
    '差別在於「知會」與「強制確認已讀」之間的取捨。\n'
    '- target_type=all：全企業都會看到。如果只想通知特定角色或部門，'
    '改成 specific 並填 target_roles／target_departments。\n'
    '- **同一個 broadcast_code 重複發動，會覆蓋前一則廣播內容，並清除'
    '所有人針對這個 code 的已讀確認記錄**——也就是說重新送單一次，'
    '即使上次已經確認過的人，這次也要重新確認一次。這代表 AlertBroadcast'
    '代表的是「目前生效的這一則」，不是逐案累積的通知歷史，不能拿它來做'
    '逐案稽核（要逐案留痕請用 EmailAdapter／Telegram 之類會各自留下獨立'
    '記錄的通知節點）。\n\n'
    '【怎麼看結果】\n'
    '送單後回到平台任一頁面（不限表單中心），最長等 1 分鐘（前端輪詢'
    '週期）就會跳出全頁強制彈窗。彈窗內容是表單裡填的標題與內容。'
    '關閉後可以到「填寫表單」重新打開這張單看 alert_result_display'
    '欄位，裡面同時顯示本次執行代碼（已替換）與說明。要直接對照'
    ' broadcast_code 有沒有被替換，查：\n'
    "SELECT code, label FROM lookup_items WHERE category_code='broadcast' "
    "AND code LIKE 'NODEDEMO_ALERT_SAMPLE%';\n"
    '應該會看到 code 欄位原封不動含有字面的 "${wi.exec_code}"，而不是'
    '被替換成實際的執行代碼。\n\n'
    '【怎麼清掉這則廣播】\n'
    'AlertBroadcast 沒有內建的有效期限欄位，也沒有 UI／API 可以手動'
    '停用——「緊急廣播管理」頁面（/security/alert-broadcasts/）只能查看'
    '已讀名單，沒有停用按鈕。每個人各自勾選「已知道」關閉後，對那個人'
    '就不會再跳出；要讓它對所有人都消失，需要管理員直接執行：\n'
    "UPDATE lookup_items SET is_active=false WHERE category_code='broadcast' "
    "AND code LIKE 'NODEDEMO_ALERT_SAMPLE%';"
)

FORM_ALERT_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-24 AlertBroadcast 示範表單（緊急廣播）'),
        _hint('送出後流程會立即觸發一則全企業的緊急廣播（全頁強制彈窗），'
              '任何登入系統企業的使用者最長等 1 分鐘就會看到。內容已固定'
              '以「[node展覽館示範]」開頭，避免被誤認為真的系統公告。'),
        _text('alert_headline', '廣播標題',
              '這段文字會經過變數替換直接顯示在彈窗標題。'),
        _textarea('alert_body', '廣播內容',
                   '這段文字會經過變數替換直接顯示在彈窗內文。', rows=5),
        _textarea('alert_result_display', '觸發結果（由流程自動填入）',
                   '此欄位由 AlertBroadcast + OpFieldWrite 自動寫入。', rows=8),
        _submit_button(),
    ],
}
FORM_ALERT_SCHEMA['components'][2]['defaultValue'] = '[node展覽館示範] 系統維護通知'
FORM_ALERT_SCHEMA['components'][3]['defaultValue'] = (
    '各位同仁好，今晚 22:00-23:00 將進行系統維護，服務可能短暫中斷。\n'
    '（本廣播由 node展覽館 AlertBroadcast 示範流程觸發，僅供教學使用，'
    '非真實維護公告）'
)


# ---------------------------------------------------------------------------
# 流程二：NT-26 NavbarBroadcast 示範（跑馬燈廣播）
# ---------------------------------------------------------------------------

NAVBAR_BROADCAST_CODE = 'NODEDEMO_NAVBAR_SAMPLE'


def build_navbar_graph():
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 100, 200,
              '流程入口，不需要任何前置設定。'),

        _node('node-NavStart', 'NavbarBroadcast', '啟動跑馬燈', {
            'mode': 'start',
            'broadcast_code': NAVBAR_BROADCAST_CODE,
            'message': '${f.navbar_message}',
            'text_color': '#1f2937',
            'bg_color': '#DBEAFE',
            'display_seconds': 8,
            'duration_minutes': 5,
        }, 380, 200,
            '在導覽列（bk-topbar-fixed）與功能選單列（bk-menubar）之間插入'
            '一條跑馬燈，對系統企業所有使用者顯示。duration_minutes=5 是'
            '保底自動過期——即使下面的 mode=end 節點沒有執行（例如流程'
            '中途失敗），5 分鐘後前端下次查詢也會自動判定過期而不再顯示。'
            '顏色選了低對比的深灰字＋淺藍底，刻意跟 AlertBroadcast 的'
            '紅色強制彈窗做區隔——這是干擾程度最低的通知方式。'),

        _node('node-Delay', 'Delay', '讓跑馬燈先顯示一段時間', {
            'delay_seconds': 40,
        }, 660, 200,
            '純粹為了示範方便，讓跑馬燈先顯示 40 秒再走下一步的 mode=end。'
            '實際使用時不需要特別加這個 Delay，跑馬燈啟動後可以讓它跑到'
            ' duration_minutes 到期，或在需要的任何時間點另外接一個'
            ' mode=end 節點手動關閉。'),

        _node('node-NavEnd', 'NavbarBroadcast', '主動關閉跑馬燈', {
            'mode': 'end',
            'broadcast_code': NAVBAR_BROADCAST_CODE,
        }, 940, 200,
            '呼叫 mode=end 依 broadcast_code 主動關閉跑馬燈，不必等'
            ' duration_minutes 到期。示範「手動關閉」與「到期自動失效」'
            '兩種收尾方式可以並存——正常情況下手動關閉會先發生，'
            ' duration_minutes 只在沒人記得關閉時當保險。'),

        _node('node-Write', 'OpFieldWrite', '寫回觸發結果', {
            'target_field': 'navbar_result_display',
            'content': (
                '[跑馬燈廣播已觸發並自動結束]\n'
                '訊息內容：${f.navbar_message}\n'
                '流程已呼叫 mode=start 啟動、等待 40 秒後呼叫 mode=end'
                ' 主動關閉。即使 mode=end 沒有執行，duration_minutes=5'
                ' 也會在 5 分鐘後讓前端不再顯示這則跑馬燈。\n\n'
                '請在流程執行期間切換到平台任一頁面，應該會看到頂部'
                '導覽列與功能選單列之間出現一條淺藍底、深灰字的跑馬燈，'
                '約 40 秒後消失。'
            ),
        }, 1220, 200,
            '把觸發過程寫回表單欄位，方便事後回顧本次示範做了什麼。'),

        _node('node-Review', 'FormAdapter', '確認已看到跑馬燈廣播',
              _approve_config('ack', '確認已看到跑馬燈廣播，結束流程', 'edge-approve-end'),
              1500, 200,
              '簽核者固定是發起人自己（assignee_type=INITIATOR），純粹作為'
              '流程收尾的關卡，方便一個帳號就能走完全程。'),

        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 1780, 200,
              '流程正常結束（finish_mode=detach）。'),
    ]
    edges = [
        _edge('edge-start-navstart', 'node-Start', 'node-NavStart'),
        _edge('edge-navstart-delay', 'node-NavStart', 'node-Delay'),
        _edge('edge-delay-navend', 'node-Delay', 'node-NavEnd'),
        _edge('edge-navend-write', 'node-NavEnd', 'node-Write'),
        _edge('edge-write-review', 'node-Write', 'node-Review'),
        _edge('edge-approve-end', 'node-Review', 'node-End', label='確認'),
    ]
    return _graph(nodes, edges)


NT26_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'NavbarBroadcast 在導覽列與功能選單列之間插入一條跑馬燈文字，對'
    '系統企業所有使用者顯示。跟 AlertBroadcast 相比，它不會打斷使用者'
    '手邊的操作、不需要任何確認動作，是全平台干擾程度最低的通知方式——'
    '適合「大家看到就好，不需要特別停下來處理」的場景（例如版本更新'
    '公告、非急迫的活動提醒），跟 AlertBroadcast 的「所有人都必須知道'
    '且必須明確表示知道」形成明顯對比。\n\n'
    '【本流程的設定重點】\n'
    '- 同一個 node_type（NavbarBroadcast）用 mode 欄位切出 start／end'
    ' 兩種行為，本流程刻意兩個都用到：先 mode=start 啟動，等 40 秒'
    '（純粹方便示範看得到效果）後再 mode=end 依同一個 broadcast_code'
    '（NODEDEMO_NAVBAR_SAMPLE）主動關閉。\n'
    '- duration_minutes=5：即使 mode=end 節點沒有執行（例如流程中途'
    '失敗、或有人把後面的節點刪掉），5 分鐘後前端下一次查詢也會自動'
    '判定過期、不再顯示。這是本流程刻意設短的保底機制，示範「有明確'
    '收尾動作時仍然值得順手設一個保底期限」——手動關閉與到期失效'
    '兩者不衝突，可以同時存在。\n'
    '- text_color／bg_color 選了低對比的深灰字＋淺藍底（預設值是'
    '黑字黃底 #FDE047，較搶眼），刻意示範這兩個顏色欄位可以自訂成'
    '更不打擾的配色。\n'
    '- display_seconds=8：只在同時有多條跑馬燈訊息輪播時才有意義'
    '（決定切換到下一條訊息前顯示幾秒），本流程只有一條訊息時看不出'
    '差異，但欄位仍然要填。\n\n'
    '【怎麼看結果】\n'
    '送單後流程立刻執行 mode=start，切換到平台任一頁面（最長等 1 分鐘'
    '前端輪詢週期），應該會看到頂部出現一條淺藍底跑馬燈文字。約 40 秒'
    '後（流程呼叫 mode=end 之後，同樣最長等 1 分鐘前端輪詢週期）跑馬燈'
    '會消失。也可以到「填寫表單」重新打開這張單看'
    ' navbar_result_display 欄位，或直接查：\n'
    "SELECT code, is_active, value->>'expires_at' FROM lookup_items "
    "WHERE category_code='broadcast' AND code='NODEDEMO_NAVBAR_SAMPLE';\n"
    '流程跑完後 is_active 應該已經是 false（mode=end 主動關閉的結果）。\n\n'
    '【怎麼清掉這則廣播】\n'
    '正常情況下流程本身的 mode=end 節點就會關閉它，不需要手動處理。'
    '如果想在流程跑到一半時提前清掉，或流程失敗導致 mode=end 沒有'
    '執行，可以直接執行：\n'
    "UPDATE lookup_items SET is_active=false WHERE category_code='broadcast' "
    "AND code='NODEDEMO_NAVBAR_SAMPLE';\n"
    '即使完全不處理，duration_minutes=5 到期後前端下次查詢也會自動'
    '判定過期，不會永久佔用畫面。'
)

FORM_NAVBAR_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-26 NavbarBroadcast 示範表單（跑馬燈廣播）'),
        _hint('送出後流程會觸發一則全企業的跑馬燈廣播，顯示在頂部導覽列，'
              '約 40 秒後流程會自動關閉它。內容已固定以「[node展覽館示範]」'
              '開頭，避免被誤認為真的系統公告。'),
        _text('navbar_message', '跑馬燈訊息',
              '這段文字會經過變數替換直接顯示在跑馬燈上。'),
        _textarea('navbar_result_display', '觸發結果（由流程自動填入）',
                   '此欄位由 NavbarBroadcast + OpFieldWrite 自動寫入。', rows=8),
        _submit_button(),
    ],
}
FORM_NAVBAR_SCHEMA['components'][2]['defaultValue'] = (
    '[node展覽館示範] 歡迎使用 node展覽館，這是一則跑馬燈廣播示範，'
    '僅供教學使用'
)


FULL_DEMOS_STATIC = [
    {
        'form_code': 'NODEDEMO_NT24_ALERT_FORM',
        'form_name': 'NT-24 AlertBroadcast 示範表單（緊急廣播）',
        'form_schema': FORM_ALERT_SCHEMA,
        'workflow_code': 'NODEDEMO_NT24_ALERT_FLOW',
        'workflow_name': 'NT-24 AlertBroadcast 示範（緊急廣播）',
        'description': NT24_DESCRIPTION,
        'graph': lambda: build_alert_graph(),
    },
    {
        'form_code': 'NODEDEMO_NT26_NAVBAR_FORM',
        'form_name': 'NT-26 NavbarBroadcast 示範表單（跑馬燈廣播）',
        'form_schema': FORM_NAVBAR_SCHEMA,
        'workflow_code': 'NODEDEMO_NT26_NAVBAR_FLOW',
        'workflow_name': 'NT-26 NavbarBroadcast 示範（跑馬燈廣播）',
        'description': NT26_DESCRIPTION,
        'graph': lambda: build_navbar_graph(),
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
            created_by_name='provision_nodedemo_broadcast',
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
        description='佈建 node展覽館的 AlertBroadcast／NavbarBroadcast 示範（B10）')
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

        log('\n=== AlertBroadcast／NavbarBroadcast 示範（表單／流程／配對／發行） ===')
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
