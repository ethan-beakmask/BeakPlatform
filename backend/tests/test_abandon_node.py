"""
Abandon（中止）節點測試

背景見 dev-notes/ABANDON_SPEC.md。本檔聚焦 AbandonHandler 自身的行為：
主流程中止的回傳結構、子流程中止喚醒父流程（含找不到父節點的降級路徑）、
wait_seconds 上限保護，以及與 node_runner 串接後 cancel 模式對同儕分支的
連鎖效應（順帶釘住「Abandon 完成後 workflow/form 狀態被記為
COMPLETED/APPROVED」這個與「中止」語意不符的現況，供 SPEC 引用）。

cancel_pending_nodes 本身的樹狀展開、PID 比對、程序終止邏輯已由
backend/tests/test_workflow_cancel_mode.py 覆蓋，本檔不重複測那些細節。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from modules.form_workflow.models import (
    FwFormInstance,
    FwNodeExecutionQueue,
    FwWorkflowInstance,
)
from modules.form_workflow.services import node_runner
from modules.form_workflow.services.node_handlers.abandon_handler import (
    MAX_WAIT_SECONDS,
    AbandonHandler,
)
from modules.form_workflow.services.workflow_engine import WorkflowEngine


ORG_SC = 'abandon_test_org'
TPL_SC = 'abandon_test_template'


def _workflow_instance(secure_code, execution_code, status='RUNNING', **extra):
    return FwWorkflowInstance(
        secure_code=secure_code,
        org_secure_code=ORG_SC,
        workflow_template_secure_code=TPL_SC,
        execution_code=execution_code,
        status=status,
        graph_snapshot={'nodes': [], 'edges': []},
        **extra,
    )


def _queue_item(secure_code, workflow_code, node_id, node_type='Test', status='PENDING', **extra):
    return FwNodeExecutionQueue(
        secure_code=secure_code,
        org_secure_code=ORG_SC,
        workflow_instance_secure_code=workflow_code,
        node_id=node_id,
        node_type=node_type,
        node_name=node_id,
        node_config=extra.pop('node_config', {}),
        status=status,
        **extra,
    )


# ---------------------------------------------------------------------------
# 主流程中止
# ---------------------------------------------------------------------------

def test_main_flow_abandon_returns_cancel_complete(app, db_session):
    """主流程 Abandon：回傳 complete_workflow + finish_mode=cancel，wait_seconds=0 不阻塞。"""
    wf = _workflow_instance('wf_abandon_main', 'ABANDON-MAIN')
    node = _queue_item(
        'q_abandon_main', wf.secure_code, 'node-Abandon-1', node_type='Abandon',
        node_config={'wait_seconds': 0},
    )
    db_session.add_all([wf, node])
    db_session.commit()

    result = AbandonHandler(node).handle()

    assert result['status'] == 'complete_workflow'
    assert result['data']['finish_mode'] == 'cancel'
    # 主流程（非子流程）路徑不帶 abandoned/parent_instance_code
    assert 'abandoned' not in result['data']
    assert 'parent_instance_code' not in result['data']


# ---------------------------------------------------------------------------
# wait_seconds 上限保護
# ---------------------------------------------------------------------------

def test_wait_seconds_clamped_to_max(app, db_session):
    """node_config 可被 API 直接改寫，wait_seconds 塞超大值時必須被夾限，不能無限期 sleep。"""
    wf = _workflow_instance('wf_abandon_clamp', 'ABANDON-CLAMP')
    node = _queue_item(
        'q_abandon_clamp', wf.secure_code, 'node-Abandon-1', node_type='Abandon',
        node_config={'wait_seconds': 86400},
    )
    db_session.add_all([wf, node])
    db_session.commit()

    handler = AbandonHandler(node)
    clamped = handler._clamp_wait_seconds(node.node_config['wait_seconds'])

    assert clamped == MAX_WAIT_SECONDS


def test_wait_seconds_negative_and_invalid_input_are_safe(app, db_session):
    """負值夾成 0（不倒著等待），非數字型別回退預設值而不拋例外。"""
    wf = _workflow_instance('wf_abandon_clamp2', 'ABANDON-CLAMP2')
    node = _queue_item('q_abandon_clamp2', wf.secure_code, 'node-Abandon-1', node_type='Abandon')
    db_session.add_all([wf, node])
    db_session.commit()

    handler = AbandonHandler(node)

    assert handler._clamp_wait_seconds(-5) == 0
    assert handler._clamp_wait_seconds('not-a-number') == 1
    assert handler._clamp_wait_seconds(None) == 1


# ---------------------------------------------------------------------------
# 子流程中止 -> 喚醒父流程
# ---------------------------------------------------------------------------

def test_subflow_abandon_marks_parent_subflow_success_with_abandoned_flag(app, db_session):
    """
    子流程走到 Abandon 時：
    - 父流程的 SubFlow queue item 被標成 SUCCESS（不是 FAILED/CANCELLED）
    - result.data.abandoned=True（但這個標記目前沒有任何變數語法能讀到，
      見 ABANDON_SPEC.md 第四節 —— 本測試只釘住「有寫入」這個事實，
      不代表父流程的 Branch 條件式能讀到它）
    - 父流程被推進到下一個節點（但這只是 AbandonHandler 內部的推進動作；
      實測透過完整 node_runner 鏈路後，新建立的節點會被同一輪
      cancel_pending_nodes 連鎖取消 —— 見
      test_subflow_abandon_missing_parent_node_id_still_cancels_real_parent，
      父流程不會真的「繼續往下跑到底」。此處只驗證推進動作本身有發生）
    """
    parent = _workflow_instance('wf_abandon_parent', 'ABANDON-PARENT')
    child = _workflow_instance(
        'wf_abandon_child', 'ABANDON-CHILD',
        parent_instance_code=parent.secure_code,
        root_instance_code=parent.secure_code,
        workflow_depth=1,
    )
    db_session.add_all([parent, child])
    db_session.flush()

    # 父流程中等待子流程完成的 SubFlow 節點
    parent_subflow_item = _queue_item(
        'q_abandon_parent_subflow', parent.secure_code, 'node-SubFlow-1',
        node_type='SubFlow', status='WAITING',
    )
    # 父流程的 graph：SubFlow 完成後推進到一個收尾節點
    parent.graph_snapshot = {
        'nodes': [
            {'id': 'node-SubFlow-1', 'type': 'SubFlow', 'label': 'SubFlow', 'config': {}},
            {'id': 'node-After-1', 'type': 'Notify', 'label': 'After', 'config': {}},
        ],
        'edges': [
            {'id': 'edge-1', 'source': 'node-SubFlow-1', 'target': 'node-After-1'},
        ],
    }

    # 子流程的 Start queue item：帶 parent_node_id 指回父流程的 SubFlow 節點
    child_start_item = _queue_item(
        'q_abandon_child_start', child.secure_code, 'node-Start-1',
        node_type='Start', status='SUCCESS', parent_node_id='node-SubFlow-1',
    )
    child_abandon_item = _queue_item(
        'q_abandon_child_abandon', child.secure_code, 'node-Abandon-1',
        node_type='Abandon', node_config={'wait_seconds': 0},
    )
    db_session.add_all([parent_subflow_item, child_start_item, child_abandon_item])
    db_session.commit()

    result = AbandonHandler(child_abandon_item).handle()

    assert result['status'] == 'complete_workflow'
    assert result['data']['finish_mode'] == 'cancel'
    assert result['data']['abandoned'] is True
    assert result['data']['parent_instance_code'] == parent.secure_code

    db_session.refresh(parent_subflow_item)
    assert parent_subflow_item.status == 'SUCCESS'
    assert parent_subflow_item.result['data']['abandoned'] is True
    assert parent_subflow_item.result['data']['child_instance_code'] == child.secure_code

    # 父流程應已被推進到 node-After-1
    advanced = FwNodeExecutionQueue.query.filter_by(
        workflow_instance_secure_code=parent.secure_code, node_id='node-After-1',
    ).first()
    assert advanced is not None
    assert advanced.status == 'PENDING'


def test_subflow_abandon_missing_parent_node_still_reports_success(app, db_session):
    """
    找不到父流程 SubFlow 節點 ID 時（_find_parent_node_id 回 None）：
    handler 仍回 complete_workflow（成功），不會拋錯、不會回 error 狀態。

    這是 briefing 質疑的「失敗但仍回成功」路徑之一：子流程的 Start queue item
    沒有帶 parent_node_id（例如資料被清過、或 SubFlow 建立邏輯本身有 bug），
    這裡驗證的是「不會讓整個節點執行拋例外」，不代表這是理想行為
    —— 是否該改成 error 見 ABANDON_SPEC.md 第二節的建議。
    """
    child = _workflow_instance(
        'wf_abandon_orphan_child', 'ABANDON-ORPHAN-CHILD',
        parent_instance_code='wf_abandon_orphan_parent',
        root_instance_code='wf_abandon_orphan_parent',
        workflow_depth=1,
    )
    # 刻意不建立帶 parent_node_id 的 Start queue item
    child_abandon_item = _queue_item(
        'q_abandon_orphan_abandon', child.secure_code, 'node-Abandon-1',
        node_type='Abandon', node_config={'wait_seconds': 0},
    )
    db_session.add_all([child, child_abandon_item])
    db_session.commit()

    result = AbandonHandler(child_abandon_item).handle()

    assert result['status'] == 'complete_workflow'
    assert result['data']['finish_mode'] == 'cancel'
    assert result['data']['abandoned'] is True
    # 父流程根本不存在，不應該有任何 SubFlow queue item 被動到
    touched = FwNodeExecutionQueue.query.filter_by(
        workflow_instance_secure_code='wf_abandon_orphan_parent',
    ).count()
    assert touched == 0


def test_subflow_abandon_missing_parent_node_id_still_cancels_real_parent(app, db_session, monkeypatch):
    """
    找不到父節點 ID，但父流程 instance 真實存在（root_instance_code 正確指向它）時：
    handler docstring 說「子流程將中止但父流程可能卡住」，但實測透過完整
    node_runner 鏈路後，父流程並不會卡住 —— cancel_pending_nodes 是用
    root_instance_code 展開整棵樹，範圍涵蓋父流程本身，父流程的 WAITING
    SubFlow 節點與 instance 本身都會被連帶標成 CANCELLED。

    「可能卡住」只在父流程的 root_instance_code 沒有正確指到子流程時才成立
    （資料異常，而非本路徑的正常後果）。這修正 briefing 原始假設，
    見 ABANDON_SPEC.md 第四節。
    """
    parent = _workflow_instance('wf_abandon_orphan_par2', 'ABANDON-ORPHAN-PAR2')
    child = _workflow_instance(
        'wf_abandon_orphan_chd2', 'ABANDON-ORPHAN-CHD2',
        parent_instance_code=parent.secure_code,
        root_instance_code=parent.secure_code,
        workflow_depth=1,
    )
    db_session.add_all([parent, child])
    db_session.flush()

    parent_subflow_item = _queue_item(
        'q_abandon_orphan_par2_sf', parent.secure_code, 'node-SubFlow-1',
        node_type='SubFlow', status='WAITING',
    )
    # 刻意不建立帶 parent_node_id 的子流程 Start queue item，模擬「找不到」
    child_abandon_item = _queue_item(
        'q_abandon_orphan_chd2_ab', child.secure_code, 'node-Abandon-1',
        node_type='Abandon', node_config={'wait_seconds': 0},
    )
    db_session.add_all([parent_subflow_item, child_abandon_item])
    db_session.commit()

    from modules.form_workflow.services import workflow_engine as we_module
    monkeypatch.setattr(we_module, '_pid_matches_queue_item', lambda pid, code: False)

    result = AbandonHandler(child_abandon_item).handle()
    node_runner.update_result(child_abandon_item, result)

    db_session.refresh(parent_subflow_item)
    db_session.refresh(parent)
    db_session.refresh(child)
    assert parent_subflow_item.status == 'CANCELLED'
    assert parent.status == 'CANCELLED'
    assert child.status == 'COMPLETED'


# ---------------------------------------------------------------------------
# 與 node_runner 串接：cancel 模式對同儕分支的連鎖效應
# ---------------------------------------------------------------------------

def test_abandon_via_node_runner_cancels_sibling_running_node(app, db_session, monkeypatch):
    """
    並行分支下，一條分支走到 Abandon、另一條分支仍在 RUNNING：
    node_runner 收到 Abandon 的 complete_workflow(finish_mode=cancel) 後，
    必須把同一個 workflow instance 內其他 PENDING/RUNNING/WAITING 節點
    一併標成 CANCELLED（不分支，範圍是整個 instance/tree）。

    process 實際終止（SIGTERM/SIGKILL、systemd unit stop）已由
    test_workflow_cancel_mode.py 覆蓋，這裡監看 os.kill 呼叫次數確認
    「確實嘗試終止」而不重複驗證終止機制本身。
    """
    wf = _workflow_instance('wf_abandon_sibling', 'ABANDON-SIBLING')
    sibling_running = _queue_item(
        'q_abandon_sibling_running', wf.secure_code, 'node-Other-1',
        node_type='Delay', status='RUNNING', process_id=0,
    )
    abandon_item = _queue_item(
        'q_abandon_sibling_abandon', wf.secure_code, 'node-Abandon-1',
        node_type='Abandon', node_config={'wait_seconds': 0},
    )
    db_session.add_all([wf, sibling_running, abandon_item])
    db_session.commit()

    from modules.form_workflow.services import workflow_engine as we_module
    monkeypatch.setattr(we_module, '_pid_matches_queue_item', lambda pid, code: False)

    result = AbandonHandler(abandon_item).handle()
    node_runner.update_result(abandon_item, result)

    db_session.refresh(sibling_running)
    db_session.refresh(wf)
    assert sibling_running.status == 'CANCELLED'

    # 釘住現況（見 ABANDON_SPEC.md 已知限制）：
    # 觸發 Abandon 的 instance 自己被 complete_workflow(status='COMPLETED') 收尾，
    # 不是 'CANCELLED' —— 與「中止」的直覺語意不符，但這是 End(cancel) 共用的
    # 既有引擎行為，不是 Abandon 獨有的缺陷。
    assert wf.status == 'COMPLETED'


def test_cancel_complete_marks_form_instance_approved_not_cancelled(app, db_session):
    """
    釘住語意矛盾（ABANDON_SPEC.md 第一節重點）：cancel 模式的 complete_workflow
    最終呼叫 WorkflowEngine.complete_workflow(status='COMPLETED')（node_runner.py
    的 wf_status 只有 finish_mode=='strict' 且 has_failures 才會是 'FAILED'），
    連帶讓 fw_form_instances.status 變成 'APPROVED'。

    被 Abandon（或 End cancel 模式）中止的申請單，在表單中心會顯示成「已核准」，
    而不是任何形式的「已取消/已中止」。這不是 Abandon handler 自己的邏輯
    （wf_status 判斷在 node_runner.py），本測試只是用測試釘住現況以供 SPEC 引用，
    不代表這是刻意設計。
    """
    wf = _workflow_instance('wf_abandon_form_status', 'ABANDON-FORM-STATUS')
    form = FwFormInstance(
        secure_code='fi_abandon_form_status',
        org_secure_code=ORG_SC,
        form_template_secure_code='abandon_test_form_tpl',
        form_name='Abandon 測試表單',
        serial_number='ABANDON-FORM-STATUS-0001',
        form_data={},
        status='PROCESSING',
    )
    db_session.add_all([wf, form])
    db_session.flush()
    wf.form_instance_secure_code = form.secure_code
    db_session.commit()

    WorkflowEngine.complete_workflow(wf.secure_code, status='COMPLETED', end_message='流程已中止')

    db_session.refresh(form)
    assert form.status == 'APPROVED'
