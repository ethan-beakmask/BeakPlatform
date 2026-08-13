"""
OpenDefense 兩個資安事件處置流程的 graph 定義（純資料 + 組裝函式）。

本檔只負責產生 fw_workflow_templates.graph 的內容，不碰資料庫。
建置流程請用 scripts/examples/provision_od_workflow_variants.py。

--------------------------------------------------------------------------
兩個流程的定位
--------------------------------------------------------------------------
A. SOC 團隊版 (build_soc_team_graph)
   適用 3~8 人、有輪班的監控中心。高危案件開「簽核 + 計時」雙軌，
   逾時只催辦與升級通報，不代替人做處置。

B. 小企業單人版 (build_solo_graph)
   適用只有一位資安人員、每天 8 小時上班、16 小時無人看管的組織。
   高危且有可處置目標的案件：
     - 非上班時段 -> 立即自動封鎖（短 TTL），隔天人工複核
     - 上班時段   -> 人工處置，但逾時未處理仍會自動封鎖（補上週末與下班邊界）

--------------------------------------------------------------------------
寫這兩份 graph 時必須遵守的引擎行為（都是實測，不是推測）
--------------------------------------------------------------------------
1. Branch 會展開「所有」命中的規則（branch_handler.py:128-147），不是
   first-match-wins。同一個 Branch 的規則必須互斥，否則會同時走多條路徑。
2. Branch 條件的 logic 是「group 切分符」：掃描 conditions，遇到 logic='OR'
   或掃到最後一條就收尾成一個 group。group 內 AND、group 間 OR。
   要表達「A 且 B」就兩條都標 AND。
3. 條件比較失敗（欄位缺值、型別不符）一律回 False（branch_handler.py:204-208）。
   這是刻意利用的 fail-safe：缺 severity_id 的案件會四條規則都不命中，
   由 fallback 送去人工處理。
4. 節點沒有出邊時該分支安全終止，不會報錯也不會結束流程
   （workflow_engine.py:360 `if not next_node_ids: return []`）。
   並行分支要「靜靜結束」就指向一個無出邊的 OpSet 節點。
5. End 的 finish_mode='cancel' 會取消所有未完成節點（node_runner.py:163）。
   有並行分支的流程一律用 cancel，否則計時分支會殘留。
6. DecisionWriter 的 target_value 替換後為空會回 error 讓節點失敗，
   所以自動封鎖前必須先用 Branch 確認 actor_ip 非空。
7. decided_via 的自動推斷看 last_completed_node_type，在並行分支下不可靠，
   因此每個 DecisionWriter 都明確標註 human / auto。
8. AlertBroadcast 的 broadcast_code 不做變數替換（只有 title/message 有），
   同 code 會覆蓋前一則並清掉確認記錄。所以它的語意是「最新一則告警橫幅」，
   不是每案通知。
9. ${t.time} 是 UTC 且沒有星期幾的變數。時段判斷只能用 matches (regex)，
   `>=` 會因為 float() 失敗而恆為 False。
"""

# 上班時段的 UTC 小時 regex：01:00:00 ~ 09:59:59 (UTC) = 09:00 ~ 17:59 (Asia/Taipei)
# 換時區或換上班時間，改這一條即可。UTC = 當地時間 - 時差。
OFFICE_HOURS_UTC_REGEX = r'^0[1-9]:'
OFFICE_HOURS_NOTE = '預設上班時段 09:00-18:00 (Asia/Taipei) = 01:00-09:59 (UTC)'

# 可自動封鎖的來源位址：排除私有網段與回送位址。
#
# 為什麼非有不可（2026-08-13 實際踩到）：偵測器多半架在流量出口的那台主機上，
# 外部訪客經反向代理進來時，偵測器看到的 actor.ip 會是**代理自己的內網位址**。
# 本機環境近 200 筆真實 suricata 告警裡，有 25 筆的 actor_ip 是 192.168.0.20
# ——那正是平台自己 Cloudflare 路徑上的 nginx。若沒有這道排除，
# 小企業版的自動封鎖會反覆把自家基礎設施加進封鎖清單，而且沒有人在看。
#
# 這類案件不是不處理，是**改走人工路徑**：交給人判斷該封的是誰。
# 用負向 lookahead 而不是 not_startswith，因為分支節點沒有這個運算子。
# 分支節點沒有 not_matches 運算子，所以正反兩個 pattern 都要備妥：
# 判「可自動封鎖」用負向 lookahead，判「不可自動封鎖」用正向列舉。
_PRIVATE_IP_ALTERNATION = (
    r'10\.|127\.|0\.|169\.254\.|192\.168\.|'
    r'172\.(1[6-9]|2[0-9]|3[01])\.|::1$|[fF][cCdD]'
)
# 注意：負向 lookahead 對**空字串**是成立的（沒東西可否定）。所以用它的規則
# 必須另外搭一條 not_empty，不能只靠這一條擋掉沒有 actor_ip 的案件。
PUBLIC_IP_REGEX = r'^(?!' + _PRIVATE_IP_ALTERNATION + r')'
PRIVATE_IP_REGEX = r'^(' + _PRIVATE_IP_ALTERNATION + r')'
PUBLIC_IP_NOTE = '排除私有網段（RFC1918）、回送與 link-local'

# 小企業版自動封鎖的 TTL：24 小時。
# 選 24 小時而不是涵蓋週末的 72 小時，理由是攻擊持續就會重複觸發、重複開案、
# 重複封鎖，短 TTL 不會留下永久缺口；反過來誤封會在 24 小時內自癒。
AUTO_BLOCK_TTL_SECONDS = 86400
# 人工確認後的封鎖 TTL：7 天
CONFIRMED_BLOCK_TTL_SECONDS = 604800
# SOC 團隊版人工封鎖的 TTL：1 小時（沿用原流程，有人隨時可再延長）
SOC_BLOCK_TTL_SECONDS = 3600

# 小企業版上班時段的人工處理等待期（分鐘）。逾時即自動封鎖。
SOLO_DAYTIME_GRACE_MINUTES = 30
# SOC 團隊版的 SLA 催辦與升級間隔（分鐘）
SOC_SLA_WARN_MINUTES = 15
SOC_SLA_ESCALATE_MINUTES = 15

ICON_BASE = '/static/modules/form_workflow/icons/workflow'

_EDGE_STYLE = {
    'width': 1,
    'line-color': 'rgb(149,165,166)',
    'line-style': 'solid',
    'arrow-scale': 1,
    'curve-style': 'straight',
    'target-arrow-color': 'rgb(149,165,166)',
    'target-arrow-shape': 'triangle',
}

# 統一的情報摘要內容（兩個流程共用）
_INTEL_TEMPLATE = (
    '24小時內同源事件 ${f.od_repeat_count} 件，本案聚合 ${f.od_event_count} 件，'
    '該 IP 歷史封鎖 ${f.od_history_block_count} 次；風險分數 ${f.risk_score}，'
    '建議處置 ${f.recommended_action}。'
)


def _node(node_id, node_type, label, config=None, x=0, y=0, description=''):
    """組一個節點。icon 一律用無 nginx 前綴的路徑（渲染時才補前綴）。"""
    return {
        'id': node_id,
        'type': node_type,
        'label': label,
        'icon': f'{ICON_BASE}/{node_type.lower()}.svg',
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


def _cond(variable, operator, value, logic='AND'):
    return {'variable': variable, 'operator': operator, 'value': value, 'logic': logic}


def _intel_node(node_id, x, y):
    return _node(
        node_id, 'OpFieldWrite', '情報摘要',
        {'target_field': 'intel_summary', 'content': _INTEL_TEMPLATE},
        x, y,
        '把聚合、歷史封鎖次數與風險分數寫進表單，讓簽核者不必自己翻原始事件。',
    )


def _archive_node(node_id, x, y):
    return _node(
        node_id, 'OpFieldWrite', '低危歸檔註記',
        {
            'target_field': 'intel_summary',
            'content': '低危事件（severity ${f.severity_id}）自動歸檔，未進入人工簽核。',
        },
        x, y,
        '低危不佔用人力，只留下可追溯的註記。',
    )


def _noop_node(node_id, label, marker, x, y, description=''):
    """
    無出邊的分支終止節點。

    並行分支要結束時不能走 End（那會結束整個流程），指向這種節點即可讓
    該分支安全停住，流程仍等待另一條分支。
    """
    return _node(
        node_id, 'OpSet', label,
        {'operations': [{'target_var': 'sla_track', 'operation': 'set', 'value': marker}]},
        x, y, description,
    )


# =============================================================================
# A. SOC 團隊版
# =============================================================================

def build_soc_team_graph(role_staff_sc: str, role_supervisor_sc: str) -> dict:
    """
    組出 SOC 團隊版的 graph。

    Args:
        role_staff_sc: 一線簽核角色（資安人員）的 secure_code
        role_supervisor_sc: 二線處置角色（資安主管）的 secure_code
    """
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, -560, 0),
        _intel_node('node-FieldWrite-intel', -420, 0),
        _node(
            'node-Branch-severity', 'Branch', '嚴重度分流',
            {
                'rules': [
                    {
                        'name': '高危雙軌（簽核＋SLA 計時）',
                        'conditions': [_cond('${f.severity_id}', '>=', 4)],
                        'target_edges': ['edge-high'],
                    },
                    {
                        'name': '中危標準簽核',
                        'conditions': [_cond('${f.severity_id}', '==', 3)],
                        'target_edges': ['edge-med'],
                    },
                    {
                        'name': '低危自動歸檔',
                        'conditions': [_cond('${f.severity_id}', '<=', 2)],
                        'target_edges': ['edge-low'],
                    },
                ],
                'fallback': {
                    'action': 'route',
                    'target_edge': 'edge-med',
                    'log_message': '嚴重度缺值或無法比較，走中危標準簽核（fail-safe 交給人）',
                },
            },
            -280, 0,
            '三條規則互斥。缺 severity_id 時比較失敗、三條都不命中，由 fallback 送人工。',
        ),
        _archive_node('node-FieldWrite-archive', -140, -190),
        _node(
            'node-Fork-high', 'ParallelFork', '高危雙軌',
            {}, -140, 0,
            '一條交給值班人員簽核，一條純計時。計時分支不會代替人做處置。',
        ),

        # --- A 路：人工簽核 ---
        _node(
            'node-FormAdapter-L1', 'FormAdapter', '一線簽核（高危）',
            {
                'assignee_type': 'ROLE',
                'assignee_value': role_staff_sc,
                'assignee_label': '資安人員',
                'assignee_list': [],
                'selection_mode': 'single',
                'output_variable': 'soc_decision',
                'allow_comment': True,
                'require_comment': True,
                'min_comment_length': 10,
                'use_custom_decisions': True,
                'input_variables': [],
                'decision_options': [
                    {'id': 'opt-block', 'label': '封鎖攻擊來源', 'value': 'block',
                     'style': 'danger', 'target_edges': ['edge-l1-block']},
                    {'id': 'opt-allow', 'label': '放行（可接受風險）', 'value': 'allow',
                     'style': 'default', 'target_edges': ['edge-l1-allow']},
                    {'id': 'opt-escalate', 'label': '升級二線', 'value': 'escalate',
                     'style': 'default', 'target_edges': ['edge-l1-escalate']},
                    {'id': 'opt-fp', 'label': '誤判結案', 'value': 'false_positive',
                     'style': 'danger', 'target_edges': ['edge-l1-fp']},
                ],
            },
            0, 90,
            'min_comment_length 設 10，避免「ok」兩個字就算完成簽核意見。',
        ),
        _node(
            'node-FormAdapter-L1med', 'FormAdapter', '一線簽核（中危）',
            {
                'assignee_type': 'ROLE',
                'assignee_value': role_staff_sc,
                'assignee_label': '資安人員',
                'assignee_list': [],
                'selection_mode': 'single',
                'output_variable': 'soc_decision',
                'allow_comment': True,
                'require_comment': True,
                'min_comment_length': 10,
                'use_custom_decisions': True,
                'input_variables': [],
                'decision_options': [
                    {'id': 'opt-m-block', 'label': '封鎖攻擊來源', 'value': 'block',
                     'style': 'danger', 'target_edges': ['edge-med-block']},
                    {'id': 'opt-m-allow', 'label': '放行（可接受風險）', 'value': 'allow',
                     'style': 'default', 'target_edges': ['edge-med-allow']},
                    {'id': 'opt-m-escalate', 'label': '升級二線', 'value': 'escalate',
                     'style': 'default', 'target_edges': ['edge-med-escalate']},
                    {'id': 'opt-m-fp', 'label': '誤判結案', 'value': 'false_positive',
                     'style': 'danger', 'target_edges': ['edge-med-fp']},
                ],
            },
            0, 250,
            '中危沒有 SLA 計時分支：60 分鐘的 SLA 靠處置中心清單標示即可。',
        ),
        _node(
            'node-FormAdapter-L2', 'FormAdapter', '二線處置',
            {
                'assignee_type': 'ROLE',
                'assignee_value': role_supervisor_sc,
                'assignee_label': '資安主管',
                'assignee_list': [],
                'selection_mode': 'single',
                'output_variable': 'l2_decision',
                'allow_comment': True,
                'require_comment': True,
                'min_comment_length': 10,
                'use_custom_decisions': True,
                'input_variables': [],
                'decision_options': [
                    {'id': 'opt-l2-block', 'label': '處置完成－封鎖', 'value': 'block',
                     'style': 'danger', 'target_edges': ['edge-l2-block']},
                    {'id': 'opt-l2-close', 'label': '處置完成－結案', 'value': 'closed',
                     'style': 'default', 'target_edges': ['edge-l2-close']},
                ],
            },
            170, 170,
            '指向資安主管而非企業管理員，把管理員從每日執行鏈裡拉出來。',
        ),
        _node(
            'node-Decision-block', 'DecisionWriter', '寫入封鎖決策',
            {
                'action': 'block',
                'target_type': 'ip',
                'target_value': '${f.actor_ip}',
                'severity': 'high',
                'ttl_seconds': SOC_BLOCK_TTL_SECONDS,
                'decided_via': 'human',
                'enforcement_points': ['nftables'],
                'reason_template':
                    'SOC 處置 ${wi.exec_code}：${f.finding_title}（rule ${f.finding_rule_id}）',
            },
            340, 90,
            'decided_via 明確標 human；並行分支下自動推斷不可靠。',
        ),
        _node(
            'node-Decision-allow', 'DecisionWriter', '寫入放行決策',
            {
                'action': 'allow',
                'target_type': 'ip',
                'target_value': '${f.actor_ip}',
                'severity': 'info',
                'decided_via': 'human',
                'enforcement_points': ['nftables'],
                'reason_template':
                    'SOC 判定可接受風險 ${wi.exec_code}：${f.finding_title}',
            },
            340, 250,
            '放行也留下決策紀錄，之後同來源再進案時看得到前次判斷。',
        ),
        _node(
            'node-Alert-blocked', 'AlertBroadcast', '封鎖完成通報',
            {
                'broadcast_code': 'SOC-BLOCK-DONE',
                'title': '資安處置：已封鎖 ${f.actor_ip}',
                'message': '案件 ${wi.exec_code}（${f.finding_title}）已寫入封鎖決策，'
                           '目標 ${f.actor_ip}，TTL 1 小時，執行點 nftables。',
                'require_ack': False,
                'target_type': 'specific',
                'target_roles': ['SECURITY_STAFF', 'SOC_SUPERVISOR'],
                'target_departments': [],
            },
            500, 90,
            'require_ack 關掉、發角色不發單一管理員：原流程要 ORG_ADMIN 逐件確認，'
            '一個人會變成瓶頸。',
        ),

        # --- B 路：SLA 計時（只催辦，不代人處置）---
        _node(
            'node-Delay-sla1', 'Delay', f'SLA 計時 {SOC_SLA_WARN_MINUTES} 分',
            {'delay_minutes': SOC_SLA_WARN_MINUTES}, 0, -70,
            '高危 SLA。時間到才醒來檢查有沒有人簽。',
        ),
        _node(
            'node-Branch-slacheck1', 'Branch', '檢查是否已簽核',
            {
                'rules': [
                    {
                        'name': '已簽核',
                        'conditions': [_cond('${v.soc_decision}', 'not_empty', '')],
                        'target_edges': ['edge-sla1-signed'],
                    },
                    {
                        'name': '逾時未簽核',
                        'conditions': [_cond('${v.soc_decision}', 'empty', '')],
                        'target_edges': ['edge-sla1-warn'],
                    },
                ],
                'fallback': {
                    'action': 'route',
                    'target_edge': 'edge-sla1-signed',
                    'log_message': '無法判定簽核狀態，不催辦（寧可漏催也不要誤催）',
                },
            },
            170, -70,
        ),
        _noop_node('node-Noop-signed1', '準時完成', 'signed_in_sla', 340, -160,
                   '無出邊：計時分支到此靜靜結束，人工簽核那條繼續。'),
        _node(
            'node-Alert-slawarn', 'AlertBroadcast', 'SLA 逾時催辦',
            {
                'broadcast_code': 'SOC-SLA-WARN',
                'title': 'SLA 逾時：${f.finding_title}',
                'message': f'案件 ${{wi.exec_code}} 已超過 {SOC_SLA_WARN_MINUTES} 分鐘'
                           '無人簽核，請至資安案件處置中心處理。',
                'require_ack': False,
                'target_type': 'specific',
                'target_roles': ['SECURITY_STAFF'],
                'target_departments': [],
            },
            340, -70,
        ),
        _node(
            'node-Delay-sla2', 'Delay', f'再等 {SOC_SLA_ESCALATE_MINUTES} 分',
            {'delay_minutes': SOC_SLA_ESCALATE_MINUTES}, 500, -70,
        ),
        _node(
            'node-Branch-slacheck2', 'Branch', '二次檢查',
            {
                'rules': [
                    {
                        'name': '已簽核',
                        'conditions': [_cond('${v.soc_decision}', 'not_empty', '')],
                        'target_edges': ['edge-sla2-signed'],
                    },
                    {
                        'name': '仍未簽核',
                        'conditions': [_cond('${v.soc_decision}', 'empty', '')],
                        'target_edges': ['edge-sla2-escalate'],
                    },
                ],
                'fallback': {
                    'action': 'route',
                    'target_edge': 'edge-sla2-signed',
                    'log_message': '無法判定簽核狀態，不升級通報',
                },
            },
            660, -70,
        ),
        _noop_node('node-Noop-signed2', '催辦後完成', 'signed_after_warn', 820, -160),
        _node(
            'node-Alert-slaescalate', 'AlertBroadcast', '升級通報主管',
            {
                'broadcast_code': 'SOC-SLA-ESCALATE',
                'title': '案件無人處理：${f.finding_title}',
                'message': f'案件 ${{wi.exec_code}} 經催辦後仍超過 '
                           f'{SOC_SLA_WARN_MINUTES + SOC_SLA_ESCALATE_MINUTES} 分鐘'
                           '無人簽核，請主管介入。',
                'require_ack': True,
                'target_type': 'specific',
                'target_roles': ['SOC_SUPERVISOR'],
                'target_departments': [],
            },
            820, -70,
            '這則要 ack：主管必須知道自己看過了。',
        ),
        _noop_node('node-Noop-escalated', '已升級通報', 'escalated', 980, -70,
                   '無出邊。計時分支的任務到此為止，處置權仍在人手上。'),

        _node(
            'node-End', 'End', 'End',
            {'finish_mode': 'cancel', 'wait_seconds': 3},
            660, 90,
            'cancel 模式：簽核完成時一併清掉還在計時的分支。',
        ),
    ]

    edges = [
        _edge('edge-start', 'node-Start', 'node-FieldWrite-intel'),
        _edge('edge-intel-branch', 'node-FieldWrite-intel', 'node-Branch-severity'),
        _edge('edge-high', 'node-Branch-severity', 'node-Fork-high', '高危'),
        _edge('edge-med', 'node-Branch-severity', 'node-FormAdapter-L1med', '中危'),
        _edge('edge-low', 'node-Branch-severity', 'node-FieldWrite-archive', '低危'),
        _edge('edge-arch-end', 'node-FieldWrite-archive', 'node-End'),

        _edge('edge-fork-sign', 'node-Fork-high', 'node-FormAdapter-L1', '簽核'),
        _edge('edge-fork-timer', 'node-Fork-high', 'node-Delay-sla1', 'SLA 計時'),

        _edge('edge-l1-block', 'node-FormAdapter-L1', 'node-Decision-block', '封鎖'),
        _edge('edge-l1-allow', 'node-FormAdapter-L1', 'node-Decision-allow', '放行'),
        _edge('edge-l1-escalate', 'node-FormAdapter-L1', 'node-FormAdapter-L2', '升級'),
        _edge('edge-l1-fp', 'node-FormAdapter-L1', 'node-End', '誤判'),

        _edge('edge-med-block', 'node-FormAdapter-L1med', 'node-Decision-block', '封鎖'),
        _edge('edge-med-allow', 'node-FormAdapter-L1med', 'node-Decision-allow', '放行'),
        _edge('edge-med-escalate', 'node-FormAdapter-L1med', 'node-FormAdapter-L2', '升級'),
        _edge('edge-med-fp', 'node-FormAdapter-L1med', 'node-End', '誤判'),

        _edge('edge-l2-block', 'node-FormAdapter-L2', 'node-Decision-block', '封鎖'),
        _edge('edge-l2-close', 'node-FormAdapter-L2', 'node-End', '結案'),

        _edge('edge-block-alert', 'node-Decision-block', 'node-Alert-blocked'),
        _edge('edge-alert-end', 'node-Alert-blocked', 'node-End'),
        _edge('edge-allow-end', 'node-Decision-allow', 'node-End'),

        _edge('edge-delay1-check', 'node-Delay-sla1', 'node-Branch-slacheck1'),
        _edge('edge-sla1-signed', 'node-Branch-slacheck1', 'node-Noop-signed1', '已簽'),
        _edge('edge-sla1-warn', 'node-Branch-slacheck1', 'node-Alert-slawarn', '逾時'),
        _edge('edge-warn-delay2', 'node-Alert-slawarn', 'node-Delay-sla2'),
        _edge('edge-delay2-check', 'node-Delay-sla2', 'node-Branch-slacheck2'),
        _edge('edge-sla2-signed', 'node-Branch-slacheck2', 'node-Noop-signed2', '已簽'),
        _edge('edge-sla2-escalate', 'node-Branch-slacheck2', 'node-Alert-slaescalate', '仍未簽'),
        _edge('edge-esc-noop', 'node-Alert-slaescalate', 'node-Noop-escalated'),
    ]

    return {'nodes': nodes, 'edges': edges}


# =============================================================================
# B. 小企業單人版
# =============================================================================

def build_solo_graph(role_staff_sc: str) -> dict:
    """
    組出小企業單人版的 graph。

    Args:
        role_staff_sc: 唯一的資安人員角色 secure_code
    """
    nodes = [
        _node('node-Start', 'Start', 'Start', {}, -700, 0),
        _intel_node('node-FieldWrite-intel', -560, 0),
        _node(
            'node-Branch-triage', 'Branch', '嚴重度與可處置性分流',
            {
                'rules': [
                    {
                        'name': '高危且有可自動封鎖的公網來源',
                        'conditions': [
                            _cond('${f.severity_id}', '>=', 4),
                            _cond('${f.actor_ip}', 'not_empty', ''),
                            _cond('${f.actor_ip}', 'matches', PUBLIC_IP_REGEX),
                        ],
                        'target_edges': ['edge-actionable'],
                    },
                    {
                        # 兩個 group：沒有 IP，或 IP 落在私有網段。
                        # conditions 的 logic 是 group 切分符：標 OR 的那一條收尾，
                        # 所以這裡是 (sev>=4 AND 無IP) OR (sev>=4 AND 私有IP)。
                        'name': '高危但無法自動處置（無來源 IP 或內網位址）',
                        'conditions': [
                            _cond('${f.severity_id}', '>=', 4),
                            _cond('${f.actor_ip}', 'empty', '', logic='OR'),
                            _cond('${f.severity_id}', '>=', 4),
                            _cond('${f.actor_ip}', 'matches', PRIVATE_IP_REGEX),
                        ],
                        'target_edges': ['edge-manual'],
                    },
                    {
                        'name': '中危',
                        'conditions': [_cond('${f.severity_id}', '==', 3)],
                        'target_edges': ['edge-manual'],
                    },
                    {
                        'name': '低危自動歸檔',
                        'conditions': [_cond('${f.severity_id}', '<=', 2)],
                        'target_edges': ['edge-low'],
                    },
                ],
                'fallback': {
                    'action': 'route',
                    'target_edge': 'edge-manual',
                    'log_message': '嚴重度缺值或無法比較，走人工處置（fail-safe）',
                },
            },
            -420, 0,
            '第二條規則擋掉兩種不該自動封鎖的案件：'
            '(1) actor_ip 為空——DecisionWriter 會失敗讓節點 error（實測 sev>=3 有 6/95 件缺）；'
            '(2) actor_ip 是內網位址——偵測器架在流量出口時，看到的來源會是反向代理自己，'
            '自動封鎖等於封掉自家基礎設施。兩者都改走人工路徑，交給人判斷該封的是誰。',
        ),
        _archive_node('node-FieldWrite-archive', -280, -230),
        _node(
            'node-Branch-clock', 'Branch', '上班時段判斷',
            {
                'rules': [
                    {
                        'name': f'上班時段（{OFFICE_HOURS_NOTE}）',
                        'conditions': [
                            _cond('${t.time}', 'matches', OFFICE_HOURS_UTC_REGEX),
                        ],
                        'target_edges': ['edge-daytime'],
                    },
                ],
                'fallback': {
                    'action': 'route',
                    'target_edge': 'edge-night',
                    'log_message': '非上班時段，走自動處置後複核',
                },
            },
            -280, 0,
            f'${{t.time}} 是 UTC 且沒有星期幾的變數，所以只判時段、不判平日假日。'
            f'週末被判成「上班時段」的缺口由等待期補上：'
            f'{SOLO_DAYTIME_GRACE_MINUTES} 分鐘沒人處理照樣自動封鎖。',
        ),

        # --- 夜間：先自動封鎖，隔天複核 ---
        _node(
            'node-FieldWrite-nightnote', 'OpFieldWrite', '夜間自動處置註記',
            {
                'target_field': 'intel_summary',
                'content': '【非上班時段自動處置】本案於 ${t.now} (UTC) 進案，'
                           '系統已先行封鎖 ${f.actor_ip}，TTL 24 小時，待人工複核。'
                           '風險分數 ${f.risk_score}，24 小時內同源事件 '
                           '${f.od_repeat_count} 件。',
            },
            -140, 150,
            '覆寫情報摘要，讓人上班第一眼就知道系統做了什麼。',
        ),
        _node(
            'node-Decision-nightblock', 'DecisionWriter', '自動封鎖（夜間）',
            {
                'action': 'block',
                'target_type': 'ip',
                'target_value': '${f.actor_ip}',
                'severity': 'high',
                'ttl_seconds': AUTO_BLOCK_TTL_SECONDS,
                'decided_via': 'auto',
                'enforcement_points': ['nftables'],
                'reason_template':
                    '非上班時段自動封鎖 ${wi.exec_code}：${f.finding_title}'
                    '（rule ${f.finding_rule_id}），待人工複核',
            },
            0, 150,
            'TTL 24 小時是安全網：人沒來上班也會自動解封，誤封不會變成永久事故。',
        ),
        _node(
            'node-Alert-review', 'AlertBroadcast', '待複核提示',
            {
                'broadcast_code': 'SOLO-REVIEW-PENDING',
                'title': '有自動封鎖待複核',
                'message': '案件 ${wi.exec_code}（${f.finding_title}）於非上班時段'
                           '自動封鎖 ${f.actor_ip}，TTL 24 小時，請上班後複核。',
                'require_ack': True,
                'target_type': 'specific',
                'target_roles': ['SECURITY_STAFF'],
                'target_departments': [],
            },
            140, 150,
        ),
        _node(
            'node-FormAdapter-review', 'FormAdapter', '上班後複核',
            {
                'assignee_type': 'ROLE',
                'assignee_value': role_staff_sc,
                'assignee_label': '資安人員',
                'assignee_list': [],
                'selection_mode': 'single',
                'output_variable': 'review_decision',
                'allow_comment': True,
                'require_comment': True,
                'min_comment_length': 10,
                'use_custom_decisions': True,
                'input_variables': [],
                'decision_options': [
                    {'id': 'opt-rv-extend', 'label': '確認封鎖（延長至 7 天）',
                     'value': 'confirmed', 'style': 'danger',
                     'target_edges': ['edge-rv-extend']},
                    {'id': 'opt-rv-unblock', 'label': '誤判，立即解除封鎖',
                     'value': 'false_positive', 'style': 'default',
                     'target_edges': ['edge-rv-unblock']},
                    {'id': 'opt-rv-observe', 'label': '維持觀察（讓 24 小時到期自動解除）',
                     'value': 'observe', 'style': 'default',
                     'target_edges': ['edge-rv-observe']},
                ],
            },
            280, 150,
            '三個選項對應三種現實：確定是攻擊、確定誤判、還不確定。'
            '不確定時什麼都不用做，TTL 會自己到期。',
        ),

        # --- 白天：人工處置 + 等待期 ---
        _node(
            'node-Fork-day', 'ParallelFork', '上班時段雙軌',
            {}, -140, -60,
            '一條給人處理，一條計時。計時到了沒人動就自動封鎖，'
            '補上「下班前 5 分鐘進案」與「週末」兩個邊界。',
        ),
        _node(
            'node-FormAdapter-day', 'FormAdapter', '即時處置',
            {
                'assignee_type': 'ROLE',
                'assignee_value': role_staff_sc,
                'assignee_label': '資安人員',
                'assignee_list': [],
                'selection_mode': 'single',
                'output_variable': 'solo_decision',
                'allow_comment': True,
                'require_comment': True,
                'min_comment_length': 10,
                'use_custom_decisions': True,
                'input_variables': [],
                'decision_options': [
                    {'id': 'opt-d-block', 'label': '封鎖攻擊來源（7 天）', 'value': 'block',
                     'style': 'danger', 'target_edges': ['edge-day-block']},
                    {'id': 'opt-d-observe', 'label': '觀察（不封鎖）', 'value': 'observe',
                     'style': 'default', 'target_edges': ['edge-day-observe']},
                    {'id': 'opt-d-allow', 'label': '放行（可接受風險）', 'value': 'allow',
                     'style': 'default', 'target_edges': ['edge-day-unblock']},
                    {'id': 'opt-d-fp', 'label': '誤判結案', 'value': 'false_positive',
                     'style': 'danger', 'target_edges': ['edge-day-unblock']},
                ],
            },
            0, -60,
            '「放行」與「誤判結案」都寫 unblock：如果等待期已經自動封鎖過，'
            '這一步就是解除；沒封鎖過則是留下「此來源可通行」的紀錄。',
        ),
        _node(
            'node-Delay-day', 'Delay', f'等待 {SOLO_DAYTIME_GRACE_MINUTES} 分',
            {'delay_minutes': SOLO_DAYTIME_GRACE_MINUTES}, 0, -230,
            '單人組織的合理反應時間。要更積極就把這個值調小。',
        ),
        _node(
            'node-Branch-daycheck', 'Branch', '檢查是否已處理',
            {
                'rules': [
                    {
                        'name': '已處理',
                        'conditions': [_cond('${v.solo_decision}', 'not_empty', '')],
                        'target_edges': ['edge-day-signed'],
                    },
                    {
                        'name': '逾時未處理',
                        'conditions': [_cond('${v.solo_decision}', 'empty', '')],
                        'target_edges': ['edge-day-timeout'],
                    },
                ],
                'fallback': {
                    'action': 'route',
                    'target_edge': 'edge-day-signed',
                    'log_message': '無法判定處理狀態，不自動封鎖（寧可不動也不要誤封）',
                },
            },
            140, -230,
            'fallback 選擇「不自動封鎖」：判不出狀態時，誤封的代價高於延後處置。',
        ),
        _noop_node('node-Noop-daysigned', '已由人處理', 'handled_in_time', 280, -330,
                   '無出邊，計時分支結束。'),
        _node(
            'node-FieldWrite-timeoutnote', 'OpFieldWrite', '逾時自動處置註記',
            {
                'target_field': 'intel_summary',
                'content': f'【上班時段逾時自動處置】本案超過 {SOLO_DAYTIME_GRACE_MINUTES} '
                           '分鐘無人處理，系統已於 ${t.now} (UTC) 封鎖 ${f.actor_ip}，'
                           'TTL 24 小時。原簽核任務仍在，可直接改判。',
            },
            280, -230,
        ),
        _node(
            'node-Decision-timeoutblock', 'DecisionWriter', '自動封鎖（逾時）',
            {
                'action': 'block',
                'target_type': 'ip',
                'target_value': '${f.actor_ip}',
                'severity': 'high',
                'ttl_seconds': AUTO_BLOCK_TTL_SECONDS,
                'decided_via': 'auto',
                'enforcement_points': ['nftables'],
                'reason_template':
                    '上班時段逾時自動封鎖 ${wi.exec_code}：${f.finding_title}'
                    '（rule ${f.finding_rule_id}）',
            },
            420, -230,
        ),
        _node(
            'node-Alert-timeout', 'AlertBroadcast', '逾時自動處置通報',
            {
                'broadcast_code': 'SOLO-AUTO-BLOCK',
                'title': '逾時自動封鎖：${f.actor_ip}',
                'message': f'案件 ${{wi.exec_code}} 超過 {SOLO_DAYTIME_GRACE_MINUTES} '
                           '分鐘無人處理，系統已自動封鎖，TTL 24 小時。'
                           '簽核任務仍在處置中心，可直接改判。',
                'require_ack': True,
                'target_type': 'specific',
                'target_roles': ['SECURITY_STAFF'],
                'target_departments': [],
            },
            560, -230,
        ),
        _noop_node('node-Noop-daytimeout', '已自動處置', 'auto_blocked', 700, -230,
                   '無出邊。人工簽核那條仍在等，人回來後可以改判。'),

        # --- 人工路徑（無 IP 的高危 / 中危）---
        _node(
            'node-FormAdapter-manual', 'FormAdapter', '人工處置',
            {
                'assignee_type': 'ROLE',
                'assignee_value': role_staff_sc,
                'assignee_label': '資安人員',
                'assignee_list': [],
                'selection_mode': 'single',
                'output_variable': 'manual_decision',
                'allow_comment': True,
                'require_comment': True,
                'min_comment_length': 10,
                'use_custom_decisions': True,
                'input_variables': [],
                'decision_options': [
                    {'id': 'opt-mn-block', 'label': '封鎖攻擊來源（7 天）', 'value': 'block',
                     'style': 'danger', 'target_edges': ['edge-mn-block']},
                    {'id': 'opt-mn-observe', 'label': '觀察（不封鎖）', 'value': 'observe',
                     'style': 'default', 'target_edges': ['edge-mn-observe']},
                    {'id': 'opt-mn-close', 'label': '結案（不留決策）', 'value': 'closed',
                     'style': 'default', 'target_edges': ['edge-mn-close']},
                ],
            },
            0, 320,
            '這條路徑沒有時間壓力也沒有自動處置：沒有 actor_ip 就沒有可自動封鎖的目標，'
            '中危也不值得自動化。',
        ),

        # --- 共用的決策寫入節點 ---
        _node(
            'node-Decision-confirm', 'DecisionWriter', '封鎖（7 天）',
            {
                'action': 'block',
                'target_type': 'ip',
                'target_value': '${f.actor_ip}',
                'severity': 'high',
                'ttl_seconds': CONFIRMED_BLOCK_TTL_SECONDS,
                'decided_via': 'human',
                'enforcement_points': ['nftables'],
                'reason_template':
                    '人工確認封鎖 ${wi.exec_code}：${f.finding_title}'
                    '（rule ${f.finding_rule_id}）',
            },
            560, 40,
        ),
        _node(
            'node-Decision-unblock', 'DecisionWriter', '解除封鎖',
            {
                'action': 'unblock',
                'target_type': 'ip',
                'target_value': '${f.actor_ip}',
                'severity': 'info',
                'decided_via': 'human',
                'enforcement_points': ['nftables'],
                'reason_template':
                    '人工解除封鎖 ${wi.exec_code}：${f.finding_title}',
            },
            560, 150,
        ),
        _node(
            'node-Decision-observe', 'DecisionWriter', '觀察（不封鎖）',
            {
                'action': 'observe',
                'target_type': 'ip',
                'target_value': '${f.actor_ip}',
                'severity': 'medium',
                'decided_via': 'human',
                'enforcement_points': ['nftables'],
                'reason_template':
                    '人工判定持續觀察 ${wi.exec_code}：${f.finding_title}',
            },
            560, 260,
        ),

        _node(
            'node-End', 'End', 'End',
            {'finish_mode': 'cancel', 'wait_seconds': 3},
            720, 100,
            'cancel 模式：處置完成時清掉還在計時的分支。',
        ),
    ]

    edges = [
        _edge('edge-start', 'node-Start', 'node-FieldWrite-intel'),
        _edge('edge-intel-triage', 'node-FieldWrite-intel', 'node-Branch-triage'),
        _edge('edge-actionable', 'node-Branch-triage', 'node-Branch-clock', '高危可處置'),
        _edge('edge-manual', 'node-Branch-triage', 'node-FormAdapter-manual', '中危／無 IP'),
        _edge('edge-low', 'node-Branch-triage', 'node-FieldWrite-archive', '低危'),
        _edge('edge-arch-end', 'node-FieldWrite-archive', 'node-End'),

        _edge('edge-daytime', 'node-Branch-clock', 'node-Fork-day', '上班時段'),
        _edge('edge-night', 'node-Branch-clock', 'node-FieldWrite-nightnote', '非上班時段'),

        _edge('edge-night-block', 'node-FieldWrite-nightnote', 'node-Decision-nightblock'),
        _edge('edge-night-alert', 'node-Decision-nightblock', 'node-Alert-review'),
        _edge('edge-night-review', 'node-Alert-review', 'node-FormAdapter-review'),
        _edge('edge-rv-extend', 'node-FormAdapter-review', 'node-Decision-confirm', '確認封鎖'),
        _edge('edge-rv-unblock', 'node-FormAdapter-review', 'node-Decision-unblock', '誤判解除'),
        _edge('edge-rv-observe', 'node-FormAdapter-review', 'node-Decision-observe', '維持觀察'),

        _edge('edge-day-sign', 'node-Fork-day', 'node-FormAdapter-day', '人工處理'),
        _edge('edge-day-timer', 'node-Fork-day', 'node-Delay-day', '等待計時'),
        _edge('edge-day-block', 'node-FormAdapter-day', 'node-Decision-confirm', '封鎖'),
        _edge('edge-day-observe', 'node-FormAdapter-day', 'node-Decision-observe', '觀察'),
        _edge('edge-day-unblock', 'node-FormAdapter-day', 'node-Decision-unblock', '放行／誤判'),

        _edge('edge-day-check', 'node-Delay-day', 'node-Branch-daycheck'),
        _edge('edge-day-signed', 'node-Branch-daycheck', 'node-Noop-daysigned', '已處理'),
        _edge('edge-day-timeout', 'node-Branch-daycheck', 'node-FieldWrite-timeoutnote', '逾時'),
        _edge('edge-timeout-block', 'node-FieldWrite-timeoutnote', 'node-Decision-timeoutblock'),
        _edge('edge-timeout-alert', 'node-Decision-timeoutblock', 'node-Alert-timeout'),
        _edge('edge-timeout-noop', 'node-Alert-timeout', 'node-Noop-daytimeout'),

        _edge('edge-mn-block', 'node-FormAdapter-manual', 'node-Decision-confirm', '封鎖'),
        _edge('edge-mn-observe', 'node-FormAdapter-manual', 'node-Decision-observe', '觀察'),
        _edge('edge-mn-close', 'node-FormAdapter-manual', 'node-End', '結案'),

        _edge('edge-confirm-end', 'node-Decision-confirm', 'node-End'),
        _edge('edge-unblock-end', 'node-Decision-unblock', 'node-End'),
        _edge('edge-observe-end', 'node-Decision-observe', 'node-End'),
    ]

    return {'nodes': nodes, 'edges': edges}


# =============================================================================
# 自我檢查：graph 結構一致性
# =============================================================================

def validate_graph(graph: dict) -> list:
    """
    檢查 graph 的結構一致性，回傳問題清單（空清單表示通過）。

    這裡查的都是「存得進 DB、跑起來才炸」的錯：
    - edge 指向不存在的節點
    - 決策選項 / Branch 規則引用了不存在的 edge，或該 edge 不是從本節點出發
    - 節點沒有任何入邊（除了 Start）
    """
    problems = []
    node_ids = {n['id'] for n in graph['nodes']}
    edge_ids = {e['id'] for e in graph['edges']}
    edges_by_source = {}
    for e in graph['edges']:
        edges_by_source.setdefault(e['source'], set()).add(e['id'])
        if e['source'] not in node_ids:
            problems.append(f"edge {e['id']} 的 source {e['source']} 不存在")
        if e['target'] not in node_ids:
            problems.append(f"edge {e['id']} 的 target {e['target']} 不存在")

    targets = {e['target'] for e in graph['edges']}
    for n in graph['nodes']:
        if n['type'] != 'Start' and n['id'] not in targets:
            problems.append(f"節點 {n['id']} 沒有任何入邊，永遠不會被執行")

    for n in graph['nodes']:
        own_edges = edges_by_source.get(n['id'], set())
        cfg = n.get('config') or {}

        for opt in cfg.get('decision_options', []) or []:
            for eid in opt.get('target_edges', []) or []:
                if eid not in edge_ids:
                    problems.append(f"{n['id']} 的選項 {opt.get('id')} 引用不存在的 edge {eid}")
                elif eid not in own_edges:
                    problems.append(
                        f"{n['id']} 的選項 {opt.get('id')} 引用的 edge {eid} 不是從本節點出發")

        for rule in cfg.get('rules', []) or []:
            for eid in rule.get('target_edges', []) or []:
                if eid not in edge_ids:
                    problems.append(f"{n['id']} 的規則「{rule.get('name')}」引用不存在的 edge {eid}")
                elif eid not in own_edges:
                    problems.append(
                        f"{n['id']} 的規則「{rule.get('name')}」引用的 edge {eid} 不是從本節點出發")

        fb_edge = (cfg.get('fallback') or {}).get('target_edge')
        if fb_edge:
            if fb_edge not in edge_ids:
                problems.append(f"{n['id']} 的 fallback 引用不存在的 edge {fb_edge}")
            elif fb_edge not in own_edges:
                problems.append(f"{n['id']} 的 fallback 引用的 edge {fb_edge} 不是從本節點出發")

    return problems
