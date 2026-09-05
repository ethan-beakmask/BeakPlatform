"""簽核節點找不到簽核人（PF-226）：退回申請人重送或改派角色。"""
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db
from app.models import Organization, Role
from app.models.associations import UserRoleAssignment
from modules.form_workflow.models import FwApprovalRecord, FwNodeExecutionQueue, FwWorkflowInstance
from modules.form_workflow.services.node_handlers.formadapter_handler import FormAdapterHandler
from modules.form_workflow.services.node_runner import update_result


TPL_SC = 'fa_no_assignee_tpl_001'
NODE_ID = 'n_approve'
GRAPH = {
    'nodes': [
        {'id': NODE_ID, 'type': 'FormAdapter', 'label': '主管核可'},
        {'id': 'n_ok', 'type': 'End', 'label': '核准結束'},
    ],
    'edges': [
        {'data': {'id': 'e_ok', 'source': NODE_ID, 'target': 'n_ok', 'label': '核准'}},
    ],
}


def _instance(org, suffix='1'):
    instance = FwWorkflowInstance(
        secure_code=f'fa_noasg_wi_{suffix}'.ljust(24, '0')[:24],
        org_secure_code=org.secure_code,
        workflow_template_secure_code=TPL_SC,
        execution_code=f'FANA-{suffix}',
        status='RUNNING',
        graph_snapshot=GRAPH,
    )
    db.session.add(instance)
    db.session.commit()
    return instance


def _queue(org, instance, config, suffix='1', **extra):
    status = extra.pop('status', 'PENDING')
    item = FwNodeExecutionQueue(
        secure_code=f'fa_noasg_q_{suffix}'.ljust(24, '0')[:24],
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
        'assignee_type': 'DYNAMIC',
        'assignee_value': 'hr_approver',
        'selection_mode': 'single',
    }
    config.update(overrides)
    return config


def _run(queue_item):
    handler = FormAdapterHandler(queue_item)
    handler.validate()
    return handler, handler.handle()


def _role(org, suffix='1', **overrides):
    role = Role(
        secure_code=f'fa_noasg_role_{suffix}'.ljust(24, '0')[:24],
        org_secure_code=org.secure_code,
        code=f'FANA_ROLE_{suffix}',
        name=f'No Assignee Role {suffix}',
        is_active=True,
        is_deleted=False,
        **overrides,
    )
    db.session.add(role)
    db.session.commit()
    return role


def _assign(role, user, org, suffix='1'):
    assignment = UserRoleAssignment(
        secure_code=f'fa_noasg_ura_{suffix}'.ljust(24, '0')[:24],
        org_secure_code=org.secure_code,
        user_secure_code=user.secure_code,
        role_secure_code=role.secure_code,
        assigned_at=datetime.utcnow(),
        is_deleted=False,
    )
    db.session.add(assignment)
    db.session.commit()
    return assignment


def test_dynamic_empty_defaults_to_return_and_marks_workflow_rejected(test_org, test_user):
    instance = _instance(test_org)
    item = _queue(test_org, instance, _config())

    _, result = _run(item)
    db.session.commit()

    assert result['status'] == 'complete_workflow'
    assert result['data']['workflow_status'] == 'REJECTED'
    assert result['data']['no_assignee'] is True
    record = FwApprovalRecord.query.filter_by(node_queue_secure_code=item.secure_code).one()
    assert record.action == 'no_assignee'
    assert record.approver_secure_code is None
    assert 'hr_approver' in record.comment

    update_result(item, result)
    db.session.refresh(instance)
    assert instance.status == 'REJECTED'


def test_dynamic_empty_fallback_role_with_member_waits_for_role(test_org, test_user):
    role = _role(test_org, 'member')
    _assign(role, test_user, test_org, 'member')
    instance = _instance(test_org, '2')
    item = _queue(test_org, instance, _config(
        no_assignee_action='fallback_role',
        no_assignee_role_secure_code=role.secure_code,
    ), '2')

    _, result = _run(item)

    data = result['data']
    assert result['status'] == 'waiting_form_action'
    assert data['assignee_type'] == 'ROLE'
    assert data['assignee_value'] == role.secure_code
    assert data['assignees'] == [test_user.secure_code]
    assert data['no_assignee_fallback_applied'] is True
    assert data['original_assignee_type'] == 'DYNAMIC'
    assert FwApprovalRecord.query.filter_by(node_queue_secure_code=item.secure_code).count() == 0


def test_fallback_role_from_another_org_fails_closed_to_return(test_org, test_user):
    other_org = Organization(
        secure_code='fa_noasg_other_org_01',
        code='FANA_OTHER',
        name='Other Org',
        domain_name='fana-other.local',
        is_active=True,
        is_deleted=False,
    )
    db.session.add(other_org)
    db.session.commit()
    other_role = _role(other_org, 'other')
    instance = _instance(test_org, '3')
    item = _queue(test_org, instance, _config(
        no_assignee_action='fallback_role',
        no_assignee_role_secure_code=other_role.secure_code,
    ), '3')

    _, result = _run(item)
    db.session.commit()

    assert result['status'] == 'complete_workflow'
    assert result['data']['workflow_status'] == 'REJECTED'
    record = FwApprovalRecord.query.filter_by(node_queue_secure_code=item.secure_code).one()
    assert record.action == 'no_assignee'
    assert record.approver_name == '系統（找不到簽核人）'


def test_fallback_role_without_members_waits_with_empty_assignees(test_org, test_user):
    role = _role(test_org, 'empty')
    instance = _instance(test_org, '4')
    item = _queue(test_org, instance, _config(
        no_assignee_action='fallback_role',
        no_assignee_role_secure_code=role.secure_code,
    ), '4')

    _, result = _run(item)

    assert result['status'] == 'waiting_form_action'
    assert result['data']['assignee_type'] == 'ROLE'
    assert result['data']['assignees'] == []
    assert result['data']['no_assignee_reason'] == '變數 hr_approver 為空'


def test_role_type_empty_assignees_does_not_trigger_no_assignee_guard(test_org, test_user):
    role = _role(test_org, 'roleempty')
    instance = _instance(test_org, '5')
    item = _queue(test_org, instance, _config(
        assignee_type='ROLE',
        assignee_value=role.secure_code,
    ), '5')

    _, result = _run(item)

    assert result['status'] == 'waiting_form_action'
    assert result['data']['assignees'] == []
    assert 'no_assignee' not in result['data']
    assert FwApprovalRecord.query.filter_by(node_queue_secure_code=item.secure_code).count() == 0


def test_validate_requires_fallback_role_and_normalizes_unknown_action(test_org, test_user):
    instance = _instance(test_org, '6')
    missing_role = _queue(test_org, instance, _config(
        no_assignee_action='fallback_role',
        no_assignee_role_secure_code='',
    ), '61')
    with pytest.raises(ValueError, match='no_assignee_role_secure_code'):
        FormAdapterHandler(missing_role).validate()

    garbage = _queue(test_org, instance, _config(no_assignee_action='garbage'), '62')
    handler = FormAdapterHandler(garbage)
    assert handler.validate() is True
    assert handler.node_config['no_assignee_action'] == 'return'
