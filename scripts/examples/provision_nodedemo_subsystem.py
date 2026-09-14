#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PF-252 B16 批次（最後一批）：node展覽館 —— SubSystemProvision（NT-16）示範（子系統配置）。

本檔佈建兩個流程：

1. NT-16 SubSystemProvision 示範（子系統配置）
   action='create'：呼叫 nocode_builder 模組的 SubSystemProvisionService，
   一次建出一個真實可用的 NoCode 子系統（子系統記錄、welcome 根頁面、
   專屬 SQLite（portal.db + portal_data.db）、Portal 公開路徑、開發者
   nocode_builder 模組使用權）。這個流程**會真的建立資源**，示範用的
   子系統名稱與 code 一律帶 NODEDEMO 字樣，方便日後辨識與清理。

2. NT-16 SubSystemProvision 示範（停用／刪除子系統）
   action='suspend' 與 'delete' 的示範，同時是流程 1 建出資源的清理工具。
   action 是字面值、不支援變數替換，所以用一個 Branch 節點依表單的
   target_action 分流到兩個各自寫死 action 的 SubSystemProvision 節點。

兩個流程互相搭配：先送流程 1 拿到 sub_system_code，再送流程 2 把它刪掉
（action=delete，會連 SQLite 目錄與 Portal 路徑一起清乾淨，不必手動下 SQL）。

目標企業固定是系統預設企業（Organization.code='SYSTEM'），分類固定是
「node展覽館」。。

前置條件（已於本批次動手前查證，見 PF-252 B16 回報）：
- SubSystemProvision **不是** org_restricted 節點（`workflow_node_definitions
  .org_restricted=false`），不需要企業節點授權。
- `SubSystemProvisionService.create_sub_system()` 需要 nocode_builder 模組已
  載入（`create_app()` 之後才能 import `modules.nocode_builder...`）。
  系統企業已有 nocode_builder 的 ROLE 型 ACL（見 module_access_control），
  且系統企業本身走 org_restricted 免合約路徑（不受此限）。
- **已知盤點發現（已記 PF-253，不影響本流程能不能跑）**：
  `provision_service.py::_SUB_SYSTEM_MENU_PARENT = 'sub_system'` 這個選單
  父節點 code，在全平台任何企業都不存在（查過 menu_defaults.py、所有
  migrations、所有模組 MODULE_INFO，皆無此 code）。這代表 create_sub_system()
  的「自動建立選單」步驟對所有企業永遠靜默失敗（記警告 log 後略過），
  不會擋住子系統本身的建立。

冪等：重跑會沿用既有表單／流程（依 code 找），bump revision 並重新發行
（會停用舊的已發行版本並建立新版）。填寫權限授予企業內所有非 EXTERNAL
的在職帳號。**本腳本本身不會建立或刪除任何子系統**——子系統的建立/清理
一律透過送單觸發流程節點執行，不在佈建階段發生。

用法：
    cd <repo>
    set -a && source .env && set +a
    venv/bin/python scripts/examples/provision_nodedemo_subsystem.py --dry-run
    venv/bin/python scripts/examples/provision_nodedemo_subsystem.py --apply

節點 config 欄位依 handler 原始碼確認：
    modules/form_workflow/services/node_handlers/sub_system_provision_handler.py
    modules/nocode_builder/services/provision_service.py（真正的資源建置邏輯）
範本：scripts/examples/provision_nodedemo_hrlookup.py（B15，最新腳本模式）
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


def _select(key, label, options, description='', default_value=None, required=False):
    comp = {
        'key': key, 'type': 'select', 'input': True, 'label': label, 'tableView': True,
        'dataSrc': 'values',
        'data': {'values': [{'label': lbl, 'value': val} for lbl, val in options]},
        'widget': 'html5',
    }
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
# 流程 1：NT-16 SubSystemProvision 示範（子系統配置）
# ---------------------------------------------------------------------------

CREATE_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'SubSystemProvision 是三合一節點（action=create/suspend/delete），'
    '本流程示範 action=create：呼叫 nocode_builder 模組的'
    ' SubSystemProvisionService.create_sub_system()，一次建出一個真正可用'
    '的 NoCode 子系統，包含：子系統本體記錄（dc_sub_systems）、一個'
    ' welcome 根頁面（空白 Page IR）、該子系統專屬的兩個 SQLite 檔案'
    '（portal.db 存帳號/角色/權限，portal_data.db 存子系統自己的業務'
    '資料，兩者位於 data/nocode_portals/<子系統secure_code>/ 下）、一組'
    '不可猜測的公開 Portal 路徑 code（供 /public/portal/<path_id>/... 對外'
    '存取），以及把指定的開發者加入子系統開發者名單並授予他'
    ' nocode_builder 模組使用權。這是一個會建立真實資源的節點，不是'
    '單純查資料或寫變數。\n\n'
    '【本流程的設定重點】\n'
    '- **action=create**：三合一動作之一。action 是節點 config 的字面值，'
    '不支援變數替換（handler 直接讀 config，不經過 replace_variables），'
    '所以沒辦法讓同一個節點用表單欄位決定要 create 還是 suspend/delete'
    '——那兩種動作留給另一個示範流程「NT-16 SubSystemProvision 示範'
    '（停用／刪除子系統）」，那邊會示範怎麼用 Branch 節點依表單輸入分流。\n'
    '- **sub_system_name=${f.system_name}**：支援變數替換，本流程直接讀'
    '表單欄位。示範預設值刻意帶 NODEDEMO 字樣，方便事後在 DB 或畫面上'
    '一眼認出這是示範資料，不影響功能——你可以改成任何名稱，不強制。\n'
    '- **sub_system_icon=${f.system_icon}**：選填，是子系統選單圖示的'
    ' class 名稱（RemixIcon），留空也不影響子系統本身能不能用，只是'
    '選單看起來沒有圖示（何況選單這步本來就會因為下面這條盤點發現而'
    '被跳過）。\n'
    '- **sub_system_developer 刻意留空**：留空時 handler 會退回'
    '「申請人」（也就是送這張單的人）。這代表**任何人送出這張示範單，'
    '都會讓自己被加進該子系統的開發者名單、並被授予 nocode_builder'
    ' 模組使用權**——這是三合一節點設計上的正常副作用，不是這個示範'
    '刻意加的功能，示範時請留意。\n'
    '- **子系統 code 由系統依名稱自動產生**（衝突會自動編號），無法'
    '自訂，這與大多數其他建立類節點一致。\n'
    '- **（盤點發現，已記 PF-253，不影響本節點能否使用）**'
    ' create_sub_system() 內建的「自動建立選單」步驟要找一個'
    ' code=sub_system 的選單當父節點，但這個 code 在全平台任何企業都'
    '不存在（menu_defaults.py、所有 migration、所有模組 MODULE_INFO'
    ' 都沒有），所以這一步在任何環境永遠靜默失敗（只記警告 log），'
    '子系統本身仍會正常建立，只是不會自動出現在選單上——反正 NoCode'
    ' 選單目前也是刻意隱藏中，這裡看不出額外差異。\n\n'
    '【怎麼看結果】\n'
    '1) 表單「子系統建置結果」欄位（OpFieldWrite 寫回）會列出這次建立的'
    ' sub_system_secure_code／code／menu_code。\n'
    '2) 查流程變數（**只有這三個**，menu_item_secure_code 與'
    ' portal_path_id 沒有寫進流程變數）：\n'
    "   SELECT var_name, var_value FROM fw_workflow_variables WHERE"
    " workflow_instance_secure_code='<實例 sc>' ORDER BY var_name;\n"
    '3) 要看 menu_item_secure_code／portal_path_id 這類沒進流程變數的'
    '欄位，查節點執行紀錄：\n'
    "   SELECT log_data FROM fw_node_execution_logs WHERE"
    " workflow_instance_id=(SELECT id FROM fw_workflow_instances WHERE"
    " secure_code='<實例 sc>') AND log_message='子系統建立成功';\n"
    '4) 直接查 DB 確認子系統真的存在：\n'
    "   SELECT secure_code, code, name, status, is_active, developers"
    " FROM dc_sub_systems WHERE code='<上面查到的 code>';\n"
    '5) 也可以直接開 NoCode 工作區網址（NoCode 選單目前隱藏中，直接輸入'
    '網址即可）：/nocode/workspace/<sub_system_secure_code>\n'
    '6) **用完別忘了處理**：帶著這裡輸出的 sub_system_code 去送'
    '「NT-16 SubSystemProvision 示範（停用／刪除子系統）」流程，選'
    ' delete，把示範建立的子系統清乾淨，不要留著。'
)

FORM_CREATE_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-16 SubSystemProvision 示範表單（建立子系統）'),
        _hint('送出後會呼叫 SubSystemProvision 節點（action=create），真的'
              '建立一個 NoCode 子系統（子系統記錄＋welcome 頁＋專屬'
              ' SQLite＋公開 Portal 路徑），你自己會被加進開發者名單。'
              '名稱請保留 NODEDEMO 字樣方便日後辨識，用完請用「停用／'
              '刪除子系統」流程清理，不要留著。'),
        _text('system_name', '子系統名稱', '會自動產生對應的 code（衝突'
              '自動編號），建議保留 NODEDEMO 前綴方便辨識與清理。',
              default_value='NODEDEMO_示範子系統', required=True),
        _text('system_icon', '選單圖示（選填）', 'RemixIcon class 名稱，'
              '留空也不影響子系統能不能用。',
              default_value='ri-flask-line'),
        _textarea('provision_summary', '子系統建置結果（由流程自動填寫）',
                   '由流程的 SubSystemProvision + OpFieldWrite 節點自動'
                   '寫入，送單者不需輸入。',
                   rows=10, disabled=True),
        _submit_button(),
    ],
}


def build_create_graph():
    summary_content = (
        '子系統已建立：\n'
        '名稱：${f.system_name}\n'
        'sub_system_secure_code：${v.sub_system_secure_code}\n'
        'sub_system_code：${v.sub_system_code}\n'
        'menu_code（自動建立選單這步因找不到父選單而被跳過，此值僅供'
        '參考不代表真的有選單）：${v.sub_system_menu_code}\n\n'
        '要清理這個示範子系統，請帶著上面的 sub_system_code 去送'
        '「NT-16 SubSystemProvision 示範（停用／刪除子系統）」流程，'
        '選「刪除」。\n\n'
        '流程執行代碼：${wi.exec_code}'
    )
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 100, 180,
              '流程入口，不需要任何前置設定。'),

        _node('node-Provision', 'SubSystemProvision', '建立子系統', {
            'action': 'create',
            'sub_system_name': '${f.system_name}',
            'sub_system_icon': '${f.system_icon}',
        }, 340, 180,
            'action=create。sub_system_developer 留空，退回申請人自己'
            '（送單者會被加入該子系統的開發者名單，並取得 nocode_builder'
            ' 模組使用權）。成功後寫入流程變數'
            ' sub_system_secure_code／sub_system_code／'
            'sub_system_menu_code。'),

        _node('node-Write', 'OpFieldWrite', '寫回建置結果', {
            'target_field': 'provision_summary',
            'content': summary_content,
        }, 580, 180,
            '把上一個節點寫入的流程變數整理成文字寫回表單，讓送單者'
            '不必查資料庫就能看到子系統的 secure_code 與 code。'),

        _node('node-Confirm', 'FormAdapter', '本人確認', {
            'assignee_type': 'INITIATOR',
            'selection_mode': 'single',
            'allow_comment': True,
            'require_comment': False,
            'use_custom_decisions': False,
        }, 820, 180,
            '簽核者固定是發起人自己（assignee_type=INITIATOR）——這一步'
            '只是讓流程像一張完整單據一樣有始有終，不是 SubSystemProvision'
            '的示範重點。確認即可推進到結束，子系統這時候早就已經建好了'
            '（建立動作發生在上游的 SubSystemProvision 節點，不是等這裡'
            '確認才生效）。'),

        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 1060, 180,
              '流程正常結束（finish_mode=detach），流程實例狀態變成'
              ' COMPLETED。子系統資源在此之前就已經建立完成，End 節點'
              '本身不會動到它。'),
    ]
    edges = [
        _edge('edge-start-provision', 'node-Start', 'node-Provision'),
        _edge('edge-provision-write', 'node-Provision', 'node-Write'),
        _edge('edge-write-confirm', 'node-Write', 'node-Confirm'),
        _edge('edge-confirm-end', 'node-Confirm', 'node-End', label='確認'),
    ]
    return _graph(nodes, edges)


# ---------------------------------------------------------------------------
# 流程 2：NT-16 SubSystemProvision 示範（停用／刪除子系統）
# ---------------------------------------------------------------------------

LIFECYCLE_DESCRIPTION = (
    '【這個節點做什麼】\n'
    '同一個 SubSystemProvision 節點的另外兩種動作：action=suspend'
    '（停用）與 action=delete（軟刪除）。本流程示範怎麼用它們，同時是'
    '「NT-16 SubSystemProvision 示範（子系統配置）」流程建出的示範子'
    '系統的清理工具——不必手動下 SQL，直接送這張單選「刪除」即可。\n\n'
    '【本流程的設定重點】\n'
    '- **action 是節點 config 的字面值，不支援變數替換**（handler 直接'
    '讀 config.action，不經過 replace_variables），所以沒辦法用一個'
    ' SubSystemProvision 節點讓表單決定要 suspend 還是 delete。本流程'
    '改用前置的 **Branch 節點**依表單的 target_action 欄位（值固定是'
    " 'suspend' 或 'delete' 兩者之一，字串相等比對天生互斥，不會同時"
    '命中兩條規則）分流到兩個各自寫死 action 的 SubSystemProvision'
    '節點，兩條分支最後匯流到同一個 OpFieldWrite／確認／結束節點。\n'
    '- **sub_system_code=${f.target_code}**：兩個節點都支援變數替換，'
    '讀的是子系統的 code（不是 secure_code）——填「NT-16'
    ' SubSystemProvision 示範（子系統配置）」流程輸出的'
    ' sub_system_code。\n'
    '- **suspend／delete 都不寫任何流程變數，只有訊息**：這與 create'
    '成功會寫三個流程變數不同，所以表單摘要只能用送單者填的'
    ' target_code／target_action 組文字說明，沒辦法在畫面上直接秀出'
    '「動作是否成功」，要確認結果得查 DB 或 fw_node_execution_logs。\n'
    '- **delete 是完整清理**：軟刪除子系統記錄（dc_sub_systems'
    '.is_deleted=true）、停用選單、**刪除**（不是停用）Portal 公開路徑'
    '的 lookup_items 記錄、整個刪掉該子系統的 SQLite 目錄（portal.db +'
    ' portal_data.db，`data/nocode_portals/<子系統secure_code>/` 整個'
    '不見）、並在開發者名下已經沒有其他子系統時撤銷他的'
    ' nocode_builder 模組使用權（若他還有其他子系統則保留權限，不會'
    '誤撤）。\n'
    '- **suspend 只做前兩項**：子系統記錄 is_active 變 false、選單同步'
    '停用，資料與 SQLite 檔案都保留不動，之後理論上可以手動改回'
    ' is_active=true 復原——但這個節點**沒有**對應的「恢復啟用」第四種'
    ' action，示範只到停用為止。\n'
    '- **填錯或已經處理過的 code 會讓節點回 error**：找不到指定 code 的'
    '子系統時，node_runner 會走 error 分支進 queue 的自動重試（3 次後'
    ' FAILED），流程會卡在 RUNNING 不會像 create 那樣安靜結束——這與'
    ' Os 系三兄弟「恆 success」的行為不同，代表填錯 code 需要人工'
    '處理才能讓流程收尾，示範時請務必先確認 code 填對、而且這個子'
    '系統還沒被刪除過。\n\n'
    '【怎麼看結果】\n'
    '1) 查 DB 確認狀態變化：\n'
    "   SELECT secure_code, code, name, is_active, status, is_deleted"
    " FROM dc_sub_systems WHERE code='<你填的 code>';\n"
    '2) 若選的是「刪除」，順便確認 SQLite 目錄與 Portal 路徑都清乾淨'
    '了（secure_code 要用上一步查到的那個）：\n'
    '   ls data/nocode_portals/<sub_system_secure_code>/'
    '（刪除後應該已經不存在）\n'
    "   SELECT * FROM lookup_items WHERE value_str='<sub_system_secure_"
    "code>';（刪除後應該 0 筆）\n"
    '3) 表單「處理結果摘要」欄位只會顯示你填的 code 與動作，不會顯示'
    '真正成功與否——真正的成敗要查 fw_node_execution_queue 該'
    ' SubSystemProvision 節點的 status：success 代表服務層回報成功'
    '（訊息會在 result 裡），error 代表找不到子系統或其他例外。'
)

FORM_LIFECYCLE_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-16 SubSystemProvision 示範表單（停用／刪除子系統）'),
        _hint('填入「建立子系統」流程輸出的 sub_system_code，選擇要'
              '停用還是刪除。選「刪除」會把該子系統與它的 SQLite 檔案、'
              'Portal 公開路徑一起清乾淨，這正是清理示範資料的正規'
              '做法，不需要手動下 SQL。'),
        _text('target_code', '目標子系統 code', '填「建立子系統」流程'
              '輸出的 sub_system_code（不是 sub_system_secure_code）。',
              required=True),
        _select('target_action', '要執行的動作',
                [('停用（suspend）', 'suspend'), ('刪除（delete）', 'delete')],
                '停用只關閉存取與選單，資料保留；刪除會連 SQLite 檔案'
                '與 Portal 路徑一起清除。',
                default_value='delete', required=True),
        _textarea('lifecycle_summary', '處理結果摘要（由流程自動填寫）',
                   '由流程的 OpFieldWrite 節點自動寫入，送單者不需輸入。'
                   '只顯示你填的輸入值，不代表節點實際執行成功與否。',
                   rows=10, disabled=True),
        _submit_button(),
    ],
}


def build_lifecycle_graph():
    summary_content = (
        '已對子系統送出處理請求：\n'
        'target_code：${f.target_code}\n'
        'target_action：${f.target_action}\n\n'
        '本節點不寫回任何流程變數，請自行查 DB 確認是否真的成功：\n'
        "SELECT secure_code, code, is_active, status, is_deleted"
        " FROM dc_sub_systems WHERE code='${f.target_code}';\n\n"
        '流程執行代碼：${wi.exec_code}'
    )
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 100, 180,
              '流程入口，不需要任何前置設定。'),

        _node('node-Route', 'Branch', '依動作分流', {
            'rules': [
                {
                    'name': '走停用',
                    'conditions': [
                        {'variable': '${f.target_action}', 'operator': '==', 'value': 'suspend'},
                    ],
                    'target_edges': ['edge-route-suspend'],
                },
                {
                    'name': '走刪除',
                    'conditions': [
                        {'variable': '${f.target_action}', 'operator': '==', 'value': 'delete'},
                    ],
                    'target_edges': ['edge-route-delete'],
                },
            ],
            'fallback': {
                'action': 'log',
                'log_message': 'target_action 既不是 suspend 也不是 delete，不執行任何動作',
            },
        }, 340, 260,
            '依表單的 target_action 分流。兩條規則的條件是字串相等'
            '比對不同的固定值，天生互斥，不會同時命中。表單欄位是'
            ' select 只給兩個選項，正常操作走不到 fallback；fallback'
            '設成 action=log（不推進任何出邊）純粹是防呆，不是本示範'
            '的重點。'),

        _node('node-Suspend', 'SubSystemProvision', '停用子系統', {
            'action': 'suspend',
            'sub_system_code': '${f.target_code}',
        }, 620, 100,
            'action=suspend。子系統 is_active 變 false、選單同步停用，'
            '資料與 SQLite 檔案都保留不動，不寫任何流程變數。'),

        _node('node-Delete', 'SubSystemProvision', '刪除子系統', {
            'action': 'delete',
            'sub_system_code': '${f.target_code}',
        }, 620, 340,
            'action=delete。軟刪除子系統記錄、停用選單、刪除 Portal'
            ' 公開路徑記錄、整個刪掉該子系統的 SQLite 目錄，並在'
            '開發者名下沒有其他子系統時撤銷 nocode_builder 模組使用權。'
            '這是清理「NT-16 SubSystemProvision 示範（子系統配置）」'
            '流程建出的示範資源時應該用的動作。'),

        _node('node-Write', 'OpFieldWrite', '寫回處理結果', {
            'target_field': 'lifecycle_summary',
            'content': summary_content,
        }, 860, 220,
            '把送單者填的 target_code／target_action 整理成文字寫回'
            '表單。suspend／delete 都不寫流程變數，所以這裡只能引用'
            '表單輸入值，無法顯示節點實際執行成功與否。'),

        _node('node-Confirm', 'FormAdapter', '本人確認', {
            'assignee_type': 'INITIATOR',
            'selection_mode': 'single',
            'allow_comment': True,
            'require_comment': False,
            'use_custom_decisions': False,
        }, 1100, 220,
            '簽核者固定是發起人自己（assignee_type=INITIATOR），只是讓'
            '流程有始有終，不是 SubSystemProvision 的示範重點。'),

        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 1340, 220,
              '流程正常結束（finish_mode=detach），流程實例狀態變成'
              ' COMPLETED。'),
    ]
    edges = [
        _edge('edge-start-route', 'node-Start', 'node-Route'),
        _edge('edge-route-suspend', 'node-Route', 'node-Suspend', label='停用'),
        _edge('edge-route-delete', 'node-Route', 'node-Delete', label='刪除'),
        _edge('edge-suspend-write', 'node-Suspend', 'node-Write'),
        _edge('edge-delete-write', 'node-Delete', 'node-Write'),
        _edge('edge-write-confirm', 'node-Write', 'node-Confirm'),
        _edge('edge-confirm-end', 'node-Confirm', 'node-End', label='確認'),
    ]
    return _graph(nodes, edges)


FULL_DEMOS_STATIC = [
    {
        'form_code': 'NODEDEMO_NT16_CREATE_FORM',
        'form_name': 'NT-16 SubSystemProvision 示範表單（建立子系統）',
        'form_schema': FORM_CREATE_SCHEMA,
        'workflow_code': 'NODEDEMO_NT16_CREATE_FLOW',
        'workflow_name': 'NT-16 SubSystemProvision 示範（子系統配置）',
        'description': CREATE_DESCRIPTION,
        'graph': lambda: build_create_graph(),
    },
    {
        'form_code': 'NODEDEMO_NT16_LIFECYCLE_FORM',
        'form_name': 'NT-16 SubSystemProvision 示範表單（停用／刪除子系統）',
        'form_schema': FORM_LIFECYCLE_SCHEMA,
        'workflow_code': 'NODEDEMO_NT16_LIFECYCLE_FLOW',
        'workflow_name': 'NT-16 SubSystemProvision 示範（停用／刪除子系統）',
        'description': LIFECYCLE_DESCRIPTION,
        'graph': lambda: build_lifecycle_graph(),
    },
]


# ---------------------------------------------------------------------------
# 寫入
# ---------------------------------------------------------------------------

def ensure_fill_permissions(db, models, org_sc, mapping, apply):
    """
    給示範表單開填寫權限（表單中心預設只放行 SYSTEM_ADMIN / FLOW_DESIGNER /
    FORM_DESIGNER，ORG_ADMIN 與一般 EMPLOYEE 都不在內）。
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
            created_by_name='provision_nodedemo_subsystem',
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
    parser = argparse.ArgumentParser(description='佈建 node展覽館的 SubSystemProvision 示範（B16）')
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
            log('\n已寫入。到 /forms/center 的「填寫表單」就看得到這張單。')
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
