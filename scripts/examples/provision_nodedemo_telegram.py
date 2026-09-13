#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PF-252 B11 批次：node展覽館 —— Telegram（NT-27）／SysTelegram（NT-18）示範。

本檔佈建兩個流程，示範一般 Telegram 通知節點與系統級 Telegram 通知節點的實際差別：

    NT-27 Telegram 示範（一般 Telegram 通知）
        任何企業只要有一組 TelegramConfig 就能用的一般通知節點
        （workflow_node_definitions.org_restricted=false）。

    NT-18 SysTelegram 示範（系統級 Telegram）
        受限節點（org_restricted=true），只有取得授權的企業才會在設計器的
        節點面板上看到它。系統預設企業（SYSTEM）出廠即已授權
        （workflow_node_org_grants）。

兩者差異的第一手驗證（2026-09-07 由本批次以 API 實測，不是抄文件）：
    - handler 原始碼 `telegram_handler.py::TelegramHandler` 是**同一個 class**，
      `NodeHandlerFactory` 把 'Telegram' 與 'SysTelegram' 都註冊指向它。
    - `_resolve_telegram_config()` 對兩者的 TelegramConfig 解析範圍完全相同：
      `{queue_item.org_secure_code, SYSTEM_ORG_CODE}`，也就是「本企業或系統
      企業」——這代表 config 能不能用、能引用哪個設定組，兩種節點完全一樣，
      差別**不在** config 解析範圍。
    - 執行期唯一的差別是 `is_node_allowed(node_type, org)`：
      `Telegram` 因為 `org_restricted=False` 恆為 True；`SysTelegram` 要求
      `workflow_node_org_grants` 有該企業的授權記錄，沒授權就直接
      `{'status': 'error', 'message': '企業未取得 SysTelegram 節點授權'}`。
    - **真正的分界線在設計器面板可見性**：呼叫
      `GET /api/workflows/data/node-definitions` 實測比對——
      以系統預設企業的管理員登入時，回應含 Telegram **與** SysTelegram 兩者；
      一般未授權企業的管理員登入時，回應**只有** Telegram，SysTelegram
      完全不在清單內。
      也就是說，一般企業的流程設計者根本不會在節點面板上看到 SysTelegram
      這個選項存在，不是點了被擋，而是連選項都不會出現。

目標企業固定是系統預設企業（Organization.code='SYSTEM'），分類固定是「node展覽館」
。兩個流程共用一組佔位 Telegram 設定組，預設停用；請到企業設定填入真實
Bot Token 與頻道並啟用後，流程才會真的送出 Telegram 訊息。

冪等：重跑會沿用既有表單／流程（依 code 找），bump revision 並重新發行（會停用
舊的已發行版本並建立新版）。填寫權限授予企業內所有非 EXTERNAL 的在職帳號。

用法：
    cd <repo>
    set -a && source .env && set +a
    venv/bin/python scripts/examples/provision_nodedemo_telegram.py --dry-run
    venv/bin/python scripts/examples/provision_nodedemo_telegram.py --apply

節點 config 欄位依 handler 原始碼確認：
    modules/form_workflow/services/node_handlers/telegram_handler.py
    modules/form_workflow/services/node_handlers/fieldwrite_handler.py
    modules/form_workflow/services/node_handlers/formadapter_handler.py
    modules/form_workflow/services/node_grant_service.py（is_node_allowed）
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

TELEGRAM_CONFIG_NAME = 'node展覽館示範（請填入真實 Bot Token）'
TELEGRAM_CONFIG_SC = None
TELEGRAM_CHANNEL = '示範頻道'

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


def ensure_telegram_config(org, apply=True):
    import json
    from app import db
    from app.models import TelegramConfig

    config = TelegramConfig.query.filter_by(
        org_secure_code=org.secure_code,
        name=TELEGRAM_CONFIG_NAME,
        is_deleted=False,
    ).first()
    if config:
        return config
    config = TelegramConfig(
        org_secure_code=org.secure_code,
        name=TELEGRAM_CONFIG_NAME,
        description='node展覽館示範用佔位設定組；請填入真實 Bot Token 與頻道後再啟用。',
        bot_token='REPLACE_ME',
        channels=json.dumps({TELEGRAM_CHANNEL: 'REPLACE_ME'}, ensure_ascii=False),
        default_channel=TELEGRAM_CHANNEL,
        is_active=False,
    )
    if apply:
        db.session.add(config)
        db.session.flush()
    return config


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
# 流程一：NT-27 Telegram 示範（一般 Telegram 通知）
# ---------------------------------------------------------------------------

def build_telegram_graph():
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 100, 200,
              '流程入口，不需要任何前置設定。'),

        _node('node-Tg', 'Telegram', '發送一般 Telegram 通知', {
            'config_id': TELEGRAM_CONFIG_SC,
            'channel_name': TELEGRAM_CHANNEL,
            'message': (
                '[node展覽館示範] ${f.tg_headline}\n\n${f.tg_body}\n\n'
                '流程執行代碼：${wi.exec_code}'
            ),
            'parse_mode': 'HTML',
            'disable_web_page_preview': False,
            'disable_notification': False,
        }, 380, 200,
            'Telegram 是**非受限**節點（org_restricted=false），任何企業'
            '只要自己有一組 TelegramConfig（或引用系統企業的設定組）就能'
            '使用。這裡引用的是系統預設企業的佔位 Telegram 設定組／「示範頻道」；'
            '佔位設定組要到企業設定填入真實值並啟用才寄得出去。message 內容示範把表單'
            '欄位（${f.tg_headline}／${f.tg_body}）與流程執行代碼'
            '（${wi.exec_code}）一起組成訊息文字，都會被實際替換。'),

        _node('node-Write', 'OpFieldWrite', '寫回送出結果', {
            'target_field': 'tg_result_display',
            'content': (
                '[Telegram 訊息已送出]\n'
                '本次流程執行代碼：${wi.exec_code}\n\n'
                'Telegram 節點本身不會把送達憑證（message_id）寫進流程'
                '變數，也不會寫回表單——這段文字是由後面這個 OpFieldWrite'
                '節點手動寫的，只能記錄「流程走到這裡」，記不到 Telegram'
                ' API 實際回傳的 message_id。要看真正的送達憑證，請查：\n'
                "SELECT log_data->>'message_id' AS message_id, log_data->>'chat_id' "
                "AS chat_id FROM fw_node_execution_logs "
                "WHERE log_message='Telegram 訊息發送成功' "
                "ORDER BY id DESC LIMIT 1;\n\n"
                '也可以直接到 Telegram「示範頻道」查看訊息本身是否送達。'
            ),
        }, 660, 200,
            '把流程執行代碼寫回表單欄位，方便事後回顧本次示範跑了哪一次。'),

        _node('node-Review', 'FormAdapter', '確認已在 Telegram 頻道看到訊息',
              _approve_config('ack', '確認已在 Telegram 頻道看到訊息，結束流程',
                               'edge-approve-end'),
              940, 200,
              '簽核者固定是發起人自己（assignee_type=INITIATOR），純粹作為'
              '流程收尾的關卡，方便一個帳號就能走完全程。'),

        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 1220, 200,
              '流程正常結束（finish_mode=detach）。'),
    ]
    edges = [
        _edge('edge-start-tg', 'node-Start', 'node-Tg'),
        _edge('edge-tg-write', 'node-Tg', 'node-Write'),
        _edge('edge-write-review', 'node-Write', 'node-Review'),
        _edge('edge-approve-end', 'node-Review', 'node-End', label='確認'),
    ]
    return _graph(nodes, edges)


NT27_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'Telegram 節點把一段文字訊息送到指定 TelegramConfig 設定組底下的某個'
    '頻道（依 chat_id）。這是**非受限節點**（workflow_node_definitions'
    '.org_restricted=false）——任何企業只要自己建立過一組 TelegramConfig'
    '（企業設定頁 /security/telegram-configs/ 或類似入口），流程設計器'
    '的節點面板上就看得到這個節點，可以直接拖進畫布使用，不需要向系統'
    '管理員申請任何額外授權。\n\n'
    '【本流程的設定重點】\n'
    '- config_id／channel_name 分別指向 TelegramConfig 的 secure_code'
    '與該設定組 channels 字典裡的頻道名稱（本流程用系統企業的「佔位 Telegram 設定組」'
    '設定組、「示範頻道」）。handler 端解析設定組時允許引用「本企業或'
    '系統企業」的設定組，所以即使不是系統企業，一般企業的流程也能填'
    '系統企業的 TelegramConfig secure_code 借用它（前提是知道那組'
    ' secure_code；跨到別家一般企業的設定組則會被擋，見下方 SysTelegram'
    '流程的說明）。\n'
    '- message 欄位把表單欄位（${f.tg_headline}／${f.tg_body}）與流程'
    '執行代碼（${wi.exec_code}）組合成一段訊息，示範這個欄位支援完整的'
    '變數替換語法，讓送單者能自訂看到的內容。\n'
    '- parse_mode=HTML（預設值）：訊息文字若含 HTML 標籤（如 <b>）會被'
    'Telegram 解析成粗體等格式；改成 Markdown／MarkdownV2 則改用對應'
    '語法解析。\n'
    '- disable_notification=false：正常推播提醒音；設成 true 則是'
    '「靜音發送」，適合非急迫的通知。\n\n'
    '【怎麼看結果】\n'
    '佔位設定組要到企業設定填入真實值並啟用才寄得出去。啟用後，流程送出應在 Telegram「示範頻道」看到一則以'
    '「[node展覽館示範]」開頭的訊息，內容含本次流程執行代碼。也可以到'
    '「填寫表單」重新打開這張單看 tg_result_display 欄位，或直接查：\n'
    "SELECT log_level, log_message, log_data FROM fw_node_execution_logs "
    "WHERE log_message LIKE 'Telegram%' ORDER BY id DESC LIMIT 5;\n"
    '`log_data` 裡的 `message_id` 就是 Telegram 回傳的訊息 ID，是「訊息'
    '真的送達」最直接的證據（訊息本身沒有失敗就一定會有這個值）。'
)

FORM_TELEGRAM_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-27 Telegram 示範表單（一般 Telegram 通知）'),
        _hint('送出後流程會立即呼叫 Telegram API，把下面填的內容送到'
              '佔位 Telegram 設定組的「示範頻道」。內容已固定以'
              '「[node展覽館示範]」開頭，避免被誤認為真的告警。'),
        _text('tg_headline', '通知標題',
              '這段文字會經過變數替換直接組進 Telegram 訊息開頭。'),
        _textarea('tg_body', '通知內容',
                   '這段文字會經過變數替換直接組進 Telegram 訊息內文。', rows=5),
        _textarea('tg_result_display', '送出結果（由流程自動填入）',
                   '此欄位由 OpFieldWrite 自動寫入，實際送達憑證要查 DB。', rows=8),
        _submit_button(),
    ],
}
FORM_TELEGRAM_SCHEMA['components'][2]['defaultValue'] = '一般 Telegram 通知節點示範'
FORM_TELEGRAM_SCHEMA['components'][3]['defaultValue'] = (
    '這是 node展覽館 Telegram 節點的示範送單，任何企業只要有自己的'
    'TelegramConfig 就能使用這個節點，不需要額外授權。僅供教學使用，'
    '非真實告警。'
)


# ---------------------------------------------------------------------------
# 流程二：NT-18 SysTelegram 示範（系統級 Telegram）
# ---------------------------------------------------------------------------

def build_systelegram_graph():
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 100, 200,
              '流程入口，不需要任何前置設定。'),

        _node('node-SysTg', 'SysTelegram', '發送系統級 Telegram 通知', {
            'config_id': TELEGRAM_CONFIG_SC,
            'channel_name': TELEGRAM_CHANNEL,
            'message': (
                '[node展覽館示範] ${f.systg_headline}\n\n${f.systg_body}\n\n'
                '流程執行代碼：${wi.exec_code}'
            ),
            'parse_mode': 'HTML',
            'disable_web_page_preview': False,
            'disable_notification': False,
        }, 380, 200,
            'SysTelegram 與上面 Telegram 流程用的是**同一支 handler'
            '（telegram_handler.TelegramHandler）**，config 欄位、訊息'
            '替換、送出邏輯完全相同，這個節點本身的執行行為跟一般'
            ' Telegram 節點沒有任何差異。唯一的差別是'
            ' workflow_node_definitions.org_restricted=true：這個節點'
            '型別本身只有取得授權的企業（workflow_node_org_grants 有'
            '記錄）才會在流程設計器的節點面板上看到它。系統預設企業'
            '出廠即已授權，一般企業（例如 一般未授權企業）預設看不到這個節點'
            '選項——不是點了被擋，是設計器面板上根本不會出現。'),

        _node('node-Write', 'OpFieldWrite', '寫回送出結果', {
            'target_field': 'systg_result_display',
            'content': (
                '[系統級 Telegram 訊息已送出]\n'
                '本次流程執行代碼：${wi.exec_code}\n\n'
                '同樣要查 DB 才看得到 message_id：\n'
                "SELECT log_data->>'message_id' AS message_id, log_data->>'chat_id' "
                "AS chat_id FROM fw_node_execution_logs "
                "WHERE log_message='Telegram 訊息發送成功' "
                "ORDER BY id DESC LIMIT 1;\n\n"
                '也可以直接到 Telegram「示範頻道」查看訊息本身是否送達。'
            ),
        }, 660, 200,
            '把流程執行代碼寫回表單欄位，方便事後回顧本次示範跑了哪一次。'),

        _node('node-Review', 'FormAdapter', '確認已在 Telegram 頻道看到訊息',
              _approve_config('ack', '確認已在 Telegram 頻道看到訊息，結束流程',
                               'edge-approve-end'),
              940, 200,
              '簽核者固定是發起人自己（assignee_type=INITIATOR），純粹作為'
              '流程收尾的關卡，方便一個帳號就能走完全程。'),

        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 1220, 200,
              '流程正常結束（finish_mode=detach）。'),
    ]
    edges = [
        _edge('edge-start-systg', 'node-Start', 'node-SysTg'),
        _edge('edge-systg-write', 'node-SysTg', 'node-Write'),
        _edge('edge-write-review', 'node-Write', 'node-Review'),
        _edge('edge-approve-end', 'node-Review', 'node-End', label='確認'),
    ]
    return _graph(nodes, edges)


NT18_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'SysTelegram 與一般 Telegram 節點功能完全相同（同一支 handler'
    '，`telegram_handler.TelegramHandler`），把訊息送到指定'
    ' TelegramConfig 設定組底下的某個頻道。差別在於這是**受限節點**'
    '（workflow_node_definitions.org_restricted=true）：企業必須先由'
    '系統管理員在「權限管理 → 節點授權」（/node-grants/）明確授權'
    '（寫入 workflow_node_org_grants），流程設計器的節點面板才會出現'
    '這個節點型別；沒有授權的企業連拖拉的選項都看不到，不是拖進畫布後'
    '被擋。系統預設企業出廠即已取得授權。\n\n'
    '【本流程的設定重點】\n'
    '- config／message 欄位與一般 Telegram 節點完全一樣，本流程刻意'
    '沿用同一組系統企業佔位 Telegram 設定組／「示範頻道」，證明兩種節點'
    '在「執行期能用哪個設定組」上沒有任何差異——`_resolve_telegram_'
    'config()` 對 Telegram／SysTelegram 兩者都是查「本企業或系統企業」'
    '的 TelegramConfig，程式碼裡完全沒有針對 SysTelegram 另外放寬或'
    '收緊設定組的解析範圍。\n'
    '- **為什麼要有一個「系統級」版本**：權限邊界設計在「企業」這個'
    '維度，而不是帳號的 user_type。系統管理員（SYSTEM_ADMIN）想在'
    '系統預設企業的流程裡用到這個節點類型時，如果只靠帳號身分判斷'
    '（例如 require_system_admin），會擋不住這個節點型別出現在其他'
    '企業的設計器面板上；改用「企業授權」（org_restricted + grant）'
    '之後，才能精確控制「哪些企業的設計者看得到這個節點」，而與操作者'
    '的帳號身分無關（該企業的一般 ORG_ADMIN 一樣看得到，SYSTEM_ADMIN'
    '本身反而常因模組 ACL 而打不進模組 API，詳見專案 CLAUDE.md'
    ' PERM-04）。這正是本專案「受限節點」機制存在的理由。\n'
    '- 本批次已用 API 實測驗證這個差異：`GET /api/workflows/data/'
    'node-definitions` 對系統企業（登入'
    ' 系統預設企業管理員）回應含 Telegram 與 SysTelegram 兩者；'
    '對 一般未授權企業（以一般未授權企業的管理員登入，一般企業、'
    '未取得 SysTelegram 授權）回應**只有** Telegram，SysTelegram'
    '完全不在清單內——不是有回傳但被前端隱藏，是 API 回應本身就沒有'
    '這一項。\n\n'
    '【怎麼看結果】\n'
    '流程送出後應立即在 Telegram「示範頻道」看到一則以'
    '「[node展覽館示範]」開頭的訊息（與一般 Telegram 流程送的訊息'
    '交錯出現，靠內文的流程執行代碼分辨是哪一次）。也可以到「填寫表單」'
    '重新打開這張單看 systg_result_display 欄位，或直接查：\n'
    "SELECT log_level, log_message, log_data FROM fw_node_execution_logs "
    "WHERE log_message LIKE 'Telegram%' ORDER BY id DESC LIMIT 5;\n"
    '想親自驗證「一般企業看不到這個節點」，可以用 一般未授權企業的帳號'
    '登入設計器，打開任一流程的節點面板，會看到 Telegram 存在但'
    ' SysTelegram 不存在。'
)

FORM_SYSTELEGRAM_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-18 SysTelegram 示範表單（系統級 Telegram）'),
        _hint('送出後流程會立即呼叫 Telegram API，把下面填的內容送到'
              '佔位設定組的「示範頻道」。佔位設定組要到企業設定填入真實值並啟用才寄得出去。'
              '內容已固定以「[node展覽館示範]」開頭。這個節點'
              '型別只有取得授權的企業才會在設計器看到，系統預設企業'
              '出廠即已授權。'),
        _text('systg_headline', '通知標題',
              '這段文字會經過變數替換直接組進 Telegram 訊息開頭。'),
        _textarea('systg_body', '通知內容',
                   '這段文字會經過變數替換直接組進 Telegram 訊息內文。', rows=5),
        _textarea('systg_result_display', '送出結果（由流程自動填入）',
                   '此欄位由 OpFieldWrite 自動寫入，實際送達憑證要查 DB。', rows=8),
        _submit_button(),
    ],
}
FORM_SYSTELEGRAM_SCHEMA['components'][2]['defaultValue'] = '系統級 Telegram 通知節點示範'
FORM_SYSTELEGRAM_SCHEMA['components'][3]['defaultValue'] = (
    '這是 node展覽館 SysTelegram 節點的示範送單。這個節點是受限節點，'
    '只有取得授權的企業才能在流程設計器裡使用，一般企業（例如 一般未授權企業）'
    '看不到這個節點選項。僅供教學使用，非真實告警。'
)


FULL_DEMOS_STATIC = [
    {
        'form_code': 'NODEDEMO_NT27_TELEGRAM_FORM',
        'form_name': 'NT-27 Telegram 示範表單（一般 Telegram 通知）',
        'form_schema': FORM_TELEGRAM_SCHEMA,
        'workflow_code': 'NODEDEMO_NT27_TELEGRAM_FLOW',
        'workflow_name': 'NT-27 Telegram 示範（一般 Telegram 通知）',
        'description': NT27_DESCRIPTION,
        'graph': lambda: build_telegram_graph(),
    },
    {
        'form_code': 'NODEDEMO_NT18_SYSTELEGRAM_FORM',
        'form_name': 'NT-18 SysTelegram 示範表單（系統級 Telegram）',
        'form_schema': FORM_SYSTELEGRAM_SCHEMA,
        'workflow_code': 'NODEDEMO_NT18_SYSTELEGRAM_FLOW',
        'workflow_name': 'NT-18 SysTelegram 示範（系統級 Telegram）',
        'description': NT18_DESCRIPTION,
        'graph': lambda: build_systelegram_graph(),
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
            created_by_name='provision_nodedemo_telegram',
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
    global TELEGRAM_CONFIG_SC
    TELEGRAM_CONFIG_SC = ensure_telegram_config(org, apply=apply).secure_code

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
    parser = argparse.ArgumentParser(description='佈建 node展覽館的 Telegram／SysTelegram 示範（B11）')
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
            log('\n已寫入。到 /forms/center 的「填寫表單」就看得到這兩張單。')
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
