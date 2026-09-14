"""
End 節點語意測試（PF-200：Abandon 併入 End 後的定版行為）

- End(finish_mode='cancel') ＝「中止」：回報 workflow_status='CANCELLED'，
  流程與表單記已取消（原 Abandon 的行為，該節點已刪除）
- 子流程 End 讀 finish_mode：cancel 只收「自己與所有下層」（scope='subtree'），
  不影響上一層；上一層 SubFlow 節點被喚醒並依 subflow_result 走 resultRouting
- 喚醒失敗不再靜默：父流程 SubFlow 節點標 FAILED（取代永久卡 WAITING）
- advance_workflow() 的終態防護（已結束流程不得復活）
- SubFlow 的 max_iterations 循環上限

cancel_pending_nodes 的 PID 比對、程序終止細節由 test_workflow_cancel_mode.py
覆蓋（它測的是主流程整棵樹 scope='tree'，與本檔的 subtree 測試互補）。

原 test_abandon_node.py 的父子流程 fixture 改寫沿用於此。
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
from modules.form_workflow.services.node_handlers.end_handler import (
    MAX_WAIT_SECONDS,
    EndHandler,
)
from modules.form_workflow.services.variable_service import VariableService
from modules.form_workflow.services.workflow_engine import WorkflowEngine


ORG_SC = 'end_test_org'
TPL_SC = 'end_test_template'


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
# 主流程：cancel ＝ 中止
# ---------------------------------------------------------------------------

def test_main_flow_end_cancel_reports_cancelled(app, db_session):
    """主流程 End(cancel)：complete_workflow + workflow_status='CANCELLED'（原 Abandon 行為）。"""
    wf = _workflow_instance('wf_end_main_cancel', 'END-MAIN-CANCEL')
    node = _queue_item(
        'q_end_main_cancel', wf.secure_code, 'node-End-1', node_type='End',
        node_config={'finish_mode': 'cancel', 'wait_seconds': 0},
    )
    db_session.add_all([wf, node])
    db_session.commit()

    result = EndHandler(node).handle()

    assert result['status'] == 'complete_workflow'
    assert result['data']['finish_mode'] == 'cancel'
    assert result['data']['workflow_status'] == 'CANCELLED'


def test_main_flow_end_detach_has_no_workflow_status(app, db_session):
    """detach 不帶 workflow_status，node_runner 落回 COMPLETED（表單記已核准，維持既有）。"""
    wf = _workflow_instance('wf_end_main_detach', 'END-MAIN-DETACH')
    node = _queue_item(
        'q_end_main_detach', wf.secure_code, 'node-End-1', node_type='End',
        node_config={'finish_mode': 'detach', 'wait_seconds': 0},
    )
    db_session.add_all([wf, node])
    db_session.commit()

    result = EndHandler(node).handle()

    assert result['status'] == 'complete_workflow'
    assert 'workflow_status' not in result['data']


# ---------------------------------------------------------------------------
# wait_seconds 上限保護（原 PF-189-1，兩處都吃 _clamp_wait_seconds）
# ---------------------------------------------------------------------------

def test_wait_seconds_clamped_to_max(app, db_session):
    wf = _workflow_instance('wf_end_clamp', 'END-CLAMP')
    node = _queue_item('q_end_clamp', wf.secure_code, 'node-End-1', node_type='End',
                       node_config={'wait_seconds': 86400})
    db_session.add_all([wf, node])
    db_session.commit()

    handler = EndHandler(node)

    assert handler._clamp_wait_seconds(86400, 3) == MAX_WAIT_SECONDS
    assert handler._clamp_wait_seconds(-5, 3) == 0
    assert handler._clamp_wait_seconds('not-a-number', 3) == 3
    assert handler._clamp_wait_seconds(None, 1) == 1


# ---------------------------------------------------------------------------
# 子流程 End：喚醒上一層並回報結束方式
# ---------------------------------------------------------------------------

def _make_parent_child(db_session, prefix, parent_config=None, parent_graph=None):
    parent = _workflow_instance(f'wf_{prefix}_parent', f'{prefix.upper()}-PARENT')
    child = _workflow_instance(
        f'wf_{prefix}_child', f'{prefix.upper()}-CHILD',
        parent_instance_code=parent.secure_code,
        root_instance_code=parent.secure_code,
        workflow_depth=1,
    )
    db_session.add_all([parent, child])
    db_session.flush()

    parent.graph_snapshot = parent_graph or {
        'nodes': [
            {'id': 'node-Subflow-1', 'type': 'Subflow', 'label': 'SubFlow', 'config': {}},
            {'id': 'node-After-1', 'type': 'Notify', 'label': 'After', 'config': {}},
        ],
        'edges': [
            {'id': 'edge-1', 'source': 'node-Subflow-1', 'target': 'node-After-1'},
        ],
    }
    # 上一層等待中的 SubFlow 節點。node_type 刻意用設計器實際寫入的 'Subflow'
    # （小寫 f）——引擎端所有比對都必須大小寫不敏感，這裡順便釘住
    parent_subflow_item = _queue_item(
        f'q_{prefix}_parent_sf', parent.secure_code, 'node-Subflow-1',
        node_type='Subflow', status='WAITING',
        node_config=parent_config or {},
    )
    child_start_item = _queue_item(
        f'q_{prefix}_child_start', child.secure_code, 'node-Start-1',
        node_type='Start', status='SUCCESS', parent_node_id='node-Subflow-1',
    )
    db_session.add_all([parent_subflow_item, child_start_item])
    return parent, child, parent_subflow_item


def test_subflow_end_detach_reports_completed_and_advances_parent(app, db_session):
    """子流程 End(detach)：上一層 SubFlow 標 SUCCESS（subflow_result=completed）、推進、寫變數。"""
    parent, child, parent_sf = _make_parent_child(db_session, 'end_detach')
    end_item = _queue_item(
        'q_end_detach_child_end', child.secure_code, 'node-End-1',
        node_type='End', node_config={'finish_mode': 'detach', 'wait_seconds': 0},
    )
    db_session.add(end_item)
    db_session.commit()

    result = EndHandler(end_item).handle()

    assert result['status'] == 'complete_workflow'
    assert result['data']['finish_mode'] == 'subflow_end'
    assert result['data']['subflow_result'] == 'completed'
    assert 'workflow_status' not in result['data']

    db_session.refresh(parent_sf)
    assert parent_sf.status == 'SUCCESS'
    assert parent_sf.result['data']['subflow_result'] == 'completed'
    assert parent_sf.result['data']['child_instance_code'] == child.secure_code

    advanced = FwNodeExecutionQueue.query.filter_by(
        workflow_instance_secure_code=parent.secure_code, node_id='node-After-1').first()
    assert advanced is not None and advanced.status == 'PENDING'

    VariableService.clear_cache()
    assert VariableService.get_flow_var(parent.secure_code, 'node-Subflow-1_result') == 'completed'
    assert VariableService.get_flow_var(parent.secure_code, 'node-Subflow-1_child') == child.secure_code


def test_subflow_end_cancel_only_cancels_own_subtree(app, db_session, monkeypatch):
    """
    驗收核心樹形（PF-200）：

        P ── Subflow-1 ── A1 ── B1     <- A1 的 End(cancel)
          └─ Subflow-2 ── A2 ── B2     <- 必須毫髮無傷

    A1 的 End(cancel) 只收 A1+B1（scope='subtree'）；P、A2、B2 不受影響；
    P 的 Subflow-1 標 SUCCESS 且 subflow_result='cancelled'，P 照常推進。
    """
    p = _workflow_instance('wf_sub_p', 'SUB-P')
    a1 = _workflow_instance('wf_sub_a1', 'SUB-A1', parent_instance_code=p.secure_code,
                            root_instance_code=p.secure_code, workflow_depth=1)
    a2 = _workflow_instance('wf_sub_a2', 'SUB-A2', parent_instance_code=p.secure_code,
                            root_instance_code=p.secure_code, workflow_depth=1)
    b1 = _workflow_instance('wf_sub_b1', 'SUB-B1', parent_instance_code=a1.secure_code,
                            root_instance_code=p.secure_code, workflow_depth=2)
    b2 = _workflow_instance('wf_sub_b2', 'SUB-B2', parent_instance_code=a2.secure_code,
                            root_instance_code=p.secure_code, workflow_depth=2)
    db_session.add_all([p, a1, a2, b1, b2])
    db_session.flush()

    p.graph_snapshot = {
        'nodes': [
            {'id': 'node-Subflow-1', 'type': 'Subflow', 'label': 'A1', 'config': {}},
            {'id': 'node-Subflow-2', 'type': 'Subflow', 'label': 'A2', 'config': {}},
            {'id': 'node-After-1', 'type': 'Notify', 'label': 'After1', 'config': {}},
        ],
        'edges': [
            {'id': 'edge-1', 'source': 'node-Subflow-1', 'target': 'node-After-1'},
        ],
    }
    items = [
        _queue_item('q_sub_p_sf1', p.secure_code, 'node-Subflow-1', node_type='Subflow', status='WAITING'),
        _queue_item('q_sub_p_sf2', p.secure_code, 'node-Subflow-2', node_type='Subflow', status='WAITING'),
        _queue_item('q_sub_a1_start', a1.secure_code, 'node-Start-1', node_type='Start',
                    status='SUCCESS', parent_node_id='node-Subflow-1'),
        _queue_item('q_sub_a1_delay', a1.secure_code, 'node-Delay-1', node_type='Delay', status='PENDING'),
        _queue_item('q_sub_a2_start', a2.secure_code, 'node-Start-1', node_type='Start',
                    status='SUCCESS', parent_node_id='node-Subflow-2'),
        _queue_item('q_sub_a2_delay', a2.secure_code, 'node-Delay-1', node_type='Delay', status='PENDING'),
        _queue_item('q_sub_b1_delay', b1.secure_code, 'node-Delay-1', node_type='Delay', status='PENDING'),
        _queue_item('q_sub_b2_delay', b2.secure_code, 'node-Delay-1', node_type='Delay', status='PENDING'),
    ]
    end_item = _queue_item('q_sub_a1_end', a1.secure_code, 'node-End-1', node_type='End',
                           node_config={'finish_mode': 'cancel', 'wait_seconds': 0})
    db_session.add_all(items + [end_item])
    db_session.commit()

    from modules.form_workflow.services import workflow_engine as we_module
    monkeypatch.setattr(we_module, '_pid_matches_queue_item', lambda pid, code: False)

    result = EndHandler(end_item).handle()
    assert result['data']['workflow_status'] == 'CANCELLED'
    assert result['data']['subflow_result'] == 'cancelled'
    node_runner.update_result(end_item, result)

    for obj in [p, a1, a2, b1, b2] + items:
        db_session.refresh(obj)

    # A1 + B1 被收掉
    assert a1.status == 'CANCELLED'
    assert b1.status == 'CANCELLED'
    assert items[3].status == 'CANCELLED'   # a1 delay
    assert items[6].status == 'CANCELLED'   # b1 delay
    # P、A2、B2 毫髮無傷
    assert p.status == 'RUNNING'
    assert a2.status == 'RUNNING'
    assert b2.status == 'RUNNING'
    assert items[1].status == 'WAITING'     # p subflow-2 仍在等 A2
    assert items[5].status == 'PENDING'     # a2 delay
    assert items[7].status == 'PENDING'     # b2 delay
    # P 的 Subflow-1 拿到 cancelled 並照常推進
    assert items[0].status == 'SUCCESS'
    assert items[0].result['data']['subflow_result'] == 'cancelled'
    advanced = FwNodeExecutionQueue.query.filter_by(
        workflow_instance_secure_code=p.secure_code, node_id='node-After-1').first()
    assert advanced is not None and advanced.status == 'PENDING'

    VariableService.clear_cache()
    assert VariableService.get_flow_var(p.secure_code, 'node-Subflow-1_result') == 'cancelled'


def test_subflow_end_result_routing_selects_edge(app, db_session):
    """resultRouting：子流程 cancel 時只走「中止時走」指定的那條出邊。"""
    graph = {
        'nodes': [
            {'id': 'node-Subflow-1', 'type': 'Subflow', 'label': 'SubFlow', 'config': {}},
            {'id': 'node-OK', 'type': 'Notify', 'label': 'OK', 'config': {}},
            {'id': 'node-CXL', 'type': 'Notify', 'label': 'CXL', 'config': {}},
        ],
        'edges': [
            {'id': 'edge-ok', 'source': 'node-Subflow-1', 'target': 'node-OK'},
            {'id': 'edge-cxl', 'source': 'node-Subflow-1', 'target': 'node-CXL'},
        ],
    }
    routing_config = {'resultRouting': {'completed': ['edge-ok'], 'cancelled': ['edge-cxl']}}
    parent, child, parent_sf = _make_parent_child(
        db_session, 'end_route', parent_config=routing_config, parent_graph=graph)
    end_item = _queue_item(
        'q_end_route_child_end', child.secure_code, 'node-End-1',
        node_type='End', node_config={'finish_mode': 'cancel', 'wait_seconds': 0},
    )
    db_session.add(end_item)
    db_session.commit()

    EndHandler(end_item).handle()

    ok = FwNodeExecutionQueue.query.filter_by(
        workflow_instance_secure_code=parent.secure_code, node_id='node-OK').first()
    cxl = FwNodeExecutionQueue.query.filter_by(
        workflow_instance_secure_code=parent.secure_code, node_id='node-CXL').first()
    assert ok is None
    assert cxl is not None and cxl.status == 'PENDING'


# ---------------------------------------------------------------------------
# 喚醒失敗路徑：標 FAILED 取代永久卡 WAITING（原 PF-189-3）
# ---------------------------------------------------------------------------

def test_subflow_end_missing_parent_node_id_fails_parent_subflow(app, db_session, monkeypatch):
    """
    找不到 parent_node_id（子流程 Start 沒帶）時：
    上一層等待中的 SubFlow 節點標 FAILED（看得見、查得到），
    而不是留在 WAITING 永久卡死；subtree scope 下上一層 instance 不受影響。
    """
    parent, child, parent_sf = _make_parent_child(db_session, 'end_orphan')
    # 抽掉 Start 的 parent_node_id，模擬「找不到」
    start = FwNodeExecutionQueue.query.filter_by(
        workflow_instance_secure_code=child.secure_code, node_id='node-Start-1').first()
    start.parent_node_id = None
    end_item = _queue_item(
        'q_end_orphan_child_end', child.secure_code, 'node-End-1',
        node_type='End', node_config={'finish_mode': 'cancel', 'wait_seconds': 0},
    )
    db_session.add(end_item)
    db_session.commit()

    from modules.form_workflow.services import workflow_engine as we_module
    monkeypatch.setattr(we_module, '_pid_matches_queue_item', lambda pid, code: False)

    result = EndHandler(end_item).handle()
    node_runner.update_result(end_item, result)

    db_session.refresh(parent_sf)
    db_session.refresh(parent)
    db_session.refresh(child)
    assert parent_sf.status == 'FAILED'
    assert parent.status == 'RUNNING'       # 上一層不被連帶取消（subtree scope）
    assert child.status == 'CANCELLED'
    assert child.error_message


def test_subflow_end_missing_parent_instance_is_safe(app, db_session):
    """父流程 instance 根本不存在時不拋例外，也不動到任何別的 queue item。"""
    child = _workflow_instance(
        'wf_end_noparent_child', 'END-NOPARENT-CHILD',
        parent_instance_code='wf_end_noparent_ghost',
        root_instance_code='wf_end_noparent_ghost',
        workflow_depth=1,
    )
    end_item = _queue_item(
        'q_end_noparent_end', child.secure_code, 'node-End-1',
        node_type='End', node_config={'finish_mode': 'detach', 'wait_seconds': 0},
    )
    db_session.add_all([child, end_item])
    db_session.commit()

    result = EndHandler(end_item).handle()

    assert result['status'] == 'complete_workflow'
    touched = FwNodeExecutionQueue.query.filter_by(
        workflow_instance_secure_code='wf_end_noparent_ghost').count()
    assert touched == 0


# ---------------------------------------------------------------------------
# node_runner 串接：主流程 cancel 收整棵樹、終態白名單
# ---------------------------------------------------------------------------

def test_main_end_cancel_via_node_runner_cancels_sibling_and_records_cancelled(app, db_session, monkeypatch):
    """主流程 End(cancel)：同 instance 其他節點被收掉，instance 記 CANCELLED（原 Abandon）。"""
    wf = _workflow_instance('wf_end_sibling', 'END-SIBLING')
    sibling = _queue_item('q_end_sibling_run', wf.secure_code, 'node-Other-1',
                          node_type='Delay', status='RUNNING', process_id=0)
    end_item = _queue_item('q_end_sibling_end', wf.secure_code, 'node-End-1',
                           node_type='End', node_config={'finish_mode': 'cancel', 'wait_seconds': 0})
    db_session.add_all([wf, sibling, end_item])
    db_session.commit()

    from modules.form_workflow.services import workflow_engine as we_module
    monkeypatch.setattr(we_module, '_pid_matches_queue_item', lambda pid, code: False)

    result = EndHandler(end_item).handle()
    node_runner.update_result(end_item, result)

    db_session.refresh(sibling)
    db_session.refresh(wf)
    assert sibling.status == 'CANCELLED'
    assert wf.status == 'CANCELLED'


def test_complete_workflow_status_mapping(app, db_session):
    """釘住 complete_workflow 的對應：COMPLETED->APPROVED、CANCELLED->CANCELLED。"""
    for idx, (wf_status, form_status) in enumerate(
            [('COMPLETED', 'APPROVED'), ('CANCELLED', 'CANCELLED')]):
        wf = _workflow_instance(f'wf_end_form_{idx}', f'END-FORM-{idx}')
        form = FwFormInstance(
            secure_code=f'fi_end_form_{idx}',
            org_secure_code=ORG_SC,
            form_template_secure_code='end_test_form_tpl',
            form_name='End 測試表單',
            serial_number=f'END-FORM-{idx}-0001',
            form_data={},
            status='PROCESSING',
        )
        db_session.add_all([wf, form])
        db_session.flush()
        wf.form_instance_secure_code = form.secure_code
        db_session.commit()

        WorkflowEngine.complete_workflow(wf.secure_code, status=wf_status)

        db_session.refresh(form)
        assert form.status == form_status


def test_node_runner_honours_workflow_status_and_rejects_junk(app, db_session, monkeypatch):
    """node_runner 採用 data.workflow_status，但只接受白名單內的值。"""
    captured = []
    monkeypatch.setattr(
        WorkflowEngine, 'complete_workflow',
        staticmethod(lambda code, status=None, end_message=None: captured.append(status)))
    monkeypatch.setattr(
        WorkflowEngine, 'cancel_pending_nodes',
        staticmethod(lambda *a, **k: None))

    cases = (
        ('CANCELLED', 'CANCELLED'),
        ('REJECTED', 'REJECTED'),
        ('NOT_A_STATUS', 'COMPLETED'),   # 白名單外 -> 退回舊規則
        (None, 'COMPLETED'),
    )
    for idx, (requested, _expected) in enumerate(cases):
        wf = _workflow_instance(f'wf_end_runner_{idx}', f'END-RUNNER-{idx}')
        node = _queue_item(f'q_end_runner_{idx}', wf.secure_code, 'node-End-x',
                           node_type='End', node_config={})
        db_session.add_all([wf, node])
        db_session.commit()
        data = {'finish_mode': 'cancel'}
        if requested is not None:
            data['workflow_status'] = requested
        node_runner.update_result(
            node, {'status': 'complete_workflow', 'message': 'x', 'data': data})

    assert captured == [expected for _r, expected in cases]


# ---------------------------------------------------------------------------
# advance_workflow 終態防護（PF-200 改動 1）
# ---------------------------------------------------------------------------

def test_advance_workflow_refuses_terminal_instance(app, db_session):
    """已結束的流程不得再建新節點——end_handler 喚醒父流程與簽核路徑都直接呼叫本函式。"""
    wf = _workflow_instance('wf_end_terminal', 'END-TERMINAL', status='COMPLETED')
    wf.graph_snapshot = {
        'nodes': [
            {'id': 'node-Start-1', 'type': 'Start', 'label': 'Start', 'config': {}},
            {'id': 'node-Next-1', 'type': 'Notify', 'label': 'Next', 'config': {}},
        ],
        'edges': [
            {'id': 'edge-1', 'source': 'node-Start-1', 'target': 'node-Next-1'},
        ],
    }
    db_session.add(wf)
    db_session.commit()

    created = WorkflowEngine.advance_workflow(wf.secure_code, 'node-Start-1')

    assert created == []
    assert FwNodeExecutionQueue.query.filter_by(
        workflow_instance_secure_code=wf.secure_code).count() == 0


# ---------------------------------------------------------------------------
# SubFlow max_iterations（PF-200：迴圈上限）
# ---------------------------------------------------------------------------

def test_subflow_max_iterations_blocks_over_limit(app, db_session):
    """max_iterations=1：第一次啟動成功，第二次回 error（計數記在含節點的那一層）。"""
    from modules.form_workflow.models import FwWorkflowTemplate
    from modules.form_workflow.services.node_handlers.subflow_handler import SubFlowHandler

    child_tpl = FwWorkflowTemplate(
        secure_code='tpl_end_maxiter_child',
        org_secure_code=ORG_SC,
        code='SFMAXITER',
        name='maxiter child',
        graph={'nodes': [{'id': 'node-Start-1', 'type': 'Start', 'label': 'Start',
                          'data': {'config': {}}}], 'edges': []},
    )
    wf = _workflow_instance('wf_end_maxiter', 'END-MAXITER')
    db_session.add_all([child_tpl, wf])
    db_session.commit()

    def _run(idx):
        item = _queue_item(
            f'q_end_maxiter_{idx}', wf.secure_code, 'node-Subflow-9', node_type='Subflow',
            node_config={'childFlowId': 'SFMAXITER', 'max_iterations': 1},
        )
        db_session.add(item)
        db_session.commit()
        result = SubFlowHandler(item).handle()
        # 讓同 node_id 的下一筆能建立（partial unique index 擋未完成的重複節點）
        item.status = 'SUCCESS'
        db_session.commit()
        return result

    VariableService.clear_cache()
    first = _run(1)
    assert first['status'] == 'waiting_subflow'

    VariableService.clear_cache()
    second = _run(2)
    assert second['status'] == 'error'
    assert 'max_iterations' in second['message']
