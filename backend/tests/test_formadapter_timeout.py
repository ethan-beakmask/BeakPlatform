"""簽核節點逾時（PF-229 第三期第 2 項）：timeout_mode ABSOLUTE／WORKING、喚醒重算、逾時去向、executor 喚醒條件。"""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db
from app.models import User, UserType, WorkSchedule
from app.services.calendar_event_service import CalendarEventService
from modules.form_workflow.models import FwApprovalRecord, FwNodeExecutionQueue, FwWorkflowInstance
from modules.form_workflow.services.node_handlers.formadapter_handler import (
    FormAdapterHandler,
    compute_timeout_deadline,
    recompute_working_deadline,
)
from modules.form_workflow.services.workflow_executor import WorkflowExecutor


TPL_SC = 'fa_timeout_template_0001'
NODE_ID = 'n_approve'
GRAPH = {
    # 引擎讀 node 是平的（node.get('id')），edge 則 data 包裝與平的都認（edge.get('data', edge)）
    'nodes': [
        {'id': NODE_ID, 'type': 'FormAdapter', 'label': '主管核可'},
        {'id': 'n_ok', 'type': 'End', 'label': '核准結束'},
        {'id': 'n_escalate', 'type': 'End', 'label': '升級處理'},
    ],
    'edges': [
        {'data': {'id': 'e_ok', 'source': NODE_ID, 'target': 'n_ok', 'label': '核准'}},
        {'data': {'id': 'e_escalate', 'source': NODE_ID, 'target': 'n_escalate', 'label': ''}},
    ],
}
# 台北 2026-09-08（週二）17:00 → UTC 09:00
TUE_17_UTC = datetime(2026, 9, 8, 9, 0)


def _schedule(org):
    schedule = WorkSchedule(
        secure_code=f'fa_sched_{org.secure_code[-8:]}',
        org_secure_code=org.secure_code,
        schedule_code='FA_STD',
        name='FormAdapter Standard',
        timezone='Asia/Taipei',
        weekly_hours={
            'mon': ['09:00-12:00', '13:00-18:00'],
            'tue': ['09:00-12:00', '13:00-18:00'],
            'wed': ['09:00-12:00', '13:00-18:00'],
            'thu': ['09:00-12:00', '13:00-18:00'],
            'fri': ['09:00-12:00', '13:00-18:00'],
            'sat': None,
            'sun': None,
        },
        is_default=True,
        is_active=True,
    )
    db.session.add(schedule)
    db.session.commit()
    return schedule


def _instance(org, suffix='1'):
    instance = FwWorkflowInstance(
        secure_code=f'fa_timeout_wi_{suffix}'.ljust(24, '0')[:24],
        org_secure_code=org.secure_code,
        workflow_template_secure_code=TPL_SC,
        execution_code=f'FAT-{suffix}',
        status='RUNNING',
        graph_snapshot=GRAPH,
    )
    db.session.add(instance)
    db.session.commit()
    return instance


def _queue(org, instance, config, suffix='1', **extra):
    status = extra.pop('status', 'PENDING')
    item = FwNodeExecutionQueue(
        secure_code=f'fa_timeout_q_{suffix}'.ljust(24, '0')[:24],
        org_secure_code=org.secure_code,
        workflow_instance_secure_code=instance.secure_code,
        node_id=NODE_ID,
        node_type='FormAdapter',
        node_name='主管核可',
        node_config=config,
        status=status,
        **extra,
    )
    db.session.add(item)
    db.session.commit()
    return item


def _config(**overrides):
    config = {
        'assignee_type': 'USER',
        'assignee_value': '',
        'selection_mode': 'single',
        'timeout_enabled': True,
        'timeout_minutes': 30,
        'timeout_mode': 'ABSOLUTE',
        'timeout_path_id': 'e_escalate',
    }
    config.update(overrides)
    return config


def _run(queue_item):
    handler = FormAdapterHandler(queue_item)
    handler.validate()
    return handler, handler.handle()


def test_absolute_timeout_sets_deadline_in_waiting_data(test_org, test_user):
    instance = _instance(test_org)
    item = _queue(test_org, instance, _config(assignee_value=test_user.secure_code))

    _, result = _run(item)

    data = result['data']
    assert result['status'] == 'waiting_form_action'
    assert data['timeout_mode_effective'] == 'ABSOLUTE' and data['timeout_reference_user'] is None
    started = datetime.fromisoformat(data['timeout_started_at'])
    deadline = datetime.fromisoformat(data['timeout_at'])
    assert deadline - started == timedelta(minutes=30)
    assert data['assignees'] == [test_user.secure_code] and data['timeout_path_id'] == 'e_escalate'


def test_working_mode_falls_back_to_absolute_without_schedule(test_org, test_user):
    instance = _instance(test_org)
    item = _queue(test_org, instance, _config(assignee_value=test_user.secure_code, timeout_mode='WORKING'))

    _, result = _run(item)

    data = result['data']
    assert data['timeout_mode'] == 'WORKING' and data['timeout_mode_effective'] == 'ABSOLUTE'
    assert data['timeout_reference_user'] is None


def test_working_mode_uses_assignee_schedule(test_org, test_user):
    _schedule(test_org)
    instance = _instance(test_org)
    item = _queue(test_org, instance, _config(assignee_value=test_user.secure_code, timeout_mode='WORKING', timeout_minutes=120))

    _, result = _run(item)

    data = result['data']
    assert data['timeout_mode_effective'] == 'WORKING' and data['timeout_reference_user'] == test_user.secure_code
    assert datetime.fromisoformat(data['timeout_at']) > datetime.fromisoformat(data['timeout_started_at'])


def test_compute_deadline_working_skips_off_hours_and_leave(test_org, test_user):
    _schedule(test_org)
    test_org.set_setting('timezone', 'Asia/Taipei')
    db.session.commit()

    # 週二 17:00 起算 120 分鐘：17-18 一小時，隔天 09-10 一小時 → 週三 10:00（UTC 02:00）
    mode, deadline = compute_timeout_deadline(test_user, TUE_17_UTC, 120, 'WORKING', 'Asia/Taipei')
    assert (mode, deadline) == ('WORKING', datetime(2026, 9, 9, 2, 0))

    # 週三上午請假 09:00~12:00 → 剩下的一小時要等到 13:00-14:00 → 週三 14:00（UTC 06:00）
    CalendarEventService.create(test_org, test_user, {
        'calendar_kind': 'PERSONAL', 'event_type': 'LEAVE', 'title': 'AM leave', 'all_day': False,
        'start': '2026-09-09T09:00', 'end': '2026-09-09T12:00', 'visibility': 'BUSY',
    })
    db.session.commit()
    mode, deadline = compute_timeout_deadline(test_user, TUE_17_UTC, 120, 'WORKING', 'Asia/Taipei')
    assert (mode, deadline) == ('WORKING', datetime(2026, 9, 9, 6, 0))

    # ABSOLUTE 不看班表；WORKING 但沒班表的人退回 ABSOLUTE
    assert compute_timeout_deadline(test_user, TUE_17_UTC, 120, 'ABSOLUTE', 'Asia/Taipei') == ('ABSOLUTE', TUE_17_UTC + timedelta(minutes=120))
    assert compute_timeout_deadline(None, TUE_17_UTC, 120, 'WORKING', 'Asia/Taipei') == ('ABSOLUTE', TUE_17_UTC + timedelta(minutes=120))


def test_recompute_working_deadline_pushes_when_work_seconds_remain(test_org, test_user):
    _schedule(test_org)
    # 17:00 起算 120 分鐘，到了原期限（週三 10:00）時發現週三上午請假 → 已累積 60 分，剩 60 分 → 週三 14:00
    CalendarEventService.create(test_org, test_user, {
        'calendar_kind': 'PERSONAL', 'event_type': 'LEAVE', 'title': 'AM leave', 'all_day': False,
        'start': '2026-09-09T09:00', 'end': '2026-09-09T12:00', 'visibility': 'BUSY',
    })
    db.session.commit()

    remaining, new_deadline = recompute_working_deadline(test_user, TUE_17_UTC, datetime(2026, 9, 9, 2, 0), 120, 'Asia/Taipei')
    assert remaining == 3600 and new_deadline == datetime(2026, 9, 9, 6, 0)

    remaining, new_deadline = recompute_working_deadline(test_user, TUE_17_UTC, datetime(2026, 9, 9, 6, 0), 120, 'Asia/Taipei')
    assert remaining <= 0 and new_deadline is None


def test_reentry_before_deadline_keeps_waiting_and_data(test_org, test_user):
    instance = _instance(test_org)
    item = _queue(test_org, instance, _config(assignee_value=test_user.secure_code))
    _, first = _run(item)
    item.status = 'WAITING'
    item.result = first
    db.session.commit()

    _, second = _run(item)

    assert second['status'] == 'waiting_form_action'
    assert second['data']['waiting_since'] == first['data']['waiting_since']
    assert second['data']['timeout_at'] == first['data']['timeout_at']


def test_reentry_after_deadline_takes_timeout_edge_and_records_action(test_org, test_user):
    instance = _instance(test_org)
    item = _queue(test_org, instance, _config(assignee_value=test_user.secure_code))
    _, first = _run(item)
    first['data']['timeout_at'] = (datetime.utcnow() - timedelta(minutes=1)).isoformat(timespec='seconds')
    item.status = 'WAITING'
    item.result = first
    db.session.commit()

    _, result = _run(item)
    db.session.commit()

    assert result['status'] == 'success'
    assert result['data']['selected_edges'] == ['e_escalate'] and result['data']['decision'] == 'timeout'
    assert result['data']['timed_out'] is True and result['data']['timeout_path_label'] == '升級處理'
    record = FwApprovalRecord.query.filter_by(node_queue_secure_code=item.secure_code).one()
    assert record.action == 'timeout' and record.approver_secure_code is None
    assert '絕對時間 30 分鐘' in record.comment and '升級處理' in record.comment


def test_reentry_after_deadline_with_custom_decision_sets_output_variable(test_org, test_user):
    instance = _instance(test_org, '2')
    config = _config(
        assignee_value=test_user.secure_code,
        use_custom_decisions=True,
        output_variable='review_decision',
        decision_options=[
            {'id': 'opt-ok', 'label': '核准', 'value': 'approved', 'target_edges': ['e_ok']},
            {'id': 'opt-observe', 'label': '維持觀察', 'value': 'observe', 'target_edges': ['e_escalate']},
        ],
        timeout_path_id='opt-observe',
    )
    item = _queue(test_org, instance, config, '2')
    _, first = _run(item)
    assert first['data']['timeout_path_id'] == 'opt-observe'
    first['data']['timeout_at'] = (datetime.utcnow() - timedelta(minutes=1)).isoformat(timespec='seconds')
    item.status = 'WAITING'
    item.result = first
    db.session.commit()

    handler, result = _run(item)
    db.session.commit()

    assert result['status'] == 'success'
    assert result['data']['selected_edges'] == ['e_escalate'] and result['data']['selected_option_value'] == 'observe'
    assert handler.get_var('review_decision') == 'observe'


def test_reentry_with_terminal_decision_completes_workflow_as_rejected(test_org, test_user):
    instance = _instance(test_org, '3')
    config = _config(
        assignee_value=test_user.secure_code,
        use_custom_decisions=True,
        decision_options=[
            {'id': 'opt-ok', 'label': '核准', 'value': 'approved', 'target_edges': ['e_ok']},
            {'id': 'opt-reject', 'label': '駁回', 'value': 'rejected', 'target_edges': []},
        ],
        timeout_path_id='opt-reject',
    )
    item = _queue(test_org, instance, config, '3')
    _, first = _run(item)
    first['data']['timeout_at'] = (datetime.utcnow() - timedelta(minutes=1)).isoformat(timespec='seconds')
    item.status = 'WAITING'
    item.result = first
    db.session.commit()

    _, result = _run(item)

    assert result['status'] == 'complete_workflow'
    assert result['data']['workflow_status'] == 'REJECTED' and result['data']['timed_out'] is True


def test_missing_timeout_path_disables_timeout_but_not_approval(test_org, test_user):
    instance = _instance(test_org, '4')
    item = _queue(test_org, instance, _config(assignee_value=test_user.secure_code, timeout_path_id='e_missing'), '4')

    _, result = _run(item)

    assert result['status'] == 'waiting_form_action' and 'timeout_at' not in result['data']


def test_validate_rejects_bad_timeout_config(test_org, test_user):
    instance = _instance(test_org, '5')
    bad_configs = [
        _config(assignee_value=test_user.secure_code, timeout_path_id=''),
        _config(assignee_value=test_user.secure_code, timeout_minutes=0),
        _config(assignee_value=test_user.secure_code, timeout_minutes=99999),
        _config(assignee_value=test_user.secure_code, timeout_mode='BOTH'),
    ]
    errors = []
    for idx, config in enumerate(bad_configs):
        item = _queue(test_org, instance, config, f'5{idx}')
        try:
            FormAdapterHandler(item).validate()
            errors.append(None)
        except ValueError as exc:
            errors.append(str(exc))
    assert all(errors)
    assert 'timeout_path_id' in errors[0] and 'timeout_minutes' in errors[1] and 'timeout_minutes' in errors[2] and 'timeout_mode' in errors[3]

    ok_item = _queue(test_org, instance, _config(assignee_value=test_user.secure_code, timeout_enabled=False, timeout_path_id=''), '59')
    assert FormAdapterHandler(ok_item).validate() is True


def test_executor_clause_wakes_only_due_timeouts(test_org, test_user):
    instance = _instance(test_org, '6')
    now = datetime.utcnow()
    due = _queue(test_org, instance, _config(), '61', status='WAITING',
                 result={'status': 'waiting_form_action', 'data': {'timeout_at': (now - timedelta(minutes=1)).isoformat(timespec='seconds')}})
    future = _queue(test_org, instance, _config(), '62', status='WAITING',
                    result={'status': 'waiting_form_action', 'data': {'timeout_at': (now + timedelta(hours=1)).isoformat(timespec='seconds')}})
    plain = _queue(test_org, instance, _config(timeout_enabled=False), '63', status='WAITING',
                   result={'status': 'waiting_form_action', 'data': {'assignees': []}})
    done = _queue(test_org, instance, _config(), '64', status='SUCCESS',
                  result={'status': 'success', 'data': {'timeout_at': (now - timedelta(minutes=1)).isoformat(timespec='seconds')}})

    rows = FwNodeExecutionQueue.query.filter(WorkflowExecutor.formadapter_timeout_due_clause(now)).all()

    assert [r.secure_code for r in rows] == [due.secure_code]
    assert future.secure_code not in {r.secure_code for r in rows} and plain.secure_code not in {r.secure_code for r in rows}
    assert done.secure_code not in {r.secure_code for r in rows}
