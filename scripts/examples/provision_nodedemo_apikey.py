#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PF-252 B13 批次：node展覽館 —— ApiKeyIssue（NT-04）／ApiKeyAction（NT-03）示範。

本檔佈建兩個流程，串成一個故事：先核發一把 API Key，再用另一個流程處置它。

    NT-04 ApiKeyIssue 示範（核發 API Key）
        核准後由 ApiKeyIssue 節點自動核發一把平台 API Key，並建立一次性
        領取憑證。**流程本身完全不經手金鑰明文**——handler 呼叫
        api_key_service.create_api_key() 拿到的明文直接丟棄
        （見 api_key_issue_handler.py 檔頭註解），只留下
        api_key_claim_service.create_claim() 建立的一次性領取票券。
        Key 歸屬人本人要到「個人設定」頁「我的 API Key」區塊按「領取金鑰」
        才看得到明文一次，之後這張票券就標記為已領取、無法再看第二次；
        要拿到新明文只能按「重新產生金鑰」（會讓舊明文立即失效）。

    NT-03 ApiKeyAction 示範（API Key 處置）
        對一把既有的 Key 做 suspend／resume 處置。這個節點只支援這兩種
        動作（VALID_ACTIONS=('suspend','resume')，見
        api_key_action_handler.py）——沒有 revoke（撤銷、不可逆），
        撤銷仍然只能到 /security/api-keys 頁面手動操作。本流程刻意連續
        排三個 ApiKeyAction 節點（暫停 → 再次暫停 → 復原），一次示範
        suspend 的正常效果、suspend 的冪等行為（已是目標狀態直接視為
        成功，不會報錯也不會二次寫入 suspended_reason／suspended_at），
        以及 resume 讓 key 復原可用。

兩個流程各自需要一張專屬表單，不共用。NT-04 的示範刻意把
ApiKeyIssue 五個 `*_field` config 欄位對到**非預設**的表單欄位 key
（例如 beneficiary_field 對到 key_owner 而不是 handler 預設的
beneficiary），藉此證明這些 config 值只是「要去 form_data 讀哪個 key」
的指標，不是寫死的欄位名。

授權表單的範圍重驗（提權防線）：ApiKeyIssue 核發前會用
fill_permission_service.list_fillable_published_templates() 重新確認
「授權表單」裡列的每一個表單模板，領取人自己都填得到——不是前端下拉
選單過濾一下就能繞過。本示範的 authorized_forms 填的是系統企業既有的
「API Key 申請單」（fw_form_templates.secure_code=執行時查得的 API Key 申請單，
`scripts/examples/provision_api_key_request_flow.py` 佈建的既有資產，
本腳本只讀取它的 secure_code，不改動它），該表單的填寫權限已授予角色
ORG_ADMIN，示範帳號（系統企業 ORG_ADMIN，以系統預設企業的管理員登入）持有這個角色，重驗會通過。

目標企業固定是系統預設企業（Organization.code='SYSTEM'），分類固定是
「node展覽館」。。
這兩個節點都**不是**受限節點（org_restricted=false），不需要企業授權。

**注意**：實際送單會真的呼叫 api_key_service.create_api_key()，在
api_keys 表新增一筆記錄（NT-03 流程再處置它）。核發出來的 Key 的
name／description 都刻意帶 NODEDEMO 字樣，方便日後辨識與清理；不會
動到既有的 2 筆 api_keys 記錄。金鑰明文只在（本腳本之外的）claim
流程當下短暫出現，不寫進本腳本、log 或任何檔案。

冪等：重跑會沿用既有表單／流程（依 code 找），bump revision 並重新
發行（會停用舊的已發行版本並建立新版）。填寫權限授予企業內所有非
EXTERNAL 的在職帳號。**重跑會再核發一把新的 Key**，不是只改資料庫。

用法：
    cd <repo>
    set -a && source .env && set +a
    venv/bin/python scripts/examples/provision_nodedemo_apikey.py --dry-run
    venv/bin/python scripts/examples/provision_nodedemo_apikey.py --apply

節點 config 欄位依 handler 原始碼確認：
    modules/form_workflow/services/node_handlers/api_key_issue_handler.py
    modules/form_workflow/services/node_handlers/api_key_action_handler.py
    modules/form_workflow/services/node_handlers/fieldwrite_handler.py
    modules/form_workflow/services/node_handlers/formadapter_handler.py
    backend/app/services/api_key_service.py
    backend/app/services/api_key_claim_service.py
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

API_KEY_REQUEST_FORM_CODE = 'API_KEY_REQUEST'

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
# 流程一：NT-04 ApiKeyIssue 示範（核發 API Key）
# ---------------------------------------------------------------------------

def build_apikeyissue_graph():
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 100, 220,
              '流程入口，不需要任何前置設定。'),

        _node('node-Approve', 'FormAdapter', '核准並核發',
              _decision_config('issue_decision', [
                  {'id': 'opt-approve', 'label': '核准並核發', 'value': 'approved',
                   'style': 'primary', 'target_edge': 'edge-approve-issue'},
                  {'id': 'opt-reject', 'label': '駁回，不核發', 'value': 'rejected',
                   'style': 'danger', 'target_edge': 'edge-reject-end'},
              ]),
              360, 120,
              '簽核者固定是發起人自己（assignee_type=INITIATOR），代表'
              '「核准這張申請」的把關動作——正式場景通常會換成企業管理員或'
              '主管角色。核准才會走到 ApiKeyIssue 節點；駁回直接收尾，'
              '不會核發任何 Key，也不會建立任何領取憑證。'),

        _node('node-Issue', 'ApiKeyIssue', '核發 API Key', {
            'beneficiary_field': 'key_owner',
            'forms_field': 'scope_forms',
            'purpose_field': 'usage_purpose',
            'expires_field': 'valid_until',
            'allowed_ips_field': 'ip_allowlist',
            'claim_ttl_hours': 48,
            'result_var': 'nodedemo_apikey',
        }, 660, 120,
            '五個 *_field 欄位刻意對到本表單的非預設欄位 key（例如'
            ' beneficiary_field=key_owner，不是 handler 預設的'
            ' beneficiary），證明這些 config 只是「去哪個表單欄位讀值」'
            '的指標。核發前會重新驗證 scope_forms 裡的表單是否落在'
            ' key_owner 自己填得到的範圍內；通過才會呼叫'
            ' api_key_service.create_api_key()，明文核發後立即丟棄，只留'
            ' api_key_claim_service 的一次性領取憑證。'),

        _node('node-Write', 'OpFieldWrite', '寫回核發結果', {
            'target_field': 'issue_result',
            'content': (
                '[已核發] Key 識別碼：${v.nodedemo_apikey_key_id}\n'
                '歸屬人：${v.nodedemo_apikey_beneficiary}\n'
                '領取憑證 secure_code：${v.nodedemo_apikey_claim_code}\n'
                '流程執行代碼：${wi.exec_code}\n\n'
                '這裡看得到的只有識別碼與領取憑證的 secure_code，看不到'
                '金鑰明文——ApiKeyIssue 節點沒有把明文寫進任何流程變數。'
                '請 Key 歸屬人本人登入平台，到「個人設定」頁「我的'
                ' API Key」區塊按「領取金鑰」，金鑰明文只會顯示這一次；'
                '之後這張領取憑證會標記為已領取，同一張憑證無法再看'
                '第二次，要拿新的明文只能按「重新產生金鑰」（會讓舊明文'
                '立即失效）。'
            ),
        }, 960, 120,
            '把核發結果的識別碼與領取憑證寫回表單，方便申請人回頭查看'
            '這次示範跑了什麼——但刻意不寫金鑰明文，因為流程本身也拿不到'
            '明文。'),

        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 1260, 200,
              '流程正常結束（finish_mode=detach）。'),
    ]
    edges = [
        _edge('edge-start-approve', 'node-Start', 'node-Approve'),
        _edge('edge-approve-issue', 'node-Approve', 'node-Issue', label='核准'),
        _edge('edge-issue-write', 'node-Issue', 'node-Write'),
        _edge('edge-write-end', 'node-Write', 'node-End'),
        _edge('edge-reject-end', 'node-Approve', 'node-End', label='駁回'),
    ]
    return _graph(nodes, edges)


NT04_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'ApiKeyIssue 在核准之後自動核發一把平台級 API Key（api_keys 表新增'
    '一筆記錄），並建立一張一次性領取憑證（api_key_claims 表）。它'
    '**不會**把金鑰明文寫進表單、流程變數或任何 log——handler 呼叫'
    ' api_key_service.create_api_key() 拿到的明文在函式內立即丟棄'
    '（見 api_key_issue_handler.py 檔頭註解），只有 Key 歸屬人本人事後'
    '透過 /api/my-api-keys/<key_sc>/claim 才拿得到明文，而且只有一次。\n\n'
    '【本流程的設定重點】\n'
    '- **beneficiary_field／forms_field／purpose_field／expires_field／'
    'allowed_ips_field**：這五個 config 值都不是欄位本身，而是「要去'
    ' form_data 讀哪個 key」的指標。本示範刻意把它們對到非預設的欄位名'
    '（key_owner／scope_forms／usage_purpose／valid_until／'
    'ip_allowlist），證明換成別的表單欄位命名也能用，不必照抄 handler'
    '預設的 beneficiary／authorized_forms／purpose／expires_at／'
    'allowed_ips。\n'
    '- **scope_forms（授權表單）不是自由填**：核發前 handler 會用'
    ' fill_permission_service.list_fillable_published_templates() 重新'
    '驗證這裡列的每一個表單模板，key_owner 自己是否真的填得到、且該'
    '表單已發行。這是核發前的強制重驗，擋的是「F12 塞進任意 template'
    ' secure_code 讓別人拿到他原本沒有的能力」這種提權——前端下拉選單'
    '只過濾一次是不夠的。本示範填的是系統企業既有的「API Key 申請單」'
    '（fw_form_templates.secure_code=執行時查得的 API Key 申請單），示範帳號'
    '持有 ORG_ADMIN 角色、該表單已對這個角色開放填寫權限，所以會通過。\n'
    '- **valid_until（expires_field）與 claim_ttl_hours 是兩個不同的'
    '「有效期」，不要混淆**：valid_until 是 Key 本身的到期日'
    '（api_keys.expires_at），過了這天不管有沒有被領取都直接失效；'
    ' claim_ttl_hours（本示範設 48 小時）是「領取憑證」的有效期限——'
    '過了這個時數沒去領，憑證本身失效（無法再領取明文），但 Key 記錄'
    '仍然存在、仍然算「已核發」，只是明文永遠拿不到了，只能靠「重新'
    '產生金鑰」補救。\n'
    '- **allowed_ips_field 選填**：留空＝不限制來源 IP；本示範填了'
    '一個 CIDR 與一個單一 IP（TEST-NET-3 文件用範圍，不影響任何真實'
    '主機），示範可以混用兩種格式並用逗號分隔。\n\n'
    '【怎麼看結果】\n'
    '1) 回填的表單欄位 issue_result（由 OpFieldWrite 寫入）能看到'
    '核發出來的 key_id 與領取憑證 secure_code，但看不到明文。\n'
    '2) 查流程變數：SELECT var_name, var_value FROM'
    ' fw_workflow_variables WHERE workflow_instance_secure_code=<sc>'
    " AND var_name LIKE 'nodedemo_apikey%';\n"
    '3) 查資料庫本身：SELECT secure_code, key_id, name, status,'
    ' applicant_user_secure_code, expires_at FROM api_keys WHERE'
    " name LIKE '%NODEDEMO%' ORDER BY id DESC;（判斷可用與否看 status，"
    '不是 is_active，那個欄位不存在）\n'
    '4) 到 /security/api-keys 頁面（需 ORG_ADMIN 或 SYSTEM_ADMIN）能'
    '看到這把新 Key 列在清單裡，狀態、授權範圍、到期日都與這裡設定的'
    '一致。\n'
    '5) 要親自驗證「金鑰只能看一次」：以 Key 歸屬人身分登入'
    '「個人設定」頁「我的 API Key」按一次「領取金鑰」會拿到明文，'
    '再按第二次（或再呼叫一次 claim API）會回「這筆領取憑證已失效或'
    '已領取過」。'
)

FORM_APIKEYISSUE_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-04 ApiKeyIssue 示範表單（核發 API Key）'),
        _hint('送出後先經過一個自簽的核准關卡，核准後由 ApiKeyIssue 節點'
              '自動核發一把平台 API Key。金鑰明文不會出現在這張表單、'
              '任何流程變數，也不會出現在本示範的任何 log 裡——歸屬人'
              '本人要到「個人設定」頁「我的 API Key」按「領取金鑰」才'
              '看得到一次。'),
        {
            'key': 'key_owner', 'type': 'userPicker', 'input': True,
            'label': 'Key 歸屬人（beneficiary_field=key_owner）',
            'description': '核發出來的 Key 只有這個人能一次性領取金鑰。這裡'
                          '刻意把欄位 key 取名 key_owner 而不是 handler'
                          '預設的 beneficiary，用來證明 beneficiary_field'
                          '只是「去哪個欄位讀值」的指標，不是寫死的欄位名。',
            'tableView': True, 'validate': {'required': True},
            'validateWhenHidden': False,
        },
        {
            'key': 'scope_forms', 'type': 'formPicker', 'input': True,
            'label': '授權表單（forms_field=scope_forms）',
            'description': '核發出來的 Key 只能用來觸發這裡選的表單。核發前'
                          '會重新驗證這些表單是否落在「Key 歸屬人」自己'
                          '填得到的範圍內——這是伺服器端的強制重驗，不是'
                          '前端下拉選單過濾一下就能繞過的提權防線。',
            'tableView': True, 'validate': {'required': True},
            'validateWhenHidden': False,
        },
        _textarea('usage_purpose', '用途說明（purpose_field=usage_purpose）',
                   '寫進核發出來的 Key 的 description 欄位，管理頁與稽核'
                   '都看得到。', rows=3),
        {
            'key': 'valid_until', 'type': 'datetime', 'input': True,
            'label': '有效期限（expires_field=valid_until）',
            'description': '這是 Key「本身」的到期日，與下面 claim_ttl_hours'
                          '（領取憑證的有效期）是兩個不同的期限。依企業'
                          '時區解讀成「當天結束」，不是當天 00:00。',
            'tableView': False, 'enableTime': False, 'format': 'yyyy-MM-dd',
            'datePicker': {'disableWeekends': False, 'disableWeekdays': False},
            'widget': {
                'type': 'calendar', 'format': 'yyyy-MM-dd', 'enableTime': False,
                'displayInTimezone': 'viewer', 'locale': 'zh-tw',
                'useLocaleSettings': False, 'allowInput': True, 'mode': 'single',
                'hourIncrement': 1, 'minuteIncrement': 1, 'time_24hr': True,
                'saveAs': 'text',
            },
            'validate': {'required': True}, 'validateWhenHidden': False,
        },
        _text('ip_allowlist', '來源 IP 限制（allowed_ips_field=ip_allowlist）',
              '選填。可填單一 IP 或 CIDR，多筆以逗號分隔。留空表示不限制'
              '來源。'),
        _textarea('issue_result', '核發結果（由流程自動填寫）',
                   '由 OpFieldWrite 節點自動寫入，申請人不需輸入；這裡只會'
                   '出現識別碼與領取憑證，不會出現金鑰明文。', rows=6,
                   disabled=True),
        _submit_button(),
    ],
}


# ---------------------------------------------------------------------------
# 流程二：NT-03 ApiKeyAction 示範（API Key 處置）
# ---------------------------------------------------------------------------

def build_apikeyaction_graph():
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 100, 260,
              '流程入口，不需要任何前置設定。'),

        _node('node-Confirm', 'FormAdapter', '確認處置對象',
              _decision_config('action_decision', [
                  {'id': 'opt-confirm', 'label': '確認，開始處置', 'value': 'approved',
                   'style': 'primary', 'target_edge': 'edge-confirm-suspend1'},
                  {'id': 'opt-cancel', 'label': '取消，不處置', 'value': 'rejected',
                   'style': 'danger', 'target_edge': 'edge-cancel-end'},
              ]),
              360, 140,
              '簽核者固定是發起人自己（assignee_type=INITIATOR），純粹作為'
              '「我確定要處置這把 Key」的把關動作，避免手滑送出。取消則'
              '直接收尾，三個 ApiKeyAction 節點都不會執行。'),

        _node('node-Suspend1', 'ApiKeyAction', '處置動作一：暫停', {
            'action': 'suspend',
            'key_source': 'variable',
            'key_id': '${f.target_key_id}',
            'reason': '${f.suspend_reason}',
        }, 660, 60,
            'action=suspend、key_source=variable：處置對象不是設計時'
            '寫死的 key_id，而是每次送單時從表單欄位 target_key_id 解析'
            '（先過 replace_variables()）。這是本示範能重複拿不同 Key'
            '來測的關鍵設定——換成 key_source=static 就會變成每次都'
            '處置同一把設計時寫死的 Key，換成 key_source=trigger 則是'
            '處置「發動本流程的那把 Key 自己」（適合資安流程自動暫停'
            '疑似盜用的來源 Key）。'),

        _node('node-Suspend2', 'ApiKeyAction', '處置動作二：再次暫停（示範冪等）', {
            'action': 'suspend',
            'key_source': 'variable',
            'key_id': '${f.target_key_id}',
            'reason': '示範冪等：對已是暫停狀態的 Key 再次執行 suspend',
        }, 660, 260,
            '對同一把 Key 再暫停一次。此時 Key 應該已經是 suspended'
            '狀態——handler 對「已是目標狀態」的情況視為冪等成功'
            '（previous_status 與 current_status 相同），不會報錯，也'
            '不會覆寫 suspended_reason／suspended_at。這節點刻意接在'
            '上一個 suspend 後面，讓讀者能直接對照兩次執行的差異。'),

        _node('node-Resume', 'ApiKeyAction', '處置動作三：復原', {
            'action': 'resume',
            'key_source': 'variable',
            'key_id': '${f.target_key_id}',
        }, 660, 460,
            'action=resume：把 Key 從 suspended 復原成 active，讓它重新'
            '可用。與 suspend 一樣支援冪等——對已是 active 的 Key 執行'
            ' resume 也會直接視為成功。'),

        _node('node-Write', 'OpFieldWrite', '寫回處置摘要', {
            'target_field': 'action_result',
            'content': (
                '[三個處置動作已依序執行] 目標 Key：${f.target_key_id}\n'
                '流程執行代碼：${wi.exec_code}\n\n'
                'ApiKeyAction 節點的處置結果（previous_status／'
                'current_status）不會寫進流程變數，只留在這個節點自己的'
                '執行紀錄裡。要看每一步實際的狀態變化，請查：\n'
                "SELECT node_id, result->'data'->>'action' AS action, "
                "result->'data'->>'previous_status' AS before_status, "
                "result->'data'->>'current_status' AS after_status "
                "FROM fw_node_execution_queue WHERE "
                "workflow_instance_secure_code='${wi.code}' AND "
                "node_type='ApiKeyAction' ORDER BY id;\n\n"
                '最終狀態也可以直接到 /security/api-keys 頁面查看這把'
                ' Key 目前是啟用還是暫停。'
            ),
        }, 960, 260,
            '把流程執行代碼與目標 Key 寫回表單，並指出真正的處置前後'
            '對照要去哪張表查——ApiKeyAction 的 data 不進流程變數，只在'
            '節點自己的執行紀錄裡。'),

        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 1260, 260,
              '流程正常結束（finish_mode=detach）。'),
    ]
    edges = [
        _edge('edge-start-confirm', 'node-Start', 'node-Confirm'),
        _edge('edge-confirm-suspend1', 'node-Confirm', 'node-Suspend1', label='確認'),
        _edge('edge-suspend1-suspend2', 'node-Suspend1', 'node-Suspend2'),
        _edge('edge-suspend2-resume', 'node-Suspend2', 'node-Resume'),
        _edge('edge-resume-write', 'node-Resume', 'node-Write'),
        _edge('edge-write-end', 'node-Write', 'node-End'),
        _edge('edge-cancel-end', 'node-Confirm', 'node-End', label='取消'),
    ]
    return _graph(nodes, edges)


NT03_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'ApiKeyAction 對一把既有的平台 API Key 做處置，目前只支援兩種動作'
    '（VALID_ACTIONS=(\'suspend\',\'resume\')）：suspend 把 Key 暫停'
    '（api_keys.status 從 active 變 suspended，仍保留記錄、可以復原）、'
    'resume 把暫停中的 Key 復原成可用。**沒有 revoke（撤銷）**——撤銷是'
    '不可逆操作，這個節點刻意不提供，只能到 /security/api-keys 頁面由'
    '管理員手動操作。\n\n'
    '【本流程的設定重點】\n'
    '- **key_source 決定「處置對象怎麼來」，是這個節點最重要的設定**：\n'
    '  - trigger（本示範沒用到）：處置發動本流程自己的那把 Key'
    '（form_instance.source_api_key）——適合資安流程「偵測到疑似盜用就'
    '自動暫停來源 Key」這種場景。\n'
    '  - static：key_id 直接寫死在 config 裡，每次執行都處置同一把。\n'
    '  - **variable（本流程使用）**：key_id 是一段變數運算式'
    '（${f.target_key_id}），送單當下才解析——本示範藉此讓同一個流程'
    '可以重複拿不同的 Key 來測，不必每次都改流程設計。\n'
    '- **三個 ApiKeyAction 節點依序示範完整生命週期**：第一個'
    ' suspend 讓 Key 從 active 變 suspended；第二個對同一把 Key 再'
    ' suspend 一次，示範**冪等**——已是目標狀態直接視為成功，不報錯、'
    '也不重複寫入 suspended_reason／suspended_at；第三個 resume 把它'
    '復原成 active。三次執行的 previous_status／current_status 可以'
    '在 fw_node_execution_queue.result 逐筆對照。\n'
    '- **租戶隔離**：處置對象一定要屬於本流程所屬企業（org_secure_code'
    '嚴格比對）且未撤銷，跨企業或已撤銷的 key_id 一律回「找不到 API'
    ' Key」，不會洩漏這把 Key 是否存在於別的企業。\n'
    '- **reason 只在 suspend 時有意義**：支援變數替換，寫入'
    ' suspended_reason（截斷 500 字）；resume 沒有對應的 reason 欄位'
    '（api_key_service.resume_key() 只清空 suspended_reason，不記錄'
    '「為什麼復原」）。\n\n'
    '【怎麼看結果】\n'
    '1) 查 fw_node_execution_queue 的 result 欄位，三個 ApiKeyAction'
    '節點各自的 previous_status／current_status 就是完整的狀態變化'
    '對照表（見表單欄位 action_result 裡列出的 SQL）。\n'
    '2) 直接查 api_keys：SELECT secure_code, key_id, status,'
    ' suspended_reason, suspended_at FROM api_keys WHERE'
    " key_id='<你填的 target_key_id>';——執行前是 active，第一次"
    ' suspend 後變 suspended 且 suspended_reason 有值，第三次 resume'
    '後變回 active 且 suspended_reason 清空。\n'
    '3) 到 /security/api-keys 頁面直接看這把 Key 目前的狀態欄位，'
    '搭配前後對照最直觀。'
)

FORM_APIKEYACTION_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-03 ApiKeyAction 示範表單（API Key 處置）'),
        _hint('填入一把既有 API Key 的識別碼（key_id，格式如'
              ' ak_xxxxxxxxxxxxxxxx，不是 secure_code），送出後會依序'
              '執行「暫停 → 再次暫停（示範冪等）→ 復原」三個處置動作。'
              '可以先跑 NT-04 ApiKeyIssue 示範核發一把，再把核發出來的'
              ' key_id 填在這裡。'),
        _text('target_key_id', '要處置的 API Key 識別碼（key_id）',
              '從 /security/api-keys 頁面或 NT-04 核發流程的結果複製，'
              '格式如 ak_xxxxxxxxxxxxxxxx。這個值會經過變數替換'
              '（key_source=variable）解析出實際要處置的 Key。'),
        _textarea('suspend_reason', '暫停原因（選填）',
                   '只用在 suspend 動作，會寫入 api_keys.suspended_reason'
                   '（截斷 500 字）。resume 動作沒有對應的原因欄位。',
                   rows=2),
        _textarea('action_result', '處置摘要（由流程自動填寫）',
                   '由 OpFieldWrite 節點自動寫入；實際的狀態前後對照要'
                   '查 fw_node_execution_queue 或 /security/api-keys'
                   '頁面。', rows=6, disabled=True),
        _submit_button(),
    ],
}


FULL_DEMOS_STATIC = [
    {
        'form_code': 'NODEDEMO_NT04_APIKEYISSUE_FORM',
        'form_name': 'NT-04 ApiKeyIssue 示範表單（核發 API Key）',
        'form_schema': FORM_APIKEYISSUE_SCHEMA,
        'workflow_code': 'NODEDEMO_NT04_APIKEYISSUE_FLOW',
        'workflow_name': 'NT-04 ApiKeyIssue 示範（核發 API Key）',
        'description': NT04_DESCRIPTION,
        'graph': lambda: build_apikeyissue_graph(),
    },
    {
        'form_code': 'NODEDEMO_NT03_APIKEYACTION_FORM',
        'form_name': 'NT-03 ApiKeyAction 示範表單（API Key 處置）',
        'form_schema': FORM_APIKEYACTION_SCHEMA,
        'workflow_code': 'NODEDEMO_NT03_APIKEYACTION_FLOW',
        'workflow_name': 'NT-03 ApiKeyAction 示範（API Key 處置）',
        'description': NT03_DESCRIPTION,
        'graph': lambda: build_apikeyaction_graph(),
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
            created_by_name='provision_nodedemo_apikey',
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
    from modules.form_workflow.models import FwFormTemplate

    del opts
    db.session.execute(db.text("SET LOCAL app.is_system_admin = 'true'"))
    global SHOWCASE_CATEGORY_SECURE_CODE
    SHOWCASE_CATEGORY_SECURE_CODE = ensure_showcase_category(org).secure_code

    models = _workflow_models()
    osc = org.secure_code
    log(f'企業：{org.name}（{osc}）')
    load_node_icons(models)

    api_key_request_form = FwFormTemplate.query.filter_by(
        org_secure_code=osc,
        code=API_KEY_REQUEST_FORM_CODE,
        is_deleted=False,
    ).first()
    if not api_key_request_form:
        raise ValueError('找不到 API Key 申請單（code=API_KEY_REQUEST），請先確認 fresh defaults 已種入')
    log(f'  API Key 申請單：{api_key_request_form.secure_code}')

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
    parser = argparse.ArgumentParser(description='佈建 node展覽館的 ApiKeyIssue／ApiKeyAction 示範（B13）')
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
