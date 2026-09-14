"""FormAdapter 角色@單位節點解析（PF-247 phase 2）。"""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db  # noqa: E402
from app.models import (  # noqa: E402
    AssignmentKind,
    MembershipType,
    Organization,
    OrganizationalUnit,
    Role,
    RoleType,
    ScheduleAdjustment,
    UnitType,
    User,
    UserRoleAssignment,
    UserType,
    UserUnitMembership,
)
from app.services.unit_resolver import (  # noqa: E402
    get_unit,
    get_unit_descendant_codes,
    resolve_role_holders,
)
from modules.form_workflow.models import (  # noqa: E402
    FwApprovalRecord,
    FwFormInstance,
    FwNodeExecutionQueue,
    FwWorkflowInstance,
)
from modules.form_workflow.services.node_handlers.formadapter_handler import FormAdapterHandler  # noqa: E402


TPL_SC = 'fa_ru_tpl'
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


def _unit(org, code, name, parent=None):
    full_path = f'{parent.full_path}/{name}' if parent else f'/{name}'
    unit = OrganizationalUnit(
        org_secure_code=org.secure_code,
        code=code,
        name=name,
        unit_type=UnitType.DEPARTMENT,
        parent_secure_code=parent.secure_code if parent else None,
        level=(parent.level + 1) if parent else 1,
        full_path=full_path,
        is_active=True,
        is_deleted=False,
    )
    db.session.add(unit)
    db.session.commit()
    return unit


def _role(org, code, role_type='ROLE', scope_type='DEPARTMENT', is_active=True):
    role = Role(
        org_secure_code=org.secure_code,
        code=code,
        name=code,
        role_type=role_type,
        scope_type=scope_type,
        is_active=is_active,
        is_deleted=False,
    )
    db.session.add(role)
    db.session.commit()
    return role


def _assign(user, role, unit=None, valid_from=None, valid_until=None, assigned_at=None,
            kind='regular', acting_for=None):
    row = UserRoleAssignment(
        user_secure_code=user.secure_code,
        role_secure_code=role.secure_code,
        org_secure_code=user.org_secure_code,
        unit_secure_code=unit.secure_code if unit else None,
        valid_from=valid_from,
        valid_until=valid_until,
        assigned_at=assigned_at or datetime.utcnow(),
        assignment_kind=kind,
        acting_for_user_secure_code=acting_for,
        is_deleted=False,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _leave(user, adjust_date, adjusted_periods, original_periods=None, status='APPROVED'):
    row = ScheduleAdjustment(
        org_secure_code=user.org_secure_code,
        user_secure_code=user.secure_code,
        adjust_date=adjust_date,
        adjust_type='LEAVE',
        original_periods=original_periods,
        adjusted_periods=adjusted_periods,
        status=status,
        is_deleted=False,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _membership(user, unit, start_date=None, end_date=None, membership_type='SOLID'):
    row = UserUnitMembership(
        org_secure_code=user.org_secure_code,
        user_secure_code=user.secure_code,
        unit_secure_code=unit.secure_code,
        membership_type=membership_type,
        start_date=start_date,
        end_date=end_date,
        is_deleted=False,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _user(sc, org, username, name):
    user = User(
        secure_code=sc,
        org_secure_code=org.secure_code,
        username=username,
        email=f'{username}@example.com',
        display_name=name,
        user_type=UserType.EMPLOYEE,
        is_active=True,
        is_deleted=False,
    )
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()
    return user


def _form_instance(org, applicant, suffix):
    fi = FwFormInstance(
        secure_code=f'fa_ru_fi_{suffix}'.ljust(24, '0')[:24],
        org_secure_code=org.secure_code,
        form_template_secure_code=TPL_SC,
        form_data={},
        serial_number=f'SN-{suffix}',
        applicant_secure_code=applicant.secure_code if applicant else None,
        is_deleted=False,
    )
    db.session.add(fi)
    db.session.commit()
    return fi


def _instance(org, suffix='1', form_instance=None):
    instance = FwWorkflowInstance(
        secure_code=f'fa_ru_wi_{suffix}'.ljust(24, '0')[:24],
        org_secure_code=org.secure_code,
        workflow_template_secure_code=TPL_SC,
        form_instance_secure_code=form_instance.secure_code if form_instance else None,
        execution_code=f'FARU-{suffix}',
        status='RUNNING',
        graph_snapshot=GRAPH,
    )
    db.session.add(instance)
    db.session.commit()
    return instance


def _queue(org, instance, config, suffix='1', form_instance=None, **extra):
    item = FwNodeExecutionQueue(
        secure_code=f'fa_ru_q_{suffix}'.ljust(24, '0')[:24],
        org_secure_code=org.secure_code,
        workflow_instance_secure_code=instance.secure_code,
        form_instance_secure_code=form_instance.secure_code if form_instance else None,
        node_id=NODE_ID,
        node_type='FormAdapter',
        node_name='主管核可',
        node_config=config,
        status='PENDING',
        **extra,
    )
    db.session.add(item)
    db.session.commit()
    return item


def _config(**overrides):
    config = {
        'assignee_type': 'ROLE',
        'selection_mode': 'single',
    }
    config.update(overrides)
    return config


def _run(queue_item):
    handler = FormAdapterHandler(queue_item)
    handler.validate()
    return handler, handler.handle()


def _env(org):
    info = _unit(org, 'INFO', '資訊群')
    sw = _unit(org, 'SW', '軟體部', info)
    sw1 = _unit(org, 'SW1', '軟體一課', sw)
    mkt = _unit(org, 'MKT', '行銷部門')
    roles = {
        'member': _role(org, 'DEPT_MEMBER'),
        'head': _role(org, 'DEPT_HEAD', RoleType.POSITION),
        'manager': _role(org, 'DEPT_MANAGER', RoleType.POSITION),
        'deputy': _role(org, 'DEPT_DEPUTY', RoleType.POSITION),
    }
    return {'info': info, 'sw': sw, 'sw1': sw1, 'mkt': mkt, **roles}


def test_global_role_snapshot_filters_expired_assignment(test_org):
    env = _env(test_org)
    today = test_org.local_today()
    unit_holder = _user('faru_global_unit', test_org, 'faruglobalunit', 'Unit Holder')
    global_holder = _user('faru_global_all', test_org, 'faruglobalall', 'Global Holder')
    expired = _user('faru_global_old', test_org, 'faruglobalold', 'Expired Holder')
    _assign(unit_holder, env['member'], env['sw'], assigned_at=datetime(2026, 1, 1))
    _assign(global_holder, env['member'], assigned_at=datetime(2026, 1, 2))
    _assign(expired, env['member'], valid_until=today - timedelta(days=1), assigned_at=datetime(2026, 1, 3))
    item = _queue(test_org, _instance(test_org, 'global'), _config(assignee_value=env['member'].secure_code), 'global')

    _, result = _run(item)

    data = result['data']
    assert result['status'] == 'waiting_form_action'
    assert data['assignees'] == [unit_holder.secure_code, global_holder.secure_code]
    assert data['assignee_unit_secure_code'] is None
    assert data['assignee_unit_name'] is None
    assert data['assignee_role_code'] == 'DEPT_MEMBER'
    assert data['assignee_role_type'] == 'ROLE'
    assert data['assignee_unit_scope'] == 'GLOBAL'
    assert 'absence_fallback' not in data
    assert data['assignee_role_name'] == env['member'].name


def test_self_target_default_escalate_or_return_rejects_at_root(test_org):
    env = _env(test_org)
    applicant = _user('faru_self_root', test_org, 'faruselfroot', 'Self Root')
    _membership(applicant, env['mkt'])
    _assign(applicant, env['manager'], env['mkt'])
    fi = _form_instance(test_org, applicant, 'selfroot')
    item = _queue(test_org, _instance(test_org, 'selfroot', fi), _config(
        assignee_value=env['manager'].secure_code,
        unit_scope='APPLICANT_UNIT',
    ), 'selfroot', fi)

    _, result = _run(item)

    assert result['status'] == 'complete_workflow'
    assert result['data']['workflow_status'] == 'REJECTED'
    assert result['data']['self_target_action'] == 'escalate_or_return'
    assert '申請人本人為簽核者' in FwApprovalRecord.query.filter_by(node_queue_secure_code=item.secure_code).one().comment


def test_self_target_escalate_or_self_keeps_applicant_when_root_has_no_other(test_org):
    env = _env(test_org)
    applicant = _user('faru_self_ok', test_org, 'faruselfok', 'Self Ok')
    _membership(applicant, env['mkt'])
    _assign(applicant, env['manager'], env['mkt'])
    fi = _form_instance(test_org, applicant, 'selfok')
    item = _queue(test_org, _instance(test_org, 'selfok', fi), _config(
        assignee_value=env['manager'].secure_code,
        unit_scope='APPLICANT_UNIT',
        self_target_action='escalate_or_self',
    ), 'selfok', fi)

    _, result = _run(item)

    assert result['status'] == 'waiting_form_action'
    assert applicant.secure_code in result['data']['assignees']
    assert result['data']['self_target_escalated_levels'] == 0


def test_self_target_self_keeps_applicant_without_escalation(test_org):
    env = _env(test_org)
    applicant = _user('faru_self_direct', test_org, 'faruselfdirect', 'Self Direct')
    _membership(applicant, env['mkt'])
    _assign(applicant, env['manager'], env['mkt'])
    fi = _form_instance(test_org, applicant, 'selfdirect')
    item = _queue(test_org, _instance(test_org, 'selfdirect', fi), _config(
        assignee_value=env['manager'].secure_code,
        unit_scope='APPLICANT_UNIT',
        self_target_action='self',
    ), 'selfdirect', fi)

    _, result = _run(item)

    assert result['status'] == 'waiting_form_action'
    assert applicant.secure_code in result['data']['assignees']
    assert result['data']['self_target_escalated_levels'] == 0
    assert result['data']['self_target_action'] == 'self'


def test_self_target_escalates_one_level_to_other_manager(test_org):
    env = _env(test_org)
    applicant = _user('faru_self_sw_mgr', test_org, 'faruselfswmgr', 'Self SW Manager')
    info_manager = _user('faru_info_mgr', test_org, 'faruinfomgr', 'Info Manager')
    _membership(applicant, env['sw'])
    _assign(applicant, env['manager'], env['sw'])
    _assign(info_manager, env['manager'], env['info'])
    fi = _form_instance(test_org, applicant, 'selfup1')
    item = _queue(test_org, _instance(test_org, 'selfup1', fi), _config(
        assignee_value=env['manager'].secure_code,
        unit_scope='APPLICANT_UNIT',
    ), 'selfup1', fi)

    _, result = _run(item)

    assert result['data']['assignee_unit_secure_code'] == env['info'].secure_code
    assert result['data']['assignees'] == [info_manager.secure_code]
    assert result['data']['self_target_escalated_levels'] == 1


def test_self_target_escalation_uses_effective_holders_on_parent(test_org):
    env = _env(test_org)
    applicant = _user('faru_self_sw_mgr2', test_org, 'faruselfswmgr2', 'Self SW Manager 2')
    info_deputy = _user('faru_info_dep', test_org, 'faruinfodep', 'Info Deputy')
    _membership(applicant, env['sw'])
    _assign(applicant, env['manager'], env['sw'])
    _assign(info_deputy, env['manager'], env['info'])
    fi = _form_instance(test_org, applicant, 'selfupdep')
    item = _queue(test_org, _instance(test_org, 'selfupdep', fi), _config(
        assignee_value=env['manager'].secure_code,
        unit_scope='APPLICANT_UNIT',
    ), 'selfupdep', fi)

    _, result = _run(item)

    assert result['data']['assignees'] == [info_deputy.secure_code]
    assert result['data']['self_target_escalated_levels'] == 1


def test_self_target_escalates_two_levels_when_parent_is_same_applicant(test_org):
    env = _env(test_org)
    applicant = _user('faru_self_sw1_mgr', test_org, 'faruselfsw1mgr', 'Self SW1 Manager')
    info_manager = _user('faru_info_mgr2', test_org, 'faruinfomgr2', 'Info Manager 2')
    _membership(applicant, env['sw1'])
    _assign(applicant, env['manager'], env['sw1'])
    _assign(applicant, env['manager'], env['sw'])
    _assign(info_manager, env['manager'], env['info'])
    fi = _form_instance(test_org, applicant, 'selfup2')
    item = _queue(test_org, _instance(test_org, 'selfup2', fi), _config(
        assignee_value=env['manager'].secure_code,
        unit_scope='APPLICANT_UNIT',
    ), 'selfup2', fi)

    _, result = _run(item)

    assert result['data']['self_target_escalated_levels'] == 2
    assert result['data']['assignee_unit_secure_code'] == env['info'].secure_code
    assert result['data']['assignees'] == [info_manager.secure_code]


def test_self_target_proxy_snapshot_member_counts_as_self(test_org):
    env = _env(test_org)
    applicant = _user('faru_self_proxy', test_org, 'faruselfproxy', 'Self Proxy')
    manager = _user('faru_self_proxy_mgr', test_org, 'faruselfproxymgr', 'Self Proxy Manager')
    _membership(applicant, env['mkt'])
    _assign(manager, env['manager'], env['mkt'])
    _assign(applicant, env['manager'], env['mkt'], kind=AssignmentKind.PROXY, acting_for=manager.secure_code)
    fi = _form_instance(test_org, applicant, 'selfproxy')
    item = _queue(test_org, _instance(test_org, 'selfdep', fi), _config(
        assignee_value=env['manager'].secure_code,
        unit_scope='APPLICANT_UNIT',
    ), 'selfdep', fi)

    _, result = _run(item)

    assert result['status'] == 'complete_workflow'
    assert '申請人本人為簽核者' in FwApprovalRecord.query.filter_by(node_queue_secure_code=item.secure_code).one().comment


def test_self_target_role_type_member_does_not_escalate(test_org):
    env = _env(test_org)
    applicant = _user('faru_self_member', test_org, 'faruselfmember', 'Self Member')
    _membership(applicant, env['mkt'])
    _assign(applicant, env['member'], env['mkt'])
    fi = _form_instance(test_org, applicant, 'selfmember')
    item = _queue(test_org, _instance(test_org, 'selfmember', fi), _config(
        assignee_value=env['member'].secure_code,
        unit_scope='APPLICANT_UNIT',
    ), 'selfmember', fi)

    _, result = _run(item)

    assert result['status'] == 'waiting_form_action'
    assert applicant.secure_code in result['data']['assignees']
    assert result['data']['self_target_escalated_levels'] == 0


def test_self_target_unit_scope_does_not_write_self_target_keys(test_org):
    env = _env(test_org)
    applicant = _user('faru_unit_self', test_org, 'faruunitself', 'Unit Self')
    _assign(applicant, env['manager'], env['mkt'])
    item = _queue(test_org, _instance(test_org, 'unitself'), _config(
        assignee_value=env['manager'].secure_code,
        unit_scope='UNIT',
        unit_secure_code=env['mkt'].secure_code,
    ), 'unitself')

    _, result = _run(item)

    assert applicant.secure_code in result['data']['assignees']
    assert 'self_target_action' not in result['data']


def test_unit_position_snapshot_uses_effective_holders_and_ignores_absence_fallback(test_org):
    env = _env(test_org)
    manager = _user('faru_mkt_mgr', test_org, 'farumktmgr', 'Manager')
    standby1 = _user('faru_mkt_p1', test_org, 'farumktp1', 'Standby 1')
    standby2 = _user('faru_mkt_p2', test_org, 'farumktp2', 'Standby 2')
    _assign(manager, env['manager'], env['mkt'])
    s1 = _assign(standby1, env['manager'], env['mkt'], kind=AssignmentKind.STANDBY)
    s2 = _assign(standby2, env['manager'], env['mkt'], kind=AssignmentKind.STANDBY)

    present = _queue(test_org, _instance(test_org, 'pos1'), _config(
        assignee_value=env['manager'].secure_code,
        unit_scope='UNIT',
        unit_secure_code=env['mkt'].secure_code,
    ), 'pos1')
    _, present_result = _run(present)
    assert present_result['data']['assignees'] == [manager.secure_code]
    assert present_result['data']['assignee_role_type'] == 'POSITION'
    assert present_result['data']['assignee_unit_name'] == '行銷部門'
    assert present_result['data']['assignee_unit_scope'] == 'UNIT'

    manager_assignment = UserRoleAssignment.query.filter_by(user_secure_code=manager.secure_code).one()
    manager_assignment.is_deleted = True
    db.session.commit()
    vacant = _queue(test_org, _instance(test_org, 'pos2'), _config(
        assignee_value=env['manager'].secure_code,
        unit_scope='UNIT',
        unit_secure_code=env['mkt'].secure_code,
    ), 'pos2')
    _, vacant_result = _run(vacant)
    assert vacant_result['data']['assignees'] == [standby1.secure_code, standby2.secure_code]

    disabled = _queue(test_org, _instance(test_org, 'pos3'), _config(
        assignee_value=env['manager'].secure_code,
        unit_scope='UNIT',
        unit_secure_code=env['mkt'].secure_code,
        absence_fallback=False,
    ), 'pos3')
    _, disabled_result = _run(disabled)
    assert disabled_result['status'] == 'waiting_form_action'
    assert disabled_result['data']['assignees'] == [standby1.secure_code, standby2.secure_code]
    assert 'absence_fallback' not in disabled_result['data']
    assert FwApprovalRecord.query.filter_by(node_queue_secure_code=disabled.secure_code).count() == 0
    assert s1.assignment_kind == AssignmentKind.STANDBY
    assert s2.assignment_kind == AssignmentKind.STANDBY


def test_unit_position_snapshot_adds_proxies_when_manager_is_on_full_day_leave(test_org, monkeypatch):
    env = _env(test_org)
    manager = _user('faru_leave_mgr', test_org, 'faruleavemgr', 'Leave Manager')
    standby1 = _user('faru_leave_s1', test_org, 'faruleaves1', 'Leave Standby 1')
    standby2 = _user('faru_leave_s2', test_org, 'faruleaves2', 'Leave Standby 2')
    proxy = _user('faru_leave_p', test_org, 'faruleavep', 'Leave Proxy')
    _assign(manager, env['manager'], env['mkt'])
    _assign(standby1, env['manager'], env['mkt'], kind=AssignmentKind.STANDBY)
    _assign(standby2, env['manager'], env['mkt'], kind=AssignmentKind.STANDBY)
    _assign(proxy, env['manager'], env['mkt'], kind=AssignmentKind.PROXY, acting_for=manager.secure_code)
    _leave(manager, date(2026, 9, 5), [])
    monkeypatch.setattr(
        FormAdapterHandler,
        '_local_now',
        lambda self: datetime(2026, 9, 5, 14, 0),
    )
    item = _queue(test_org, _instance(test_org, 'posleave'), _config(
        assignee_value=env['manager'].secure_code,
        unit_scope='UNIT',
        unit_secure_code=env['mkt'].secure_code,
    ), 'posleave')

    _, result = _run(item)

    assert result['data']['assignees'] == [
        manager.secure_code,
        proxy.secure_code,
    ]


def test_unit_position_snapshot_partial_leave_proxies_follow_current_time(test_org, monkeypatch):
    env = _env(test_org)
    manager = _user('faru_partial_mgr', test_org, 'farupartialmgr', 'Partial Manager')
    standby1 = _user('faru_partial_s1', test_org, 'farupartials1', 'Partial Standby 1')
    standby2 = _user('faru_partial_s2', test_org, 'farupartials2', 'Partial Standby 2')
    _assign(manager, env['manager'], env['mkt'])
    _assign(standby1, env['manager'], env['mkt'], kind=AssignmentKind.STANDBY)
    _assign(standby2, env['manager'], env['mkt'], kind=AssignmentKind.STANDBY)
    _leave(
        manager,
        date(2026, 9, 5),
        ['13:00-18:00'],
        ['09:00-12:00', '13:00-18:00'],
    )

    monkeypatch.setattr(
        FormAdapterHandler,
        '_local_now',
        lambda self: datetime(2026, 9, 5, 10, 0),
    )
    morning = _queue(test_org, _instance(test_org, 'posleaveam'), _config(
        assignee_value=env['manager'].secure_code,
        unit_scope='UNIT',
        unit_secure_code=env['mkt'].secure_code,
    ), 'posleaveam')
    _, morning_result = _run(morning)
    assert morning_result['data']['assignees'] == [manager.secure_code, standby1.secure_code, standby2.secure_code]

    monkeypatch.setattr(
        FormAdapterHandler,
        '_local_now',
        lambda self: datetime(2026, 9, 5, 14, 0),
    )
    afternoon = _queue(test_org, _instance(test_org, 'posleavepm'), _config(
        assignee_value=env['manager'].secure_code,
        unit_scope='UNIT',
        unit_secure_code=env['mkt'].secure_code,
    ), 'posleavepm')
    _, afternoon_result = _run(afternoon)
    assert afternoon_result['data']['assignees'] == [manager.secure_code]


def test_unit_role_snapshot_includes_descendant_and_global_holders(test_org):
    env = _env(test_org)
    sw = _user('faru_sw_member', test_org, 'faruswmember', 'Software Member')
    sw1 = _user('faru_sw1_member', test_org, 'farusw1member', 'Software One Member')
    mkt = _user('faru_mkt_member', test_org, 'farumktmember', 'Marketing Member')
    global_user = _user('faru_any_member', test_org, 'faruanymember', 'Any Member')
    _assign(sw, env['member'], env['sw'], assigned_at=datetime(2026, 1, 1))
    _assign(sw1, env['member'], env['sw1'], assigned_at=datetime(2026, 1, 2))
    _assign(mkt, env['member'], env['mkt'], assigned_at=datetime(2026, 1, 3))
    _assign(global_user, env['member'], assigned_at=datetime(2026, 1, 4))
    item = _queue(test_org, _instance(test_org, 'bubble'), _config(
        assignee_value=env['member'].secure_code,
        unit_scope='UNIT',
        unit_secure_code=env['info'].secure_code,
    ), 'bubble')

    _, result = _run(item)

    assert result['data']['assignees'] == [sw.secure_code, sw1.secure_code, global_user.secure_code]


def test_applicant_unit_failures_use_pf226_records(test_org):
    env = _env(test_org)
    applicant = _user('faru_applicant', test_org, 'faruapplicant', 'Applicant')
    _membership(applicant, env['mkt'])
    fi = _form_instance(test_org, applicant, 'app1')
    wi = _instance(test_org, 'app1', fi)
    item = _queue(test_org, wi, _config(
        assignee_value=env['manager'].secure_code,
        unit_scope='APPLICANT_UNIT',
    ), 'app1', fi)
    _, result = _run(item)
    assert result['data']['assignee_unit_secure_code'] == env['mkt'].secure_code

    no_member = _user('faru_no_unit', test_org, 'farunounit', 'No Unit')
    fi2 = _form_instance(test_org, no_member, 'app2')
    item2 = _queue(test_org, _instance(test_org, 'app2', fi2), _config(
        assignee_value=env['manager'].secure_code,
        unit_scope='APPLICANT_UNIT',
    ), 'app2', fi2)
    _, rejected = _run(item2)
    assert rejected['status'] == 'complete_workflow'
    assert rejected['data']['workflow_status'] == 'REJECTED'
    assert '申請人沒有所屬單位' in FwApprovalRecord.query.filter_by(node_queue_secure_code=item2.secure_code).one().comment

    item3 = _queue(test_org, _instance(test_org, 'app3'), _config(
        assignee_value=env['manager'].secure_code,
        unit_scope='APPLICANT_UNIT',
    ), 'app3')
    _, missing_applicant = _run(item3)
    assert '表單沒有申請人' in FwApprovalRecord.query.filter_by(node_queue_secure_code=item3.secure_code).one().comment
    assert missing_applicant['data']['workflow_status'] == 'REJECTED'


def test_applicant_ancestor_levels_clamp_to_root_and_root_stays_self(test_org):
    env = _env(test_org)
    applicant = _user('faru_ancestor', test_org, 'faruancestor', 'Ancestor')
    root_applicant = _user('faru_root_app', test_org, 'farurootapp', 'Root Applicant')
    _membership(applicant, env['sw1'])
    _membership(root_applicant, env['info'])

    results = []
    for suffix, levels, expected in [
        ('anc1', 1, env['sw']),
        ('anc2', 2, env['info']),
        ('anc5', 5, env['info']),
    ]:
        fi = _form_instance(test_org, applicant, suffix)
        item = _queue(test_org, _instance(test_org, suffix, fi), _config(
            assignee_value=env['member'].secure_code,
            unit_scope='APPLICANT_ANCESTOR',
            unit_levels_up=levels,
        ), suffix, fi)
        _, result = _run(item)
        results.append(result['data']['assignee_unit_secure_code'] == expected.secure_code)

    fi_root = _form_instance(test_org, root_applicant, 'ancroot')
    item_root = _queue(test_org, _instance(test_org, 'ancroot', fi_root), _config(
        assignee_value=env['member'].secure_code,
        unit_scope='APPLICANT_ANCESTOR',
        unit_levels_up=1,
    ), 'ancroot', fi_root)
    _, root_result = _run(item_root)
    assert results == [True, True, True]
    assert root_result['data']['assignee_unit_secure_code'] == env['info'].secure_code


def test_missing_cross_org_and_deleted_roles_fail_closed(test_org):
    env = _env(test_org)
    other = Organization(
        secure_code='faru_other_org',
        code='FARU_OTHER',
        name='Other Org',
        domain_name='faru-other.local',
        is_active=True,
        is_deleted=False,
    )
    db.session.add(other)
    db.session.commit()
    other_role = _role(other, 'DEPT_MEMBER')
    deleted_role = _role(test_org, 'FARU_DELETED')
    deleted_role.is_deleted = True
    db.session.commit()

    for suffix, role_sc in [('norole', 'missing_role_sc'), ('otherrole', other_role.secure_code), ('delrole', deleted_role.secure_code)]:
        item = _queue(test_org, _instance(test_org, suffix), _config(assignee_value=role_sc), suffix)
        _, result = _run(item)
        assert result['status'] == 'complete_workflow'
        assert result['data']['workflow_status'] == 'REJECTED'
        assert '不存在或已刪除' in FwApprovalRecord.query.filter_by(node_queue_secure_code=item.secure_code).one().comment

    item = _queue(test_org, _instance(test_org, 'badunit'), _config(
        assignee_value=env['member'].secure_code,
        unit_scope='UNIT',
        unit_secure_code=_unit(other, 'OTHER_UNIT', 'Other Unit').secure_code,
    ), 'badunit')
    _, bad_unit = _run(item)
    assert bad_unit['status'] == 'complete_workflow'
    assert '不存在或已刪除' in FwApprovalRecord.query.filter_by(node_queue_secure_code=item.secure_code).one().comment


def test_missing_role_can_fallback_to_global_role_spec(test_org, test_user):
    env = _env(test_org)
    _assign(test_user, env['member'])
    item = _queue(test_org, _instance(test_org, 'fallback'), _config(
        assignee_value='missing_role_sc',
        no_assignee_action='fallback_role',
        no_assignee_role_secure_code=env['member'].secure_code,
    ), 'fallback')

    _, result = _run(item)

    data = result['data']
    assert result['status'] == 'waiting_form_action'
    assert data['no_assignee_fallback_applied'] is True
    assert data['assignee_role_code'] == 'DEPT_MEMBER'
    assert data['assignee_role_type'] == 'ROLE'
    assert data['assignee_unit_secure_code'] is None
    assert data['assignee_unit_scope'] == 'GLOBAL'
    assert data['assignees'] == [test_user.secure_code]


def test_department_alias_uses_dept_member_role_not_primary_unit_snapshot(test_org):
    env = _env(test_org)
    holder = _user('faru_dept_holder', test_org, 'farudeptholder', 'Department Holder')
    primary_only = _user('faru_primary_only', test_org, 'faruprimaryonly', 'Primary Only')
    primary_only.primary_unit_secure_code = env['info'].secure_code
    _assign(holder, env['member'], env['sw'])
    db.session.commit()
    item = _queue(test_org, _instance(test_org, 'dept1'), {
        'assignee_type': 'DEPARTMENT',
        'assignee_value': env['info'].secure_code,
        'selection_mode': 'single',
    }, 'dept1')

    _, result = _run(item)

    data = result['data']
    assert data['assignee_type'] == 'ROLE'
    assert data['assignee_value'] == env['member'].secure_code
    assert data['assignee_unit_secure_code'] == env['info'].secure_code
    assert data['assignee_unit_scope'] == 'DEPARTMENT'
    assert data['original_assignee_type'] == 'DEPARTMENT'
    assert data['original_assignee_value'] == env['info'].secure_code
    assert data['assignees'] == [holder.secure_code]
    assert primary_only.secure_code not in data['assignees']

    empty = _queue(test_org, _instance(test_org, 'dept2'), {
        'assignee_type': 'DEPARTMENT',
        'assignee_value': env['mkt'].secure_code,
        'selection_mode': 'single',
    }, 'dept2')
    _, empty_result = _run(empty)
    assert empty_result['status'] == 'waiting_form_action'
    assert empty_result['data']['assignees'] == []

    other = Organization(
        secure_code='faru_nodept_org',
        code='FARU_NODEPT',
        name='No Dept Role Org',
        domain_name='faru-nodept.local',
        is_active=True,
        is_deleted=False,
    )
    db.session.add(other)
    db.session.commit()
    other_unit = _unit(other, 'INFO', '資訊群')
    no_role_item = _queue(other, _instance(other, 'dept3'), {
        'assignee_type': 'DEPARTMENT',
        'assignee_value': other_unit.secure_code,
        'selection_mode': 'single',
    }, 'dept3')
    _, no_role = _run(no_role_item)
    assert no_role['status'] == 'complete_workflow'
    assert 'DEPT_MEMBER' in FwApprovalRecord.query.filter_by(node_queue_secure_code=no_role_item.secure_code).one().comment


def test_validate_role_unit_keys_only_apply_to_role(test_org):
    env = _env(test_org)
    instance = _instance(test_org, 'val')
    cases = [
        (_config(assignee_value=env['member'].secure_code, unit_scope='garbage'), 'unit_scope'),
        (_config(assignee_value=env['member'].secure_code, unit_scope='UNIT'), 'unit_secure_code'),
        (_config(assignee_value=env['member'].secure_code, unit_scope='APPLICANT_ANCESTOR', unit_levels_up=0), 'unit_levels_up'),
        (_config(assignee_value=env['member'].secure_code, unit_scope='APPLICANT_ANCESTOR', unit_levels_up='abc'), 'unit_levels_up'),
        (_config(assignee_value=env['member'].secure_code, self_target_action='garbage'), 'self_target_action'),
    ]
    for idx, (config, message) in enumerate(cases):
        with pytest.raises(ValueError, match=message):
            FormAdapterHandler(_queue(test_org, instance, config, f'valbad{idx}')).validate()

    normal = _queue(test_org, instance, _config(assignee_value=env['member'].secure_code), 'valok')
    handler = FormAdapterHandler(normal)
    assert handler.validate() is True
    assert handler.node_config['unit_scope'] == 'GLOBAL'
    assert handler.node_config['self_target_action'] == 'escalate_or_return'

    false_item = _queue(test_org, instance, _config(
        assignee_value=env['member'].secure_code,
        absence_fallback='false',
    ), 'valfalse')
    false_handler = FormAdapterHandler(false_item)
    assert false_handler.validate() is True

    user_item = _queue(test_org, instance, {
        'assignee_type': 'USER',
        'assignee_value': 'u1',
        'unit_scope': 'garbage',
        'selection_mode': 'single',
    }, 'valuser')
    assert FormAdapterHandler(user_item).validate() is True


def test_self_target_escalate_or_return_can_fallback_to_role(test_org, test_user):
    env = _env(test_org)
    applicant = _user('faru_self_fb', test_org, 'faruselffb', 'Self Fallback')
    _membership(applicant, env['mkt'])
    _assign(applicant, env['manager'], env['mkt'])
    _assign(test_user, env['member'])
    fi = _form_instance(test_org, applicant, 'selffb')
    item = _queue(test_org, _instance(test_org, 'selffb', fi), _config(
        assignee_value=env['manager'].secure_code,
        unit_scope='APPLICANT_UNIT',
        no_assignee_action='fallback_role',
        no_assignee_role_secure_code=env['member'].secure_code,
    ), 'selffb', fi)

    _, result = _run(item)

    assert result['status'] == 'waiting_form_action'
    assert result['data']['no_assignee_fallback_applied'] is True
    assert result['data']['assignees'] == [test_user.secure_code]


def test_timeout_reference_user_receives_role_unit_snapshot(test_org, monkeypatch):
    env = _env(test_org)
    manager = _user('faru_to_mgr', test_org, 'farutomgr', 'Timeout Manager')
    deputy = _user('faru_to_dep', test_org, 'farutodep', 'Timeout Deputy')
    _assign(manager, env['head'], env['mkt'], assigned_at=datetime(2026, 1, 1))
    _assign(deputy, env['head'], env['mkt'], assigned_at=datetime(2026, 1, 2))
    seen = {}

    def fake_reference(self, assignees):
        seen['assignees'] = list(assignees)
        return None

    monkeypatch.setattr(FormAdapterHandler, '_working_reference_user', fake_reference)
    item = _queue(test_org, _instance(test_org, 'timeout'), _config(
        assignee_value=env['head'].secure_code,
        unit_scope='UNIT',
        unit_secure_code=env['mkt'].secure_code,
        timeout_enabled=True,
        timeout_minutes=30,
        timeout_mode='WORKING',
        timeout_path_id='e_ok',
    ), 'timeout')

    _, result = _run(item)

    assert seen['assignees'] == result['data']['assignees']
    assert result['data']['assignees'] == [manager.secure_code, deputy.secure_code]


def test_head_gate_snapshot_lists_manager_and_deputy(test_org):
    env = _env(test_org)
    manager = _user('faru_head_mgr', test_org, 'faruheadmgr', 'Head Manager')
    deputy = _user('faru_head_dep', test_org, 'faruheaddep', 'Head Deputy')
    _assign(manager, env['head'], env['mkt'], assigned_at=datetime(2026, 1, 1))
    _assign(deputy, env['head'], env['mkt'], assigned_at=datetime(2026, 1, 2))
    _assign(manager, env['manager'], env['mkt'], assigned_at=datetime(2026, 1, 3))
    _assign(deputy, env['deputy'], env['mkt'], assigned_at=datetime(2026, 1, 4))

    head_item = _queue(test_org, _instance(test_org, 'headsnap'), _config(
        assignee_value=env['head'].secure_code,
        unit_scope='UNIT',
        unit_secure_code=env['mkt'].secure_code,
    ), 'headsnap')
    _, head_result = _run(head_item)
    assert head_result['data']['assignees'] == [manager.secure_code, deputy.secure_code]

    manager_item = _queue(test_org, _instance(test_org, 'mgrsnap'), _config(
        assignee_value=env['manager'].secure_code,
        unit_scope='UNIT',
        unit_secure_code=env['mkt'].secure_code,
    ), 'mgrsnap')
    _, manager_result = _run(manager_item)
    assert manager_result['data']['assignees'] == [manager.secure_code]


def test_snapshot_standby_only_when_no_available_holder(test_org):
    env = _env(test_org)
    manager = _user('faru_standby_mgr', test_org, 'farustandbymgr', 'Standby Manager')
    standby = _user('faru_standby', test_org, 'farustandby', 'Standby')
    _assign(manager, env['manager'], env['mkt'])
    _assign(standby, env['manager'], env['mkt'], kind=AssignmentKind.STANDBY)

    present_item = _queue(test_org, _instance(test_org, 'standbyon'), _config(
        assignee_value=env['manager'].secure_code,
        unit_scope='UNIT',
        unit_secure_code=env['mkt'].secure_code,
    ), 'standbyon')
    _, present_result = _run(present_item)
    assert present_result['data']['assignees'] == [manager.secure_code]

    manager.is_active = False
    db.session.commit()
    inactive_item = _queue(test_org, _instance(test_org, 'standbyoff'), _config(
        assignee_value=env['manager'].secure_code,
        unit_scope='UNIT',
        unit_secure_code=env['mkt'].secure_code,
    ), 'standbyoff')
    _, inactive_result = _run(inactive_item)
    assert inactive_result['data']['assignees'] == [standby.secure_code]


def test_snapshot_never_writes_absence_fallback_key(test_org):
    env = _env(test_org)
    holder = _user('faru_no_absence_key', test_org, 'farunoabsencekey', 'No Absence Key')
    _assign(holder, env['member'], env['mkt'])
    item = _queue(test_org, _instance(test_org, 'noabsence'), _config(
        assignee_value=env['member'].secure_code,
        unit_scope='UNIT',
        unit_secure_code=env['mkt'].secure_code,
        absence_fallback=True,
    ), 'noabsence')

    _, result = _run(item)

    assert result['status'] == 'waiting_form_action'
    assert 'absence_fallback' not in result['data']


def test_non_role_assignee_data_shape_is_unchanged(test_org):
    item = _queue(test_org, _instance(test_org, 'user'), {
        'assignee_type': 'USER',
        'assignee_value': 'u_a, u_b',
        'selection_mode': 'single',
    }, 'user')

    _, result = _run(item)

    assert result['data']['assignees'] == ['u_a', 'u_b']
    assert 'assignee_unit_secure_code' not in result['data']
    assert 'assignee_role_type' not in result['data']


def test_unit_resolver_descendants_units_and_role_holders(test_org):
    env = _env(test_org)
    today = test_org.local_today()
    base = datetime(2026, 1, 1)
    root_holder = _user('faru_res_root', test_org, 'faruresroot', 'Root Holder')
    child_holder = _user('faru_res_child', test_org, 'farureschild', 'Child Holder')
    other_holder = _user('faru_res_other', test_org, 'faruresother', 'Other Holder')
    global_holder = _user('faru_res_global', test_org, 'faruresglobal', 'Global Holder')
    inactive = _user('faru_res_inactive', test_org, 'faruresinactive', 'Inactive Holder')
    expired = _user('faru_res_expired', test_org, 'faruresexpired', 'Expired Holder')
    inactive.is_active = False
    db.session.commit()
    _assign(child_holder, env['member'], env['sw'], assigned_at=base + timedelta(seconds=1))
    _assign(root_holder, env['member'], env['info'], assigned_at=base)
    _assign(other_holder, env['member'], env['mkt'], assigned_at=base + timedelta(seconds=2))
    _assign(global_holder, env['member'], assigned_at=base + timedelta(seconds=3))
    _assign(inactive, env['member'], env['info'], assigned_at=base + timedelta(seconds=4))
    _assign(expired, env['member'], env['info'], valid_until=today - timedelta(days=1), assigned_at=base + timedelta(seconds=5))

    assert get_unit_descendant_codes(env['info'].secure_code, test_org.secure_code) == [
        env['sw'].secure_code,
        env['sw1'].secure_code,
    ]
    assert resolve_role_holders(env['member'].secure_code, test_org.secure_code) == [
        root_holder.secure_code,
        child_holder.secure_code,
        other_holder.secure_code,
        global_holder.secure_code,
    ]
    assert resolve_role_holders(env['member'].secure_code, test_org.secure_code, env['info'].secure_code) == [
        root_holder.secure_code,
        global_holder.secure_code,
    ]
    assert resolve_role_holders(
        env['member'].secure_code,
        test_org.secure_code,
        env['info'].secure_code,
        include_descendant_units=True,
    ) == [root_holder.secure_code, child_holder.secure_code, global_holder.secure_code]

    env['sw'].is_deleted = True
    db.session.commit()
    assert get_unit_descendant_codes(env['info'].secure_code, test_org.secure_code) == []
    assert get_unit_descendant_codes('missing', test_org.secure_code) == []
    assert get_unit(env['mkt'].secure_code, 'other_org') is None
