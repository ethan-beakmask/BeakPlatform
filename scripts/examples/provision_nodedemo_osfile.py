#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PF-252 B7 批次：node展覽館 —— OsFileRead（NT-29）／OsFileWrite（NT-30）示範。

本檔佈建四個流程：

    NT-29 OsFileRead 示範（讀取檔案內容）
        入門：用 tail 模式讀 /opt/tmp/frtest/sample.log 最後 10 行寫回表單；
        接著示範用既有的 symlink（evil.link -> /etc/passwd）測試路徑逃逸，
        驗證 base_dir 白名單的 realpath 檢查擋不擋得住。

    NT-29 OsFileRead 示範（不同擷取模式的差別）
        八個 OsFileRead 節點依序對照 mode（head/tail/around）、occurrence
        （first/last/all）、match_mode（literal/regex）、match_scope
        （anywhere/line_start）四個維度的實際差異，中間插三個自簽關卡分組
        （基本模式 → occurrence 對照 → regex 對照 → match_scope 對照）。

    NT-30 OsFileWrite 示範（寫入檔案）
        把使用者輸入的內容寫進 /opt/tmp/fwtest/nodedemo-intro.txt；接著故意用
        同一個 base_dir 呼叫 OsFileRead 嘗試讀回剛寫的檔案——這一步會失敗，
        因為 os_file_read_base_dirs 只允許 /opt/tmp/frtest，與
        os_file_write_base_dirs 的 /opt/tmp/fwtest 完全不重疊，這正是
        「可讀不等於可寫」最直接的證據；接著再示範對既有 symlink
        （evil-link.log）寫入會被拒絕。

    NT-30 OsFileWrite 示範（換行處理的差別）
        對同一個檔案連續寫入三次，分別對照 newline_smart 預設開啟（一筆一行）
        與 newline_smart=False+newline_before=False（黏成一行的舊坑）兩種設定，
        中間插一個自簽關卡。流程本身只記錄位元組數等統計（result_var 沒有
        `_content` 這個 key，OsFileWrite 不會把檔案內容讀回流程變數），
        實際的換行位元組要在流程跑完後另外用 shell 檢查。

目標企業固定是系統預設企業（Organization.code='SYSTEM'），分類固定是「node展覽館」
。。系統企業已對 OsFileRead／
OsFileWrite 有效授權（workflow_node_org_grants），.env 的
OS_FILE_READ_NODE_ENABLED=1／OS_FILE_WRITE_NODE_ENABLED=1，不需額外開通。

冪等：重跑會沿用既有表單／流程（依 code 找），bump revision 並重新發行（會停用
舊的已發行版本並建立新版）。填寫權限授予企業內所有非 EXTERNAL 的在職帳號。

**注意**：NT-30 的兩個流程每次送單都會對同一份檔案再 APPEND 一次（OsFileWrite
是追加寫入，不是覆寫），所以 /opt/tmp/fwtest/nodedemo-*.txt 的內容會隨著測試次數
增加而變長——這是設計上的正常行為，不是 bug。

用法：
    cd <repo>
    set -a && source .env && set +a
    venv/bin/python scripts/examples/provision_nodedemo_osfile.py --dry-run
    venv/bin/python scripts/examples/provision_nodedemo_osfile.py --apply

節點 config 欄位依 handler 原始碼確認：
    modules/form_workflow/services/node_handlers/os_file_read_handler.py
    modules/form_workflow/services/node_handlers/os_file_write_handler.py
    modules/form_workflow/services/node_handlers/opset_handler.py
    modules/form_workflow/services/node_handlers/fieldwrite_handler.py
    modules/form_workflow/services/node_handlers/formadapter_handler.py
規格：dev-notes/OS_EXECUTOR_SPEC.md（第六節 OsFileRead、第十四節「實作後記」）、
dev-notes/OS_FILE_WRITE_SPEC.md

安全限制（Ethan 派工要求）：
- 讀取一律限制在 /opt/tmp/frtest/ 底下，不刪除該目錄任何既有檔案（含 symlink）。
- 寫入一律限制在 /opt/tmp/fwtest/ 底下，檔名一律用 nodedemo- 前綴。
- 故意失敗的節點：OsFileRead／OsFileWrite 本身沒有 notify_on_exception 這個欄位
  （只有 OsExecutor 才有，見 config reference），所以本檔的故意失敗節點不需要
  額外關閉通知。
- 不修改任何系統設定、不改白名單、不刪除既有檔案。
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

READ_DIR = '/opt/tmp/frtest'
WRITE_DIR = '/opt/tmp/fwtest'
SAMPLE_LOG = 'sample.log'
READ_SYMLINK = 'evil.link'          # 既有 symlink，指向 /etc/passwd（不可刪除）
WRITE_SYMLINK = 'evil-link.log'     # 既有 symlink，指向 /opt/tmp/fwoutside/link-target.log（不可刪除）

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
# 流程一：NT-29 OsFileRead 示範（讀取檔案內容）
# ---------------------------------------------------------------------------

def build_r1_graph():
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 220, 210,
              '流程入口，不需要任何前置設定。'),

        _node('node-TailRead', 'OsFileRead', '讀取 sample.log 最後 10 行', {
            'result_var': 'fr_tail',
            'base_dir': READ_DIR,
            'file_path': SAMPLE_LOG,
            'mode': 'tail',
            'lines': 10,
        }, 500, 100,
            f'用 mode=tail、lines=10 讀取 {READ_DIR}/{SAMPLE_LOG}（92KB、2000 行）'
            '最後 10 行——這是 OsFileRead 最典型的用法：只想看 log 最新狀態，'
            '不需要（也不應該）把整份檔案載入。'),
        _node('node-TailWrite', 'OpFieldWrite', '把讀取結果寫回表單', {
            'target_field': 'tail_content_result',
            'content': '【mode=tail, lines=10】\n'
                       '判定結果：${v.fr_tail_result}（應為 ok）\n'
                       '檔案大小：${v.fr_tail_file_size} bytes\n'
                       '是否截斷：${v.fr_tail_truncated}\n'
                       '內容：\n${v.fr_tail_content}',
        }, 780, 100,
            '把 fr_tail_content 等流程變數組成文字寫回表單欄位 tail_content_result。'),

        _node('node-EscapeRead', 'OsFileRead', '嘗試透過 symlink 讀取 /etc/passwd', {
            'result_var': 'fr_escape',
            'base_dir': READ_DIR,
            'file_path': READ_SYMLINK,
            'mode': 'whole',
        }, 500, 340,
            f'file_path 指向 {READ_DIR}/{READ_SYMLINK}，這是一個既有的 symlink，'
            '實際指向 /etc/passwd——本節點示範 base_dir 白名單的路徑逃逸防護：'
            'handler 對 file_path 做 realpath 解析後才比對是否落在 base_dir 之下，'
            'symlink 指向的真實路徑不在 base_dir 內，預期會被拒絕。'),
        _node('node-EscapeWrite', 'OpFieldWrite', '記錄逃逸測試結果', {
            'target_field': 'symlink_escape_result',
            'content': '【symlink 逃逸測試：file_path=evil.link → 實際指向 /etc/passwd】\n'
                       '判定結果：${v.fr_escape_result}（預期為 exception）\n'
                       '錯誤分類：${v.fr_escape_error_kind}（預期為 path_denied）\n'
                       '※ 這一步在流程管理頁一樣顯示成功（queue status=SUCCESS），'
                       '請看上面兩個流程變數才是真正的判定結果。若 error_kind 不是'
                       ' path_denied，代表白名單防護失效，請回報。',
        }, 780, 340, '把逃逸測試的判定結果寫回表單，這是本流程最重要的一個對照。'),

        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 1060, 210,
              '流程正常結束，記為 COMPLETED——即使 symlink 逃逸測試被拒絕，'
              '流程本身仍完整跑完（OsFileRead 恆回 status=success）。'),
    ]
    edges = [
        _edge('edge-start-tail', 'node-Start', 'node-TailRead'),
        _edge('edge-tail-write', 'node-TailRead', 'node-TailWrite'),
        _edge('edge-write-escape', 'node-TailWrite', 'node-EscapeRead'),
        _edge('edge-escape-write', 'node-EscapeRead', 'node-EscapeWrite'),
        _edge('edge-write-end', 'node-EscapeWrite', 'node-End'),
    ]
    return _graph(nodes, edges)


NT29_R1_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'OsFileRead 讓流程唯讀取用主機上的檔案內容，寫進流程變數供後續節點使用。'
    '它不經過 shell、只能讀允許目錄（base_dir 白名單）之下的檔案，授權門檻比'
    'OsExecutor 低一階——大部分「只想讀 log 判斷狀態」的需求，不需要開放整個'
    'OS 命令執行權限，開 OsFileRead 就夠了。\n\n'
    '【本流程的設定重點】\n'
    '- 第一個節點用 mode=tail、lines=10 讀取一份 2000 行、92KB 的示範 log 檔'
    '（/opt/tmp/frtest/sample.log）最後 10 行——只取需要的一小段，不會把整份'
    '檔案載入記憶體。改成 mode=whole 會整份讀入（超過內部上限會自動退化為'
    'head 並標記 _truncated），改成 mode=head 則是看檔頭而不是檔尾。\n'
    '- 第二個節點刻意示範安全邊界：file_path 設成 evil.link，這是'
    '/opt/tmp/frtest 目錄下一個既有的 symlink，實際指向 /etc/passwd。'
    'base_dir 白名單的檢查方式是先對 file_path 做 realpath（解析出真實路徑），'
    '再確認真實路徑落在 base_dir 之下——symlink 指向的 /etc/passwd 不在'
    '/opt/tmp/frtest 之下，因此預期會被拒絕（exception／path_denied）。這證明'
    '白名單比對的是「真實路徑」而不是「看起來像什麼路徑」，能擋住這種常見的'
    '路徑逃逸手法。\n\n'
    '【怎麼看結果】\n'
    '送單後回到「填寫表單」重新打開這張單，tail_content_result 欄位會顯示'
    'sample.log 最後 10 行的內容；symlink_escape_result 欄位會顯示逃逸測試的'
    '判定結果——正常情況下應該是「exception／path_denied」，代表白名單擋下了'
    '這次嘗試。也可以直接查流程變數 fr_tail_content（實際內容）與'
    'fr_escape_error_kind（應為 path_denied）；`fw_node_execution_logs` 的'
    'ERROR 記錄會留一筆逃逸測試的細節。'
)

FORM_R1_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-29 OsFileRead 示範表單（讀取檔案內容）'),
        _hint('送出後流程會自動讀取示範 log 檔的最後 10 行，並嘗試透過一個'
              '既有的 symlink 讀取 /etc/passwd（預期會被擋下）。送出當下兩個'
              '結果欄位還是空的，流程跑完（通常幾秒內）後重新整理本頁才看得到'
              '內容。'),
        _text('applicant_note', '備註（非必填）'),
        _textarea('tail_content_result', 'sample.log 最後 10 行（由流程自動填入）',
                   '此欄位由 OsFileRead（mode=tail）+ OpFieldWrite 自動寫入。',
                   rows=12),
        _textarea('symlink_escape_result', 'symlink 逃逸測試結果（由流程自動填入）',
                   '此欄位由 OsFileRead（讀取 evil.link）+ OpFieldWrite 自動寫入，'
                   '正常情況下應顯示 exception／path_denied。'),
        _submit_button(),
    ],
}


# ---------------------------------------------------------------------------
# 流程二：NT-29 OsFileRead 示範（不同擷取模式的差別）
# ---------------------------------------------------------------------------

def build_r2_graph():
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 120, 270,
              '流程入口，不需要任何前置設定。'),

        # --- 分組一：基本模式 head / tail ---
        _node('node-HeadRead', 'OsFileRead', '模式 1：head（檔頭 5 行）', {
            'result_var': 'm_head', 'base_dir': READ_DIR, 'file_path': SAMPLE_LOG,
            'mode': 'head', 'lines': 5,
        }, 340, 60, 'mode=head，讀取檔案最前面 5 行。'),
        _node('node-HeadWrite', 'OpFieldWrite', '記錄 head 結果', {
            'target_field': 'head_result',
            'content': '【mode=head, lines=5】\n${v.m_head_content}',
        }, 510, 60, '把 head 模式的結果寫回表單欄位 head_result。'),
        _node('node-TailRead', 'OsFileRead', '模式 2：tail（檔尾 5 行）', {
            'result_var': 'm_tail', 'base_dir': READ_DIR, 'file_path': SAMPLE_LOG,
            'mode': 'tail', 'lines': 5,
        }, 680, 60, 'mode=tail，讀取檔案最後面 5 行——與 head 直接對照。'),
        _node('node-TailWrite', 'OpFieldWrite', '記錄 tail 結果', {
            'target_field': 'tail_result',
            'content': '【mode=tail, lines=5】\n${v.m_tail_content}',
        }, 850, 60, '把 tail 模式的結果寫回表單欄位 tail_result。'),
        _node('node-Gate1', 'FormAdapter', '確認已檢視 head/tail，繼續看 occurrence 對照',
              _approve_config('ack_basic', '已檢視，繼續看 occurrence 對照', 'edge-to-group2'),
              1020, 60,
              '停下來讓送單者先看完 head／tail 兩種基本模式的結果，再繼續看'
              ' occurrence（first/last/all）的對照。'),

        # --- 分組二：occurrence first / last / all ---
        _node('node-FirstRead', 'OsFileRead', '模式 3：around occurrence=first', {
            'result_var': 'm_first', 'base_dir': READ_DIR, 'file_path': SAMPLE_LOG,
            'mode': 'around', 'keyword': 'ERROR', 'occurrence': 'first',
            'before': 1, 'after': 1,
        }, 340, 200,
            'mode=around，keyword=ERROR，occurrence=first：sample.log 裡'
            '「ERROR」共出現 3 次（第 37、1200、1999 行），這裡只取第一次'
            '出現的前後各 1 行。'),
        _node('node-FirstWrite', 'OpFieldWrite', '記錄 occurrence=first 結果', {
            'target_field': 'around_first_result',
            'content': '【around, keyword=ERROR, occurrence=first, before/after=1】\n'
                       '命中次數：${v.m_first_match_count}（應為 1，first 只算到第一次就停）\n'
                       '${v.m_first_content}',
        }, 510, 200, '把 occurrence=first 的結果寫回表單。'),
        _node('node-LastRead', 'OsFileRead', '模式 4：around occurrence=last', {
            'result_var': 'm_last', 'base_dir': READ_DIR, 'file_path': SAMPLE_LOG,
            'mode': 'around', 'keyword': 'ERROR', 'occurrence': 'last',
            'before': 1, 'after': 1,
        }, 680, 200,
            '同樣的 keyword，改成 occurrence=last，只取最後一次出現'
            '（第 1999 行）的前後各 1 行——與 first 對照，証明 occurrence 決定'
            '的是「取哪一次命中」而不是「取多少筆」。'),
        _node('node-LastWrite', 'OpFieldWrite', '記錄 occurrence=last 結果', {
            'target_field': 'around_last_result',
            'content': '【around, keyword=ERROR, occurrence=last, before/after=1】\n'
                       '${v.m_last_content}',
        }, 850, 200, '把 occurrence=last 的結果寫回表單。'),
        _node('node-AllRead', 'OsFileRead', '模式 5：around occurrence=all', {
            'result_var': 'm_all', 'base_dir': READ_DIR, 'file_path': SAMPLE_LOG,
            'mode': 'around', 'keyword': 'ERROR', 'occurrence': 'all',
            'before': 0, 'after': 0, 'max_windows': 5,
        }, 1020, 200,
            'occurrence=all、before=after=0：把 3 次命中全部列出（各自只有'
            '命中那一行本身），視窗之間用 -- 分隔——這是唯一能一次看到'
            '「總共有幾筆」的模式，match_count 應為 3。'),
        _node('node-AllWrite', 'OpFieldWrite', '記錄 occurrence=all 結果', {
            'target_field': 'around_all_result',
            'content': '【around, keyword=ERROR, occurrence=all, before/after=0, max_windows=5】\n'
                       '命中次數：${v.m_all_match_count}（應為 3，sample.log 裡 ERROR 共 3 筆）\n'
                       '${v.m_all_content}',
        }, 1190, 200, '把 occurrence=all 的結果（含命中總數）寫回表單。'),
        _node('node-Gate2', 'FormAdapter', '確認已檢視 occurrence 對照，繼續看 regex 對照',
              _approve_config('ack_occurrence', '已檢視，繼續看 regex 對照', 'edge-to-group3'),
              1360, 200,
              '停下來讓送單者對照 first／last／all 三種 occurrence 的差異，'
              '再繼續看 match_mode=regex 的示範。'),

        # --- 分組三：match_mode=regex ---
        _node('node-RegexRead', 'OsFileRead', '模式 6：match_mode=regex', {
            'result_var': 'm_regex', 'base_dir': READ_DIR, 'file_path': SAMPLE_LOG,
            'mode': 'around', 'match_mode': 'regex',
            'keyword': r'payload-(37|1200|1999)$',
            'occurrence': 'all', 'before': 0, 'after': 0, 'max_windows': 5,
        }, 340, 340,
            '同樣要找出第 37、1200、1999 這三行，這次不用「ERROR」這個字面值，'
            '改用 regex 樣式 payload-(37|1200|1999)$ 直接鎖定這三個 payload'
            '編號——巧合的是 sample.log 裡 payload 編號與行號相同，所以這個'
            'regex 命中的正好是同樣的 3 行，用來對照「用內容特徵找」（literal'
            '找 ERROR）與「用規則找」（regex 找特定編號）兩種思路。'),
        _node('node-RegexWrite', 'OpFieldWrite', '記錄 regex 結果', {
            'target_field': 'regex_result',
            'content': '【around, match_mode=regex, keyword=payload-(37|1200|1999)$】\n'
                       '命中次數：${v.m_regex_match_count}（應為 3，與 ERROR 字面搜尋'
                       '找到的是同樣 3 行，只是用不同的比對邏輯）\n'
                       '${v.m_regex_content}',
        }, 510, 340, '把 regex 比對的結果寫回表單。'),
        _node('node-Gate3', 'FormAdapter', '確認已檢視 regex 對照，繼續看 match_scope 對照',
              _approve_config('ack_regex', '已檢視，繼續看 match_scope 對照', 'edge-to-group4'),
              680, 340,
              '停下來讓送單者先看 regex 比對的結果，再繼續看 match_scope'
              '（anywhere/line_start）的對照——這是本流程最後一組對照。'),

        # --- 分組四：match_scope anywhere / line_start ---
        _node('node-ScopeAnyRead', 'OsFileRead', '模式 7：match_scope=anywhere', {
            'result_var': 'm_scope_any', 'base_dir': READ_DIR, 'file_path': SAMPLE_LOG,
            'mode': 'around', 'keyword': '37', 'match_scope': 'anywhere',
            'occurrence': 'all', 'before': 0, 'after': 0, 'max_windows': 5,
        }, 340, 480,
            'keyword="37"，match_scope=anywhere（預設值）：只要整行任何位置'
            '出現「37」這個子字串就算命中，sample.log 裡實際有 40 行符合'
            '（行號含 37 的、payload 編號含 37 的都算），但 max_windows=5 只保留'
            '前 5 筆，其餘會被 scan_truncated 標記截斷——這個節點示範的是'
            '「anywhere 比對很寬鬆，命中很多」與「max_windows 會提早結束掃描」'
            '兩件事。'),
        _node('node-ScopeAnyWrite', 'OpFieldWrite', '記錄 anywhere 結果', {
            'target_field': 'scope_anywhere_result',
            'content': '【around, keyword=37, match_scope=anywhere, max_windows=5】\n'
                       '命中次數（受 max_windows 限制而提早停止）：${v.m_scope_any_match_count}'
                       '（實際全檔案有 40 行含有「37」這個子字串，但這裡只掃到前 5 筆就停）\n'
                       '是否提早截斷：${v.m_scope_any_scan_truncated}（應為 True）\n'
                       '${v.m_scope_any_content}',
        }, 510, 480, '把 anywhere 比對的結果（含截斷旗標）寫回表單。'),
        _node('node-ScopeStartRead', 'OsFileRead', '模式 8：match_scope=line_start', {
            'result_var': 'm_scope_start', 'base_dir': READ_DIR, 'file_path': SAMPLE_LOG,
            'mode': 'around', 'keyword': '37', 'match_scope': 'line_start',
            'occurrence': 'all', 'before': 0, 'after': 0, 'max_windows': 5,
        }, 680, 480,
            '同樣的 keyword="37"，改成 match_scope=line_start：這次要求'
            '「整行開頭」就是「37」才算命中。sample.log 每一行都以「line 」'
            '開頭，沒有任何一行是以「37」開頭，所以命中次數預期是 0——與上一個'
            '節點（40 行）形成強烈對照，證明 match_scope 決定的是比對位置'
            '（任意處 vs 行首），不是比對內容。'),
        _node('node-ScopeStartWrite', 'OpFieldWrite', '記錄 line_start 結果', {
            'target_field': 'scope_line_start_result',
            'content': '【around, keyword=37, match_scope=line_start】\n'
                       '命中次數：${v.m_scope_start_match_count}（預期為 0——這份'
                       'log 的每一行都以「line 」開頭，沒有行是以「37」開頭；'
                       '與上一個節點 anywhere 模式的 40 筆命中直接對照）\n'
                       '內容（預期為空）：${v.m_scope_start_content}',
        }, 850, 480, '把 line_start 比對的結果寫回表單，這是本流程最後一個對照。'),

        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 1020, 480,
              '流程正常結束，記為 COMPLETED。'),
    ]
    edges = [
        _edge('edge-start', 'node-Start', 'node-HeadRead'),
        _edge('edge-head-write', 'node-HeadRead', 'node-HeadWrite'),
        _edge('edge-write-tail', 'node-HeadWrite', 'node-TailRead'),
        _edge('edge-tail-write', 'node-TailRead', 'node-TailWrite'),
        _edge('edge-write-gate1', 'node-TailWrite', 'node-Gate1'),
        _edge('edge-to-group2', 'node-Gate1', 'node-FirstRead', '已檢視，繼續看 occurrence 對照'),
        _edge('edge-first-write', 'node-FirstRead', 'node-FirstWrite'),
        _edge('edge-write-last', 'node-FirstWrite', 'node-LastRead'),
        _edge('edge-last-write', 'node-LastRead', 'node-LastWrite'),
        _edge('edge-write-all', 'node-LastWrite', 'node-AllRead'),
        _edge('edge-all-write', 'node-AllRead', 'node-AllWrite'),
        _edge('edge-write-gate2', 'node-AllWrite', 'node-Gate2'),
        _edge('edge-to-group3', 'node-Gate2', 'node-RegexRead', '已檢視，繼續看 regex 對照'),
        _edge('edge-regex-write', 'node-RegexRead', 'node-RegexWrite'),
        _edge('edge-write-gate3', 'node-RegexWrite', 'node-Gate3'),
        _edge('edge-to-group4', 'node-Gate3', 'node-ScopeAnyRead', '已檢視，繼續看 match_scope 對照'),
        _edge('edge-any-write', 'node-ScopeAnyRead', 'node-ScopeAnyWrite'),
        _edge('edge-write-start', 'node-ScopeAnyWrite', 'node-ScopeStartRead'),
        _edge('edge-start-write', 'node-ScopeStartRead', 'node-ScopeStartWrite'),
        _edge('edge-write-end', 'node-ScopeStartWrite', 'node-End'),
    ]
    return _graph(nodes, edges)


NT29_R2_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'OsFileRead 的擷取行為由 mode（whole/head/tail/around）、occurrence'
    '（first/last/all）、match_mode（literal/regex）、match_scope'
    '（anywhere/line_start）四個維度共同決定。本流程用 8 個 OsFileRead 節點、'
    '分成 4 組、中間插 3 個自簽關卡，逐一對照這些維度實際造成的差異，'
    '一個人就能走完全程。\n\n'
    '【本流程的設定重點】\n'
    '- 分組一（基本模式）：同一個檔案分別用 mode=head 與 mode=tail 各取 5 行，'
    '直接看出「檔頭」與「檔尾」的差異。\n'
    '- 分組二（occurrence）：同樣搜尋關鍵字「ERROR」（sample.log 裡共出現 3 次'
    '，分別在第 37、1200、1999 行），occurrence=first 只取第一次、last 只取'
    '最後一次、all 搭配 max_windows=5 把全部 3 次都列出並回報 match_count=3。'
    '改成別的值：occurrence=all 若 max_windows 設得比實際命中次數小，只會保留'
    '前 N 筆並標記 scan_truncated，不會報錯。\n'
    '- 分組三（match_mode）：同樣要找出第 37/1200/1999 行，改用 regex'
    ' payload-(37|1200|1999)$ 而不是字面搜尋「ERROR」——結果命中的是同樣'
    '3 行，示範 regex 可以用「內容規則」而不是「固定字串」定位。\n'
    '- 分組四（match_scope）：同樣的 keyword="37"，match_scope=anywhere'
    '（整行任何位置）在這份 2000 行的檔案裡命中 40 行（但 max_windows=5'
    '只留前 5 筆並標記截斷）；改成 match_scope=line_start（只比對整行開頭）'
    '則命中 0 行——因為這份 log 每一行都以「line 」開頭，沒有一行以「37」'
    '開頭。這組對照直接證明 match_scope 決定的是「比對位置」，不是「比對'
    '內容」。\n\n'
    '【怎麼看結果】\n'
    '依序完成 3 個自簽關卡（assignee_type=INITIATOR，都是自己簽自己的），'
    '每次簽核前先重新整理表單，對照 head_result／tail_result／'
    'around_first_result／around_last_result／around_all_result／'
    'regex_result／scope_anywhere_result／scope_line_start_result 八個欄位。'
    '也可以直接查流程變數 m_all_match_count（應為 3）、'
    'm_scope_any_match_count（應為 5，因 max_windows 截斷）、'
    'm_scope_start_match_count（應為 0）三組數字最能看出差異。'
)

FORM_R2_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-29 OsFileRead 示範表單（不同擷取模式的差別）'),
        _hint('送出後會依序執行 8 個 OsFileRead 節點、分成 4 組，中間插 3 個'
              '待簽任務（指派給你自己）。請到「表單中心」的待簽清單依序點開'
              '簽核，每次簽核前先看一次對應的結果欄位再繼續。'),
        _text('applicant_note', '備註（非必填）'),
        _textarea('head_result', '模式 1：head（由流程自動填入）'),
        _textarea('tail_result', '模式 2：tail（由流程自動填入）'),
        _textarea('around_first_result', '模式 3：around occurrence=first（由流程自動填入）'),
        _textarea('around_last_result', '模式 4：around occurrence=last（由流程自動填入）'),
        _textarea('around_all_result', '模式 5：around occurrence=all（由流程自動填入）', rows=8),
        _textarea('regex_result', '模式 6：match_mode=regex（由流程自動填入）', rows=8),
        _textarea('scope_anywhere_result', '模式 7：match_scope=anywhere（由流程自動填入）', rows=8),
        _textarea('scope_line_start_result', '模式 8：match_scope=line_start（由流程自動填入）'),
        _submit_button(),
    ],
}


# ---------------------------------------------------------------------------
# 流程三：NT-30 OsFileWrite 示範（寫入檔案）
# ---------------------------------------------------------------------------

def build_w1_graph():
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 220, 210,
              '流程入口，不需要任何前置設定。'),

        _node('node-Write', 'OsFileWrite', '把表單內容寫進檔案', {
            'result_var': 'fw_intro',
            'base_dir': WRITE_DIR,
            'file_path': 'nodedemo-intro.txt',
            'content': '${f.write_content}',
        }, 500, 100,
            '把表單欄位 write_content 的內容追加寫進'
            f' {WRITE_DIR}/nodedemo-intro.txt。config 沒有設定'
            ' newline_smart／newline_after，走各自的預設值（皆為 True）——'
            '這代表每次送單都會在檔案多加一行，不會覆蓋既有內容。'),
        _node('node-WriteResult', 'OpFieldWrite', '記錄寫入結果', {
            'target_field': 'write_result',
            'content': '【寫入內容】\n${f.write_content}\n\n'
                       '判定結果：${v.fw_intro_result}（應為 ok）\n'
                       '本次寫入位元組數：${v.fw_intro_bytes_written}\n'
                       '寫入前後檔案大小：${v.fw_intro_size_before} -> ${v.fw_intro_size_after}\n'
                       '截斷掉的檔尾換行位元組數：${v.fw_intro_trimmed_bytes}\n'
                       '是否為新建檔案：${v.fw_intro_created}',
        }, 780, 100,
            '把寫入結果的統計資訊寫回表單。注意 OsFileWrite 不會把檔案內容讀'
            '回流程變數（result_var 只有 _result/_error_kind/_file_path/'
            '_bytes_written/_trimmed_bytes/_size_before/_size_after/_created'
            '這組 key，沒有 _content），所以這裡顯示的「寫入內容」是直接引用'
            '表單欄位本身，不是讀回來的。'),

        _node('node-ReadbackAttempt', 'OsFileRead', '嘗試用 OsFileRead 讀回剛寫的檔案', {
            'result_var': 'fr_readback',
            'base_dir': WRITE_DIR,
            'file_path': 'nodedemo-intro.txt',
            'mode': 'whole',
        }, 500, 340,
            f'刻意用 base_dir={WRITE_DIR}（剛剛寫入的同一個目錄）呼叫'
            'OsFileRead，嘗試讀回剛寫入的內容，看起來像是合理的「寫了就讀'
            '回來確認」——但這一步預期會失敗：平台設定'
            'os_file_read_base_dirs 只允許 /opt/tmp/frtest，與'
            'os_file_write_base_dirs 的 /opt/tmp/fwtest 完全不重疊。'
            'OsFileRead 的 base_dir 檢查在還沒看 file_path 之前就會先判定'
            f'{WRITE_DIR} 不在讀取白名單內而拒絕。'),
        _node('node-ReadbackWrite', 'OpFieldWrite', '記錄讀回嘗試的結果', {
            'target_field': 'readback_attempt_result',
            'content': '【嘗試用 OsFileRead 讀回 OsFileWrite 剛寫入的檔案】\n'
                       '判定結果：${v.fr_readback_result}（預期為 exception）\n'
                       '錯誤分類：${v.fr_readback_error_kind}（預期為 path_denied）\n'
                       '※ 這正是「讀與寫的白名單是分開的」最直接的證據：'
                       'OsFileWrite 只能寫 /opt/tmp/fwtest，OsFileRead 只能讀'
                       '/opt/tmp/frtest，兩者沒有交集。「可讀不等於可寫」'
                       '反過來看就是「可寫不等於可讀」——寫進去的檔案不能用'
                       '同一組節點權限讀回來，如果流程設計需要「寫完讀回'
                       '確認」，兩個目錄都要分別被平台與企業授權才行。',
        }, 780, 340,
            '把讀回嘗試的失敗結果寫回表單，這是本流程最重要的一個對照——'
            '流程管理頁一樣顯示成功（queue status=SUCCESS），請看上面兩個'
            '流程變數才是真相。'),

        _node('node-SymlinkWrite', 'OsFileWrite', '嘗試透過既有 symlink 寫入', {
            'result_var': 'fw_symlink',
            'base_dir': WRITE_DIR,
            'file_path': WRITE_SYMLINK,
            'content': '嘗試透過 symlink 寫入的內容（預期不會真的寫入任何地方）',
        }, 500, 570,
            f'file_path 指向 {WRITE_DIR}/{WRITE_SYMLINK}，這是一個既有的'
            'symlink，實際指向 /opt/tmp/fwoutside/link-target.log——'
            'OsFileWrite 對「目標檔最後一段是 symlink」一律拒絕（設定階段用'
            'os.path.islink() 檢查，開檔時另外用 O_NOFOLLOW 做 TOCTOU 防線），'
            '這是與 OsFileRead 的 symlink 逃逸測試對稱的「寫入端」示範。'),
        _node('node-SymlinkWriteResult', 'OpFieldWrite', '記錄 symlink 寫入測試結果', {
            'target_field': 'symlink_write_result',
            'content': '【symlink 寫入測試：file_path=evil-link.log → 實際指向 fwtest 目錄外】\n'
                       '判定結果：${v.fw_symlink_result}（預期為 exception）\n'
                       '錯誤分類：${v.fw_symlink_error_kind}（預期為 path_denied）',
        }, 780, 570, '把 symlink 寫入測試的結果寫回表單。'),

        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 1060, 340,
              '流程正常結束，記為 COMPLETED——即使中間兩個節點的操作都被'
              '拒絕，流程本身仍完整跑完（OsFileRead／OsFileWrite 恆回'
              'status=success）。'),
    ]
    edges = [
        _edge('edge-start-write', 'node-Start', 'node-Write'),
        _edge('edge-write-result', 'node-Write', 'node-WriteResult'),
        _edge('edge-result-readback', 'node-WriteResult', 'node-ReadbackAttempt'),
        _edge('edge-readback-write', 'node-ReadbackAttempt', 'node-ReadbackWrite'),
        _edge('edge-readback-symlink', 'node-ReadbackWrite', 'node-SymlinkWrite'),
        _edge('edge-symlink-write', 'node-SymlinkWrite', 'node-SymlinkWriteResult'),
        _edge('edge-write-end', 'node-SymlinkWriteResult', 'node-End'),
    ]
    return _graph(nodes, edges)


NT30_W1_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'OsFileWrite 讓流程把內容追加寫進主機上允許目錄（base_dir 白名單）之下的'
    '一般檔案。它與 OsFileRead 分開授權——可讀不等於可寫，這是本流程要重點'
    '示範的觀念。\n\n'
    '【本流程的設定重點】\n'
    '- 第一步是最基本的用法：把表單欄位 write_content 的內容寫進'
    ' /opt/tmp/fwtest/nodedemo-intro.txt，沒有特別設定 newline_smart／'
    'newline_after，走預設值（都是 True，即「一筆一行」）。\n'
    '- 第二步刻意示範一個容易誤解的地方：寫完之後，直接用同一個目錄'
    '（base_dir=/opt/tmp/fwtest）呼叫 OsFileRead 想把剛寫的內容讀回來——'
    '這一步**一定會失敗**，因為平台設定 os_file_read_base_dirs 只允許'
    '/opt/tmp/frtest，與 OsFileWrite 能寫的 /opt/tmp/fwtest 完全是兩個不'
    '重疊的目錄。這不是本次示範刻意設錯，而是目前環境的真實設定——如果'
    '流程設計需要「寫完馬上讀回確認」，寫入目錄與讀取目錄必須同時被平台'
    '與企業授權涵蓋才行，這件事在設計流程前應該先跟平台管理員確認。\n'
    '- 第三步示範 OsFileWrite 自己的 symlink 防護：file_path 指向一個既有的'
    ' symlink（evil-link.log，實際指向 fwtest 目錄外），OsFileWrite 對'
    '「目標檔最後一段是 symlink」一律拒絕，與 OsFileRead 的 symlink 逃逸'
    '防護對稱。\n\n'
    '【怎麼看結果】\n'
    '送單後回到「填寫表單」重新打開這張單，write_result 顯示寫入成功的'
    '統計數字；readback_attempt_result 顯示嘗試讀回失敗的判定結果（預期'
    'exception／path_denied）；symlink_write_result 顯示透過 symlink 寫入'
    '同樣被拒絕。也可以直接查流程變數 fw_intro_bytes_written（本次寫入的'
    '位元組數）、fr_readback_error_kind（應為 path_denied）、'
    'fw_symlink_error_kind（應為 path_denied）；用 shell 檢查'
    ' /opt/tmp/fwtest/nodedemo-intro.txt 的實際內容也能直接驗證寫入確實'
    '發生了。'
)

FORM_W1_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-30 OsFileWrite 示範表單（寫入檔案）'),
        _hint('請在下面欄位輸入任意文字，送出後流程會把這段文字追加寫進伺服器上'
              '的一個檔案，並嘗試（刻意失敗地）用 OsFileRead 讀回來，最後再'
              '示範透過 symlink 寫入會被拒絕。送出當下下面三個結果欄位還是'
              '空的，流程跑完（通常幾秒內）後重新整理本頁才看得到內容。'),
        _textarea('write_content', '要寫入檔案的內容',
                   '例如：這是 NT-30 OsFileWrite 示範的測試內容。', rows=3),
        _textarea('write_result', '寫入結果（由流程自動填入）'),
        _textarea('readback_attempt_result', '嘗試讀回結果（由流程自動填入，預期失敗）'),
        _textarea('symlink_write_result', 'symlink 寫入測試結果（由流程自動填入，預期失敗）'),
        _submit_button(),
    ],
}


# ---------------------------------------------------------------------------
# 流程四：NT-30 OsFileWrite 示範（換行處理的差別）
# ---------------------------------------------------------------------------

def build_w2_graph():
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 180, 260,
              '流程入口，不需要任何前置設定。'),

        _node('node-SmartWrite1', 'OsFileWrite', '一筆一行 A：第一次寫入', {
            'result_var': 'ns_a1', 'base_dir': WRITE_DIR,
            'file_path': 'nodedemo-newline-smart.txt',
            'content': '${wi.exec_code} 一筆一行示範 - 第一次寫入',
        }, 420, 100,
            '沒有設定 newline_smart（缺 key 時預設是 True，等同「一筆一行」）。'
            '這是本流程第一次寫入這個檔案，檔案原本不存在，會被自動建立。'),
        _node('node-SmartWrite2', 'OsFileWrite', '一筆一行 A：第二次寫入', {
            'result_var': 'ns_a2', 'base_dir': WRITE_DIR,
            'file_path': 'nodedemo-newline-smart.txt',
            'content': '${wi.exec_code} 一筆一行示範 - 第二次寫入',
        }, 420, 220,
            '同一個檔案再寫一次，同樣不設定 newline_smart。newline_smart=True'
            '時，寫入前會先截斷檔尾所有換行位元組，只要截斷後檔案非空就自動'
            '補一個前置換行——效果是新內容永遠另起一行，不會接在前一筆的'
            '尾巴。'),
        _node('node-SmartWrite3', 'OsFileWrite', '一筆一行 A：第三次寫入', {
            'result_var': 'ns_a3', 'base_dir': WRITE_DIR,
            'file_path': 'nodedemo-newline-smart.txt',
            'content': '${wi.exec_code} 一筆一行示範 - 第三次寫入',
        }, 420, 340, '第三次寫入，驗證第三行是否仍然獨立成行。'),
        _node('node-SmartResult', 'OpFieldWrite', '記錄一筆一行組的結果', {
            'target_field': 'smart_writes_result',
            'content': '【newline_smart 預設開啟（一筆一行），連續寫入 3 次】\n'
                       '第 1 次：截斷 ${v.ns_a1_trimmed_bytes} bytes，'
                       '大小 ${v.ns_a1_size_before}->${v.ns_a1_size_after}，'
                       '新建檔案：${v.ns_a1_created}\n'
                       '第 2 次：截斷 ${v.ns_a2_trimmed_bytes} bytes，'
                       '大小 ${v.ns_a2_size_before}->${v.ns_a2_size_after}\n'
                       '第 3 次：截斷 ${v.ns_a3_trimmed_bytes} bytes，'
                       '大小 ${v.ns_a3_size_before}->${v.ns_a3_size_after}\n'
                       '※ OsFileWrite 不會把檔案內容讀回流程變數，實際換行'
                       '位元組要用 shell（例如 cat -A）檢查'
                       ' /opt/tmp/fwtest/nodedemo-newline-smart.txt，預期是'
                       '三行分開顯示（每行結尾各一個 $ 符號）。',
        }, 640, 220, '把三次寫入的統計數字（截斷量、前後大小）寫回表單。'),

        _node('node-Gate', 'FormAdapter', '確認已檢視一筆一行結果，繼續看黏成一行對照組',
              _approve_config('ack_smart', '已檢視，繼續看黏成一行對照組', 'edge-to-glued'),
              860, 220,
              '停下來讓送單者先看完 newline_smart=True（預設）的結果，'
              '再繼續看 newline_smart=False + newline_before=False 的'
              '對照組——這正是 CLAUDE.md 記錄的「連續寫入黏成一行」舊坑'
              '重現的設定組合。'),

        _node('node-GluedWrite1', 'OsFileWrite', '黏成一行 B：第一次寫入', {
            'result_var': 'ng_b1', 'base_dir': WRITE_DIR,
            'file_path': 'nodedemo-newline-glued.txt',
            'content': '${wi.exec_code} 黏成一行示範 - 第一段',
            'newline_smart': False, 'newline_before': False, 'newline_after': True,
        }, 1100, 100,
            'newline_smart=False、newline_before=False、newline_after=True——'
            '這正是「只勾後面」的舊坑組合：newline_smart 關閉後，'
            'newline_before=False 代表這次寫入不會在前面補換行。第一次寫入'
            '檔案是空的，效果與一筆一行組相同（都不會有前置換行）。'),
        _node('node-GluedWrite2', 'OsFileWrite', '黏成一行 B：第二次寫入', {
            'result_var': 'ng_b2', 'base_dir': WRITE_DIR,
            'file_path': 'nodedemo-newline-glued.txt',
            'content': '${wi.exec_code} 黏成一行示範 - 第二段',
            'newline_smart': False, 'newline_before': False, 'newline_after': True,
        }, 1100, 220,
            '同一個檔案第二次寫入，設定不變。這次寫入前，上一次寫入留下的'
            '檔尾換行會先被截斷（trimmed_bytes 應為 1），但因為'
            'newline_before=False 且 newline_smart=False，不會補回任何前置'
            '換行——新內容會直接接在第一段的文字尾巴，兩段內容因此黏成'
            '同一行。'),
        _node('node-GluedWrite3', 'OsFileWrite', '黏成一行 B：第三次寫入', {
            'result_var': 'ng_b3', 'base_dir': WRITE_DIR,
            'file_path': 'nodedemo-newline-glued.txt',
            'content': '${wi.exec_code} 黏成一行示範 - 第三段',
            'newline_smart': False, 'newline_before': False, 'newline_after': True,
        }, 1100, 340, '第三次寫入，驗證第三段是否同樣黏上前兩段。'),
        _node('node-GluedResult', 'OpFieldWrite', '記錄黏成一行組的結果', {
            'target_field': 'glued_writes_result',
            'content': '【newline_smart=False + newline_before=False + newline_after=True，連續寫入 3 次】\n'
                       '第 1 次：截斷 ${v.ng_b1_trimmed_bytes} bytes，'
                       '大小 ${v.ng_b1_size_before}->${v.ng_b1_size_after}，'
                       '新建檔案：${v.ng_b1_created}\n'
                       '第 2 次：截斷 ${v.ng_b2_trimmed_bytes} bytes（截斷了'
                       '第 1 次留下的檔尾換行，但沒有補回新的前置換行），'
                       '大小 ${v.ng_b2_size_before}->${v.ng_b2_size_after}\n'
                       '第 3 次：截斷 ${v.ng_b3_trimmed_bytes} bytes，'
                       '大小 ${v.ng_b3_size_before}->${v.ng_b3_size_after}\n'
                       '※ 用 shell 檢查'
                       ' /opt/tmp/fwtest/nodedemo-newline-glued.txt 預期會'
                       '看到三段文字黏在同一行（只有檔案最尾端一個換行），'
                       '與上面「一筆一行」組直接對照——兩組的 trimmed_bytes'
                       '數字其實一樣，差異只在有沒有補上新的前置換行。',
        }, 1320, 220, '把黏成一行組的統計數字寫回表單，供對照。'),

        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 1540, 220,
              '流程正常結束，記為 COMPLETED。'),
    ]
    edges = [
        _edge('edge-start', 'node-Start', 'node-SmartWrite1'),
        _edge('edge-smart1-2', 'node-SmartWrite1', 'node-SmartWrite2'),
        _edge('edge-smart2-3', 'node-SmartWrite2', 'node-SmartWrite3'),
        _edge('edge-smart3-result', 'node-SmartWrite3', 'node-SmartResult'),
        _edge('edge-result-gate', 'node-SmartResult', 'node-Gate'),
        _edge('edge-to-glued', 'node-Gate', 'node-GluedWrite1', '已檢視，繼續看黏成一行對照組'),
        _edge('edge-glued1-2', 'node-GluedWrite1', 'node-GluedWrite2'),
        _edge('edge-glued2-3', 'node-GluedWrite2', 'node-GluedWrite3'),
        _edge('edge-glued3-result', 'node-GluedWrite3', 'node-GluedResult'),
        _edge('edge-write-end', 'node-GluedResult', 'node-End'),
    ]
    return _graph(nodes, edges)


NT30_W2_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'OsFileWrite 每次寫入前會先把檔尾所有連續的換行位元組截斷掉，再依'
    ' newline_smart／newline_before／newline_after 三個設定決定要不要補回'
    '換行。newline_smart（預設 True）開啟時等同「一筆一行」：只要截斷後'
    '檔案非空就自動補一個前置換行，newline_before 這個欄位會完全被忽略'
    '（面板上應該要反灰）。本流程用兩組各 3 次的連續寫入，對照'
    ' newline_smart 開啟（預設）與關閉（且只勾 newline_after）兩種設定'
    '的實際差異。\n\n'
    '【本流程的設定重點】\n'
    '- 第一組（一筆一行 A）：完全不設定 newline_smart／newline_before，'
    '走預設值（newline_smart=True）。連續寫入 3 次，每次都會先截斷上一次'
    '留下的檔尾換行，再補回一個前置換行——效果是三次寫入各自獨立成一行。\n'
    '- 第二組（黏成一行 B）：newline_smart=False、newline_before=False、'
    'newline_after=True——這正是「只勾後面」的舊坑：newline_smart 關閉後，'
    'newline_before=False 代表不會補前置換行，但每次寫入仍然會截斷上一次'
    '留下的檔尾換行（因為截斷邏輯與 newline_smart／newline_before 無關，'
    '一律執行）。結果是第 2、3 次寫入的內容會直接接上前一次的文字尾巴，'
    '三段內容黏成同一行，只有最末端保留一個換行。\n'
    '- 兩組的 trimmed_bytes（截斷掉的檔尾換行位元組數）數字其實完全相同'
    '（第 2、3 次都是 1），差異只在於截斷之後「有沒有補回新的前置換行」——'
    '這代表光看 trimmed_bytes 看不出兩種設定的差異，一定要看實際檔案內容'
    '或 size 的變化量才能分辨。\n\n'
    '【怎麼看結果，這是本流程最重要的一段】\n'
    'OsFileWrite 不會把檔案內容讀回流程變數（result_var 只有'
    ' _result/_error_kind/_file_path/_bytes_written/_trimmed_bytes/'
    '_size_before/_size_after/_created 這組 key），所以流程本身只能顯示'
    '統計數字（smart_writes_result／glued_writes_result 兩個表單欄位）。'
    '要真正看到換行位元組的差異，跑完之後要用 shell 檢查兩個檔案：'
    '`cat -A /opt/tmp/fwtest/nodedemo-newline-smart.txt`（預期三行，'
    '每行結尾各一個 $ 符號）與'
    '`cat -A /opt/tmp/fwtest/nodedemo-newline-glued.txt`（預期只有一行，'
    '三段文字黏在一起，只有最尾端一個 $ 符號）。'
)

FORM_W2_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-30 OsFileWrite 示範表單（換行處理的差別）'),
        _hint('送出後會對兩個不同檔案各連續寫入 3 次，中間插一個待簽任務'
              '（指派給你自己）。流程本身只能顯示統計數字，實際的換行差異'
              '要在流程跑完後另外用 shell（例如 cat -A）檢查伺服器上的檔案'
              '內容。'),
        _text('applicant_note', '備註（非必填）'),
        _textarea('smart_writes_result', 'newline_smart=True（預設，一筆一行）（由流程自動填入）', rows=8),
        _textarea('glued_writes_result', 'newline_smart=False + 只勾 newline_after（黏成一行）（由流程自動填入）', rows=8),
        _submit_button(),
    ],
}


FULL_DEMOS_STATIC = [
    {
        'form_code': 'NODEDEMO_NT29_INTRO_FORM',
        'form_name': 'NT-29 OsFileRead 示範表單（讀取檔案內容）',
        'form_schema': FORM_R1_SCHEMA,
        'workflow_code': 'NODEDEMO_NT29_INTRO_FLOW',
        'workflow_name': 'NT-29 OsFileRead 示範（讀取檔案內容）',
        'description': NT29_R1_DESCRIPTION,
        'graph': lambda: build_r1_graph(),
    },
    {
        'form_code': 'NODEDEMO_NT29_MODES_FORM',
        'form_name': 'NT-29 OsFileRead 示範表單（不同擷取模式的差別）',
        'form_schema': FORM_R2_SCHEMA,
        'workflow_code': 'NODEDEMO_NT29_MODES_FLOW',
        'workflow_name': 'NT-29 OsFileRead 示範（不同擷取模式的差別）',
        'description': NT29_R2_DESCRIPTION,
        'graph': lambda: build_r2_graph(),
    },
    {
        'form_code': 'NODEDEMO_NT30_INTRO_FORM',
        'form_name': 'NT-30 OsFileWrite 示範表單（寫入檔案）',
        'form_schema': FORM_W1_SCHEMA,
        'workflow_code': 'NODEDEMO_NT30_INTRO_FLOW',
        'workflow_name': 'NT-30 OsFileWrite 示範（寫入檔案）',
        'description': NT30_W1_DESCRIPTION,
        'graph': lambda: build_w1_graph(),
    },
    {
        'form_code': 'NODEDEMO_NT30_NEWLINE_FORM',
        'form_name': 'NT-30 OsFileWrite 示範表單（換行處理的差別）',
        'form_schema': FORM_W2_SCHEMA,
        'workflow_code': 'NODEDEMO_NT30_NEWLINE_FLOW',
        'workflow_name': 'NT-30 OsFileWrite 示範（換行處理的差別）',
        'description': NT30_W2_DESCRIPTION,
        'graph': lambda: build_w2_graph(),
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
            created_by_name='provision_nodedemo_osfile',
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
    parser = argparse.ArgumentParser(description='佈建 node展覽館的 OsFileRead／OsFileWrite 示範（B7）')
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
