from datetime import timedelta
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db  # noqa: E402
from app.utils.security import generate_secure_code  # noqa: E402
from app.models import (
    AssignmentKind,
    OrganizationalUnit,
    Role,
    RoleType,
    ScopeType,
    UnitType,
    User,
    UserRoleAssignment,
    UserType,
)

from modules.form_workflow.models import (
    FwFormInstance,
    FwNodeExecutionQueue,
    FwWorkflowInstance,
    FwWorkflowVariable,
)  # noqa: E402
from modules.form_workflow.services.node_handlers.op_proxy_grant_handler import OpProxyGrantHandler  # noqa: E402


def _user(org, sc, username, user_type=UserType.EMPLOYEE):
    user = User(
        secure_code=sc,
        org_secure_code=org.secure_code,
        username=username,
        email=f'{username}@example.com',
        display_name=username,
        user_type=user_type,
        is_active=True,
        is_deleted=False,
    )
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()
    return user


def _role(org, sc, code, name=None, scope=ScopeType.GLOBAL, role_type=RoleType.ROLE):
    role = Role(
        secure_code=sc,
        org_secure_code=org.secure_code,
        code=code,
        name=name or code,
        scope_type=scope,
        role_type=role_type,
        is_active=True,
        is_deleted=False,
    )
    db.session.add(role)
    db.session.commit()
    return role


def _unit(org, sc='op_proxy_unit_0000000001'):
    unit = OrganizationalUnit(
        secure_code=sc,
        org_secure_code=org.secure_code,
        code=sc[-8:],
        name='代理節點測試部',
        unit_type=UnitType.DEPARTMENT,
        is_active=True,
        is_deleted=False,
    )
    db.session.add(unit)
    db.session.commit()
    return unit


def _regular(org, user, role, unit=None):
    row = UserRoleAssignment(
        org_secure_code=org.secure_code,
        user_secure_code=user.secure_code,
        role_secure_code=role.secure_code,
        unit_secure_code=unit.secure_code if unit else None,
        assignment_kind=AssignmentKind.REGULAR,
        is_deleted=False,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _queue(org, applicant, delegate_sc, roles, *, forms=None, reason='出差期間代理簽核',
           start=None, end=None):
    today = org.local_today()
    form = FwFormInstance(
        org_secure_code=org.secure_code,
        form_template_secure_code='op_proxy_form_tpl',
        form_name='代理指定申請單',
        form_code='PROXY_REQUEST',
        serial_number=f'OPP-{generate_secure_code()[:12]}',
        applicant_secure_code=applicant.secure_code if applicant else None,
        applicant_name=applicant.display_name if applicant else None,
        form_data={
            'delegate': delegate_sc,
            'proxy_roles': roles,
            'effective_from': start if start is not None else today.isoformat(),
            'effective_until': end if end is not None else (today + timedelta(days=3)).isoformat(),
            'authorized_forms': forms if forms is not None else [],
            'reason': reason,
        },
        status='PENDING',
    )
    db.session.add(form)
    db.session.flush()
    workflow = FwWorkflowInstance(
        org_secure_code=org.secure_code,
        form_instance_secure_code=form.secure_code,
        workflow_template_secure_code='op_proxy_wf_tpl',
        workflow_name='代理指定同意流程',
        execution_code=f'EXEC-{form.secure_code[-8:]}',
        status='RUNNING',
    )
    db.session.add(workflow)
    db.session.flush()
    form.workflow_instance_secure_code = workflow.secure_code
    queue = FwNodeExecutionQueue(
        org_secure_code=org.secure_code,
        workflow_instance_secure_code=workflow.secure_code,
        form_instance_secure_code=form.secure_code,
        node_id='node-OpProxyGrant',
        node_type='OpProxyGrant',
        status='PENDING',
        node_config={},
    )
    db.session.add(queue)
    db.session.commit()
    return queue


def _run(queue):
    return OpProxyGrantHandler(queue).handle()


def _proxy_rows(org, delegate):
    return UserRoleAssignment.query.filter_by(
        org_secure_code=org.secure_code,
        user_secure_code=delegate.secure_code,
        assignment_kind=AssignmentKind.PROXY,
        is_deleted=False,
    ).order_by(UserRoleAssignment.id).all()


def _var(workflow_sc, name):
    row = FwWorkflowVariable.query.filter_by(
        workflow_instance_secure_code=workflow_sc,
        var_name=name,
        var_type='FLOW',
    ).one()
    return row.var_value


def test_success_creates_proxy_rows_and_flow_variables(test_org):
    applicant = _user(test_org, 'op_proxy_applicant_001', 'opproxyapplicant')
    delegate = _user(test_org, 'op_proxy_delegate_0001', 'opproxydelegate')
    unit = _unit(test_org)
    manager = _role(test_org, 'op_proxy_role_mgr001', 'DEPT_MANAGER', '部門正主管',
                    ScopeType.DEPARTMENT, RoleType.POSITION)
    staff = _role(test_org, 'op_proxy_role_staff01', 'SECURITY_STAFF', '資訊安全人員')
    _regular(test_org, applicant, manager, unit)
    _regular(test_org, applicant, staff)
    today = test_org.local_today()
    queue = _queue(test_org, applicant, delegate.secure_code, [
        {'role_secure_code': manager.secure_code, 'unit_secure_code': unit.secure_code},
        {'role_secure_code': staff.secure_code, 'unit_secure_code': None},
    ])

    result = _run(queue)

    rows = _proxy_rows(test_org, delegate)
    assert result['status'] == 'success'
    assert len(rows) == 2
    assert {row.acting_for_user_secure_code for row in rows} == {applicant.secure_code}
    assert {row.source_ref.startswith('flow:EXEC-') for row in rows} == {True}
    assert {row.valid_from for row in rows} == {today}
    assert {row.valid_until for row in rows} == {today + timedelta(days=3)}
    assert {row.grant_reason for row in rows} == {'出差期間代理簽核'}
    assert _var(queue.workflow_instance_secure_code, 'proxy_count') == 2


def test_allowed_forms_are_copied_or_left_unlimited(test_org):
    applicant = _user(test_org, 'op_proxy_forms_app01', 'opproxyformsapp')
    delegate = _user(test_org, 'op_proxy_forms_del01', 'opproxyformsdel')
    role = _role(test_org, 'op_proxy_forms_role1', 'FORM_SIGNER')
    _regular(test_org, applicant, role)

    with_forms = _queue(test_org, applicant, delegate.secure_code, [
        {'role_secure_code': role.secure_code, 'unit_secure_code': None},
    ], forms=['tpl_a', 'tpl_b'])
    assert _run(with_forms)['status'] == 'success'
    assert _proxy_rows(test_org, delegate)[0].allowed_form_templates == ['tpl_a', 'tpl_b']

    other_delegate = _user(test_org, 'op_proxy_forms_del02', 'opproxyformsdel2')
    no_forms = _queue(test_org, applicant, other_delegate.secure_code, [
        {'role_secure_code': role.secure_code, 'unit_secure_code': None},
    ], forms=[])
    assert _run(no_forms)['status'] == 'success'
    assert _proxy_rows(test_org, other_delegate)[0].allowed_form_templates is None


def test_revalidates_regular_roles_at_execution_time_and_rolls_back(test_org):
    applicant = _user(test_org, 'op_proxy_reval_app1', 'opproxyrevalapp')
    delegate = _user(test_org, 'op_proxy_reval_del1', 'opproxyrevaldel')
    unit = _unit(test_org, 'op_proxy_reval_unit01')
    manager = _role(test_org, 'op_proxy_reval_mgr01', 'DEPT_MANAGER', '部門正主管',
                    ScopeType.DEPARTMENT, RoleType.POSITION)
    staff = _role(test_org, 'op_proxy_reval_staff', 'SECURITY_STAFF', '資訊安全人員')
    manager_row = _regular(test_org, applicant, manager, unit)
    _regular(test_org, applicant, staff)
    queue = _queue(test_org, applicant, delegate.secure_code, [
        {'role_secure_code': manager.secure_code, 'unit_secure_code': unit.secure_code},
        {'role_secure_code': staff.secure_code, 'unit_secure_code': None},
    ])
    manager_row.is_deleted = True
    db.session.commit()

    result = _run(queue)

    assert result['status'] == 'error'
    assert '已不在你目前持有的範圍內' in result['message']
    assert _proxy_rows(test_org, delegate) == []


def test_delegate_self_and_external_are_rejected(test_org):
    applicant = _user(test_org, 'op_proxy_self_app01', 'opproxyselfapp')
    external = _user(test_org, 'op_proxy_external01', 'opproxyexternal', UserType.EXTERNAL)
    role = _role(test_org, 'op_proxy_self_role1', 'SELF_SIGNER')
    _regular(test_org, applicant, role)

    self_queue = _queue(test_org, applicant, applicant.secure_code, [
        {'role_secure_code': role.secure_code, 'unit_secure_code': None},
    ])
    external_queue = _queue(test_org, applicant, external.secure_code, [
        {'role_secure_code': role.secure_code, 'unit_secure_code': None},
    ])

    assert _run(self_queue)['status'] == 'error'
    result = _run(external_queue)
    assert result['status'] == 'error'
    assert _proxy_rows(test_org, external) == []


def test_invalid_dates_reason_and_empty_roles_are_errors(test_org):
    applicant = _user(test_org, 'op_proxy_bad_app001', 'opproxybadapp')
    delegate = _user(test_org, 'op_proxy_bad_del001', 'opproxybaddel')
    role = _role(test_org, 'op_proxy_bad_role01', 'BAD_SIGNER')
    _regular(test_org, applicant, role)

    cases = [
        {'start': '2026/99/01'},
        {'start': '2026-10-05', 'end': '2026-10-01'},
        {'reason': '   '},
        {'roles': []},
    ]
    for idx, case in enumerate(cases):
        queue = _queue(
            test_org, applicant, delegate.secure_code,
            case.get('roles', [{'role_secure_code': role.secure_code, 'unit_secure_code': None}]),
            reason=case.get('reason', '出差期間代理簽核'),
            start=case.get('start'),
            end=case.get('end'),
        )
        result = _run(queue)
        assert result['status'] == 'error', idx
    assert _proxy_rows(test_org, delegate) == []


def test_unknown_role_is_rejected_as_out_of_scope(test_org):
    applicant = _user(test_org, 'op_proxy_unknown_app', 'opproxyunknownapp')
    delegate = _user(test_org, 'op_proxy_unknown_del', 'opproxyunknowndel')
    held = _role(test_org, 'op_proxy_unknown_hld', 'HELD_SIGNER')
    other = _role(test_org, 'op_proxy_unknown_oth', 'OTHER_SIGNER')
    _regular(test_org, applicant, held)
    queue = _queue(test_org, applicant, delegate.secure_code, [
        {'role_secure_code': other.secure_code, 'unit_secure_code': None},
    ])

    result = _run(queue)

    assert result['status'] == 'error'
    assert '已不在你目前持有的範圍內' in result['message']
    assert _proxy_rows(test_org, delegate) == []


def test_partial_assign_failure_rolls_back_all_rows(test_org, test_admin):
    applicant = _user(test_org, 'op_proxy_rb_app0001', 'opproxyrbapp')
    delegate = _user(test_org, 'op_proxy_rb_del0001', 'opproxyrbdel')
    role_a = _role(test_org, 'op_proxy_rb_role_a1', 'RB_SIGNER_A')
    role_b = _role(test_org, 'op_proxy_rb_role_b1', 'RB_SIGNER_B')
    _regular(test_org, applicant, role_a)
    _regular(test_org, applicant, role_b)
    today = test_org.local_today()
    from app.services.role_assignment_service import assign_role
    assign_role(
        test_org.secure_code,
        delegate.secure_code,
        role_b.secure_code,
        kind='proxy',
        acting_for_sc=applicant.secure_code,
        valid_from=today,
        valid_until=today + timedelta(days=5),
        grant_reason='既有重疊代理',
        operator=test_admin,
    )
    queue = _queue(test_org, applicant, delegate.secure_code, [
        {'role_secure_code': role_a.secure_code, 'unit_secure_code': None},
        {'role_secure_code': role_b.secure_code, 'unit_secure_code': None},
    ])

    result = _run(queue)

    rows = _proxy_rows(test_org, delegate)
    assert result['status'] == 'error'
    assert len(rows) == 1
    assert rows[0].role_secure_code == role_b.secure_code
