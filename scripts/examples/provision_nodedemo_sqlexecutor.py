#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PF-252 B8 批次：node展覽館 —— SysSqlExecutor（NT-15）示範。

本檔佈建兩個流程：

    NT-15 SysSqlExecutor 示範（呼叫預存程序取值）
        入門：呼叫白名單登記的 stock_qty（scalar 模式）拿一個庫存數字進流程
        變數，寫回表單讓人直接看到。第一次呼叫的參數來自表單欄位
        ${f.item_code}，第二次呼叫先用 OpSet 把一個刻意不存在的料號設進流程
        變數，再用 ${v.probe_item_code} 當參數，示範「查無資料」時 scalar
        模式的行為（資料庫函式用 COALESCE 保底回 0，但 _found 旗標會是
        false）。

    NT-15 SysSqlExecutor 示範（三種結果模式的差別）
        用三個簽核關卡串接三個 SysSqlExecutor，依序呼叫 stock_qty（scalar）／
        check_stock（row）／low_stock_items（rows），對照三種 result_mode
        實際拿到的流程變數長什麼樣。另外從 Start 拉一條平行分支，呼叫一個
        刻意沒有登記在白名單裡的函式名，示範白名單擋下未登記呼叫的行為
        （這個節點不接出線、不影響主線）。low_stock_items 的白名單登記
        max_rows=50，示範資料庫裡刻意灌了 55 筆低於安全存量的料號，用來
        驗證「回傳列數上限」的截斷行為。

目標企業固定是系統預設企業（Organization.code='SYSTEM'），分類固定是「node展覽館」
。。SysSqlExecutor 是受限節點
（org_restricted），出廠只授權系統預設企業。

冪等：重跑會沿用既有表單／流程（依 code 找），bump revision 並重新發行（會停用
舊的已發行版本並建立新版）。填寫權限授予企業內所有非 EXTERNAL 的在職帳號。
示範用的庫存資料表 fw_demo_inventory 是正式 ORM model，由 fresh install 建表；
本檔只冪等種入展示資料與三筆 SQL 白名單資料。

用法：
    cd <repo>
    set -a && source .env && set +a
    venv/bin/python scripts/examples/provision_nodedemo_sqlexecutor.py --dry-run
    venv/bin/python scripts/examples/provision_nodedemo_sqlexecutor.py --apply

節點 config 欄位依 handler 原始碼確認：
    modules/form_workflow/services/node_handlers/sys_sqlexecutor_handler.py
    modules/form_workflow/services/node_handlers/opset_handler.py
    modules/form_workflow/services/node_handlers/fieldwrite_handler.py
    modules/form_workflow/services/node_handlers/formadapter_handler.py
規格：dev-notes/SQL_EXECUTOR_SPEC.md

安全限制（派工要求）：
- 只呼叫既有的三個唯讀查詢函式（stock_qty／check_stock／low_stock_items），
  不新增或修改任何預存程序。
- fw_demo_inventory 是純展示資料表（非平台功能、非預存程序），本檔只透過 ORM
  冪等種入展示資料。
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

# 示範用料號（見檔頭安全限制：只還原資料，不動預存程序本身）
ITEM_STOCK_OK = 'NODEDEMO-STK-001'      # 庫存充足：qty=120, safety=50
ITEM_NOT_FOUND = 'NODEDEMO-STK-404'     # 刻意不存在，示範查無資料
ITEM_LOW_FOR_ROW = 'NODEDEMO-LOW-055'   # 55 筆低於安全存量料號中的其中一筆（shortage 最大）
LOW_STOCK_COUNT = 55                    # 白名單登記 max_rows=50，55 > 50 才看得出截斷
WHITELIST_BLOCK_CODE = 'not_registered_probe'  # 刻意不在 fw_sql_procedures 內

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


def _textarea(key, label, description='', rows=8):
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
# 示範用庫存資料（純資料表，非預存程序，見檔頭安全限制）
# ---------------------------------------------------------------------------

SQL_PROCEDURES = [
    {
        'code': 'check_stock',
        'function_name': 'check_stock',
        'display_name': '查詢庫存',
        'description': '依料號查詢本企業目前庫存量與安全存量，回傳單列。',
        'parameters': [
            {'name': 'p_org_secure_code', 'type': 'text', 'label': '企業識別碼',
             'required': True, 'description': '由系統自動帶入'},
            {'name': 'p_item_code', 'type': 'text', 'label': '料號',
             'required': True, 'description': '要查詢的料號，例如 A-1001'},
        ],
        'result_mode': 'row',
        'result_columns': [
            {'name': 'item_code', 'label': '料號'},
            {'name': 'item_name', 'label': '品名'},
            {'name': 'qty_on_hand', 'label': '現有庫存'},
            {'name': 'safety_qty', 'label': '安全存量'},
            {'name': 'unit', 'label': '單位'},
            {'name': 'is_below_safety', 'label': '低於安全存量'},
        ],
        'max_rows': 1,
    },
    {
        'code': 'low_stock_items',
        'function_name': 'low_stock_items',
        'display_name': '低於安全存量清單',
        'description': '列出本企業所有低於安全存量的料號，缺口大的排前面。',
        'parameters': [
            {'name': 'p_org_secure_code', 'type': 'text', 'label': '企業識別碼',
             'required': True, 'description': '由系統自動帶入'},
        ],
        'result_mode': 'rows',
        'result_columns': [
            {'name': 'item_code', 'label': '料號'},
            {'name': 'item_name', 'label': '品名'},
            {'name': 'qty_on_hand', 'label': '現有庫存'},
            {'name': 'safety_qty', 'label': '安全存量'},
            {'name': 'shortage', 'label': '缺口'},
        ],
        'max_rows': 50,
    },
    {
        'code': 'stock_qty',
        'function_name': 'stock_qty',
        'display_name': '庫存量（單一數值）',
        'description': '回傳本企業某料號的現有庫存量，查無資料回 0。適合直接放進 Branch 條件比大小。',
        'parameters': [
            {'name': 'p_org_secure_code', 'type': 'text', 'label': '企業識別碼',
             'required': True, 'description': '由系統自動帶入'},
            {'name': 'p_item_code', 'type': 'text', 'label': '料號',
             'required': True, 'description': '要查詢的料號'},
        ],
        'result_mode': 'scalar',
        'result_columns': [],
        'max_rows': 1,
    },
]


def ensure_sql_procedures(db, apply):
    from modules.form_workflow.models import FwSqlProcedure

    changed = 0
    for spec in SQL_PROCEDURES:
        proc = FwSqlProcedure.query.filter(
            FwSqlProcedure.org_secure_code.is_(None),
            FwSqlProcedure.code == spec['code'],
            FwSqlProcedure.is_deleted.is_(False),
        ).first()
        if not proc:
            changed += 1
            if apply:
                proc = FwSqlProcedure(org_secure_code=None, **spec, is_active=True)
                db.session.add(proc)
            continue
        for key, value in spec.items():
            if getattr(proc, key) != value:
                changed += 1
                if apply:
                    setattr(proc, key, value)
        if proc and not proc.is_active:
            changed += 1
            if apply:
                proc.is_active = True
    if apply:
        db.session.flush()
    log(f'  {"已確保" if apply else "[預演] 會確保"} fw_sql_procedures 三筆白名單（變更 {changed} 筆）')


def ensure_demo_inventory(db, org_secure_code, apply):
    """
    還原 fw_demo_inventory（migration 106 原始結構，已於 dev 清理中被刪除），
    並灌入本次示範需要的資料：
      - NODEDEMO-STK-001：庫存充足（qty=120, safety=50）
      - NODEDEMO-LOW-001 ~ NODEDEMO-LOW-055：55 筆低於安全存量的料號
        （qty = 100-i, safety=100，shortage = i，範圍 1~55），用來驗證
        low_stock_items 白名單登記 max_rows=50 的截斷行為。
    冪等：依 (org_secure_code, item_code) 查找，不存在才新增。
    """
    from app.models import FwDemoInventory

    if not apply:
        log(f'  [預演] 會確保 fw_demo_inventory 存在，並灌入 1 + {LOW_STOCK_COUNT} 筆示範資料'
            f'（企業 {org_secure_code}）')
        return

    rows = [
        (ITEM_STOCK_OK, 'node展覽館示範料件（庫存充足）', 120, 50, 'PCS'),
    ]
    rows.extend(
        (f'NODEDEMO-LOW-{i:03d}', f'node展覽館示範料件（低於安全存量 #{i}）',
         100 - i, 100, 'PCS')
        for i in range(1, LOW_STOCK_COUNT + 1)
    )
    added = 0
    for item_code, item_name, qty, safety, unit in rows:
        row = FwDemoInventory.query.filter_by(
            org_secure_code=org_secure_code,
            item_code=item_code,
            is_deleted=False,
        ).first()
        if row:
            row.item_name = item_name
            row.qty_on_hand = qty
            row.safety_qty = safety
            row.unit = unit
            continue
        db.session.add(FwDemoInventory(
            org_secure_code=org_secure_code,
            item_code=item_code,
            item_name=item_name,
            qty_on_hand=qty,
            safety_qty=safety,
            unit=unit,
        ))
        added += 1

    db.session.flush()
    log(f'  已確保 fw_demo_inventory 示範資料（1 + {LOW_STOCK_COUNT} 筆，新增 {added} 筆，企業 {org_secure_code}）')


# ---------------------------------------------------------------------------
# 流程一：NT-15 SysSqlExecutor 示範（呼叫預存程序取值）
# ---------------------------------------------------------------------------

def build_intro_graph():
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 100, 200,
              '流程入口，不需要任何前置設定。'),

        _node('node-SqlByForm', 'SysSqlExecutor', '查詢庫存（參數來自表單欄位）', {
            'procedure_code': 'stock_qty',
            'params': {'p_item_code': '${f.item_code}'},
            'result_var': 'qty_from_form',
            'timeout_seconds': 10,
        }, 380, 100,
            '呼叫白名單登記的 stock_qty（procedure_code=stock_qty），'
            'p_item_code 參數來自表單欄位 ${f.item_code}。result_var='
            'qty_from_form，因為 stock_qty 的 result_mode 是 scalar，只會'
            '寫入單一數值，另外附帶 qty_from_form_count／_found／_truncated'
            '三個旗標。'),

        _node('node-SetProbe', 'OpSet', '設定一個不存在的料號', {
            'operations': [
                {'target_var': 'probe_item_code', 'operation': 'set',
                 'value': ITEM_NOT_FOUND},
            ],
        }, 660, 200,
            '用 OpSet 把一個刻意不存在的料號寫進流程變數 probe_item_code，'
            '供下一個 SysSqlExecutor 示範「查無資料」時的行為。'),

        _node('node-SqlByVar', 'SysSqlExecutor', '查詢庫存（參數來自流程變數，示範查無資料）', {
            'procedure_code': 'check_stock',
            'params': {'p_item_code': '${v.probe_item_code}'},
            'result_var': 'stock_from_var',
            'timeout_seconds': 10,
        }, 940, 100,
            '呼叫 check_stock（result_mode=row），p_item_code 改用'
            ' ${v.probe_item_code}（流程變數來源，不是表單欄位），示範參數'
            '不一定要來自表單。此料號在庫存表裡不存在，check_stock 內部是'
            ' WHERE 過濾 + LIMIT 1（非聚合查詢），查無符合資料時 SQL 真的'
            '不會回傳任何列，所以 stock_from_var_found 會是 false、'
            'stock_from_var 會是空 dict {}——這才是可靠的「查無資料」判斷'
            '方式。\n\n'
            '附註：如果改呼叫 stock_qty（scalar，內部用 MAX+COALESCE 聚合'
            '），因為聚合查詢不論有沒有符合資料，SQL 都固定回傳一列（保底'
            '值 0），_found 會恆為 true，並不能反映真正有沒有資料——'
            '_found 旗標的可靠度取決於 SP 本身的 SQL 是不是聚合查詢，不是'
            ' SysSqlExecutor 通用保證的行為，設計流程時要留意這一點。'),

        _node('node-Write', 'OpFieldWrite', '寫回查詢結果', {
            'target_field': 'query_result_display',
            'content': (
                '【參數來自表單欄位：${f.item_code}，procedure_code=stock_qty（scalar）】\n'
                '庫存量：${v.qty_from_form}\n'
                '是否查得到：${v.qty_from_form_found}\n'
                '\n'
                '【參數來自流程變數：${v.probe_item_code}（刻意設為不存在的料號），'
                'procedure_code=check_stock（row）】\n'
                '查得的列：${v.stock_from_var}\n'
                '是否查得到：${v.stock_from_var_found}（應為 false——'
                'check_stock 不是聚合查詢，查無資料時 SQL 真的不會回傳任何列，'
                '這與同一個節點若改用 stock_qty 這種聚合函式時 _found 恆為'
                ' true 的行為不同，見上一個節點的附註）'
            ),
        }, 1220, 100, '把兩次查詢的數值／列與 _found 旗標組成文字寫回表單欄位 query_result_display。'),

        _node('node-Approve', 'FormAdapter', '確認已看到查詢結果',
              _approve_config('ack', '確認已看到查詢結果，結束流程', 'edge-approve-end'),
              1500, 100,
              '簽核者固定是發起人自己（assignee_type=INITIATOR），純粹作為'
              '流程收尾的關卡，方便一個帳號就能走完全程。'),

        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 1780, 100,
              '流程正常結束（finish_mode=detach）。'),
    ]
    edges = [
        _edge('edge-start-sqlform', 'node-Start', 'node-SqlByForm'),
        _edge('edge-sqlform-setprobe', 'node-SqlByForm', 'node-SetProbe'),
        _edge('edge-setprobe-sqlvar', 'node-SetProbe', 'node-SqlByVar'),
        _edge('edge-sqlvar-write', 'node-SqlByVar', 'node-Write'),
        _edge('edge-write-approve', 'node-Write', 'node-Approve'),
        _edge('edge-approve-end', 'node-Approve', 'node-End', label='確認'),
    ]
    return _graph(nodes, edges)


NT15_INTRO_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'SysSqlExecutor 讓流程呼叫平台主庫裡「事先登錄過」的預存程序（stored'
    ' procedure），把查詢結果寫進流程變數。它不能自由下 SQL，只能呼叫白'
    '名單（fw_sql_procedures 表）登記過的函式——這是它與「直接執行 SQL」'
    '最大的差別，也是這個節點存在的核心價值：流程 config 存在'
    ' fw_workflow_templates.graph 裡，而 graph 可以透過 API 直接改寫，'
    '如果流程可以自己組 SQL 字串，任何拿得到流程編輯權限的人就等於拿到了'
    '資料庫的任意查詢權限。\n\n'
    '【本流程的設定重點】\n'
    '- procedure_code 填的是白名單登記的識別碼（本例是 stock_qty），不是'
    '資料庫函式名本身——兩者目前剛好同名，但 handler 是拿 code 去'
    ' fw_sql_procedures 表重新查一次，就算資料庫函式改了名字，也不必連帶'
    '改 procedure_code。\n'
    '- params 裡只能填白名單宣告過的參數名（本例是 p_item_code）。'
    ' p_org_secure_code 由系統自動帶入，config 裡如果出現這個名字會被整次'
    '拒絕——這是租戶隔離的最後一道防線，不讓流程設計者有機會指定別家企業'
    '的識別碼。\n'
    '- 第一個 SysSqlExecutor 的 p_item_code 值是 ${f.item_code}，來自表單'
    '欄位；第二個則是 ${v.probe_item_code}，來自前一個 OpSet 節點設定的'
    '流程變數——兩種來源都合法，差別只在 ${...} 引用的前綴（f. 是表單'
    '欄位、v. 是流程變數）。\n'
    '- 第二次查詢改呼叫 check_stock（row 模式），且改用一個不存在的料號，'
    '示範「查無資料」時 _found 旗標真正的行為：check_stock 內部是'
    ' WHERE 過濾 + LIMIT 1（非聚合查詢），查無符合資料時 SQL 真的不會'
    '回傳任何列，所以 stock_from_var_found 會是 false、stock_from_var'
    ' 是空 dict {}——這才是可靠的「查無資料」判斷方式。若改用 stock_qty'
    '這種內部用 MAX+COALESCE 聚合的 SP，即使查無資料，聚合查詢仍會固定'
    '回傳一列（保底值 0），此時 _found 會恆為 true，並不能反映真正有沒有'
    '資料。**_found 旗標的可靠度取決於 SP 本身的 SQL 是不是聚合查詢，'
    '不是 SysSqlExecutor 通用保證的行為**，設計流程時要注意。\n\n'
    '【怎麼看結果】\n'
    '送單後回到「填寫表單」重新打開這張單，query_result_display 欄位會'
    '同時顯示兩次查詢的結果與 _found 旗標。也可以直接查流程變數'
    ' qty_from_form／qty_from_form_found／stock_from_var／'
    'stock_from_var_found。'
)

FORM_INTRO_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-15 SysSqlExecutor 示範表單（呼叫預存程序取值）'),
        _hint('送出後流程會呼叫白名單登記的 stock_qty 兩次：第一次查詢下方'
              '「料號」欄位的值，第二次改查一個流程內部設定的不存在料號。'
              '送出當下結果欄位還是空的，流程跑完（通常幾秒內）後重新整理'
              '本頁才看得到內容。'),
        _text('item_code', '要查詢的料號',
              f'預設值 {ITEM_STOCK_OK} 是示範資料裡庫存充足的料號，'
              '會直接當成 SysSqlExecutor 的 p_item_code 參數，不修改也可以。'),
        _textarea('query_result_display', '查詢結果（由流程自動填入）',
                   '此欄位由 SysSqlExecutor + OpFieldWrite 自動寫入。', rows=10),
        _submit_button(),
    ],
}
FORM_INTRO_SCHEMA['components'][2]['defaultValue'] = ITEM_STOCK_OK


# ---------------------------------------------------------------------------
# 流程二：NT-15 SysSqlExecutor 示範（三種結果模式的差別）
# ---------------------------------------------------------------------------

def build_modes_graph():
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 100, 260,
              '流程入口。從這裡拉出兩條出線：一條是主線（三種 result_mode'
              '對照），一條是平行分支（白名單擋人示範）——「一個節點接兩條'
              '出線＝並行」，不需要 ParallelFork。'),

        # --- 主線：三種 result_mode 對照 ---
        _node('node-SqlScalar', 'SysSqlExecutor', '呼叫 stock_qty（scalar）', {
            'procedure_code': 'stock_qty',
            'params': {'p_item_code': ITEM_STOCK_OK},
            'result_var': 'mode_scalar',
            'timeout_seconds': 10,
        }, 380, 100,
            f'呼叫 stock_qty（result_mode=scalar），查詢料號 {ITEM_STOCK_OK}'
            '（示範資料中庫存充足）的庫存量，寫入 mode_scalar。'),
        _node('node-WriteScalar', 'OpFieldWrite', '寫回 scalar 結果', {
            'target_field': 'scalar_result_display',
            'content': (
                '【result_mode=scalar，procedure_code=stock_qty】\n'
                'mode_scalar = ${v.mode_scalar}\n'
                'mode_scalar_count = ${v.mode_scalar_count}\n'
                'mode_scalar_found = ${v.mode_scalar_found}\n'
                'mode_scalar_truncated = ${v.mode_scalar_truncated}\n'
                '\n'
                'scalar 模式只會得到一個「值」本身，沒有欄位名，也不會有'
                ' mode_scalar_<欄位名> 這種攤平變數。'
            ),
        }, 660, 100, '把 scalar 模式的結果與旗標寫回表單欄位 scalar_result_display。'),
        _node('node-Gate1', 'FormAdapter', '確認已檢視 scalar 結果',
              _approve_config('ack_scalar', '已檢視 scalar 結果，繼續看 row 模式', 'edge-gate1-row'),
              940, 100, '停下來讓送單者先看 scalar 模式的結果，確認後才推進到 row 模式。'),

        _node('node-SqlRow', 'SysSqlExecutor', '呼叫 check_stock（row）', {
            'procedure_code': 'check_stock',
            'params': {'p_item_code': ITEM_LOW_FOR_ROW},
            'result_var': 'mode_row',
            'timeout_seconds': 10,
        }, 1220, 100,
            f'呼叫 check_stock（result_mode=row），查詢料號 {ITEM_LOW_FOR_ROW}'
            '（示範資料中刻意設為低於安全存量），寫入 mode_row 並攤平成'
            ' mode_row_<欄位名>。'),
        _node('node-WriteRow', 'OpFieldWrite', '寫回 row 結果', {
            'target_field': 'row_result_display',
            'content': (
                '【result_mode=row，procedure_code=check_stock】\n'
                '完整 dict：mode_row = ${v.mode_row}\n'
                '\n'
                '攤平後的個別欄位（handler 額外寫入 <result_var>_<欄位名>）：\n'
                'mode_row_item_name = ${v.mode_row_item_name}\n'
                'mode_row_qty_on_hand = ${v.mode_row_qty_on_hand}\n'
                'mode_row_safety_qty = ${v.mode_row_safety_qty}\n'
                'mode_row_is_below_safety = ${v.mode_row_is_below_safety}'
                '（應為 true）\n'
                'mode_row_found = ${v.mode_row_found}\n'
                '\n'
                '流程變數系統只支援一層扁平查詢，${v.mode_row.qty_on_hand}'
                ' 這種巢狀寫法不會生效——要比大小或做條件判斷，一律用攤平後'
                '的 mode_row_qty_on_hand，不要引用巢狀路徑。'
            ),
        }, 1500, 100, '把 row 模式的完整 dict 與攤平後的個別欄位寫回表單欄位 row_result_display。'),
        _node('node-Gate2', 'FormAdapter', '確認已檢視 row 結果',
              _approve_config('ack_row', '已檢視 row 結果，繼續看 rows 模式', 'edge-gate2-rows'),
              1780, 100, '停下來讓送單者對照 row 模式與 scalar 模式的差異，確認後才推進到 rows 模式。'),

        _node('node-SqlRows', 'SysSqlExecutor', '呼叫 low_stock_items（rows）', {
            'procedure_code': 'low_stock_items',
            'params': {},
            'result_var': 'mode_rows',
            'timeout_seconds': 15,
        }, 2060, 100,
            '呼叫 low_stock_items（result_mode=rows），列出所有低於安全'
            f'存量的料號。白名單登記的 max_rows=50，示範資料庫裡刻意灌了'
            f' {LOW_STOCK_COUNT} 筆，用來驗證截斷行為。'),
        _node('node-WriteRows', 'OpFieldWrite', '寫回 rows 結果', {
            'target_field': 'rows_result_display',
            'content': (
                '【result_mode=rows，procedure_code=low_stock_items】\n'
                f'這次示範資料共有 {LOW_STOCK_COUNT} 筆低於安全存量的料號，'
                '但白名單登記的 max_rows=50。\n'
                'mode_rows_count = ${v.mode_rows_count}'
                f'（應為 50，不是 {LOW_STOCK_COUNT}）\n'
                'mode_rows_truncated = ${v.mode_rows_truncated}（應為 true）\n'
                'mode_rows_found = ${v.mode_rows_found}\n'
                '\n'
                'rows 模式的 mode_rows 本身是一個列表，本平台沒有陣列迭代'
                '節點，無法直接在單一文字欄位逐筆列出——rows 模式通常只用來'
                '看 _count／_truncated 這兩個旗標，或整包交給簽核註記／'
                'SQL Sync 之類會處理陣列的機制，這是它與 scalar／row 模式'
                '最大的使用門檻差異。'
            ),
        }, 2340, 100, '把 rows 模式的 _count 與 _truncated 旗標寫回表單欄位 rows_result_display。'),
        _node('node-Gate3', 'FormAdapter', '最後確認',
              _approve_config('ack_rows', '已檢視 rows 結果，結束流程', 'edge-gate3-end'),
              2620, 100, '最後一個確認關卡，通過後流程結束。'),

        _node('node-End', 'End', 'End', {'finish_mode': 'detach'}, 2900, 100,
              '流程正常結束（finish_mode=detach）。'),

        # --- 平行分支：白名單擋人示範 ---
        _node('node-SqlBlocked', 'SysSqlExecutor', '呼叫白名單外的函式（示範被擋下）', {
            'procedure_code': WHITELIST_BLOCK_CODE,
            'params': {},
            'result_var': 'mode_blocked',
            'timeout_seconds': 10,
            'on_error': 'error',
        }, 380, 420,
            f'刻意呼叫一個沒有登記在白名單（fw_sql_procedures）裡的函式名'
            f'「{WHITELIST_BLOCK_CODE}」，示範白名單擋下未登記呼叫的行為。'
            '這個節點故意沒有接出線，也不影響主線流程——白名單拒絕會讓這個'
            '節點本身失敗（on_error 用預設值「error」，不是「continue」，'
            '所以查詢失敗會讓節點真的失敗，重試最多 3 次後變成 FAILED，'
            '這與 Os 系列節點刻意讓失敗也回報 success 的「四分法」是不同的'
            '設計——SysSqlExecutor 失敗就是真的失敗，在流程管理頁看得出來）。'),
    ]
    edges = [
        _edge('edge-start-scalar', 'node-Start', 'node-SqlScalar'),
        _edge('edge-start-blocked', 'node-Start', 'node-SqlBlocked'),
        _edge('edge-scalar-write', 'node-SqlScalar', 'node-WriteScalar'),
        _edge('edge-writescalar-gate1', 'node-WriteScalar', 'node-Gate1'),
        _edge('edge-gate1-row', 'node-Gate1', 'node-SqlRow', label='繼續看 row 模式'),
        _edge('edge-row-write', 'node-SqlRow', 'node-WriteRow'),
        _edge('edge-writerow-gate2', 'node-WriteRow', 'node-Gate2'),
        _edge('edge-gate2-rows', 'node-Gate2', 'node-SqlRows', label='繼續看 rows 模式'),
        _edge('edge-rows-write', 'node-SqlRows', 'node-WriteRows'),
        _edge('edge-writerows-gate3', 'node-WriteRows', 'node-Gate3'),
        _edge('edge-gate3-end', 'node-Gate3', 'node-End', label='結束'),
    ]
    return _graph(nodes, edges)


NT15_MODES_DESCRIPTION = (
    '【這個節點做什麼】\n'
    'SysSqlExecutor 讓流程呼叫平台主庫裡「事先登錄過」的預存程序，把查詢結果'
    '依登記的 result_mode（scalar／row／rows）寫成不同形狀的流程變數。它'
    '刻意不支援自由下 SQL——流程 config 存在 fw_workflow_templates.graph'
    '裡，而 graph 可以透過 API 直接改寫，如果流程可以自己組 SQL 字串，'
    '任何拿得到流程編輯權限的人就等於拿到了資料庫的任意查詢權限（甚至寫入'
    '權限）。白名單制度把「能不能查」與「查什麼」拆成兩件事：能不能查由'
    '部署期的白名單（fw_sql_procedures 表）決定，流程設計者只能在白名單'
    '允許的範圍內填參數，即使 config 被竄改，能觸及的範圍仍鎖死在白名單'
    '登記過的那幾支函式。\n\n'
    '新增一支可呼叫的預存程序，需要：(1) 在資料庫 fw_sp 這個專用 schema'
    '裡建函式，第一個參數固定 p_org_secure_code 且必須是函式內部實際的'
    ' WHERE 過濾條件（租戶隔離不是靠平台的權限系統，是靠這個參數）、且'
    '不可以是 SECURITY DEFINER；(2) 在 fw_sql_procedures 這張白名單表'
    '登記一筆，欄位包含 code（流程設定引用的識別碼）、function_name'
    '（資料庫裡的實際函式名）、parameters（每個參數的名稱／型別／是否'
    '必填，第一筆固定是 p_org_secure_code）、result_mode（scalar／row／'
    'rows 三選一）、max_rows（結果列數上限）。這張表沒有 Web UI，只能透過'
    '部署期的 SQL 直接寫入——登記一筆等同授權流程設計者呼叫該函式，是刻意'
    '的部署期決定，不開放讓一般使用者自己新增。\n\n'
    '【本流程的設定重點】\n'
    '- 三個主線節點依序呼叫 stock_qty（scalar）／check_stock（row）／'
    'low_stock_items（rows），procedure_code 不同，但都是同一套白名單機制'
    '、同一支 handler 執行。\n'
    '- scalar 模式：mode_scalar 直接就是那個數值本身，沒有欄位名，也不會'
    '有 mode_scalar_<欄位> 這種攤平變數。\n'
    '- row 模式：mode_row 是一個 dict，handler 額外把每個欄位攤平成'
    ' mode_row_<欄位名>（例如 mode_row_qty_on_hand）——因為流程變數系統'
    '只支援一層扁平查詢，${v.mode_row.qty_on_hand} 這種巢狀寫法不會生效，'
    '要比大小或做條件判斷一律用攤平後的變數。\n'
    '- rows 模式：mode_rows 是一個 list，本平台沒有陣列迭代節點，拿到手上'
    '能做的事很有限，通常只用來看 _count／_truncated 這兩個旗標。\n'
    f'- low_stock_items 這支白名單登記的 max_rows=50，但本次示範資料庫裡'
    f'刻意灌了 {LOW_STOCK_COUNT} 筆低於安全存量的料號——執行結果'
    ' mode_rows_count 會是 50（不是 55），mode_rows_truncated 會是 true，'
    '證明「回傳列數上限」是登記值與資料庫實際筆數兩者取小，不會因為資料'
    '變多就跟著變多。\n'
    '- 另外有一個平行分支，呼叫一個刻意沒有登記在白名單裡的函式名'
    f'（{WHITELIST_BLOCK_CODE}）。這是 SysSqlExecutor 安全設計的核心：即使'
    '流程設計者在 config 裡填了任意函式名，handler 執行時一定會拿'
    ' procedure_code 重新查一次 fw_sql_procedures 白名單表，查不到就整次'
    '拒絕——設計器的下拉選單只是輔助，不是防線。\n'
    '- 這個節點的 on_error 用預設值「error」（不是「continue」），所以查詢'
    '失敗會讓這個節點本身變成失敗，而不是靜默放行——這與 Os 系列節點刻意'
    '讓失敗也回報 success（四分法）是不同的設計：SysSqlExecutor 失敗時是真的'
    '失敗，會重試最多 3 次，3 次都失敗才變成 FAILED，行為在流程管理頁看'
    '得出來，不需要額外看流程變數才能發現。\n\n'
    '【怎麼看結果】\n'
    '主線每跑完一次 SysSqlExecutor 就用一個自簽關卡（assignee_type='
    'INITIATOR）停下來，回「填寫表單」重新打開這張單，可以依序看到'
    ' scalar_result_display／row_result_display／rows_result_display 三個'
    '欄位。也可以直接查流程變數 mode_scalar／mode_row／'
    'mode_row_qty_on_hand／mode_rows_count／mode_rows_truncated。平行分支'
    '那個刻意失敗的節點看不到表單欄位變化——它要看'
    ' fw_node_execution_queue 的狀態（會先變 PENDING 重試，重試 3 次後變'
    ' FAILED，或者主線先結束流程而被標記 CANCELLED）與'
    ' fw_node_execution_logs 的 ERROR 記錄（會留下「不在白名單內或已停用」'
    '的訊息）。'
)

FORM_MODES_SCHEMA = {
    'display': 'form',
    'components': [
        _title('NT-15 SysSqlExecutor 示範表單（三種結果模式的差別）'),
        _hint('送出後會依序執行 scalar／row／rows 三種 result_mode 的'
              '查詢，中間插 3 個待簽任務（指派給你自己）。請到「表單中心」'
              '的待簽清單依序點開簽核，每次簽核前先重新整理本頁看對應的'
              '結果欄位。另有一個平行分支會呼叫白名單外的函式，預期會失敗'
              '，不影響這裡三個欄位的內容。'),
        _text('applicant_note', '備註（非必填）'),
        _textarea('scalar_result_display', '模式 1：scalar（由流程自動填入）'),
        _textarea('row_result_display', '模式 2：row（由流程自動填入）', rows=10),
        _textarea('rows_result_display', '模式 3：rows（由流程自動填入）'),
        _submit_button(),
    ],
}


# ---------------------------------------------------------------------------
# 佈建清單
# ---------------------------------------------------------------------------

FULL_DEMOS_STATIC = [
    {
        'form_code': 'NODEDEMO_NT15_INTRO_FORM',
        'form_name': 'NT-15 SysSqlExecutor 示範表單（呼叫預存程序取值）',
        'form_schema': FORM_INTRO_SCHEMA,
        'workflow_code': 'NODEDEMO_NT15_INTRO_FLOW',
        'workflow_name': 'NT-15 SysSqlExecutor 示範（呼叫預存程序取值）',
        'description': NT15_INTRO_DESCRIPTION,
        'graph': lambda: build_intro_graph(),
    },
    {
        'form_code': 'NODEDEMO_NT15_MODES_FORM',
        'form_name': 'NT-15 SysSqlExecutor 示範表單（三種結果模式的差別）',
        'form_schema': FORM_MODES_SCHEMA,
        'workflow_code': 'NODEDEMO_NT15_MODES_FLOW',
        'workflow_name': 'NT-15 SysSqlExecutor 示範（三種結果模式的差別）',
        'description': NT15_MODES_DESCRIPTION,
        'graph': lambda: build_modes_graph(),
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
            created_by_name='provision_nodedemo_sqlexecutor',
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

    log('\n=== SysSqlExecutor 白名單（fw_sql_procedures） ===')
    ensure_sql_procedures(db, apply)
    ensure_demo_inventory(db, osc, apply)

    results = {}
    for demo in FULL_DEMOS_STATIC:
        log(f"\n--- {demo['workflow_name']} ---")
        results[demo['workflow_code']] = apply_full_demo(
            db, models, org, demo, publisher, apply)
    return {'results': results, 'category_secure_code': SHOWCASE_CATEGORY_SECURE_CODE}

def main():
    parser = argparse.ArgumentParser(description='佈建 node展覽館的 SysSqlExecutor 示範（B8）')
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
