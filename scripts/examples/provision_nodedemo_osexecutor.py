#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PF-252 B6 批次：node展覽館 —— OsExecutor（NT-28）示範。

使用者點名的批次，原話：「例如 OsExecutor 可以簡單的執行 ls -al 或取得系統時間
等變數填回表單，或先透過表單的 n 個簽核給 n 個 OsExecutor 展示 n 個設定方式的差別」。
本檔佈建三個流程：

    NT-28 OsExecutor 示範（取得系統資訊填回表單）
        最直觀的入門示範：執行 date 與 ls -al 兩個唯讀命令，結果整段寫回表單欄位。

    NT-28 OsExecutor 示範（命令引號化與工作目錄的差異）
        OpSet 先設一個帶 shell 特殊字元的變數，用 ${v.x}（預設引號化）與
        ${v.x!raw}（原樣代入）各執行一次同樣的 echo 命令，對照 shlex.quote() 的
        實際效果；接著再用 cwd 留空（臨時目錄）與 cwd 明確指定兩種設定各跑一次
        pwd+ls，對照工作目錄的差異。四個 OsExecutor 之間各插一個 FormAdapter
        （assignee_type=INITIATOR）自簽關卡，送單者一個人就能走完全程。

    NT-28 OsExecutor 示範（逾時與失敗判定：四分法怎麼記）
        三個 OsExecutor：timeout_seconds 故意小於命令實際所需時間（逾時分類）、
        同一命令但給足時間的對照組（正常分類）、對不存在路徑執行 ls 導致 exit
        code 不符 expect_exit_codes（例外分類）。刻意示範「queue 的 status 全部
        是 SUCCESS（綠色），真正的成敗要看流程變數與 fw_node_execution_logs」。

目標企業固定是系統預設企業（Organization.code='SYSTEM'），分類固定是「node展覽館」
。。系統企業已對 OsExecutor
有效授權（workflow_node_org_grants），.env 的 OS_NODE_ENABLED=1，不需額外開通。

冪等：重跑會沿用既有表單／流程（依 code 找），bump revision 並重新發行（會停用
舊的已發行版本並建立新版）。填寫權限授予企業內所有非 EXTERNAL 的在職帳號。

用法：
    cd <repo>
    set -a && source .env && set +a
    venv/bin/python scripts/examples/provision_nodedemo_osexecutor.py --dry-run
    venv/bin/python scripts/examples/provision_nodedemo_osexecutor.py --apply

節點 config 欄位依 handler 原始碼確認：
    modules/form_workflow/services/node_handlers/os_executor_handler.py
    modules/form_workflow/services/node_handlers/opset_handler.py
    modules/form_workflow/services/node_handlers/fieldwrite_handler.py
    modules/form_workflow/services/node_handlers/formadapter_handler.py
OpFieldWrite／FormAdapter 各節）
規格：dev-notes/OS_EXECUTOR_SPEC.md（第十四節「實作後記」為準，與規格本文有六處差異）

安全限制（派工要求）：全部命令唯讀無副作用（date／ls／echo／sleep／pwd），
不建立、不刪除任何檔案，不需要 sudo。故意逾時／故意失敗的節點皆設
notify_on_exception=False，避免示範過程觸發真實 email 通知（收件人
admin-demo@系統預設企業網域 是不存在的網域，觸發只會產生無謂的失敗通知，
不影響本節點的示範重點——四分法本身不受這個設定影響）。
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
DEMO_DIR = '/opt/tmp/verify'  # 唯讀示範目錄，全平台驗收 log 都放這裡，不做任何寫入

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
# 流程一：NT-28 OsExecutor 示範（取得系統資訊填回表單）
# ---------------------------------------------------------------------------

def build_intro_graph():
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 220, 220,
              '流程入口，不需要任何前置設定。'),
        _node('node-Time', 'OsExecutor', '取得伺服器時間', {
            'command': "date '+%Y-%m-%d %H:%M:%S %Z'",
            'result_var': 'os_time',
            'timeout_seconds': 15,
            'expect_exit_codes': [0],
        }, 500, 100,
            '執行 date 指令取得伺服器目前的日期時間，是最基本、完全無副作用的'
            'OS 命令示範。'),
        _node('node-WriteTime', 'OpFieldWrite', '把時間寫回表單', {
            'target_field': 'server_time_result',
            'content': '伺服器目前時間：${v.os_time_stdout}\n'
                       '（判定結果：${v.os_time_result}，退出碼：${v.os_time_exit_code}，'
                       '耗時：${v.os_time_duration_ms} 毫秒）',
            'content_type': 'text',
        }, 780, 100,
            '把上一個 OsExecutor 節點寫入的流程變數 os_time_stdout 組成一段文字，'
            '寫回表單欄位 server_time_result，送單者重新整理表單就看得到。'),
        _node('node-Dir', 'OsExecutor', '列出示範目錄內容', {
            'command': f'ls -al {DEMO_DIR}',
            'result_var': 'os_dir',
            'timeout_seconds': 15,
            'expect_exit_codes': [0],
        }, 500, 340,
            f'執行 ls -al {DEMO_DIR} 列出既有目錄的內容（唯讀操作，'
            '不建立、不刪除、不修改任何檔案），示範把系統資訊查詢結果整段帶進流程。'),
        _node('node-WriteDir', 'OpFieldWrite', '把目錄內容寫回表單', {
            'target_field': 'dir_listing_result',
            'content': f'{DEMO_DIR} 目錄內容：\n${{v.os_dir_stdout}}\n'
                       '（判定結果：${v.os_dir_result}，退出碼：${v.os_dir_exit_code}）',
            'content_type': 'text',
        }, 780, 340,
            '把 ls -al 的輸出寫回表單欄位 dir_listing_result。'),
        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 1060, 220,
              '流程正常結束，記為 COMPLETED。'),
    ]
    edges = [
        _edge('edge-start', 'node-Start', 'node-Time'),
        _edge('edge-time-write', 'node-Time', 'node-WriteTime'),
        _edge('edge-write-dir', 'node-WriteTime', 'node-Dir'),
        _edge('edge-dir-write', 'node-Dir', 'node-WriteDir'),
        _edge('edge-write-end', 'node-WriteDir', 'node-End'),
    ]
    return _graph(nodes, edges)


NT28_INTRO_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'OsExecutor 讓流程在平台主機上執行任意命令，取得命令的輸出、退出碼、耗時等'
    '結果，寫進流程變數供後續節點使用。它是流程系統唯一能直接碰觸作業系統的'
    '節點，執行權限等同 executor 進程的 OS 帳號。\n\n'
    '【本流程的設定重點】\n'
    '- 兩個 OsExecutor 節點都只是唯讀命令（date、ls -al），沒有任何副作用，'
    '完全可以放心重複執行。\n'
    '- result_var 分別設 os_time／os_dir，OsExecutor 會依此前綴寫出'
    ' {result_var}_result／{result_var}_stdout／{result_var}_exit_code 等一組流程'
    '變數（詳見「怎麼看結果」）。\n'
    '- expect_exit_codes 都明確設為 [0]（其實是預設值，這裡刻意寫出來讓讀者看到'
    '這個欄位存在）：只有退出碼等於 0 才會被判定為 ok，否則會是 exception。\n'
    '- 每個 OsExecutor 後面都接一個 OpFieldWrite，把 ${v.os_time_stdout}／'
    '${v.os_dir_stdout} 組成一段可讀文字直接寫回表單欄位——這是本流程要示範的'
    '核心用法：「命令輸出 → 流程變數 → 表單欄位」，讓送單的人不必查資料庫或 log，'
    '重新整理表單就能看到 OS 層取得的資訊。\n\n'
    '【怎麼看結果】\n'
    '送單後回到「填寫表單」重新打開這張單，表單欄位 server_time_result 會顯示'
    '伺服器時間、dir_listing_result 會顯示目錄內容——這是最直接的證據。'
    '更完整的執行細節在流程變數 os_time_result／os_dir_result（值應為 ok）、'
    'os_time_stdout／os_dir_stdout（完整輸出，超過 4KB 會截斷）；'
    '若想確認命令真的有被執行、多久完成，可查 os_time_duration_ms／'
    'os_dir_duration_ms。命令輸出同時也會被摘要記進'
    ' fw_node_execution_logs（INFO 等級），但完整內容以表單欄位與流程變數為準。'
)

FORM_INTRO_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-28 OsExecutor 示範表單（取得系統資訊填回表單）'),
        _hint('送出後流程會自動執行 date 與 ls -al 兩個命令，結果會寫回下面兩個欄位。'
              '送出當下這兩個欄位還是空的，流程跑完（通常幾秒內）後重新整理本頁'
              '才看得到內容。'),
        _text('applicant_note', '備註（非必填）'),
        _textarea('server_time_result', '伺服器時間查詢結果（由流程自動填入）',
                   '此欄位由 OsExecutor + OpFieldWrite 自動寫入，不需要手動填寫。'),
        _textarea('dir_listing_result', '目錄列表查詢結果（由流程自動填入）',
                   '此欄位由 OsExecutor + OpFieldWrite 自動寫入，不需要手動填寫。',
                   rows=10),
        _submit_button(),
    ],
}


# ---------------------------------------------------------------------------
# 流程二：NT-28 OsExecutor 示範（命令引號化與工作目錄的差異）
# ---------------------------------------------------------------------------

def build_config_a_graph():
    payload = 'hello ; echo INJECTED_BY_RAW'
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 180, 260,
              '流程入口，不需要任何前置設定。'),
        _node('node-Set', 'OpSet', '設定含特殊字元的變數', {
            'operations': [
                {'target_var': 'nt28_payload', 'operation': 'set', 'value': payload},
            ],
        }, 420, 260,
            f'把字面值「{payload}」寫進流程變數 nt28_payload，做為底下兩種插值'
            '方式的對照組——這個值包含 shell 的分號，正常情況下不應該被當成'
            '第二條命令執行。'),

        _node('node-OsQuoted', 'OsExecutor', '插值方式 A：預設引號化', {
            'command': 'echo ${v.nt28_payload}',
            'result_var': 'os_quoted',
            'timeout_seconds': 15,
        }, 660, 100,
            '命令模板裡 ${v.nt28_payload} 用預設語法插入。OsExecutor 對所有沒有'
            '標記 !raw 的變數插值一律先做 shlex.quote()，把整個代入值包成單一'
            'shell 詞——即使值裡有分號，也只會被當成 echo 的一個純文字參數。'),
        _node('node-WriteQuoted', 'OpFieldWrite', '記錄插值方式 A 的結果', {
            'target_field': 'quoted_result',
            'content': '【插值方式 A：預設引號化】\n'
                       '指令樣板：echo ${v.nt28_payload}\n'
                       '實際輸出：${v.os_quoted_stdout}\n'
                       '（判定結果：${v.os_quoted_result}）',
        }, 900, 100, '把插值方式 A 的執行結果寫回表單，供下一關卡的人核對。'),
        _node('node-Approve1', 'FormAdapter', '確認已檢視 A，繼續看 B',
              _approve_config('ack_quoted', '已檢視，繼續看插值方式 B', 'edge-to-raw'),
              1140, 100,
              '停下來讓送單者（本流程一律自簽）先看完插值方式 A 的結果，'
              '再繼續看插值方式 B——兩者要對照著看才看得出差異。'),

        _node('node-OsRaw', 'OsExecutor', '插值方式 B：!raw 原樣代入', {
            'command': 'echo ${v.nt28_payload!raw}',
            'result_var': 'os_raw',
            'timeout_seconds': 15,
        }, 660, 260,
            '同一個變數改用 ${v.nt28_payload!raw} 插入。加上 !raw 之後代入值'
            '完全不做引號化，字面上的分號會被 shell 當成命令分隔符號解讀——'
            '這代表「echo」之後其實變成執行了兩條命令。'),
        _node('node-WriteRaw', 'OpFieldWrite', '記錄插值方式 B 的結果', {
            'target_field': 'raw_result',
            # 注意：這裡刻意不寫字面的 ${v.nt28_payload!raw}——OpFieldWrite 的
            # content 走的是 base.py::replace_variables() 通用解析，它不認得
            # "!raw" 這個標記（!raw 只有 os_executor_handler.py 自己的命令模板
            # 解析器認得），把 "nt28_payload!raw" 當成一個不存在的變數名查詢，
            # 靜默回空字串。這不是平台 bug（規格從未宣稱 !raw 是跨節點通用語法），
            # 純粹是本示範腳本一開始想偷懶重複展示模板文字時撞到的設計陷阱，
            # 已在此改用純文字描述，不再嵌入字面 ${...} 語法。
            'content': '【插值方式 B：!raw 原樣代入】\n'
                       '指令樣板：對 nt28_payload 變數加上 !raw 標記後執行 echo'
                       '（不會做 shlex.quote()）\n'
                       '實際輸出（注意這裡會有兩行）：\n${v.os_raw_stdout}\n'
                       '（判定結果：${v.os_raw_result}）',
        }, 900, 260, '把插值方式 B 的執行結果寫回表單。'),
        _node('node-Approve2', 'FormAdapter', '確認已檢視 B，繼續看工作目錄對照',
              _approve_config('ack_raw', '已檢視，繼續看工作目錄設定', 'edge-to-cwd-default'),
              1140, 260,
              '停下來讓送單者對照插值方式 A／B 兩段輸出的差異，再繼續看'
              '工作目錄（cwd）的設定對照。'),

        _node('node-OsCwdDefault', 'OsExecutor', '工作目錄 C：不設定 cwd', {
            'command': 'pwd && ls',
            'result_var': 'os_cwd_default',
            'timeout_seconds': 15,
        }, 660, 420,
            'config 裡沒有 cwd 這個 key。OsExecutor 在這種情況下會自動建立一個'
            '空的臨時目錄當作工作目錄——pwd 會顯示一個臨時路徑，ls 應該是空的'
            '（因為是全新建立的空目錄）。'),
        _node('node-WriteCwdDefault', 'OpFieldWrite', '記錄工作目錄 C 的結果', {
            'target_field': 'cwd_default_result',
            'content': '【工作目錄 C：未設定 cwd（自動使用臨時目錄）】\n'
                       '${v.os_cwd_default_stdout}\n'
                       '（判定結果：${v.os_cwd_default_result}）',
        }, 900, 420, '把「未設定 cwd」這組設定的執行結果寫回表單。'),
        _node('node-Approve3', 'FormAdapter', '確認已檢視 C，繼續看 D',
              _approve_config('ack_cwd_default', '已檢視，繼續看明確指定 cwd', 'edge-to-cwd-explicit'),
              1140, 420,
              '停下來讓送單者先看未設定 cwd 的結果，再對照明確指定 cwd 的結果。'),

        _node('node-OsCwdExplicit', 'OsExecutor', '工作目錄 D：明確指定 cwd', {
            'command': 'pwd && ls',
            'cwd': DEMO_DIR,
            'result_var': 'os_cwd_explicit',
            'timeout_seconds': 15,
        }, 1380, 420,
            f'config 明確指定 cwd={DEMO_DIR}（一個既存的唯讀示範目錄）。同樣的'
            'pwd && ls 命令，這次 pwd 會顯示這個真實路徑，ls 會列出目錄下'
            '真正的檔案——與上一個節點（未設定 cwd）形成直接對照。'),
        _node('node-WriteCwdExplicit', 'OpFieldWrite', '記錄工作目錄 D 的結果', {
            'target_field': 'cwd_explicit_result',
            'content': f'【工作目錄 D：明確指定 cwd={DEMO_DIR}】\n'
                       '${v.os_cwd_explicit_stdout}\n'
                       '（判定結果：${v.os_cwd_explicit_result}）',
        }, 1620, 420, '把「明確指定 cwd」這組設定的執行結果寫回表單。'),
        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 1860, 260,
              '流程正常結束，記為 COMPLETED。'),
    ]
    edges = [
        _edge('edge-start', 'node-Start', 'node-Set'),
        _edge('edge-set-quoted', 'node-Set', 'node-OsQuoted'),
        _edge('edge-quoted-write', 'node-OsQuoted', 'node-WriteQuoted'),
        _edge('edge-write-approve1', 'node-WriteQuoted', 'node-Approve1'),
        _edge('edge-to-raw', 'node-Approve1', 'node-OsRaw', '已檢視，繼續看 B'),
        _edge('edge-raw-write', 'node-OsRaw', 'node-WriteRaw'),
        _edge('edge-write-approve2', 'node-WriteRaw', 'node-Approve2'),
        _edge('edge-to-cwd-default', 'node-Approve2', 'node-OsCwdDefault', '已檢視，繼續看工作目錄設定'),
        _edge('edge-cwddefault-write', 'node-OsCwdDefault', 'node-WriteCwdDefault'),
        _edge('edge-write-approve3', 'node-WriteCwdDefault', 'node-Approve3'),
        _edge('edge-to-cwd-explicit', 'node-Approve3', 'node-OsCwdExplicit', '已檢視，繼續看明確指定 cwd'),
        _edge('edge-cwdexplicit-write', 'node-OsCwdExplicit', 'node-WriteCwdExplicit'),
        _edge('edge-write-end', 'node-WriteCwdExplicit', 'node-End'),
    ]
    return _graph(nodes, edges)


NT28_CONFIG_A_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'OsExecutor 讓流程在平台主機上執行任意命令。命令模板裡的 ${...} 插值方式與'
    'cwd（工作目錄）設定，會直接影響命令實際執行的內容與環境。本流程用四個'
    'OsExecutor 節點兩兩對照這兩個維度的差異，中間各插一個自簽關卡讓讀者'
    '一步步看清楚每組設定的效果，一個人就能走完全程。\n\n'
    '【本流程的設定重點】\n'
    '- 插值方式 A（預設）／B（!raw）：先用 OpSet 設一個帶分號的變數'
    ' nt28_payload="hello ; echo INJECTED_BY_RAW"，同一個 echo 命令模板分別用'
    ' ${v.nt28_payload}（預設）與 ${v.nt28_payload!raw}（原樣代入）插入。'
    '預設方式會先 shlex.quote() 才代入，分號只是文字的一部分，輸出只有一行'
    '（整段字面值）；!raw 方式完全不引號化，分號被 shell 當成命令分隔符號，'
    '實際上變成執行了兩條命令，輸出會多一行「INJECTED_BY_RAW」——這正是規格'
    '文件強調「!raw 只在完全信任來源時才能用」的原因：改成別的值，若這個變數'
    '來自表單欄位（填表人可控），!raw 就等於讓填表人取得設計師的執行權限。\n'
    '- 工作目錄 C（未設定 cwd）／D（明確指定 cwd）：同樣的 pwd && ls 命令，'
    '不設定 cwd 時 OsExecutor 會自動建立一個空的臨時目錄執行，pwd 顯示臨時'
    f'路徑、ls 應為空；明確指定 cwd={DEMO_DIR} 時 pwd 顯示這個真實路徑、'
    'ls 列出目錄下真正的檔案。改成別的值：cwd 若指向不存在的目錄，節點會直接'
    '判定為設定錯誤（error），不會退回臨時目錄。\n\n'
    '【怎麼看結果】\n'
    '送單後依序完成三個自簽關卡（assignee_type=INITIATOR，都是自己簽自己的），'
    '每次簽核前先重新整理表單，對照 quoted_result／raw_result／'
    'cwd_default_result／cwd_explicit_result 四個欄位的內容差異。也可以直接查'
    '流程變數 os_quoted_stdout（應為一行）與 os_raw_stdout（應為兩行，第二行是'
    ' INJECTED_BY_RAW）——這組對照比文字說明更能看出引號化的實際效果。'
)

FORM_CONFIG_A_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-28 OsExecutor 示範表單（命令引號化與工作目錄的差異）'),
        _hint('送出後會依序執行「插值方式 A」「插值方式 B」「工作目錄 C」「工作目錄 D」'
              '四個 OsExecutor 節點，中間各插一個待簽任務（指派給你自己），'
              '請到「表單中心」的待簽清單依序點開簽核，每次簽核前先看一次'
              '對應的結果欄位再繼續。'),
        _text('applicant_note', '備註（非必填）'),
        _textarea('quoted_result', '插值方式 A：預設引號化（由流程自動填入）'),
        _textarea('raw_result', '插值方式 B：!raw 原樣代入（由流程自動填入）'),
        _textarea('cwd_default_result', '工作目錄 C：未設定 cwd（由流程自動填入）'),
        _textarea('cwd_explicit_result', '工作目錄 D：明確指定 cwd（由流程自動填入）'),
        _submit_button(),
    ],
}


# ---------------------------------------------------------------------------
# 流程三：NT-28 OsExecutor 示範（逾時與失敗判定：四分法怎麼記）
# ---------------------------------------------------------------------------

def build_config_b_graph():
    bad_path = f'{DEMO_DIR}/this_directory_does_not_exist_at_all_nodedemo'
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 180, 220,
              '流程入口，不需要任何前置設定。'),

        _node('node-OsTimeout', 'OsExecutor', '故意逾時：timeout 小於命令耗時', {
            'command': 'sleep 6',
            'result_var': 'os_timeout',
            'timeout_seconds': 2,
            'kill_on_timeout': 'group',
            'notify_on_exception': False,
        }, 460, 60,
            '命令是 sleep 6（需要 6 秒才會結束），但 timeout_seconds 故意設成 2 秒。'
            '在時限內沒有結束，OsExecutor 會把整個 process group 收乾淨，四分法'
            '判定為 timeout。notify_on_exception 關閉是刻意的（避免示範觸發真實'
            'email 通知），不影響四分法本身的判定。'),
        _node('node-WriteTimeout', 'OpFieldWrite', '記錄逾時結果', {
            'target_field': 'timeout_result',
            'content': '【逾時示範：timeout_seconds=2，命令 sleep 6】\n'
                       '判定結果：${v.os_timeout_result}\n'
                       '是否被強制中止：${v.os_timeout_killed}\n'
                       '耗時：${v.os_timeout_duration_ms} 毫秒\n'
                       '※ 這一步在流程管理頁一樣顯示成功（queue status=SUCCESS），'
                       '真正逾時的證據在上面「判定結果」這一行。',
        }, 700, 60, '把逾時示範的判定結果寫回表單，這是本流程最重要的一個對照。'),
        _node('node-Approve1', 'FormAdapter', '確認已檢視逾時結果，繼續看正常對照組',
              _approve_config('ack_timeout', '已檢視，繼續看正常對照組', 'edge-to-normal'),
              940, 60,
              '停下來讓送單者先看逾時示範的結果，再繼續看時限足夠的對照組。'),

        _node('node-OsNormal', 'OsExecutor', '正常對照組：timeout 遠大於命令耗時', {
            'command': 'sleep 2',
            'result_var': 'os_normal',
            'timeout_seconds': 15,
        }, 460, 220,
            '同樣是 sleep，這次命令只需要 2 秒，timeout_seconds 給了 15 秒，'
            '時限內正常結束，四分法判定為 ok——與上一個節點的 timeout 直接對照，'
            '差異只在 timeout_seconds 這一個設定值。'),
        _node('node-WriteNormal', 'OpFieldWrite', '記錄正常對照組結果', {
            'target_field': 'normal_result',
            'content': '【正常對照組：timeout_seconds=15，命令 sleep 2】\n'
                       '判定結果：${v.os_normal_result}\n'
                       '耗時：${v.os_normal_duration_ms} 毫秒',
        }, 700, 220, '把正常對照組的判定結果寫回表單。'),
        _node('node-Approve2', 'FormAdapter', '確認已檢視正常對照組，繼續看故意失敗示範',
              _approve_config('ack_normal', '已檢視，繼續看故意失敗示範', 'edge-to-fail'),
              940, 220,
              '停下來讓送單者對照逾時與正常兩種結果，再繼續看第三種'
              '（退出碼不符預期）分類。'),

        _node('node-OsFail', 'OsExecutor', '故意失敗：對不存在的路徑執行 ls', {
            'command': f'ls {bad_path}',
            'result_var': 'os_fail',
            'timeout_seconds': 15,
            'expect_exit_codes': [0],
            'notify_on_exception': False,
        }, 460, 380,
            f'對一個刻意不存在的路徑（{bad_path}）執行 ls，命令本身不會建立或'
            '刪除任何東西，但一定會失敗——ls 對不存在的路徑會回非 0 的退出碼，'
            '不符合 expect_exit_codes=[0]，四分法判定為 exception。'),
        _node('node-WriteFail', 'OpFieldWrite', '記錄故意失敗的結果', {
            'target_field': 'fail_result',
            'content': '【故意失敗示範：對不存在的路徑執行 ls，expect_exit_codes=[0]】\n'
                       '判定結果：${v.os_fail_result}\n'
                       '退出碼：${v.os_fail_exit_code}\n'
                       'stderr：${v.os_fail_stderr}\n'
                       '※ 這一步在「流程管理」頁一樣顯示成功（queue status=SUCCESS，'
                       '因為 OsExecutor 刻意不用 fail() 的自動重試機制），指令'
                       '實際上失敗了——請對照本頁「判定結果」欄位（應為 exception）'
                       '與 fw_node_execution_logs 的 ERROR 記錄，不要只看流程管理頁'
                       '的顏色。',
        }, 700, 380, '這是本流程最核心的一個示範：queue 是綠的，指令是失敗的。'),
        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 940, 380,
              '流程正常結束，記為 COMPLETED——即使中間有節點的命令執行失敗，'
              '流程本身仍然完整跑完（因為 OsExecutor 恆回 status=success）。'),
    ]
    edges = [
        _edge('edge-start-timeout', 'node-Start', 'node-OsTimeout'),
        _edge('edge-timeout-write', 'node-OsTimeout', 'node-WriteTimeout'),
        _edge('edge-write-approve1', 'node-WriteTimeout', 'node-Approve1'),
        _edge('edge-to-normal', 'node-Approve1', 'node-OsNormal', '已檢視，繼續看正常對照組'),
        _edge('edge-normal-write', 'node-OsNormal', 'node-WriteNormal'),
        _edge('edge-write-approve2', 'node-WriteNormal', 'node-Approve2'),
        _edge('edge-to-fail', 'node-Approve2', 'node-OsFail', '已檢視，繼續看故意失敗示範'),
        _edge('edge-fail-write', 'node-OsFail', 'node-WriteFail'),
        _edge('edge-write-end', 'node-WriteFail', 'node-End'),
    ]
    return _graph(nodes, edges)


NT28_CONFIG_B_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'OsExecutor 對命令執行結果採「四分法」（ok／exception／timeout／dispatched），'
    '而且**四種結果全部回 status=success**——這是刻意設計，不是缺陷：有副作用的'
    '命令不能被平台自動重跑 3 次，所以 OsExecutor 刻意避開一般節點失敗時的自動'
    '重試機制。代價是流程管理頁看不出命令失敗過，真正的成敗必須看流程變數與'
    ' log。本流程用三個 OsExecutor 節點示範四分法中的三種分類。\n\n'
    '【本流程的設定重點】\n'
    '- 逾時（timeout）：命令是 sleep 6，timeout_seconds 故意設成 2 秒，時限內'
    '沒有結束，OsExecutor 收乾淨整個 process group 後判定為 timeout。\n'
    '- 正常（ok）：同樣是 sleep，但改成 sleep 2、timeout_seconds 給 15 秒，'
    '時限內正常結束，判定為 ok——與上一個節點的差異只在 timeout_seconds 這'
    '一個設定值，藉此看出「逾時」不是命令本身的問題，是設定與命令耗時的'
    '相對關係。\n'
    '- 例外（exception）：對一個不存在的路徑執行 ls，退出碼不是 0，不符合'
    ' expect_exit_codes=[0]，判定為 exception。這個命令本身沒有任何副作用'
    '（失敗的 ls 不會建立或刪除任何東西），純粹用來示範「退出碼不符預期」'
    '這種失敗分類。\n\n'
    '【怎麼看結果，這是本流程最重要的一段】\n'
    '三個節點跑完後，流程實例的狀態與 fw_node_execution_queue 每一列的'
    ' status 都會是成功（COMPLETED／SUCCESS），**光看流程管理頁會誤以為'
    '一切正常**。要看到真相必須查兩個地方：(1) 流程變數'
    ' os_timeout_result／os_normal_result／os_fail_result——正確答案分別是'
    ' timeout／ok／exception；(2) fw_node_execution_logs 裡 log_level=ERROR'
    '的記錄，逾時與例外的節點各會留一筆，正常的節點不會。表單欄位'
    ' timeout_result／normal_result／fail_result 也會把這幾個流程變數組成'
    '文字寫回，方便不查資料庫就能對照。'
)

FORM_CONFIG_B_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-28 OsExecutor 示範表單（逾時與失敗判定：四分法怎麼記）'),
        _hint('送出後會依序執行「故意逾時」「正常對照組」「故意失敗」三個 OsExecutor'
              '節點，中間各插一個待簽任務（指派給你自己）。這三個節點在流程管理頁'
              '都會顯示成功，請對照下面三個欄位與流程變數才看得出真正的判定結果。'),
        _text('applicant_note', '備註（非必填）'),
        _textarea('timeout_result', '逾時示範（由流程自動填入）'),
        _textarea('normal_result', '正常對照組（由流程自動填入）'),
        _textarea('fail_result', '故意失敗示範（由流程自動填入）'),
        _submit_button(),
    ],
}


FULL_DEMOS_STATIC = [
    {
        'form_code': 'NODEDEMO_NT28_INTRO_FORM',
        'form_name': 'NT-28 OsExecutor 示範表單（取得系統資訊填回表單）',
        'form_schema': FORM_INTRO_SCHEMA,
        'workflow_code': 'NODEDEMO_NT28_INTRO_FLOW',
        'workflow_name': 'NT-28 OsExecutor 示範（取得系統資訊填回表單）',
        'description': NT28_INTRO_DESCRIPTION,
        'graph': lambda: build_intro_graph(),
    },
    {
        'form_code': 'NODEDEMO_NT28_CONFIG_A_FORM',
        'form_name': 'NT-28 OsExecutor 示範表單（命令引號化與工作目錄的差異）',
        'form_schema': FORM_CONFIG_A_SCHEMA,
        'workflow_code': 'NODEDEMO_NT28_CONFIG_A_FLOW',
        'workflow_name': 'NT-28 OsExecutor 示範（命令引號化與工作目錄的差異）',
        'description': NT28_CONFIG_A_DESCRIPTION,
        'graph': lambda: build_config_a_graph(),
    },
    {
        'form_code': 'NODEDEMO_NT28_CONFIG_B_FORM',
        'form_name': 'NT-28 OsExecutor 示範表單（逾時與失敗判定：四分法怎麼記）',
        'form_schema': FORM_CONFIG_B_SCHEMA,
        'workflow_code': 'NODEDEMO_NT28_CONFIG_B_FLOW',
        'workflow_name': 'NT-28 OsExecutor 示範（逾時與失敗判定：四分法怎麼記）',
        'description': NT28_CONFIG_B_DESCRIPTION,
        'graph': lambda: build_config_b_graph(),
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
            created_by_name='provision_nodedemo_osexecutor',
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
    parser = argparse.ArgumentParser(description='佈建 node展覽館的 OsExecutor 示範（B6）')
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
