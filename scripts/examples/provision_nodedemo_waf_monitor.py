#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
node展覽館 —— WAF 熱備健康監看（常駐迴圈 + 逾時自動處置）。

這張範本表單示範系統級維運流程：送單後流程常駐在背景，每 N 分鐘呼叫
ITHome2026-WAF/monitor_probe.sh 判定 WAF 對外與對內服務是否仍通；連續失敗
達門檻時發 Telegram 告警並開決策關卡。無人在時限內決定時，依送單時選的
預設值自動切換或繼續監看。

目標企業預設是系統預設企業（Organization.code='SYSTEM'），分類固定是
「node展覽館」。。

冪等：重跑會沿用既有表單／流程（依 code 找），bump revision 並重新發行
（會停用舊的已發行版本並建立新版）。填寫權限授予企業內所有非 EXTERNAL
的在職帳號。

用法：
    cd <repo>
    set -a && source .env && set +a
    venv/bin/python scripts/examples/provision_nodedemo_waf_monitor.py --dry-run
    venv/bin/python scripts/examples/provision_nodedemo_waf_monitor.py --apply

節點 config 欄位依 handler 原始碼確認：
    modules/form_workflow/services/node_handlers/os_executor_handler.py
    modules/form_workflow/services/node_handlers/formadapter_handler.py
    modules/form_workflow/services/node_handlers/branch_handler.py
    modules/form_workflow/services/node_handlers/fieldwrite_handler.py
    modules/form_workflow/services/node_handlers/end_handler.py
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

FORM_CODE = 'NODEDEMO_WAF_MONITOR'
FORM_NAME = 'WAF 熱備健康監看'
WORKFLOW_CODE = 'NODEDEMO_WAF_MONITOR_FLOW'
WORKFLOW_NAME = 'WAF 熱備健康監看（常駐迴圈 + 逾時自動處置）'
TELEGRAM_CONFIG_NAME = 'node展覽館示範（請填入真實 Bot Token）'
TELEGRAM_CHANNEL = '測試頻道'

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


def _select(key, label, options, description=''):
    comp = {
        'key': key, 'type': 'select', 'input': True, 'label': label, 'tableView': True,
        'dataSrc': 'values',
        'data': {'values': [{'label': label, 'value': value} for label, value in options]},
        'validate': {'required': True},
    }
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


def _disabled(comp):
    comp['disabled'] = True
    return comp


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


def build_monitor_schema(interval_minutes):
    fail_threshold = _select(
        'fail_threshold', '連續失敗幾次才告警',
        [('2 次', '2'), ('3 次', '3'), ('5 次', '5')],
        f'每圈間隔 {interval_minutes} 分鐘，3 次約 {interval_minutes * 3} 分鐘。')
    fail_threshold['defaultValue'] = '3'

    timeout_default_action = _select(
        'timeout_default_action', '無人決定時的處置',
        [('逾時自動執行切換', 'switch'), ('逾時不切換，只記錄並繼續監看', 'hold')],
        '這就是「無人在決策時限內回應時」系統採用的動作。')
    timeout_default_action['defaultValue'] = 'switch'

    return {
        'display': 'form',
        'components': [
            _title(FORM_NAME),
            _hint(f'這張單送出後流程就常駐在背景，每 {interval_minutes} 分鐘檢查一次；'
                  '正常時不寫表單、只留流程記錄（目前狀態請看流程管理頁）。請先依 '
                  'ITHome2026-WAF/failover.conf.example 建立 failover.conf。Telegram 佔位設定組'
                  '要到企業設定填入真實值並啟用才寄得出去。'),
            fail_threshold,
            timeout_default_action,
            _disabled(_textarea('event_log', '事件記錄（由流程寫回）', rows=16)),
            _submit_button(),
        ],
    }


def _decision_config(assignee_config, timeout_minutes):
    config = dict(assignee_config)
    config.update({
        'selection_mode': 'single',
        'output_variable': 'monitor_decision',
        'allow_comment': True,
        'require_comment': False,
        'use_custom_decisions': True,
        'input_variables': [],
        'timeout_enabled': True,
        'timeout_minutes': timeout_minutes,
        'timeout_mode': 'ABSOLUTE',
        'timeout_path_id': 'opt-auto',
        'decision_options': [
            {'id': 'opt-switch', 'label': '執行切換', 'value': 'switch',
             'style': 'primary', 'target_edges': ['edge-decision-switch']},
            {'id': 'opt-hold', 'label': '暫不切換，繼續監看', 'value': 'hold',
             'style': 'default', 'target_edges': ['edge-decision-hold']},
            {'id': 'opt-auto', 'label': '依本單預設設定處置', 'value': 'auto',
             'style': 'warning', 'target_edges': ['edge-decision-auto']},
        ],
    })
    return config


def build_monitor_graph(args, failover_dir, config_path, assignee_config, center_url):
    probe_command = f'bash {failover_dir}/monitor_probe.sh --config {config_path}'
    switch_command = f'bash {failover_dir}/failover.sh --config {config_path} switch --yes'
    # ${fi.serial} 才是流水號（不是 fi.serial_number；未知鍵一律靜默回空字串）
    # 網址一律取自系統設定 system_base_url（URL-02），未設定就不放連結、不猜。
    alert_message = (
        '⚠️ WAF 對外服務異常\n'
        '偵測：${v.hc_stdout}'          # hc_stdout 自帶尾端換行
        '連續失敗：${v.fail_streak} 次\n'
        '單號：${fi.serial}（${wi.exec_code}）\n'
        '請到表單中心決定是否切換；'
        f'逾時 {args.decision_timeout_minutes} 分鐘未回應將依本單設定「'
        '${f.timeout_default_action}」處置。'
    )
    if center_url:
        alert_message += '\n' + center_url
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, 120, 300,
              '流程入口。送單後即啟動常駐監看迴圈。'),
        _node('node-Init', 'OpSet', '初始化計數', {
            'operations': [{'target_var': 'fail_streak', 'operation': 'set', 'value': 0}],
        }, 320, 300,
            '初始化連續失敗次數，確保第一次進入迴圈時從 0 開始計算。'),
        _node('node-Delay', 'Delay', '等待下一輪', {
            'delay_minutes': args.interval_minutes,
        }, 520, 300,
            '等待下一輪健康探測。這個流程刻意形成迴圈，讓同一張單常駐監看。'),
        _node('node-Probe', 'OsExecutor', '健康探測', {
            'command': probe_command,
            'result_var': 'hc',
            'timeout_seconds': args.probe_timeout_seconds,
            'expect_exit_codes': [0],
            'wait_for_result': True,
            'kill_on_timeout': 'group',
            'notify_on_exception': False,
        }, 720, 300,
            '呼叫 monitor_probe.sh 檢查停止旗標、自我隔離、對外與對內連線；'
            '判定結果由 stdout 的 STATE 欄位提供。'),
        _node('node-BranchState', 'Branch', '探測結果分流', {
            'rules': [
                {'name': '收到停止旗標',
                 'conditions': [{'variable': '${v.hc_stdout}', 'operator': 'contains',
                                  'value': 'STATE=STOP'}],
                 'target_edges': ['edge-state-stop']},
                {'name': '服務正常',
                 'conditions': [{'variable': '${v.hc_stdout}', 'operator': 'contains',
                                  'value': 'STATE=OK'}],
                 'target_edges': ['edge-state-ok']},
                {'name': '管理機自己斷網',
                 'conditions': [{'variable': '${v.hc_stdout}', 'operator': 'contains',
                                  'value': 'STATE=ISOLATED'}],
                 'target_edges': ['edge-state-isolated']},
            ],
            'fallback': {'action': 'route', 'target_edge': 'edge-state-fail',
                         'log_message': '探測未回報 OK/ISOLATED/STOP，視為服務失敗'},
        }, 940, 300,
            '依探測 stdout 分流。沒有明確 OK、ISOLATED 或 STOP 時，fallback 會視為服務失敗並推進。'),
        _node('node-Healthy', 'OpSet', '恢復正常，重置計數', {
            'operations': [{'target_var': 'fail_streak', 'operation': 'set', 'value': 0}],
        }, 940, 120,
            '服務正常時清空連續失敗次數，回到下一輪監看。'),
        _node('node-Fail', 'OpSet', '失敗計數 +1', {
            'operations': [{'target_var': 'fail_streak', 'operation': 'increment'}],
        }, 1160, 300,
            '探測判定服務失敗時，將連續失敗次數加一。'),
        _node('node-BranchThreshold', 'Branch', '達到告警門檻？', {
            'rules': [
                {'name': '達到告警門檻',
                 'conditions': [{'variable': '${v.fail_streak}', 'operator': '>=',
                                  'value': '${f.fail_threshold}'}],
                 'target_edges': ['edge-threshold-alert']},
            ],
            'fallback': {'action': 'route', 'target_edge': 'edge-threshold-delay',
                         'log_message': '尚未達門檻，繼續監看'},
        }, 1380, 300,
            '連續失敗次數達到送單時設定的門檻才告警；未達門檻就回到等待下一輪。'),
        _node('node-Alert', 'SysTelegram', '發出告警', {
            'config_id': args.telegram_config,
            'channel_name': args.telegram_channel,
            'message': alert_message,
        }, 1600, 300,
            '服務連續失敗達門檻時，以系統 Telegram 設定發送告警與表單中心連結。'),
        _node('node-Decision', 'FormAdapter', '是否切換（逾時自動處置）',
              _decision_config(assignee_config, args.decision_timeout_minutes), 1820, 300,
              '人員決策關卡。可執行切換、暫不切換，或主動選擇依本單預設設定處置；'
              '逾時也會走同一個預設處置選項。'),
        _node('node-Switch', 'OsExecutor', '執行熱備切換', {
            'command': switch_command,
            'result_var': 'fo',
            'timeout_seconds': args.switch_timeout_seconds,
            'expect_exit_codes': [0],
            'wait_for_result': True,
            'kill_on_timeout': 'group',
            'notify_on_exception': True,
        }, 2060, 220,
            '呼叫 failover.sh switch --yes 執行 WAF 熱備切換。真正結果看 fo_result 與 fo_stdout。'),
        _node('node-BranchAuto', 'Branch', '逾時預設動作', {
            'rules': [
                {'name': '預設為切換',
                 'conditions': [{'variable': '${f.timeout_default_action}', 'operator': '==',
                                  'value': 'switch'}],
                 'target_edges': ['edge-auto-switch']},
            ],
            'fallback': {'action': 'route', 'target_edge': 'edge-auto-hold',
                         'log_message': '預設為不切換，只記錄'},
        }, 2060, 420,
            '依送單時選擇的逾時預設動作分流；未選切換時只記錄事件。'),
        _node('node-WriteEvent', 'OpFieldWrite', '寫回事件記錄', {
            'target_field': 'event_log',
            # hc_stdout 自帶尾端換行，直接接續即可；額外包中括號會被換行拆開
            'content': ('${f.event_log}\n'
                        '${v.hc_stdout}'
                        '決策=${v.monitor_decision} 切換結果=${v.fo_result}\n'
                        '${v.fo_stdout}'),
            'content_type': 'text',
        }, 2300, 300,
            '把本次告警、決策與切換輸出追加到事件記錄欄位，保留表單留痕。'),
        _node('node-Resume', 'OpSet', '重置計數，回到監看', {
            'operations': [
                {'target_var': 'fail_streak', 'operation': 'set', 'value': 0},
                {'target_var': 'fo_result', 'operation': 'set', 'value': ''},
                {'target_var': 'fo_stdout', 'operation': 'set', 'value': ''},
            ],
        }, 2520, 300,
            '處置完成後重置連續失敗次數並清掉上一輪的切換結果，'
            '避免下一圈立刻重複告警、或把過期的切換輸出寫進事件記錄。'),
        _node('node-EndStop', 'End', '停止監看', {'finish_mode': 'detach'}, 1160, 120,
              '收到停止旗標時正常結束流程，使用 detach 表示這是預期收尾。'),
    ]
    edges = [
        _edge('edge-start-init', 'node-Start', 'node-Init'),
        _edge('edge-init-delay', 'node-Init', 'node-Delay'),
        _edge('edge-delay-probe', 'node-Delay', 'node-Probe'),
        _edge('edge-probe-state', 'node-Probe', 'node-BranchState'),
        _edge('edge-state-stop', 'node-BranchState', 'node-EndStop', '收到停止旗標'),
        _edge('edge-state-ok', 'node-BranchState', 'node-Healthy', '正常'),
        _edge('edge-state-isolated', 'node-BranchState', 'node-Delay', '管理機自己斷網'),
        _edge('edge-state-fail', 'node-BranchState', 'node-Fail', '失敗'),
        _edge('edge-healthy-delay', 'node-Healthy', 'node-Delay'),
        _edge('edge-fail-threshold', 'node-Fail', 'node-BranchThreshold'),
        _edge('edge-threshold-alert', 'node-BranchThreshold', 'node-Alert', '達門檻'),
        _edge('edge-threshold-delay', 'node-BranchThreshold', 'node-Delay', '未達門檻'),
        _edge('edge-alert-decision', 'node-Alert', 'node-Decision'),
        _edge('edge-decision-switch', 'node-Decision', 'node-Switch', '執行切換'),
        _edge('edge-decision-hold', 'node-Decision', 'node-WriteEvent', '暫不切換'),
        _edge('edge-decision-auto', 'node-Decision', 'node-BranchAuto', '依預設設定處置'),
        _edge('edge-auto-switch', 'node-BranchAuto', 'node-Switch', '預設＝切換'),
        _edge('edge-auto-hold', 'node-BranchAuto', 'node-WriteEvent', '預設＝不切換'),
        _edge('edge-switch-write', 'node-Switch', 'node-WriteEvent'),
        _edge('edge-write-resume', 'node-WriteEvent', 'node-Resume'),
        _edge('edge-resume-delay', 'node-Resume', 'node-Delay'),
    ]
    return _graph(nodes, edges)


MONITOR_DESCRIPTION = (
    '【這個流程示範什麼】\n'
    '這是一個系統級表單流程範例：送單後流程常駐在背景，每圈呼叫 monitor_probe.sh'
    '檢查 WAF 對外與對內服務。圖上有多條邊回到「等待下一輪」，這個迴圈是刻意的，'
    '用同一張單承載長時間監看與告警決策。\n\n'
    '【本流程的設定重點】\n'
    '- 正常與管理機自我隔離時只留流程記錄，不寫表單欄位，避免表單被每圈噪音洗版。\n'
    '- stop 旗標 /opt/tmp/waf-monitor.stop 存在時，下一圈會走到 End(detach) 正常結束。\n'
    '- 連續失敗達門檻才發 Telegram；決策關卡有三顆按鈕：執行切換、暫不切換，'
    '以及依本單預設設定處置。逾時會自動走第三顆按鈕，再依送單時選的預設值分流。\n'
    '- monitor_probe.sh 每次執行都會寫 heartbeat；另有 waf_monitor_watchdog.py 由 crontab'
    '監看 heartbeat，避免監看流程自己靜默停止。\n\n'
    '【怎麼看結果】\n'
    '正常輪次請看流程節點記錄；只有達門檻告警與處置後才會追加 event_log。若要停止'
    '常駐監看，建立 stop 旗標後等下一輪，流程會以正常收尾方式離開。'
)


def build_demo(args, failover_dir, config_path, assignee_config, center_url):
    return {
        'form_code': FORM_CODE,
        'form_name': FORM_NAME,
        'form_schema': build_monitor_schema(args.interval_minutes),
        'workflow_code': WORKFLOW_CODE,
        'workflow_name': WORKFLOW_NAME,
        'description': MONITOR_DESCRIPTION,
        'graph': lambda: build_monitor_graph(args, failover_dir, config_path, assignee_config, center_url),
    }


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
            created_by_name='provision_nodedemo_waf_monitor',
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
    log(f"  表單欄位 {len(demo['form_schema']['components'])} 個，流程節點 "
        f"{len(graph['nodes'])} 個，邊 {len(graph['edges'])} 條")

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


def repo_root():
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))


def default_failover_dir():
    return os.path.join(repo_root(), 'ITHome2026-WAF')


def build_parser():
    parser = argparse.ArgumentParser(
        description='佈建 node展覽館的 WAF 熱備健康監看範本',
        formatter_class=argparse.RawTextHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--dry-run', action='store_true', help='只列出會做什麼，不寫入')
    group.add_argument('--apply', action='store_true', help='實際寫入資料庫')
    parser.add_argument('--org', default=ORG_CODE, help=f'企業 code（預設 {ORG_CODE}）')
    parser.add_argument('--failover-dir', default=default_failover_dir(),
                        help='failover.sh / monitor_probe.sh 所在目錄（預設為本 repo 的 ITHome2026-WAF）')
    parser.add_argument('--config', default=None,
                        help='failover.conf 路徑（預設 <failover-dir>/failover.conf）')
    parser.add_argument('--interval-minutes', type=int, default=3,
                        help='每圈間隔分鐘數（預設 3）')
    parser.add_argument('--decision-timeout-minutes', type=int, default=15,
                        help='決策關卡逾時分鐘數（預設 15）')
    parser.add_argument('--probe-timeout-seconds', type=int, default=60,
                        help='健康探測 OsExecutor timeout_seconds（預設 60）')
    parser.add_argument('--switch-timeout-seconds', type=int, default=240,
                        help='熱備切換 OsExecutor timeout_seconds（預設 240）')
    parser.add_argument('--approver-role', default=None,
                        help='決策關卡角色 code；未給則指派送單者自己決策')
    parser.add_argument('--telegram-config', default=None,
                        help='TelegramConfig secure_code（預設為 node展覽館佔位設定組）')
    parser.add_argument('--telegram-channel', default=TELEGRAM_CHANNEL,
                        help='Telegram 頻道名稱（預設 測試頻道）')
    return parser


def resolve_role_secure_code(Role, org_sc, role_code):
    if not role_code:
        return None
    role = Role.query.filter_by(
        org_secure_code=org_sc, code=role_code, is_deleted=False, is_active=True).first()
    if not role:
        raise ValueError(f'找不到角色：{role_code}（企業內 roles.code）')
    return role.secure_code


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


def _validate_opts(args):
    if args.interval_minutes < 1 or args.interval_minutes > 60:
        raise ValueError('--interval-minutes 必須介於 1 到 60')
    if args.decision_timeout_minutes < 1 or args.decision_timeout_minutes > 1440:
        raise ValueError('--decision-timeout-minutes 必須介於 1 到 1440')
    if args.probe_timeout_seconds < 1 or args.probe_timeout_seconds > 3600:
        raise ValueError('--probe-timeout-seconds 必須介於 1 到 3600')
    if args.switch_timeout_seconds < 1 or args.switch_timeout_seconds > 3600:
        raise ValueError('--switch-timeout-seconds 必須介於 1 到 3600')


def provision(org, apply=True, **opts):
    from argparse import Namespace
    from app import db
    from app.models import Role, User
    from app.utils.external_url import get_system_base_url

    db.session.execute(db.text("SET LOCAL app.is_system_admin = 'true'"))
    global SHOWCASE_CATEGORY_SECURE_CODE
    SHOWCASE_CATEGORY_SECURE_CODE = ensure_showcase_category(org).secure_code

    telegram_config = opts.get('telegram_config')
    if not telegram_config:
        telegram_config = ensure_telegram_config(org, apply=apply).secure_code

    args = Namespace(
        interval_minutes=int(opts.get('interval_minutes') or 3),
        decision_timeout_minutes=int(opts.get('decision_timeout_minutes') or 15),
        probe_timeout_seconds=int(opts.get('probe_timeout_seconds') or 60),
        switch_timeout_seconds=int(opts.get('switch_timeout_seconds') or 240),
        approver_role=opts.get('approver_role'),
        telegram_config=telegram_config,
        telegram_channel=opts.get('telegram_channel') or TELEGRAM_CHANNEL,
    )
    _validate_opts(args)

    failover_dir = os.path.abspath(opts.get('failover_dir') or default_failover_dir())
    config_path = os.path.abspath(opts.get('config') or os.path.join(failover_dir, 'failover.conf'))

    models = _workflow_models()
    osc = org.secure_code
    log(f'企業：{org.name}（{osc}）')
    load_node_icons(models)

    role_sc = resolve_role_secure_code(Role, osc, args.approver_role)
    if role_sc:
        assignee_config = {'assignee_type': 'ROLE', 'assignee_value': role_sc,
                           'unit_scope': 'GLOBAL'}
        log(f'決策關卡角色：{args.approver_role}（{role_sc}）')
    else:
        assignee_config = {'assignee_type': 'INITIATOR'}
        log('決策關卡：INITIATOR（送單者自己決策）')

    publisher = User.query.filter_by(
        org_secure_code=osc, user_type='ORG_ADMIN',
        is_deleted=False, is_active=True).first()

    log(f'failover-dir：{failover_dir}')
    log(f'config：{config_path}')
    log(f'每圈間隔：{args.interval_minutes} 分鐘')
    log(f'決策逾時：{args.decision_timeout_minutes} 分鐘')
    log(f'Telegram：config={args.telegram_config} channel={args.telegram_channel}')

    base_url = get_system_base_url()
    if base_url:
        center_url = f"{base_url}{os.getenv('APP_PREFIX', '/beakplatform').rstrip('/')}/forms/center"
        log(f'表單中心連結：{center_url}')
    else:
        center_url = None
        log('系統對外網址（system_base_url）未設定，告警訊息不附連結')

    demo = build_demo(args, failover_dir, config_path, assignee_config, center_url)

    log('\n=== WAF 熱備健康監看（表單／流程／配對／發行） ===')
    result = apply_full_demo(db, models, org, demo, publisher, apply)
    return {'results': {WORKFLOW_CODE: result}, 'category_secure_code': SHOWCASE_CATEGORY_SECURE_CODE}


def main():
    parser = build_parser()
    args = parser.parse_args()

    from app import create_app, db

    app = create_app('development')
    with app.app_context():
        from app.models import Organization

        org = Organization.query.filter_by(code=args.org, is_deleted=False).first()
        if not org:
            log(f'找不到企業：{args.org}')
            return 1
        try:
            result = provision(
                org,
                apply=args.apply,
                failover_dir=args.failover_dir,
                config=args.config,
                interval_minutes=args.interval_minutes,
                decision_timeout_minutes=args.decision_timeout_minutes,
                probe_timeout_seconds=args.probe_timeout_seconds,
                switch_timeout_seconds=args.switch_timeout_seconds,
                approver_role=args.approver_role,
                telegram_config=args.telegram_config,
                telegram_channel=args.telegram_channel,
            )
        except ValueError as exc:
            parser.error(str(exc))

        if args.apply:
            db.session.commit()
            log('\n已寫入。到 /forms/center 的「填寫表單」就看得到這張單。')
            item = result['results'][WORKFLOW_CODE]
            if item:
                log(f"\n{WORKFLOW_CODE}: form_sc={item['form_sc']} "
                    f"wf_sc={item['wf_sc']} published_sc={item['published_sc']}")
        else:
            db.session.rollback()
            log('\n[預演] 未寫入任何資料')
    return 0


if __name__ == '__main__':
    sys.exit(main())
