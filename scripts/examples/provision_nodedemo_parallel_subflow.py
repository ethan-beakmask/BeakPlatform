#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PF-252 B4 批次：node展覽館 —— ParallelJoin（並行匯合）與 SubFlow（子流程）示範。

    NT-10 ParallelJoin 示範（ALL 全部到齊）        兩條並行分支（快 8 秒／慢 25 秒），
                                                    匯合設 join_mode=ALL：等兩條都抵達
                                                    才放行，最後接 End(detach) 正常結束。
    NT-10 ParallelJoin 示範（ANY 任一即放行）       同骨架，join_mode=ANY：快分支一到就
                                                    放行，不等慢分支；刻意不接 End（怕
                                                    流程結束把還在跑的慢分支一併影響），
                                                    改用無出邊節點安全終止。
    NT-10 ParallelJoin 示範（release_once 關閉）   同骨架但 join_mode=ANY 且
                                                    release_once=False：快分支放行一次，
                                                    慢分支抵達時因為匯合節點的舊執行紀錄
                                                    已是 SUCCESS（不再擋新記錄），會建立
                                                    第二筆匯合執行、再放行一次，下游節點
                                                    因此被執行兩次（用 increment 操作
                                                    精確計數，不是用時間差猜測）。
    NT-10 ParallelJoin 示範（逾時出線）             一條分支正常抵達，另一條刻意是一個
                                                    永遠不簽核的 FormAdapter 任務、
                                                    永遠不會抵達；啟用 enable_timeout，
                                                    1 分鐘後強制走逾時出線收尾。這條路徑
                                                    在本次盤點之前從未被驗證過。
    NT-11 SubFlow 子流程（被呼叫端）                極簡子流程模板（is_subprocess=True）：
                                                    依收到的 sub_mode 變數決定自己用
                                                    detach 還是 cancel 結束。只透過主流程
                                                    的 SubFlow 節點呼叫，刻意不建表單／
                                                    不發行（本身不需要被單獨送單）。
    NT-11 SubFlow 示範（主流程）                    完整表單＋流程＋配對＋發行。兩次呼叫
                                                    同一個子流程模板、分別帶不同的
                                                    sub_mode，藉此讓子流程分別以 completed
                                                    與 cancelled 兩種結果結束，驗證
                                                    resultRouting 的兩個 key 各自把路由帶到
                                                    不同節點，並驗證回寫父層變數
                                                    ${v.<節點>_result} / ${v.<節點>_child}。

目標企業固定是系統預設企業（Organization.code='SYSTEM'），分類固定是「node展覽館」
（fw_categories.secure_code='J1ygL6zexauKlLM0_Ktoaw'）。

冪等：重跑會沿用既有表單／流程（依 code 找），bump revision 並重新發行（會停用
舊的已發行版本並建立新版）。填寫權限授予企業內所有非 EXTERNAL 的在職帳號。
子流程模板（NT-11 被呼叫端）不建表單、不建配對、不發行，僅維護 graph。

用法：
    cd /opt/BeakPlatform-dev
    set -a && source .env && set +a
    venv/bin/python scripts/examples/provision_nodedemo_parallel_subflow.py --dry-run
    venv/bin/python scripts/examples/provision_nodedemo_parallel_subflow.py --apply

節點 config 欄位依 handler 原始碼確認：
    modules/form_workflow/services/node_handlers/paralleljoin_handler.py
    modules/form_workflow/services/node_handlers/subflow_handler.py
    modules/form_workflow/services/node_handlers/end_handler.py
    modules/form_workflow/services/node_handlers/opset_handler.py
    modules/form_workflow/services/node_handlers/branch_handler.py
    modules/form_workflow/services/node_handlers/delay_handler.py
    modules/form_workflow/services/node_handlers/formadapter_handler.py
權威對照表：/opt/tmp/verify/20260907-node-config-reference.md（ParallelJoin／SubFlow／
End／OpSet／Branch／Delay／FormAdapter 節）

已核對的引擎行為（與舊文件 dev-notes/NODE_TEST_INVENTORY.md 的「附：子流程的結束
語意」不同，該章節已標示過時）：子流程裡的 End 節點會讀 finish_mode
（detach/strict → subflow_result='completed'；cancel → subflow_result='cancelled'），
不是恆為 'subflow_end'。本腳本的雙 SubFlow 呼叫設計正是利用這點，讓同一個子流程
模板依 sub_mode 分別走向不同的 finish_mode，觀察 resultRouting 的兩個 key 各自生效。
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

CHILD_FLOW_CODE = 'NODEDEMO_NT11_SUBFLOW_CHILD_FLOW'


def log(msg):
    print(msg, flush=True)


def load_node_icons(models):
    """從 workflow_node_definitions 讀每個節點型別登記的圖示（檔名與型別名不是硬規則對應）"""
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


def _fast_slow_skeleton(join_config, join_label, join_description,
                         after_join_ops, after_join_label, after_join_description,
                         has_end, fast_seconds=8, slow_seconds=25):
    """
    ParallelJoin 三個「快慢分支」示範共用的骨架：
    Start 兩條出線 -> 快分支 Delay+OpSet / 慢分支 Delay+OpSet -> ParallelJoin -> OpSet(收尾)
    -> （視 has_end 決定要不要接 End）
    """
    nodes = [
        _node(
            'node-Start', 'Start', 'Start', {}, 340, 200,
            '流程入口，兩條出線同時推進形成快、慢兩條並行分支，不需要 ParallelFork。',
        ),
        _node(
            'node-Delay-Fast', 'Delay', f'快分支：等待{fast_seconds}秒',
            {'delay_seconds': fast_seconds}, 580, 80,
            f'快分支起點，只等待 {fast_seconds} 秒，示範較快抵達匯合點的路徑。',
        ),
        _node(
            'node-OpSet-Fast', 'OpSet', '快分支：標記抵達',
            {'operations': [
                {'target_var': 'fast_arrived_at', 'operation': 'set', 'value': '${t.now}'},
                {'target_var': 'fast_branch_done', 'operation': 'set', 'value': 'true'},
            ]},
            820, 80,
            '快分支最後一步，寫入 fast_arrived_at（UTC 時間）與 fast_branch_done，'
            '證明快分支已經抵達 ParallelJoin 的入口。',
        ),
        _node(
            'node-Delay-Slow', 'Delay', f'慢分支：等待{slow_seconds}秒',
            {'delay_seconds': slow_seconds}, 580, 340,
            f'慢分支起點，等待 {slow_seconds} 秒才抵達，示範一條明顯比快分支慢的路徑。',
        ),
        _node(
            'node-OpSet-Slow', 'OpSet', '慢分支：標記抵達',
            {'operations': [
                {'target_var': 'slow_arrived_at', 'operation': 'set', 'value': '${t.now}'},
                {'target_var': 'slow_branch_done', 'operation': 'set', 'value': 'true'},
            ]},
            820, 340,
            f'慢分支最後一步，寫入 slow_arrived_at 與 slow_branch_done，比快分支晚約'
            f'{slow_seconds - fast_seconds} 秒抵達。',
        ),
        _node('node-Join', 'ParallelJoin', join_label, join_config, 1060, 200, join_description),
        _node(
            'node-OpSet-AfterJoin', 'OpSet', after_join_label,
            {'operations': after_join_ops}, 1300, 200, after_join_description,
        ),
    ]
    edges = [
        _edge('edge-start-fast', 'node-Start', 'node-Delay-Fast', '快分支'),
        _edge('edge-start-slow', 'node-Start', 'node-Delay-Slow', '慢分支'),
        _edge('edge-fast-opset', 'node-Delay-Fast', 'node-OpSet-Fast'),
        _edge('edge-slow-opset', 'node-Delay-Slow', 'node-OpSet-Slow'),
        _edge('edge-fast-join', 'node-OpSet-Fast', 'node-Join'),
        _edge('edge-slow-join', 'node-OpSet-Slow', 'node-Join'),
        _edge('edge-join-after', 'node-Join', 'node-OpSet-AfterJoin'),
    ]
    if has_end:
        nodes.append(_node(
            'node-End', 'End', 'End', {'finish_mode': 'detach'}, 1540, 200,
            '流程收尾，ALL 模式下兩條分支都會抵達匯合點，流程可以正常走到底、'
            '正常標記 COMPLETED。',
        ))
        edges.append(_edge('edge-after-end', 'node-OpSet-AfterJoin', 'node-End'))
    return {'nodes': nodes, 'edges': edges, 'relayPoints': [],
            'canvasSettings': _canvas(), 'fieldReadConfig': {}}


# ---------------------------------------------------------------------------
# NT-10 ParallelJoin：ALL
# ---------------------------------------------------------------------------

def build_pj_all_graph():
    return _fast_slow_skeleton(
        join_config={'join_mode': 'ALL', 'release_once': True, 'enable_timeout': False},
        join_label='並行匯合（ALL）',
        join_description=(
            'join_mode=ALL：兩條入線（快分支、慢分支）的來源節點都要是 SUCCESS 才會放行。'
            '快分支約 8 秒抵達，但這個節點會回 waiting 並每 10 秒重新檢查一次，'
            '一直到慢分支（約 25 秒）也抵達才真正放行。'
        ),
        after_join_ops=[
            {'target_var': 'join_released_at', 'operation': 'set', 'value': '${t.now}'},
            {'target_var': 'all_release_count', 'operation': 'increment'},
        ],
        after_join_label='匯合後：記錄放行時間',
        after_join_description=(
            '寫入 join_released_at（放行當下的 UTC 時間）與 all_release_count'
            '（用 increment 操作計數，證明整條流程只被放行一次）。'
        ),
        has_end=True,
    )


NT10_ALL_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'ParallelJoin（並行匯合）等待多條並行分支都抵達（或至少一條抵達，視 join_mode 而定）'
    '後才繼續往下推進，是流程裡「分岔之後要收攏」的標準做法。它不是一次性判斷：沒到齊時'
    '會回 waiting，每 10 秒由背景排程重新檢查一次，直到滿足放行條件或逾時（若有設定）。\n\n'
    '【本流程的設定重點】\n'
    '- join_mode=\'ALL\'：本示範的重點設定。快分支 8 秒抵達、慢分支 25 秒抵達，'
    'ParallelJoin 會等兩者都完成——查 fw_node_execution_queue 會看到這個節點在快分支'
    '抵達後先回一次 waiting（arrived_count=1/2），大約每 10 秒被重新檢查一次，直到慢分支'
    '也完成才變成 SUCCESS 並推進下游。改成 ANY 只要任一分支到就會放行，不會等待另一條——'
    '這正是另外兩個 ParallelJoin 示範要對照的差異。\n'
    '- release_once=True（預設值）：本流程只會被放行一次，這是最常見也最安全的用法。'
    '關掉之後會發生什麼事，見「release_once 關閉」那個示範。\n'
    '- enable_timeout=False：本示範不需要逾時機制，因為兩條分支最終都一定會抵達。'
    '需要逾時保護時看「逾時出線」那個示範。\n\n'
    '【怎麼看結果】\n'
    '查 fw_node_execution_queue（依 node_id / status / scheduled_at）能看到 ParallelJoin'
    '節點先回 waiting 再變 SUCCESS 的過程；查 fw_workflow_variables 的'
    ' fast_arrived_at / slow_arrived_at / join_released_at 三個時間戳，用時間差證明'
    '「join_released_at 明顯晚於 fast_arrived_at、接近 slow_arrived_at」，這就是 ALL'
    '模式「等最慢的那條」的具體證據。all_release_count 應該恆為 1。'
)


# ---------------------------------------------------------------------------
# NT-10 ParallelJoin：ANY
# ---------------------------------------------------------------------------

def build_pj_any_graph():
    return _fast_slow_skeleton(
        join_config={'join_mode': 'ANY', 'release_once': True, 'enable_timeout': False},
        join_label='並行匯合（ANY）',
        join_description=(
            'join_mode=ANY：任一入線的來源節點是 SUCCESS 就放行，不等其他分支。'
            '快分支約 8 秒完成即會讓這個節點立刻放行，慢分支（約 25 秒）抵達時'
            'release_once=True 已經放行過，這次只會被記錄成「已放行過，不再推進」。'
        ),
        after_join_ops=[
            {'target_var': 'any_released_at', 'operation': 'set', 'value': '${t.now}'},
            {'target_var': 'any_release_count', 'operation': 'increment'},
        ],
        after_join_label='匯合後：記錄放行時間（無出邊，安全終止）',
        after_join_description=(
            '刻意沒有設定任何出線：這是本流程唯一的收尾方式。ANY 模式下慢分支之後'
            '還會再次嘗試進入 ParallelJoin，如果收尾節點接了 End，流程可能已經結束、'
            '干擾對慢分支後續行為的觀察，所以本示範刻意不接 End，改用「無出邊節點'
            '安全終止該分支」。any_release_count 應該恆為 1（release_once 生效）。'
        ),
        has_end=False,
    )


NT10_ANY_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'ParallelJoin（並行匯合）等待多條並行分支抵達後才繼續往下推進。join_mode=ANY 時'
    '只要任一分支完成就放行，不等其他分支，適合「有一條做完就能往下走，其他條讓它'
    '自然跑完即可」的場景。\n\n'
    '【本流程的設定重點】\n'
    '- join_mode=\'ANY\'：本示範的重點設定，對照另一個「ALL」示範。快分支（8 秒）'
    '抵達的當下這個節點就會放行，完全不理會慢分支（25 秒）還沒到——用'
    ' fast_arrived_at 與 any_released_at 兩個時間戳幾乎同時，就能證明「不等待」。\n'
    '- release_once=True：慢分支之後抵達時，ParallelJoin 會建立第二次執行紀錄（因為'
    '第一次的執行紀錄已經是 SUCCESS，不再擋新的推進），但因為 release_once=True，'
    '這第二次執行會判斷「已經放行過」而不再往下推進——查 fw_node_execution_queue'
    '會看到這個節點有兩筆紀錄，但下游的「匯合後」節點只執行一次。\n'
    '- 本流程刻意不接 End 節點：流程尾端用一個沒有出邊的節點安全終止，'
    '避免流程結束影響到還在跑的慢分支。\n\n'
    '【怎麼看結果】\n'
    '查 fw_node_execution_queue：ParallelJoin（node-Join）應該有兩筆紀錄，第一筆'
    'SUCCESS 且 data.arrived_count=1、第二筆 SUCCESS 但 data.skip_advance=true'
    '（release_once 生效，不推進）；「匯合後」節點（node-OpSet-AfterJoin）只有一筆'
    '紀錄。查 fw_workflow_variables 的 any_released_at 應該接近 fast_arrived_at'
    '（差距約在秒等級，不必等慢分支的 slow_arrived_at），any_release_count 恆為 1。'
)


# ---------------------------------------------------------------------------
# NT-10 ParallelJoin：release_once 關閉
# ---------------------------------------------------------------------------

def build_pj_release_off_graph():
    return _fast_slow_skeleton(
        join_config={'join_mode': 'ANY', 'release_once': False, 'enable_timeout': False},
        join_label='並行匯合（release_once 關閉）',
        join_description=(
            'join_mode=ANY 且 release_once=False：快分支抵達放行一次；慢分支抵達時，'
            '由於上一次執行已經是 SUCCESS（不再擋新的推進），會建立第二筆執行紀錄，'
            '而這次因為 release_once=False，不會檢查「是否已放行過」，只要滿足'
            ' ANY 條件（此時兩條都是 SUCCESS，一樣滿足）就再放行一次——下游因此'
            '被推進兩次。'
        ),
        after_join_ops=[
            {'target_var': 'release_off_released_at', 'operation': 'set', 'value': '${t.now}'},
            {'target_var': 'release_off_release_count', 'operation': 'increment'},
        ],
        after_join_label='匯合後：記錄放行次數（無出邊，安全終止）',
        after_join_description=(
            '用 increment 操作精確計數：第一次放行後這裡是 1；如果 release_once 真的'
            '被關閉且下游因此被執行第二次，這裡最終會是 2。這是刻意選 increment 而不是'
            '只記時間戳的原因——時間戳容易被誤判成「同一次寫兩個欄位」，計數器才是'
            '「真的被執行了兩次」的直接證據。同樣刻意不接 End。'
        ),
        has_end=False,
    )


NT10_RELEASE_OFF_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'ParallelJoin（並行匯合）的 release_once 欄位決定「同一個流程實例內，這個匯合點'
    '最多放行幾次」。預設 True＝只放行一次，這是絕大多數情境要的行為。這個示範刻意'
    '關閉它，示範「關掉之後」會發生什麼——這不是假設性的警告，是真的會發生的行為。\n\n'
    '【本流程的設定重點】\n'
    '- release_once=False：本流程唯一的重點設定，其餘骨架與「ANY」示範相同'
    '（join_mode=\'ANY\'，快 8 秒／慢 25 秒的兩條分支）。快分支抵達時 ParallelJoin'
    '第一次放行，下游「匯合後」節點執行一次（release_off_release_count 從 0 變 1）。'
    '慢分支抵達時，因為第一次的執行紀錄已經是 SUCCESS，流程引擎判定「這個節點目前'
    '沒有 PENDING/RUNNING/WAITING 的紀錄」而建立第二筆全新的執行紀錄；這第二筆執行'
    '因為 release_once=False，不會檢查「先前是否已放行過」，只要當下滿足 ANY 條件'
    '（此時兩條都已 SUCCESS，當然滿足）就再放行一次，下游節點因此被建立第二筆執行紀錄、'
    '再跑一次，release_off_release_count 變成 2。\n'
    '- 這與另一個「ANY」示範的差異只有這一個欄位，但下游執行次數不同——這正是'
    ' release_once 存在的意義：它不是「防止 ParallelJoin 自己重複判斷」，而是'
    '「防止下游被同一個匯合點重複推進」。\n\n'
    '【怎麼看結果】\n'
    '查 fw_node_execution_queue：node-Join 應該有兩筆 SUCCESS 紀錄（都沒有'
    ' skip_advance），node-OpSet-AfterJoin 也應該有兩筆紀錄（第一筆約在送單後 8~20'
    '秒、第二筆約在 25~40 秒）。查 fw_workflow_variables 的 release_off_release_count'
    '，最終值應該是 2（不是 1）——這是「下游真的被執行兩次」最直接的證據，'
    '不必依賴時間戳判讀。'
)


# ---------------------------------------------------------------------------
# NT-10 ParallelJoin：逾時出線
# ---------------------------------------------------------------------------

FORM_ADAPTER_NEVER_SIGNED_CONFIG = {
    'assignee_type': 'INITIATOR',
    'assignee_label': '發起人（示範用，故意永遠不簽）',
    'selection_mode': 'single',
    'output_variable': 'timeout_demo_signed',
    'allow_comment': True,
    'require_comment': False,
    'use_custom_decisions': True,
    'input_variables': [],
    'decision_options': [
        {'id': 'opt-ok', 'label': '確認（示範用，請不要按）', 'value': 'approved',
         'style': 'default', 'target_edges': []},
    ],
}


def build_pj_timeout_graph():
    nodes = [
        _node(
            'node-Start', 'Start', 'Start', {}, 340, 200,
            '流程入口，兩條出線同時推進：一條會正常抵達，另一條刻意設計成永遠不會'
            '抵達（等人簽核但沒有人會簽），逼 ParallelJoin 真的走到逾時。',
        ),
        _node(
            'node-Delay-Fast', 'Delay', '正常分支：等待5秒',
            {'delay_seconds': 5}, 580, 80,
            '正常分支，只等待 5 秒就抵達匯合點。',
        ),
        _node(
            'node-OpSet-Fast', 'OpSet', '正常分支：標記抵達',
            {'operations': [
                {'target_var': 'fast_arrived_at', 'operation': 'set', 'value': '${t.now}'},
            ]},
            820, 80,
            '寫入 fast_arrived_at，證明這條分支已經抵達 ParallelJoin 的入口。',
        ),
        _node(
            'node-FormAdapter-NeverSigned', 'FormAdapter', '永不簽核分支（示範故意不簽）',
            dict(FORM_ADAPTER_NEVER_SIGNED_CONFIG), 580, 340,
            '指定簽核人＝發起人自己，但本示範刻意永遠不簽核，模擬「一條實際上永遠'
            '不會完成的分支」。這條分支的節點永遠停在 waiting_form_action，'
            '所以它對 ParallelJoin 而言永遠不算「已抵達」。',
        ),
        _node(
            'node-Join', 'ParallelJoin', '並行匯合（逾時 1 分鐘）',
            {'join_mode': 'ALL', 'release_once': True, 'enable_timeout': True,
             'timeout_minutes': 1, 'timeout_edge_id': 'edge-timeout'},
            1060, 200,
            'join_mode=ALL，但其中一條分支（永不簽核）永遠不會抵達，所以正常放行條件'
            '永遠不會滿足。enable_timeout=True、timeout_minutes=1：從這個節點第一次'
            '被執行（第一條分支抵達的當下）起算，1 分鐘後仍未到齊就會強制走'
            ' timeout_edge_id 指定的出線，不再無限期等下去。這條逾時路徑在本次盤點'
            '之前從未被實測驗證過。',
        ),
        _node(
            'node-OpSet-Timeout', 'OpSet', '逾時處置',
            {'operations': [
                {'target_var': 'timeout_triggered_at', 'operation': 'set', 'value': '${t.now}'},
                {'target_var': 'timeout_release_count', 'operation': 'increment'},
            ]},
            1300, 120,
            '走逾時出線後才會執行到這裡，寫入 timeout_triggered_at 與'
            ' timeout_release_count（用 increment 確認只被觸發一次，不是重複逾時）。',
        ),
        _node(
            'node-End', 'End', 'End', {'finish_mode': 'detach'}, 1540, 120,
            '流程收尾。detach 模式不會處理那個永遠 WAITING 的簽核任務——它會繼續'
            '留在待簽清單，這是刻意保留的示範道具，不是遺漏。',
        ),
    ]
    edges = [
        _edge('edge-start-fast', 'node-Start', 'node-Delay-Fast', '正常分支'),
        _edge('edge-start-never', 'node-Start', 'node-FormAdapter-NeverSigned', '永不簽核分支'),
        _edge('edge-fast-opset', 'node-Delay-Fast', 'node-OpSet-Fast'),
        _edge('edge-fast-join', 'node-OpSet-Fast', 'node-Join'),
        _edge('edge-never-join', 'node-FormAdapter-NeverSigned', 'node-Join'),
        _edge('edge-timeout', 'node-Join', 'node-OpSet-Timeout', '逾時'),
        _edge('edge-timeout-end', 'node-OpSet-Timeout', 'node-End'),
    ]
    return {'nodes': nodes, 'edges': edges, 'relayPoints': [],
            'canvasSettings': _canvas(), 'fieldReadConfig': {}}


NT10_TIMEOUT_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'ParallelJoin 的 enable_timeout／timeout_minutes／timeout_edge_id 三個欄位讓'
    '匯合點不會無限期等下去：超過設定的分鐘數仍未滿足放行條件，就強制走指定的'
    '逾時出線收尾。這條路徑此前在 dev-notes/NODE_TEST_INVENTORY.md 的盤點裡'
    '從未被實際驗證過，本示範刻意讓其中一條分支永遠不會完成，逼真的走到逾時。\n\n'
    '【本流程的設定重點】\n'
    '- join_mode=\'ALL\'：兩條入線都要到齊才正常放行。\n'
    '- 「永不簽核分支」是一個 FormAdapter 簽核節點，指定簽核人是發起人自己，但本'
    '示範刻意永遠不去簽它——它會永遠停在 waiting_form_action，對 ParallelJoin'
    '而言永遠算「未抵達」，逼 ALL 條件永遠無法自然滿足。\n'
    '- enable_timeout=True、timeout_minutes=1、timeout_edge_id=\'edge-timeout\'：'
    '從 ParallelJoin 第一次被執行（正常分支抵達、觸發它進入 waiting 的那一刻）起算，'
    '1 分鐘內沒到齊就會做最後一次確認、確定還是沒到齊，然後強制走 edge-timeout'
    '這條出線，不再等下去。\n\n'
    '【怎麼看結果】\n'
    '查 fw_node_execution_queue 的 node-Join：started_at 是它第一次被執行的時間，'
    'completed_at 應該落在 started_at 之後約 1 分鐘（timeout_minutes=1）加上輪詢'
    '間隔的誤差（最多 10 秒），result.data.timed_out 應為 true 且'
    ' selected_edge=\'edge-timeout\'。查 fw_workflow_variables 的'
    ' timeout_triggered_at 與 timeout_release_count（應為 1，證明只逾時觸發一次）。'
    '同時查 node-FormAdapter-NeverSigned 應該仍停在 WAITING（waiting_form_action），'
    '流程實例本身雖然已經 COMPLETED（detach 不影響其他未完成節點），這個簽核任務'
    '會繼續留在待簽清單——這是刻意保留的示範道具。'
)


# ---------------------------------------------------------------------------
# NT-11 SubFlow：被呼叫端（子流程模板，不建表單／不發行）
# ---------------------------------------------------------------------------

CHILD_FLOW_NAME = 'NT-11 SubFlow 子流程（被呼叫端）'

CHILD_FLOW_DESCRIPTION = (
    '【這個節點做什麼】\n'
    '這是一個極簡的子流程模板，本身不對外提供表單、不會被使用者直接送單——它只透過'
    '主流程（NT-11 SubFlow 示範（主流程））的 SubFlow 節點以 childFlowId 指定呼叫。'
    '收到呼叫後，它從 TREE scope 讀取主流程透過 paramMapping.input 傳進來的'
    ' sub_mode 變數，依值決定自己要用 detach 還是 cancel 結束——藉此讓呼叫端能'
    '觀察到子流程「正常結束」與「中止結束」兩種不同的下場。\n\n'
    '【本流程的設定重點】\n'
    '- Start 節點沒有特殊設定。子流程的 Start 節點會被 SubFlowHandler 建立成獨立的'
    '執行佇列項目，但目前有一個已知瑕疵：SubFlowHandler 讀子流程 Start 節點的'
    ' config 時只走 data.config 這個路徑（cytoscape 原生匯出格式），沒有先試'
    '平台標準的頂層 config，所以子流程 Start 節點的 config 一律讀到空字典——好在'
    ' Start 節點的 config（init.variables）本來就是死碼，這個瑕疵目前沒有實際影響，'
    '但如果日後 Start 節點的 config 真的被實作出功能，子流程情境下會失效。\n'
    '- OpSet-Echo 讀 ${v.sub_mode}（TREE scope，由主流程 paramMapping.input 寫入）'
    '寫成 child_echo_mode，讓查詢子流程自己的流程變數時能直接確認「這次收到的'
    ' sub_mode 是什麼」，不必回頭查主流程。\n'
    '- Branch 只有一條規則：sub_mode==\'cancel\' 時走 cancel 路徑，其餘一律 fallback'
    '走 detach 路徑。\n'
    '- 兩個 End 節點分別設 finish_mode=\'cancel\' 與 finish_mode=\'detach\'——子流程'
    '裡的 End 節點會讀 finish_mode（與舊文件描述的「恆為 subflow_end」不同，已於'
    '2026-09 確認 handler 原始碼），cancel 會讓 subflow_result=\'cancelled\'、'
    'detach（或 strict）讓 subflow_result=\'completed\'，這個結果會被寫回主流程的'
    ' SubFlow 節點並依 resultRouting 決定往哪個出邊推進。\n\n'
    '【怎麼看結果】\n'
    '這個模板不會被直接送單，要看結果請到主流程「NT-11 SubFlow 示範（主流程）」'
    '執行後，用它寫回的 ${node}_child 變數查到子流程實例的 secure_code，'
    '再查該實例底下的 fw_workflow_variables（child_echo_mode / child_path_taken）'
    '與 fw_workflow_instances.status（detach 結束是 COMPLETED，cancel 結束是'
    ' CANCELLED）。'
)


def build_child_flow_graph():
    nodes = [
        _node(
            'node-Start', 'Start', 'Start', {}, 340, 200,
            '子流程的入口。由主流程的 SubFlow 節點呼叫時建立。',
        ),
        _node(
            'node-OpSet-Echo', 'OpSet', '回顯收到的 sub_mode',
            {'operations': [
                {'target_var': 'child_echo_mode', 'operation': 'set', 'value': '${v.sub_mode}'},
                {'target_var': 'child_started_at', 'operation': 'set', 'value': '${t.now}'},
            ]},
            580, 200,
            '讀取 TREE scope 的 sub_mode（由主流程 paramMapping.input 寫入），'
            '寫成子流程自己的流程變數 child_echo_mode，方便直接從子流程實例查到'
            '「這次收到的模式是什麼」。',
        ),
        _node(
            'node-Branch', 'Branch', '依 sub_mode 決定結束方式',
            {
                'rules': [
                    {'name': '走取消路徑',
                     'conditions': [{'variable': '${v.sub_mode}', 'operator': '==',
                                      'value': 'cancel'}],
                     'target_edges': ['edge-branch-cancel']},
                ],
                'fallback': {'action': 'route', 'target_edge': 'edge-branch-detach'},
            },
            820, 200,
            'sub_mode==\'cancel\' 時走取消路徑（子流程用 cancel 結束）；'
            '其餘一律 fallback 走結束路徑（子流程用 detach 結束）。',
        ),
        _node(
            'node-OpSet-CancelPath', 'OpSet', '標記：即將以 cancel 結束',
            {'operations': [
                {'target_var': 'child_path_taken', 'operation': 'set', 'value': 'cancel_path'},
            ]},
            1060, 80,
            '寫入 child_path_taken=\'cancel_path\'，接著就會執行 finish_mode=cancel'
            '的 End 節點。',
        ),
        _node(
            'node-End-Cancel', 'End', 'End（cancel，中止）', {'finish_mode': 'cancel'},
            1300, 80,
            'finish_mode=\'cancel\'：子流程結束時 subflow_result=\'cancelled\'，'
            '子流程自己的實例狀態記 CANCELLED，並依 scope=\'subtree\' 取消自己與'
            '所有後代（此處子流程沒有其他未完成節點，實際影響範圍就是自己）。',
        ),
        _node(
            'node-OpSet-DetachPath', 'OpSet', '標記：即將以 detach 結束',
            {'operations': [
                {'target_var': 'child_path_taken', 'operation': 'set', 'value': 'detach_path'},
            ]},
            1060, 320,
            '寫入 child_path_taken=\'detach_path\'，接著就會執行 finish_mode=detach'
            '的 End 節點。',
        ),
        _node(
            'node-End-Detach', 'End', 'End（detach，正常結束）', {'finish_mode': 'detach'},
            1300, 320,
            'finish_mode=\'detach\'：子流程結束時 subflow_result=\'completed\'，'
            '子流程自己的實例狀態記 COMPLETED。',
        ),
    ]
    edges = [
        _edge('edge-start-echo', 'node-Start', 'node-OpSet-Echo'),
        _edge('edge-echo-branch', 'node-OpSet-Echo', 'node-Branch'),
        _edge('edge-branch-cancel', 'node-Branch', 'node-OpSet-CancelPath', '取消路徑'),
        _edge('edge-branch-detach', 'node-Branch', 'node-OpSet-DetachPath', '結束路徑'),
        _edge('edge-cancelpath-end', 'node-OpSet-CancelPath', 'node-End-Cancel'),
        _edge('edge-detachpath-end', 'node-OpSet-DetachPath', 'node-End-Detach'),
    ]
    return {'nodes': nodes, 'edges': edges, 'relayPoints': [],
            'canvasSettings': _canvas(), 'fieldReadConfig': {}}


# ---------------------------------------------------------------------------
# NT-11 SubFlow：主流程（完整表單／流程／配對／發行）
# ---------------------------------------------------------------------------

WF_PARENT_CODE = 'NODEDEMO_NT11_SUBFLOW_PARENT_FLOW'
WF_PARENT_NAME = 'NT-11 SubFlow 示範（主流程）'
FORM_PARENT_CODE = 'NODEDEMO_NT11_SUBFLOW_PARENT_FORM'
FORM_PARENT_NAME = 'NT-11 SubFlow 示範表單'

WF_PARENT_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'SubFlow（子流程）讓一個流程模板呼叫另一個流程模板，被呼叫的子流程會建立自己'
    '獨立的 fw_workflow_instances 記錄（透過 parent_instance_code 關聯回這個'
    '主流程），跑完之後才喚醒主流程繼續。這個節點本身不做任何業務邏輯，只負責'
    '「啟動並等待子流程」，並在子流程結束時依 resultRouting 決定要推進哪一條出邊。\n\n'
    '【本流程的設定重點】\n'
    '- 本流程刻意呼叫**同一個**子流程模板（NT-11 SubFlow 子流程（被呼叫端））'
    '兩次（node-SubFlow-A、node-SubFlow-B），但透過 paramMapping.input 分別傳入'
    '不同的 sub_mode：第一次傳 \'detach\'，讓子流程以 detach 結束'
    '（subflow_result=\'completed\'）；第二次傳 \'cancel\'，讓子流程以 cancel 結束'
    '（subflow_result=\'cancelled\'）。同一次流程送單就能同時看到 resultRouting'
    '的兩個 key 各自生效，不必跑兩次流程對照。\n'
    '- 每個 SubFlow 節點的 resultRouting 都同時設定了 completed 與 cancelled 兩個'
    'key，各自指向不同的下游節點——其中一條在本次示範中理論上不會被觸發（例如'
    ' node-SubFlow-A 的 cancelled 那條），刻意保留在 graph 裡，用來對照「另一條'
    '路徑確實沒有被執行」。\n'
    '- node-SubFlow-A 設了 max_iterations=5：這個欄位限制同一個 SubFlow 節點'
    '（同一個 node_id）在同一個流程實例內最多能重複呼叫子流程幾次，計數存在'
    '主流程自己的流程變數 node-SubFlow-A_runs。本示範每次送單只呼叫一次，'
    '不會真的觸及這個上限，只是示範這個欄位的存在與寫法——如果流程設計成迴圈'
    '（呼叫子流程後依某個條件繞回同一個 SubFlow 節點），這個欄位就是防止無限'
    '循環的安全閥。\n'
    '- SubFlow 結束後，子流程的 End handler 會寫回兩個主流程變數：'
    '${node-SubFlow-A_result}（=\'completed\'）、${node-SubFlow-A_child}'
    '（=子流程實例的 secure_code），node-SubFlow-B 同理但值分別是 \'cancelled\''
    '與另一個子流程實例的 secure_code。\n\n'
    '【怎麼看結果】\n'
    '查 fw_workflow_variables：path_a_taken 應為 \'completed_edge_used\'（不是'
    '\'cancelled_edge_used\'），path_b_taken 應為 \'cancelled_edge_used\''
    '（不是 \'completed_edge_used\'）；node-SubFlow-A_result=\'completed\'、'
    'node-SubFlow-B_result=\'cancelled\'。再用 node-SubFlow-A_child 與'
    ' node-SubFlow-B_child 兩個變數的值去查 fw_workflow_instances：前者'
    ' parent_instance_code 指回本流程實例、status=COMPLETED；後者同樣'
    ' parent_instance_code 指回本流程實例、status=CANCELLED。查子流程實例自己的'
    ' fw_workflow_variables 應該看到 child_echo_mode 分別是 \'detach\' 與'
    '\'cancel\'、child_path_taken 分別是 \'detach_path\' 與 \'cancel_path\'。'
)

FORM_PARENT_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-11 SubFlow 示範表單（主流程）'),
        _hint('送出後主流程會呼叫同一個子流程模板兩次，分別讓子流程以 detach／cancel'
              '兩種方式結束，藉此同時驗證 resultRouting 的 completed／cancelled 兩個'
              '出邊各自生效。跑完查 fw_workflow_variables 的 path_a_taken／'
              'path_b_taken 與 node-SubFlow-A_child／node-SubFlow-B_child。'),
        _text('applicant_note', '備註（非必填）', '示範用，內容沒有特別的邏輯用途。'),
        _submit_button(),
    ],
}


def build_parent_flow_graph():
    nodes = [
        _node(
            'node-Start', 'Start', 'Start', {}, 340, 200,
            '流程入口，之後接一個 OpSet 設定兩次 SubFlow 呼叫要用的 sub_mode 值。',
        ),
        _node(
            'node-OpSet-Init', 'OpSet', '設定兩次呼叫要用的 sub_mode',
            {'operations': [
                {'target_var': 'mode_for_a', 'operation': 'set', 'value': 'detach'},
                {'target_var': 'mode_for_b', 'operation': 'set', 'value': 'cancel'},
                {'target_var': 'parent_started_at', 'operation': 'set', 'value': '${t.now}'},
            ]},
            580, 200,
            '寫入 mode_for_a=\'detach\'（第一次呼叫子流程要用的模式）與'
            ' mode_for_b=\'cancel\'（第二次呼叫要用的模式），兩者稍後分別透過'
            ' paramMapping.input 傳給兩個 SubFlow 節點。',
        ),
        _node(
            'node-SubFlow-A', 'SubFlow', '呼叫子流程（預期 completed）',
            {
                'childFlowId': CHILD_FLOW_CODE,
                'paramMapping': {'input': {'mode_for_a': 'sub_mode'}},
                'max_iterations': 5,
                'resultRouting': {
                    'completed': ['edge-a-completed'],
                    'cancelled': ['edge-a-cancelled'],
                },
            },
            820, 120,
            '呼叫子流程並傳入 sub_mode=\'detach\'（由 mode_for_a 映射），預期子流程'
            '以 detach 結束、subflow_result=\'completed\'，走 resultRouting.completed'
            '指定的出邊。max_iterations=5：本示範只呼叫一次不會觸及上限，只是示範'
            '這個欄位存在。',
        ),
        _node(
            'node-OpSet-A-Completed', 'OpSet', '子流程A：completed 出邊',
            {'operations': [
                {'target_var': 'path_a_taken', 'operation': 'set', 'value': 'completed_edge_used'},
                {'target_var': 'a_completed_at', 'operation': 'set', 'value': '${t.now}'},
            ]},
            1060, 40,
            '這是 node-SubFlow-A 的 resultRouting.completed 指向的節點，預期會被'
            '執行到。執行後繼續呼叫第二個 SubFlow 節點。',
        ),
        _node(
            'node-OpSet-A-Cancelled-Unexpected', 'OpSet', '子流程A：cancelled 出邊（不應觸發）',
            {'operations': [
                {'target_var': 'path_a_taken', 'operation': 'set',
                 'value': 'cancelled_edge_used_UNEXPECTED'},
            ]},
            1060, 220,
            '這是 node-SubFlow-A 的 resultRouting.cancelled 指向的節點。本示範傳入'
            ' sub_mode=\'detach\'，子流程理論上不會走到 cancel 結束，所以這個節點'
            '預期不會被執行——刻意保留在 graph 裡，用來對照「另一條路徑確實沒被'
            '觸發」。沒有出邊，即使被觸發也會安全終止。',
        ),
        _node(
            'node-SubFlow-B', 'SubFlow', '呼叫子流程（預期 cancelled）',
            {
                'childFlowId': CHILD_FLOW_CODE,
                'paramMapping': {'input': {'mode_for_b': 'sub_mode'}},
                'max_iterations': 5,
                'resultRouting': {
                    'completed': ['edge-b-completed'],
                    'cancelled': ['edge-b-cancelled'],
                },
            },
            1300, 40,
            '再次呼叫同一個子流程模板，這次傳入 sub_mode=\'cancel\'（由 mode_for_b'
            '映射），預期子流程以 cancel 結束、subflow_result=\'cancelled\'，走'
            ' resultRouting.cancelled 指定的出邊。與 node-SubFlow-A 是同一個'
            ' childFlowId，但各自的 max_iterations 計數是獨立的（分別記在'
            ' node-SubFlow-A_runs／node-SubFlow-B_runs）。',
        ),
        _node(
            'node-OpSet-B-Completed-Unexpected', 'OpSet', '子流程B：completed 出邊（不應觸發）',
            {'operations': [
                {'target_var': 'path_b_taken', 'operation': 'set',
                 'value': 'completed_edge_used_UNEXPECTED'},
            ]},
            1540, -40,
            '這是 node-SubFlow-B 的 resultRouting.completed 指向的節點。本示範傳入'
            ' sub_mode=\'cancel\'，子流程理論上不會走到 detach 結束，所以這個節點'
            '預期不會被執行。沒有出邊，安全終止。',
        ),
        _node(
            'node-OpSet-B-Cancelled', 'OpSet', '子流程B：cancelled 出邊',
            {'operations': [
                {'target_var': 'path_b_taken', 'operation': 'set', 'value': 'cancelled_edge_used'},
                {'target_var': 'b_cancelled_at', 'operation': 'set', 'value': '${t.now}'},
            ]},
            1540, 120,
            '這是 node-SubFlow-B 的 resultRouting.cancelled 指向的節點，預期會被'
            '執行到，接著結束整個主流程。',
        ),
        _node(
            'node-End', 'End', 'End', {'finish_mode': 'detach'}, 1780, 120,
            '主流程收尾。兩次子流程呼叫都應該已經各自依 resultRouting 走到正確的'
            '出邊，這裡只是單純結束。',
        ),
    ]
    edges = [
        _edge('edge-start-init', 'node-Start', 'node-OpSet-Init'),
        _edge('edge-init-suba', 'node-OpSet-Init', 'node-SubFlow-A'),
        _edge('edge-a-completed', 'node-SubFlow-A', 'node-OpSet-A-Completed', '完成'),
        _edge('edge-a-cancelled', 'node-SubFlow-A', 'node-OpSet-A-Cancelled-Unexpected',
              '中止（示範中不應觸發）'),
        _edge('edge-acompleted-subb', 'node-OpSet-A-Completed', 'node-SubFlow-B'),
        _edge('edge-b-completed', 'node-SubFlow-B', 'node-OpSet-B-Completed-Unexpected',
              '完成（示範中不應觸發）'),
        _edge('edge-b-cancelled', 'node-SubFlow-B', 'node-OpSet-B-Cancelled', '中止'),
        _edge('edge-bcancelled-end', 'node-OpSet-B-Cancelled', 'node-End'),
    ]
    return {'nodes': nodes, 'edges': edges, 'relayPoints': [],
            'canvasSettings': _canvas(), 'fieldReadConfig': {}}


# ---------------------------------------------------------------------------
# ParallelJoin 的四個示範定義（皆為 full：表單＋流程＋配對＋發行）
# ---------------------------------------------------------------------------

def _pj_form_schema(title, hint):
    return {
        'display': 'form',
        'components': [
            _title(title),
            _hint(hint),
            _text('applicant_note', '備註（非必填）', '示範用，內容沒有特別的邏輯用途。'),
            _submit_button(),
        ],
    }


FULL_DEMOS = [
    {
        'form_code': 'NODEDEMO_NT10_PJ_ALL_FORM',
        'form_name': 'NT-10 ParallelJoin 示範表單（ALL）',
        'form_schema': _pj_form_schema(
            'NT-10 ParallelJoin 示範表單（ALL）',
            '送出後分成快（8秒）慢（25秒）兩條分支，ParallelJoin 設 join_mode=ALL：'
            '等兩條都抵達才放行。跑完查 fw_workflow_variables 的'
            ' fast_arrived_at / slow_arrived_at / join_released_at。',
        ),
        'workflow_code': 'NODEDEMO_NT10_PJ_ALL_FLOW',
        'workflow_name': 'NT-10 ParallelJoin 示範（ALL 全部到齊）',
        'description': NT10_ALL_DESCRIPTION,
        'graph': build_pj_all_graph,
    },
    {
        'form_code': 'NODEDEMO_NT10_PJ_ANY_FORM',
        'form_name': 'NT-10 ParallelJoin 示範表單（ANY）',
        'form_schema': _pj_form_schema(
            'NT-10 ParallelJoin 示範表單（ANY）',
            '送出後分成快（8秒）慢（25秒）兩條分支，ParallelJoin 設 join_mode=ANY：'
            '快分支一到就放行，不等慢分支。跑完查 fw_node_execution_queue 的'
            ' node-Join 應有兩筆紀錄，第二筆 skip_advance=true。',
        ),
        'workflow_code': 'NODEDEMO_NT10_PJ_ANY_FLOW',
        'workflow_name': 'NT-10 ParallelJoin 示範（ANY 任一即放行）',
        'description': NT10_ANY_DESCRIPTION,
        'graph': build_pj_any_graph,
    },
    {
        'form_code': 'NODEDEMO_NT10_PJ_RELEASEOFF_FORM',
        'form_name': 'NT-10 ParallelJoin 示範表單（release_once 關閉）',
        'form_schema': _pj_form_schema(
            'NT-10 ParallelJoin 示範表單（release_once 關閉）',
            '與 ANY 示範同骨架，但 release_once=False：慢分支抵達時會讓下游節點'
            '被再執行一次。跑完查 fw_workflow_variables 的'
            ' release_off_release_count，最終應為 2（不是 1）。',
        ),
        'workflow_code': 'NODEDEMO_NT10_PJ_RELEASEOFF_FLOW',
        'workflow_name': 'NT-10 ParallelJoin 示範（release_once 關閉）',
        'description': NT10_RELEASE_OFF_DESCRIPTION,
        'graph': build_pj_release_off_graph,
    },
    {
        'form_code': 'NODEDEMO_NT10_PJ_TIMEOUT_FORM',
        'form_name': 'NT-10 ParallelJoin 示範表單（逾時出線）',
        'form_schema': _pj_form_schema(
            'NT-10 ParallelJoin 示範表單（逾時出線）',
            '送出後一條分支正常抵達，另一條是永遠不會有人簽核的任務。'
            'ParallelJoin 設 enable_timeout=True、timeout_minutes=1，1 分鐘後'
            '強制走逾時出線。跑完查 fw_workflow_variables 的 timeout_triggered_at。',
        ),
        'workflow_code': 'NODEDEMO_NT10_PJ_TIMEOUT_FLOW',
        'workflow_name': 'NT-10 ParallelJoin 示範（逾時出線）',
        'description': NT10_TIMEOUT_DESCRIPTION,
        'graph': build_pj_timeout_graph,
    },
    {
        'form_code': FORM_PARENT_CODE,
        'form_name': FORM_PARENT_NAME,
        'form_schema': FORM_PARENT_SCHEMA,
        'workflow_code': WF_PARENT_CODE,
        'workflow_name': WF_PARENT_NAME,
        'description': WF_PARENT_DESCRIPTION,
        'graph': build_parent_flow_graph,
    },
]

# 子流程模板：只建流程模板，不建表單／配對／發行
WORKFLOW_ONLY_DEMOS = [
    {
        'workflow_code': CHILD_FLOW_CODE,
        'workflow_name': CHILD_FLOW_NAME,
        'description': CHILD_FLOW_DESCRIPTION,
        'graph': build_child_flow_graph,
        'is_subprocess': True,
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
            created_by_name='provision_nodedemo_parallel_subflow',
        ))
        added += 1
    if added:
        log(f'  {"[預演] 會新增" if not apply else "已新增"}填寫授權 {added} 筆'
            f'（共 {len(users)} 個帳號）')
    else:
        log(f'  填寫授權已存在（{len(users)} 個帳號）')


def apply_workflow_only(db, models, org, demo, apply):
    """只維護流程模板本身（子流程被呼叫端），不建表單／配對／發行。"""
    from app.utils.security import generate_secure_code

    FwWorkflowTemplate = models['FwWorkflowTemplate']
    osc = org.secure_code

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
            is_protected=False, permission_type='org',
            is_subprocess=demo.get('is_subprocess', False))
    else:
        wf.name = demo['workflow_name']
        wf.description = demo['description']
        wf.graph = graph
        wf.cytoscape_config = graph
        wf.revision = (wf.revision or 0) + 1
        wf.is_subprocess = demo.get('is_subprocess', False)

    log(f"  子流程模板 {demo['workflow_code']}{'（新建）' if is_new_wf else ''}"
        f"（is_subprocess={demo.get('is_subprocess', False)}，不建表單／不發行）")

    if not apply:
        log('  [預演] 會寫入流程 graph')
        return None

    db.session.add(wf)
    db.session.flush()
    log(f'  已寫入子流程模板：wf_sc={wf.secure_code}')
    return {'wf_sc': wf.secure_code}


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
        log('  [預演] 會寫入表單 schema 與流程 graph，並重新發行（含子流程樹系快照）')
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
    sub_wf_count = len((published.workflow_snapshot or {}).get('sub_workflows', {}))
    log(f'  已發行 v{published.publish_version}：{published.secure_code}'
        f'（表單 sc={form.secure_code}，流程 sc={wf.secure_code}，'
        f'快照內子流程數={sub_wf_count}）')
    return {'form_sc': form.secure_code, 'wf_sc': wf.secure_code,
            'published_sc': published.secure_code}


def main():
    parser = argparse.ArgumentParser(
        description='佈建 node展覽館的 ParallelJoin（四個）與 SubFlow（兩個）示範流程')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--dry-run', action='store_true', help='只列出會做什麼，不寫入')
    group.add_argument('--apply', action='store_true', help='實際寫入資料庫')
    parser.add_argument('--org', default=ORG_CODE, help=f'企業 code（預設 {ORG_CODE}）')
    args = parser.parse_args()

    from app import create_app, db

    # modules 套件要等 create_app() 跑過 module_loader 才會被插進 sys.path，
    # 所以模組層 import 必須放在 create_app() 之後（CLAUDE.md 的既有教訓）。
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
        log(f'企業：{org.name}（{org.secure_code}）')
        load_node_icons(models)

        publisher = User.query.filter_by(
            org_secure_code=org.secure_code, user_type='ORG_ADMIN',
            is_deleted=False, is_active=True).first()

        # 子流程模板必須先寫入（同 code），才能在主流程發行時被
        # collect_sub_workflow_tree() 找到並嵌進 workflow_snapshot.sub_workflows。
        log('\n=== 子流程模板（被呼叫端，先建） ===')
        wo_results = {}
        for demo in WORKFLOW_ONLY_DEMOS:
            log(f"\n--- {demo['workflow_name']} ---")
            wo_results[demo['workflow_code']] = apply_workflow_only(db, models, org, demo, args.apply)

        if args.apply:
            db.session.flush()

        log('\n=== ParallelJoin 與 SubFlow 主流程（完整表單／流程／配對／發行） ===')
        full_results = {}
        for demo in FULL_DEMOS:
            log(f"\n--- {demo['workflow_name']} ---")
            full_results[demo['workflow_code']] = apply_full_demo(
                db, models, org, demo, publisher, args.apply)

        if args.apply:
            db.session.commit()
            log('\n已寫入。到 /forms/center 的「填寫表單」就看得到 ParallelJoin 與'
                ' SubFlow 主流程這五張單（子流程被呼叫端不對外提供表單）。')
            log('\n子流程模板：')
            for code, r in wo_results.items():
                if r:
                    log(f"  {code}: wf_sc={r['wf_sc']}")
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
