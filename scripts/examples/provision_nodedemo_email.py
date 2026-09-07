#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PF-252 B12 批次：node展覽館 —— EmailAdapter（NT-25）／SysEmailRelay（NT-14）示範。

本檔佈建兩個流程，示範一般企業都能用的 Email 通知節點，
與只有取得授權的企業才看得到的系統級 Email 轉發節點，兩者的實作差異：

    NT-25 EmailAdapter 示範（一般企業 Email 通知）
        任何企業只要自己有一組 SmtpConfig 就能用的一般通知節點
        （workflow_node_definitions.org_restricted=false）。走 smtplib
        直接連線外部 SMTP 伺服器。

    NT-14 SysEmailRelay 示範（系統級 Email 轉發）
        受限節點（org_restricted=true），只有取得授權的企業才會在設計器
        的節點面板上看到它。走本機 `emailrelay-submit` 子行程把信寫進
        spool，交給獨立的 E-MailRelay daemon 轉送，完全不依賴任何
        SmtpConfig 設定組。

兩者差異的第一手驗證（2026-09-07 由本批次以原始碼閱讀＋API 實測確認）：
    - handler 是**兩個獨立 class**（與 Telegram／SysTelegram 共用同一支
      handler 不同）：`email_handler.py::EmailHandler` 走
      `smtplib.SMTP()` 直接連線 `SmtpConfig` 指定的外部主機；
      `sys_emailrelay_handler.py::SysEmailRelayHandler` 走
      `subprocess.run(['emailrelay-submit', ...])` 把信寫入本機 spool
      目錄，兩者的傳輸路徑完全不同、互不依賴。
    - **EmailAdapter 有自動降級機制，SysEmailRelay 沒有**：
      `EmailHandler._resolve_smtp_config()` 在 `smtp_config_id` 對不到
      任何啟用中的 SmtpConfig 時（含疑似髒資料），會先降級找「本企業
      is_default」，找不到再找「本企業任一啟用中依 priority」，最後才
      落到「系統企業依 priority」——三層 fallback 都沒有才報錯。
      `SysEmailRelayHandler` 完全不解析任何 SmtpConfig，寄件位址固定寫死
      `beakmask@beakplatform.local`，沒有「找不到設定組」這件事可言。
    - **真正的分界線在設計器面板可見性**：呼叫
      `GET /api/workflows/data/node-definitions` 實測比對——
      系統企業（SYSTEM，quick-login `UC1oK01uDeKbG2MDwBflGD`）回應同時含
      `notification` 分類的 EmailAdapter **與** `system_admin` 分類的
      SysEmailRelay；BELUGA 企業（quick-login
      `jIYEQ-_lZMZNBkVy-hijal`，一般企業、未取得 SysEmailRelay 授權）
      回應只有 EmailAdapter，連 `system_admin` 這個分類本身都不存在。
      也就是說，一般企業的流程設計者根本不會在節點面板上看到
      SysEmailRelay 這個選項存在。

目標企業固定是系統預設企業（Organization.code='SYSTEM'），分類固定是
「node展覽館」（fw_categories.secure_code='J1ygL6zexauKlLM0_Ktoaw'）。
EmailAdapter 流程引用系統企業 SMTP 設定組「lionsecbot@gmail.com」
（secure_code=9V_rPCngCX-q65mbSbICJa，唯一一組、is_default=True）；
SysEmailRelay 流程完全不需要任何 SmtpConfig。

**EmailAdapter 流程刻意示範自動降級**：流程裡放兩個 EmailAdapter 節點，
第一個明確填對的 smtp_config_id，第二個故意填一個不存在的
secure_code（`NODEDEMO-INVALID-SMTP-CONFIG-SC`）——如果第二個節點仍然
成功送出，就證明「找不到設定組不會直接報錯，而是靜默降級選用別的
設定組」這件事真的發生了。因為本流程本身掛在系統企業底下，降級後
選到的其實是同一組 lionsecbot@gmail.com（系統企業目前只有這一組
SmtpConfig），這正好呼應描述裡要強調的重點：**設計者以為指定了某個
設定組，實際上可能用的是別的**——這裡「別的」剛好與原本那組相同，
純粹是因為系統企業只有一組可用；換成有多組 SmtpConfig 的企業，降級
後寄出的信可能來自完全不同的寄件位址，卻不會有任何錯誤訊息提示這件事。

**注意（Ethan 明確同意）**：這兩個流程會真的呼叫外部 SMTP／emailrelay
daemon 把信寄到 `lionsecbot@gmail.com`（就是 SMTP 設定組自己的信箱，
自寄自收，不會打擾別人）。主旨一律以「[node展覽館示範]」開頭，避免被
誤認為真實通知。

冪等：重跑會沿用既有表單／流程（依 code 找），bump revision 並重新發行
（會停用舊的已發行版本並建立新版）。填寫權限授予企業內所有非 EXTERNAL
的在職帳號。**重跑會再送出一次真實的 Email**，不是只改資料庫。

用法：
    cd /opt/BeakPlatform-dev
    set -a && source .env && set +a
    venv/bin/python scripts/examples/provision_nodedemo_email.py --dry-run
    venv/bin/python scripts/examples/provision_nodedemo_email.py --apply

節點 config 欄位依 handler 原始碼確認：
    modules/form_workflow/services/node_handlers/email_handler.py
    modules/form_workflow/services/node_handlers/sys_emailrelay_handler.py
    modules/form_workflow/services/node_handlers/fieldwrite_handler.py
    modules/form_workflow/services/node_handlers/formadapter_handler.py
權威對照表：/opt/tmp/verify/20260907-node-config-reference.md
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

SMTP_CONFIG_SC = '9V_rPCngCX-q65mbSbICJa'  # 系統企業 SmtpConfig「lionsecbot@gmail.com」（is_default）
INVALID_SMTP_CONFIG_SC = 'NODEDEMO-INVALID-SMTP-CONFIG-SC'  # 刻意造的假 secure_code，用來觸發降級
RECIPIENT_EMAIL = 'lionsecbot@gmail.com'  # 設定組自己的信箱，自寄自收

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
# 流程一：NT-25 EmailAdapter 示範（一般企業 Email 通知）
# ---------------------------------------------------------------------------

def build_email_graph():
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 100, 200,
              '流程入口，不需要任何前置設定。'),

        _node('node-MailValid', 'EmailAdapter', '寄送郵件（明確指定正確設定組）', {
            'smtp_config_id': SMTP_CONFIG_SC,
            'recipient_type': 'manual',
            'recipient_manual': RECIPIENT_EMAIL,
            'subject': '[node展覽館示範] EmailAdapter 正確設定組 - ${f.email_subject_suffix}',
            'body': (
                '${f.email_body}\n\n'
                '流程執行代碼：${wi.exec_code}\n\n'
                '本封信的 smtp_config_id 明確指向系統企業的 SmtpConfig'
                '「lionsecbot@gmail.com」，走 smtplib 直接連線'
                ' smtp.gmail.com:587 寄出，沒有經過任何降級判斷。'
            ),
            'body_type': 'plain',
            'priority': 'normal',
        }, 340, 120,
            'EmailAdapter 是**非受限節點**（org_restricted=false），任何'
            '企業只要自己有一組 SmtpConfig（企業設定頁的「SMTP 設定組」'
            '功能）就能使用。這個節點的 smtp_config_id 明確填了系統企業'
            '這組設定組的 secure_code，是「正常、建議」的用法。'),

        _node('node-MailFallback', 'EmailAdapter', '寄送郵件（刻意填錯設定組，示範自動降級）', {
            'smtp_config_id': INVALID_SMTP_CONFIG_SC,
            'recipient_type': 'manual',
            'recipient_manual': RECIPIENT_EMAIL,
            'subject': '[node展覽館示範] EmailAdapter 自動降級 - ${f.email_subject_suffix}',
            'body': (
                '${f.email_body}\n\n'
                '流程執行代碼：${wi.exec_code}\n\n'
                '本封信的 smtp_config_id 刻意填了一個不存在的 secure_code'
                '（NODEDEMO-INVALID-SMTP-CONFIG-SC），藉此觸發'
                ' email_handler.py::_resolve_smtp_config() 的自動降級'
                '邏輯：查無符合記錄時不會直接報錯，而是依序改試「本企業'
                ' is_default」→「本企業任一啟用中依 priority」→「系統'
                '企業依 priority」。如果您收到這封信，就代表降級生效了'
                '——本流程掛在系統企業底下，系統企業目前只有'
                ' lionsecbot@gmail.com 這一組 SmtpConfig，所以降級後用'
                '到的剛好與上一封信相同；如果企業本身有多組設定組，降級'
                '後寄出的信可能來自完全不同的寄件位址，而流程設計者不會'
                '收到任何錯誤或警告提示。'
            ),
            'body_type': 'plain',
            'priority': 'normal',
        }, 340, 320,
            '刻意把 smtp_config_id 設成一個查無此記錄的假 secure_code，'
            '驗證「找不到就報錯」還是「找不到就靜默降級」。這是本流程的'
            '核心示範重點，詳見流程本身的 description。'),

        _node('node-Write', 'OpFieldWrite', '寫回送出結果', {
            'target_field': 'email_result_display',
            'content': (
                '[兩封郵件已依序送出]\n'
                '本次流程執行代碼：${wi.exec_code}\n\n'
                '第一封使用明確指定的設定組，第二封刻意填錯設定組觸發'
                '自動降級——兩封都應該送達 lionsecbot@gmail.com。\n\n'
                'EmailAdapter 節點本身不會把外部送達憑證（例如 SMTP 的'
                ' Message-ID）寫進流程變數，也不會寫回表單——這段文字是'
                '由後面這個 OpFieldWrite 節點手動寫的，只能記錄「流程'
                '走到這裡、兩個節點都回報成功」，記不到 Gmail 那端實際'
                '收信的憑證。要看節點本身回報的結果，請查：\n'
                "SELECT log_level, log_message, log_data FROM "
                "fw_node_execution_logs WHERE log_message LIKE '郵件%' "
                "ORDER BY id DESC LIMIT 5;\n\n"
                '真正的送達要到 lionsecbot@gmail.com 的信箱確認。'
            ),
        }, 660, 220,
            '把流程執行代碼寫回表單欄位，方便事後回顧本次示範跑了哪一次。'),

        _node('node-Review', 'FormAdapter', '確認兩封信都已送出',
              _approve_config('ack', '確認已收到兩封示範郵件，結束流程',
                               'edge-approve-end'),
              940, 220,
              '簽核者固定是發起人自己（assignee_type=INITIATOR），純粹作為'
              '流程收尾的關卡，方便一個帳號就能走完全程。'),

        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 1220, 220,
              '流程正常結束（finish_mode=detach）。'),
    ]
    edges = [
        _edge('edge-start-valid', 'node-Start', 'node-MailValid'),
        _edge('edge-valid-fallback', 'node-MailValid', 'node-MailFallback'),
        _edge('edge-fallback-write', 'node-MailFallback', 'node-Write'),
        _edge('edge-write-review', 'node-Write', 'node-Review'),
        _edge('edge-approve-end', 'node-Review', 'node-End', label='確認'),
    ]
    return _graph(nodes, edges)


NT25_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'EmailAdapter 節點透過 SMTP 直接寄送一封 Email。它引用一組'
    ' SmtpConfig（企業自己設定的 SMTP 連線資訊：主機、帳號、應用程式'
    '密碼），走 Python smtplib 連線外部郵件伺服器（例如 Gmail）發信。'
    '這是**非受限節點**（workflow_node_definitions.org_restricted='
    'false）——任何企業只要建立過至少一組 SmtpConfig，流程設計器的節點'
    '面板上就看得到這個節點，不需要向系統管理員申請任何額外授權。\n\n'
    '【本流程的設定重點】\n'
    '本流程刻意放了**兩個** EmailAdapter 節點依序執行，示範同一件事的'
    '正常用法與一個容易被忽略的行為：\n'
    '- 第一個節點（寄送郵件（明確指定正確設定組））：smtp_config_id 明確'
    '填系統企業 SmtpConfig「lionsecbot@gmail.com」的 secure_code'
    '（9V_rPCngCX-q65mbSbICJa）。這是建議的正常用法——填一個你確定'
    '存在、啟用中的設定組。\n'
    '- 第二個節點（寄送郵件（刻意填錯設定組，示範自動降級））：'
    'smtp_config_id 刻意填一個不存在的 secure_code。`email_handler.py'
    '::_resolve_smtp_config()` 在查無符合記錄時**不會讓節點失敗**，而是'
    '依序降級：先找「本企業 is_default 的設定組」，找不到再找「本企業'
    '任一啟用中依 priority」，最後才落到「系統企業依 priority」——三層'
    '都沒有才會報「沒有可用的 SMTP 設定」。這代表：**如果你在節點裡填錯'
    '了 secure_code（或那筆設定組後來被刪除／停用），節點不會失敗、也'
    '不會有任何警告，會靜默改用別的設定組寄信**——收件人收到的信可能來自'
    '完全不同的寄件位址，而流程設計者對此毫無察覺。本流程因為系統企業'
    '目前只有一組 SmtpConfig，兩封信的寄件位址剛好相同；换成有多組'
    '設定組的企業，這個差異就會直接反映在收件人看到的寄件人上。\n'
    '- recipient_type=manual：兩個節點都直接填 Email 地址'
    '（${...} 之外的固定字串），也支援 recipient_type=group 引用'
    '「收件人群組」批次收件。\n'
    '- subject／body 都示範把表單欄位（${f.email_subject_suffix}／'
    '${f.email_body}）與流程執行代碼（${wi.exec_code}）組進內容，證明'
    '這兩個欄位支援完整的變數替換語法。\n\n'
    '【怎麼看結果】\n'
    '流程送出後應該收到**兩封**以「[node展覽館示範]」開頭的信'
    '（收件匣是 lionsecbot@gmail.com 自己），主旨分別標「正確設定組」'
    '與「自動降級」，內容都含本次流程執行代碼可互相對照。也可以到'
    '「填寫表單」重新打開這張單看 email_result_display 欄位，或直接查：\n'
    "SELECT log_level, log_message, log_data FROM fw_node_execution_logs "
    "WHERE log_message LIKE '郵件%' ORDER BY id DESC LIMIT 5;\n"
    '`log_data` 裡的 to／cc／subject 可以看出兩個節點各自送出的收件者與'
    '主旨；但**這裡看不到 Gmail 端的送達憑證**（EmailAdapter 不像'
    ' Telegram 或 SysEmailRelay 會留下 message_id 或 spool 檔案的痕跡），'
    '真正的送達要以收件匣實際收到信為準。'
)

FORM_EMAIL_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-25 EmailAdapter 示範表單（一般 Email 通知）'),
        _hint('送出後流程會連續呼叫兩次 EmailAdapter 節點，各自寄出一封信'
              '到「lionsecbot@gmail.com」。第一封使用正確設定組，第二封'
              '刻意填錯設定組觸發自動降級，兩封都應該送達。內容已固定以'
              '「[node展覽館示範]」開頭，避免被誤認為真的通知。'),
        _text('email_subject_suffix', '通知主旨補充',
              '這段文字會經過變數替換直接組進兩封信的主旨結尾。'),
        _textarea('email_body', '通知內容',
                   '這段文字會經過變數替換直接組進兩封信的內文開頭。', rows=5),
        _textarea('email_result_display', '送出結果（由流程自動填入）',
                   '此欄位由 OpFieldWrite 自動寫入，實際送達要看收件匣。', rows=8),
        _submit_button(),
    ],
}
FORM_EMAIL_SCHEMA['components'][2]['defaultValue'] = '一般 EmailAdapter 節點示範'
FORM_EMAIL_SCHEMA['components'][3]['defaultValue'] = (
    '這是 node展覽館 EmailAdapter 節點的示範送單，同時驗證正確設定組與'
    '自動降級兩種情境，任何企業只要有自己的 SmtpConfig 就能使用這個'
    '節點，不需要額外授權。僅供教學使用，非真實通知。'
)


# ---------------------------------------------------------------------------
# 流程二：NT-14 SysEmailRelay 示範（系統級 Email 轉發）
# ---------------------------------------------------------------------------

def build_sysemailrelay_graph():
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 100, 200,
              '流程入口，不需要任何前置設定。'),

        _node('node-SysMail', 'SysEmailRelay', '透過本機 emailrelay-submit 轉發系統郵件', {
            'recipient_type': 'manual',
            'recipient_manual': RECIPIENT_EMAIL,
            'subject': '[node展覽館示範] SysEmailRelay - ${f.sysmail_subject_suffix}',
            'body': (
                '${f.sysmail_body}\n\n'
                '流程執行代碼：${wi.exec_code}\n\n'
                '本封信不經過 smtplib、也不引用任何 SmtpConfig 設定組，'
                '而是呼叫本機 emailrelay-submit 執行檔把信寫進 spool 目錄'
                '（/opt/emailrelay/spool），由獨立的 E-MailRelay daemon'
                '（systemctl 服務 emailrelay）自動轉送到外部 SMTP。'
                '寄件位址固定是 beakmask@beakplatform.local，與企業自己的'
                ' SmtpConfig 完全無關。'
            ),
            'body_type': 'plain',
            'priority': 'normal',
        }, 380, 200,
            'SysEmailRelay 是**受限節點**（workflow_node_definitions'
            '.org_restricted=true），必須由系統管理員在「權限管理 → '
            '節點授權」（/node-grants/）明確授權（寫入'
            ' workflow_node_org_grants），流程設計器的節點面板才會出現'
            '這個節點型別。系統預設企業出廠即已取得授權。它的實作'
            '（sys_emailrelay_handler.SysEmailRelayHandler）與'
            ' EmailAdapter（email_handler.EmailHandler）是**兩個獨立的'
            ' class**，走完全不同的傳輸路徑：本節點透過子行程呼叫'
            ' emailrelay-submit 寫入本機 spool，不連線任何外部 SMTP'
            '，也沒有「設定組解析失敗自動降級」這件事——它根本不解析'
            '任何 SmtpConfig。'),

        _node('node-Write', 'OpFieldWrite', '寫回送出結果', {
            'target_field': 'sysmail_result_display',
            'content': (
                '[系統郵件已提交至本機 spool]\n'
                '本次流程執行代碼：${wi.exec_code}\n\n'
                '這個節點回報成功只代表 emailrelay-submit 子行程正常'
                '結束（回傳碼 0），信已經寫進 /opt/emailrelay/spool，'
                '**不代表已經送達外部收件人**。要看實際轉送狀況要查'
                ' E-MailRelay 自己的 log：\n'
                'tail /opt/emailrelay/logs/emailrelay-$(date +%Y%m%d).log\n\n'
                '看到一行 "smtp connection to smtp.gmail.com:587" 就代表'
                ' daemon 已經把這封信轉送出去了。也可以直接到'
                ' lionsecbot@gmail.com 的收件匣確認。'
            ),
        }, 660, 200,
            '把流程執行代碼寫回表單欄位，方便事後回顧本次示範跑了哪一次。'),

        _node('node-Review', 'FormAdapter', '確認已在收件匣看到訊息',
              _approve_config('ack', '確認已收到示範郵件，結束流程',
                               'edge-approve-end'),
              940, 200,
              '簽核者固定是發起人自己（assignee_type=INITIATOR），純粹作為'
              '流程收尾的關卡，方便一個帳號就能走完全程。'),

        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 1220, 200,
              '流程正常結束（finish_mode=detach）。'),
    ]
    edges = [
        _edge('edge-start-sysmail', 'node-Start', 'node-SysMail'),
        _edge('edge-sysmail-write', 'node-SysMail', 'node-Write'),
        _edge('edge-write-review', 'node-Write', 'node-Review'),
        _edge('edge-approve-end', 'node-Review', 'node-End', label='確認'),
    ]
    return _graph(nodes, edges)


NT14_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'SysEmailRelay 把一封信透過本機的 emailrelay-submit 執行檔寫進'
    ' spool 目錄，交給獨立跑在本機的 E-MailRelay daemon（systemd 服務'
    ' emailrelay）自動轉送到外部 SMTP 伺服器。它**不使用**任何企業自己'
    '設定的 SmtpConfig，寄件位址固定是 beakmask@beakplatform.local。'
    '這是**受限節點**（workflow_node_definitions.org_restricted='
    'true）：企業必須先由系統管理員在「權限管理 → 節點授權」'
    '（/node-grants/）明確授權（寫入 workflow_node_org_grants），流程'
    '設計器的節點面板才會出現這個節點型別；沒有授權的企業連拖拉的選項'
    '都看不到，不是拖進畫布後被擋。系統預設企業出廠即已取得授權。\n\n'
    '【本流程的設定重點】\n'
    '- 沒有 smtp_config_id 這個欄位——SysEmailRelay 的 config 完全不'
    '涉及任何 SmtpConfig，subject／body／recipient_type／'
    'recipient_manual 幾個欄位與 EmailAdapter 同名同義，但少了'
    ' smtp_config_id，因為它根本不需要解析設定組。與上面 EmailAdapter'
    '流程「填錯設定組會靜默降級」的行為相比，SysEmailRelay 完全沒有'
    '這種模糊地帶：要嘛提交到 spool 成功、要嘛因為收件者/主旨/內容缺漏'
    '而直接報錯，沒有中間的「用了別的設定組」狀態。\n'
    '- **為什麼要有一個「系統級」版本**：權限邊界設計在「企業」這個'
    '維度，而不是帳號的 user_type。系統管理員想在系統預設企業的流程裡'
    '用到「透過本機服務轉發郵件」這種能力時，如果只靠帳號身分判斷'
    '（例如 require_system_admin），會擋不住這個節點型別出現在其他'
    '企業的設計器面板上；改用「企業授權」（org_restricted + grant）'
    '之後，才能精確控制「哪些企業的設計者看得到這個節點」，而與操作者'
    '的帳號身分無關（詳見專案 CLAUDE.md PERM-04）。這正是本專案「受限'
    '節點」機制存在的理由，也是本批次刻意示範的另一個節點型別'
    '（前一批 B11 用 SysTelegram／Telegram 示範過同一個機制）。\n'
    '- 本批次已用 API 實測驗證這個差異：`GET /api/workflows/data/'
    'node-definitions` 對系統企業（quick-login'
    ' UC1oK01uDeKbG2MDwBflGD）回應同時含 EmailAdapter（分類'
    ' notification）與 SysEmailRelay（分類 system_admin）；對 BELUGA'
    '企業（quick-login jIYEQ-_lZMZNBkVy-hijal，一般企業、未取得'
    ' SysEmailRelay 授權）回應只有 EmailAdapter，連 system_admin 這個'
    '分類本身都不存在——不是有回傳但被前端隱藏，是 API 回應本身就沒有'
    '這一項。\n\n'
    '【怎麼看結果】\n'
    '流程送出後，信先被寫進本機 spool，通常在 10 秒內（E-MailRelay 設定'
    '的 poll 間隔）被 daemon 轉送並從 spool 移除，所以幾乎來不及去看'
    ' spool 目錄本身。要確認送達請看：\n'
    "1) 節點日誌：SELECT log_level, log_message, log_data FROM "
    "fw_node_execution_logs WHERE log_message LIKE '%SysEmailRelay%' "
    "ORDER BY id DESC LIMIT 5;\n"
    '2) E-MailRelay 自己的 log：tail /opt/emailrelay/logs/emailrelay-'
    '$(date +%Y%m%d).log，看到一行 "smtp connection to '
    'smtp.gmail.com:587" 就代表這封信已經被轉送出去。\n'
    '3) 到「填寫表單」重新打開這張單看 sysmail_result_display 欄位'
    '（只能證明「流程走到這裡」，不能證明送達，送達要看前兩項）。\n'
    '4) 最終要以 lionsecbot@gmail.com 的收件匣實際收到信為準。\n'
    '想親自驗證「一般企業看不到這個節點」，可以用 BELUGA 企業的帳號'
    '登入設計器，打開任一流程的節點面板，會看到 EmailAdapter 存在但'
    ' SysEmailRelay 不存在（連分類都不存在）。'
)

FORM_SYSEMAILRELAY_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-14 SysEmailRelay 示範表單（系統級 Email 轉發）'),
        _hint('送出後流程會呼叫本機 emailrelay-submit，把下面填的內容'
              '透過 spool 轉送到「lionsecbot@gmail.com」。內容已固定以'
              '「[node展覽館示範]」開頭，避免被誤認為真的通知。這個節點'
              '型別只有取得授權的企業才會在設計器看到，系統預設企業'
              '出廠即已授權。'),
        _text('sysmail_subject_suffix', '通知主旨補充',
              '這段文字會經過變數替換直接組進信件主旨結尾。'),
        _textarea('sysmail_body', '通知內容',
                   '這段文字會經過變數替換直接組進信件內文開頭。', rows=5),
        _textarea('sysmail_result_display', '送出結果（由流程自動填入）',
                   '此欄位由 OpFieldWrite 自動寫入，實際送達要看收件匣'
                   '與 E-MailRelay log。', rows=8),
        _submit_button(),
    ],
}
FORM_SYSEMAILRELAY_SCHEMA['components'][2]['defaultValue'] = '系統級 SysEmailRelay 節點示範'
FORM_SYSEMAILRELAY_SCHEMA['components'][3]['defaultValue'] = (
    '這是 node展覽館 SysEmailRelay 節點的示範送單。這個節點是受限節點，'
    '只有取得授權的企業才能在流程設計器裡使用，一般企業（例如 BELUGA）'
    '看不到這個節點選項。它走本機 emailrelay-submit，不使用任何'
    ' SmtpConfig。僅供教學使用，非真實通知。'
)


FULL_DEMOS_STATIC = [
    {
        'form_code': 'NODEDEMO_NT25_EMAIL_FORM',
        'form_name': 'NT-25 EmailAdapter 示範表單（一般 Email 通知）',
        'form_schema': FORM_EMAIL_SCHEMA,
        'workflow_code': 'NODEDEMO_NT25_EMAIL_FLOW',
        'workflow_name': 'NT-25 EmailAdapter 示範',
        'description': NT25_DESCRIPTION,
        'graph': lambda: build_email_graph(),
    },
    {
        'form_code': 'NODEDEMO_NT14_SYSEMAILRELAY_FORM',
        'form_name': 'NT-14 SysEmailRelay 示範表單（系統級 Email 轉發）',
        'form_schema': FORM_SYSEMAILRELAY_SCHEMA,
        'workflow_code': 'NODEDEMO_NT14_SYSEMAILRELAY_FLOW',
        'workflow_name': 'NT-14 SysEmailRelay 示範（系統 Email 轉發）',
        'description': NT14_DESCRIPTION,
        'graph': lambda: build_sysemailrelay_graph(),
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
            created_by_name='provision_nodedemo_email',
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
        description='佈建 node展覽館的 EmailAdapter／SysEmailRelay 示範（B12）')
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

        log('\n=== EmailAdapter／SysEmailRelay 示範（表單／流程／配對／發行） ===')
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
