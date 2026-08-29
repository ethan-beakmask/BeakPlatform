import os
import signal
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from modules.form_workflow.models import FwNodeExecutionQueue, FwWorkflowInstance
from modules.form_workflow.services import node_runner
from modules.form_workflow.services import workflow_engine
from modules.form_workflow.services.workflow_engine import WorkflowEngine


ORG_SC = 'cancel_test_org'
TPL_SC = 'cancel_test_template'


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


def _queue_item(secure_code, workflow_code, node_id, status='PENDING', **extra):
    return FwNodeExecutionQueue(
        secure_code=secure_code,
        org_secure_code=ORG_SC,
        workflow_instance_secure_code=workflow_code,
        node_id=node_id,
        node_type='Test',
        node_name=node_id,
        status=status,
        **extra,
    )


def test_cancel_pending_nodes_covers_child_instance_tree(app, db_session):
    root = _workflow_instance('wf_cancel_root_0001', 'CANCEL-TREE-ROOT')
    child = _workflow_instance(
        'wf_cancel_child_0001',
        'CANCEL-TREE-CHILD',
        parent_instance_code=root.secure_code,
        root_instance_code=root.secure_code,
        workflow_depth=1,
    )
    root_node = _queue_item('q_cancel_root_pending', root.secure_code, 'node-root')
    child_node = _queue_item('q_cancel_child_waiting', child.secure_code, 'node-child', status='WAITING')
    db_session.add_all([root, child, root_node, child_node])
    db_session.commit()

    WorkflowEngine.cancel_pending_nodes(root.secure_code)

    db_session.refresh(child_node)
    db_session.refresh(child)
    assert child_node.status == 'CANCELLED'
    assert child.status == 'CANCELLED'


def test_cancel_pending_nodes_reaches_grandchild_instance(app, db_session):
    """多層子流程：root_instance_code 是鏈式繼承的，第二層以下也必須在範圍內。"""
    root = _workflow_instance('wf_cancel_gp_root', 'CANCEL-GP-ROOT')
    child = _workflow_instance(
        'wf_cancel_gp_child',
        'CANCEL-GP-CHILD',
        parent_instance_code=root.secure_code,
        root_instance_code=root.secure_code,
        workflow_depth=1,
    )
    grandchild = _workflow_instance(
        'wf_cancel_gp_grand',
        'CANCEL-GP-GRAND',
        parent_instance_code=child.secure_code,
        root_instance_code=root.secure_code,
        workflow_depth=2,
    )
    grand_node = _queue_item(
        'q_cancel_gp_grand', grandchild.secure_code, 'node-grandchild', status='WAITING')
    db_session.add_all([root, child, grandchild, grand_node])
    db_session.commit()

    WorkflowEngine.cancel_pending_nodes(root.secure_code)

    db_session.refresh(grand_node)
    db_session.refresh(grandchild)
    assert grand_node.status == 'CANCELLED'
    assert grandchild.status == 'CANCELLED'


def test_cancel_pending_nodes_skips_pid_when_cmdline_mismatch(app, db_session, monkeypatch):
    wf = _workflow_instance('wf_cancel_pid_guard', 'CANCEL-PID-GUARD')
    node = _queue_item(
        'q_cancel_pid_guard',
        wf.secure_code,
        'node-running',
        status='RUNNING',
        process_id=os.getpid(),
    )
    db_session.add_all([wf, node])
    db_session.commit()

    sent_signals = []

    def fake_kill(pid, sig):
        sent_signals.append(('pid', pid, sig))

    def fake_killpg(pgid, sig):
        sent_signals.append(('pgid', pgid, sig))

    monkeypatch.setattr(workflow_engine.os, 'kill', fake_kill)
    monkeypatch.setattr(workflow_engine.os, 'killpg', fake_killpg)

    WorkflowEngine.cancel_pending_nodes(wf.secure_code)

    assert sent_signals == []


def test_cancel_pending_nodes_terminates_running_process_group(app, db_session, monkeypatch):
    proc = subprocess.Popen(['sleep', '30'], start_new_session=True)
    try:
        wf = _workflow_instance('wf_cancel_real_kill', 'CANCEL-REAL-KILL')
        node = _queue_item(
            'q_cancel_real_kill',
            wf.secure_code,
            'node-running',
            status='RUNNING',
            process_id=proc.pid,
        )
        db_session.add_all([wf, node])
        db_session.commit()

        monkeypatch.setattr(workflow_engine, '_pid_matches_queue_item', lambda pid, code: True)

        WorkflowEngine.cancel_pending_nodes(wf.secure_code)

        assert proc.poll() is not None
    finally:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait(timeout=5)


def test_cancelled_queue_item_does_not_write_success_or_advance(app, db_session, monkeypatch):
    wf = _workflow_instance('wf_cancel_writeback', 'CANCEL-WRITEBACK')
    node = _queue_item(
        'q_cancel_writeback',
        wf.secure_code,
        'node-cancelled',
        status='CANCELLED',
    )
    db_session.add_all([wf, node])
    db_session.commit()

    advance_calls = []
    monkeypatch.setattr(
        workflow_engine.WorkflowEngine,
        'advance_workflow',
        lambda *args, **kwargs: advance_calls.append((args, kwargs)),
    )

    node_runner.update_result(node, {'status': 'success', 'data': {'value': 1}})

    db_session.refresh(node)
    assert node.status == 'CANCELLED'
    assert advance_calls == []
