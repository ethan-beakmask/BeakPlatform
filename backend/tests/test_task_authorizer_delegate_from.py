from datetime import timedelta
import sys
from pathlib import Path

from sqlalchemy import event

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db  # noqa: E402
from app.models import AssignmentKind, OrganizationalUnit, Role, RoleType, UnitType, User, UserRoleAssignment, UserType  # noqa: E402
from modules.form_workflow.models import FwFormInstance, FwFormTemplate, FwNodeExecutionQueue  # noqa: E402
from modules.form_workflow.services.task_authorizer import (  # noqa: E402
    build_actor,
    can_act_on_task,
    delegate_from_fields,
    resolve_acting_identity,
    is_pending_assignee,
)


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


def _role(org, sc, code, role_type=RoleType.POSITION):
    role = Role(
        secure_code=sc,
        org_secure_code=org.secure_code,
        code=code,
        name=code,
        role_type=role_type,
        scope_type='DEPARTMENT',
        is_active=True,
        is_deleted=False,
    )
    db.session.add(role)
    db.session.commit()
    return role


def _unit(org):
    unit = OrganizationalUnit(
        secure_code='ta_unit_000000000000001',
        org_secure_code=org.secure_code,
        code='TA',
        name='Test Dept',
        unit_type=UnitType.DEPARTMENT,
        is_active=True,
        is_deleted=False,
    )
    db.session.add(unit)
    db.session.commit()
    return unit


def _assign(org, user, role, unit, *, kind=AssignmentKind.REGULAR, acting_for=None,
            start=None, end=None, allowed_form_templates=None):
    row = UserRoleAssignment(
        org_secure_code=org.secure_code,
        user_secure_code=user.secure_code,
        role_secure_code=role.secure_code,
        unit_secure_code=unit.secure_code if unit else None,
        assignment_kind=kind,
        acting_for_user_secure_code=acting_for.secure_code if acting_for else None,
        valid_from=start,
        valid_until=end,
        allowed_form_templates=allowed_form_templates,
        is_deleted=False,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _proxy(org, delegator, delegate, role, unit, start, end, allowed_form_templates=None):
    return _assign(
        org,
        delegate,
        role,
        unit,
        kind=AssignmentKind.PROXY,
        acting_for=delegator,
        start=start,
        end=end,
        allowed_form_templates=allowed_form_templates,
    )


def _role_task(org, role, unit, form_instance_secure_code=None):
    task = FwNodeExecutionQueue(
        org_secure_code=org.secure_code,
        workflow_instance_secure_code=f'wfi_{role.secure_code[-8:]}',
        node_id=f'node_{role.secure_code[-8:]}',
        node_type='FormAdapter',
        status='WAITING',
        form_instance_secure_code=form_instance_secure_code,
        result={'data': {
            'assignee_type': 'ROLE',
            'assignee_value': role.secure_code,
            'assignee_unit_secure_code': unit.secure_code,
            'assignee_role_code': role.code,
            'assignee_role_type': role.role_type,
            'assignees': [],
        }},
    )
    db.session.add(task)
    db.session.commit()
    return task


def _waiting_task(org, assignees, assignee_type='USER', form_instance_secure_code=None):
    task = FwNodeExecutionQueue(
        org_secure_code=org.secure_code,
        workflow_instance_secure_code=f'wfi_{assignees[0][-12:]}',
        node_id=f'node_{assignees[0][-8:]}',
        node_type='FormAdapter',
        status='WAITING',
        form_instance_secure_code=form_instance_secure_code,
        result={'data': {
            'assignee_type': assignee_type,
            'assignee_value': assignees[0],
            'assignees': assignees,
        }},
    )
    db.session.add(task)
    db.session.commit()
    return task


def _form_template(org, secure_code, code, name):
    template = FwFormTemplate(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        code=code,
        name=name,
        schema={'components': []},
        is_published=True,
        is_deleted=False,
    )
    db.session.add(template)
    db.session.commit()
    return template


def _form_instance(org, secure_code, template):
    instance = FwFormInstance(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        form_template_secure_code=template.secure_code,
        form_data={},
        serial_number=f'SN-{secure_code}',
        is_deleted=False,
    )
    db.session.add(instance)
    db.session.commit()
    return instance


def _env(test_org):
    return (
        _unit(test_org),
        _role(test_org, 'ta_role_000000000000001', 'DEPT_MANAGER'),
    )


def test_self_assignment_resolves_self(test_org, test_user):
    task = _waiting_task(test_org, [test_user.secure_code])

    identity = resolve_acting_identity(
        task, test_user.secure_code, test_org.secure_code
    )

    assert identity['via'] == 'self'
    assert identity['delegator_secure_code'] is None
    assert can_act_on_task(task, test_user.secure_code, test_org.secure_code) is True


def test_proxy_resolves_delegator(test_org, test_user):
    today = test_org.local_today()
    unit, role = _env(test_org)
    boss = _user('boss_full_0000000000001', test_org, 'bossfull', 'Boss Full')
    _assign(test_org, boss, role, unit)
    _proxy(test_org, boss, test_user, role, unit, today - timedelta(days=1), today + timedelta(days=1))
    task = _role_task(test_org, role, unit)

    identity = resolve_acting_identity(task, test_user.secure_code, test_org.secure_code)

    assert identity == {
        'via': 'self',
        'delegator_secure_code': boss.secure_code,
        'acted_as_role_code': role.code,
        'acted_as_kind': 'proxy',
    }
    assert can_act_on_task(task, test_user.secure_code, test_org.secure_code) is True


def test_self_wins_when_self_and_proxy_both_match(test_org, test_user):
    today = test_org.local_today()
    unit, role = _env(test_org)
    boss = _user('boss_both_0000000000001', test_org, 'bossboth', 'Boss Both')
    _assign(test_org, boss, role, unit)
    _assign(test_org, test_user, role, unit)
    _proxy(test_org, boss, test_user, role, unit, today, today)
    task = _role_task(test_org, role, unit)

    identity = resolve_acting_identity(task, test_user.secure_code, test_org.secure_code)

    assert identity == {
        'via': 'self',
        'delegator_secure_code': None,
        'acted_as_role_code': None,
        'acted_as_kind': 'regular',
    }


def test_expired_proxy_does_not_authorize(test_org, test_user):
    today = test_org.local_today()
    unit, role = _env(test_org)
    boss = _user('boss_expired_0000000001', test_org, 'bossexpired', 'Boss Expired')
    _assign(test_org, boss, role, unit)
    _proxy(test_org, boss, test_user, role, unit, today - timedelta(days=2), today - timedelta(days=1))

    assert resolve_acting_identity(
        _role_task(test_org, role, unit), test_user.secure_code, test_org.secure_code
    ) is None


def test_specific_proxy_only_authorizes_allowed_form_template(test_org, test_user):
    today = test_org.local_today()
    unit, role = _env(test_org)
    boss = _user('boss_specific_000000001', test_org, 'bossspecific', 'Boss Specific')
    _assign(test_org, boss, role, unit)
    template_a = _form_template(test_org, 'ft_specific_a_000000001', 'FORM-A', 'Form A')
    template_b = _form_template(test_org, 'ft_specific_b_000000001', 'FORM-B', 'Form B')
    instance_a = _form_instance(test_org, 'fi_specific_a_000000001', template_a)
    instance_b = _form_instance(test_org, 'fi_specific_b_000000001', template_b)
    _proxy(test_org, boss, test_user, role, unit, today, today, [template_a.secure_code])

    task_a = _role_task(test_org, role, unit, instance_a.secure_code)
    task_b = _role_task(test_org, role, unit, instance_b.secure_code)
    task_without_instance = _role_task(test_org, role, unit)
    actor = build_actor(test_user.secure_code, test_org.secure_code)

    assert can_act_on_task(task_a, test_user.secure_code, test_org.secure_code, actor) is True
    assert can_act_on_task(task_b, test_user.secure_code, test_org.secure_code, actor) is False
    assert can_act_on_task(task_without_instance, test_user.secure_code, test_org.secure_code, actor) is False


def test_empty_scope_proxy_is_fail_closed_and_full_proxy_allows(test_org, test_user):
    today = test_org.local_today()
    unit, role = _env(test_org)
    boss = _user('boss_specific_full_00001', test_org, 'bossspecificfull', 'Boss Specific Full')
    _assign(test_org, boss, role, unit)
    template = _form_template(test_org, 'ft_specific_full_a_001', 'FORM-A2', 'Form A2')
    instance = _form_instance(test_org, 'fi_specific_full_a_001', template)
    task = _role_task(test_org, role, unit, instance.secure_code)

    _proxy(test_org, boss, test_user, role, unit, today, today, [])
    assert can_act_on_task(task, test_user.secure_code, test_org.secure_code,
                           build_actor(test_user.secure_code, test_org.secure_code)) is False

    _proxy(test_org, boss, test_user, role, unit, today, today, None)
    assert can_act_on_task(task, test_user.secure_code, test_org.secure_code,
                           build_actor(test_user.secure_code, test_org.secure_code)) is True


def test_specific_proxy_form_template_lookup_is_cached(test_org, test_user):
    today = test_org.local_today()
    unit, role = _env(test_org)
    boss = _user('boss_specific_cache_001', test_org, 'bossspecificcache', 'Boss Specific Cache')
    _assign(test_org, boss, role, unit)
    template = _form_template(test_org, 'ft_specific_cache_0001', 'FORM-CACHE', 'Form Cache')
    instance = _form_instance(test_org, 'fi_specific_cache_0001', template)
    _proxy(test_org, boss, test_user, role, unit, today, today, [template.secure_code])
    task = _role_task(test_org, role, unit, instance.secure_code)
    actor = build_actor(test_user.secure_code, test_org.secure_code)
    calls = {'count': 0}

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        if 'fw_form_instances' in statement.lower():
            calls['count'] += 1

    event.listen(db.engine, 'before_cursor_execute', before_cursor_execute)
    try:
        assert can_act_on_task(task, test_user.secure_code, test_org.secure_code, actor) is True
        assert can_act_on_task(task, test_user.secure_code, test_org.secure_code, actor) is True
    finally:
        event.remove(db.engine, 'before_cursor_execute', before_cursor_execute)

    assert calls['count'] == 1


def test_multiple_proxy_sources_use_assignment_order(test_org, test_user):
    today = test_org.local_today()
    unit, role = _env(test_org)
    boss_a = _user('boss_a_000000000000001', test_org, 'bossa', 'Boss A')
    boss_b = _user('boss_b_000000000000001', test_org, 'bossb', 'Boss B')
    _assign(test_org, boss_a, role, unit)
    _assign(test_org, boss_b, role, unit)
    _proxy(test_org, boss_b, test_user, role, unit, today, today)
    _proxy(test_org, boss_a, test_user, role, unit, today, today)
    task = _role_task(test_org, role, unit)

    first = resolve_acting_identity(task, test_user.secure_code, test_org.secure_code)
    second = resolve_acting_identity(task, test_user.secure_code, test_org.secure_code)

    assert first['delegator_secure_code'] == boss_b.secure_code
    assert second['delegator_secure_code'] == boss_b.secure_code


def test_delegate_from_fields_name_and_fallbacks(test_org):
    boss = _user('boss_fields_00000000001', test_org, 'bossfields', 'Boss Fields')

    assert delegate_from_fields(
        {'via': 'self', 'delegator_secure_code': None}, test_org.secure_code
    ) == {}

    fields = delegate_from_fields(
        {'via': 'self', 'delegator_secure_code': boss.secure_code},
        test_org.secure_code,
    )
    assert fields['delegate_from_secure_code'] == boss.secure_code
    assert fields['delegate_from_name'] == boss.display_name

    boss.is_active = False
    db.session.commit()
    inactive_fields = delegate_from_fields(
        {'via': 'self', 'delegator_secure_code': boss.secure_code},
        test_org.secure_code,
    )
    assert inactive_fields['delegate_from_name'] == boss.display_name

    missing_sc = 'missing_delegator_0000001'
    missing_fields = delegate_from_fields(
        {'via': 'self', 'delegator_secure_code': missing_sc},
        test_org.secure_code,
    )
    assert missing_fields['delegate_from_secure_code'] == missing_sc
    assert missing_fields['delegate_from_name'] == missing_sc


def test_missing_assignee_type_allows_action_but_is_not_pending_assignee(test_org, test_user):
    task = FwNodeExecutionQueue(
        org_secure_code=test_org.secure_code,
        workflow_instance_secure_code='wfi_open_assignee',
        node_id='node_open',
        node_type='FormAdapter',
        status='WAITING',
        result={'data': {'assignees': []}},
    )
    db.session.add(task)
    db.session.commit()

    identity = resolve_acting_identity(
        task, test_user.secure_code, test_org.secure_code
    )

    assert identity == {
        'via': 'self',
        'delegator_secure_code': None,
        'acted_as_role_code': None,
        'acted_as_kind': None,
    }
    assert is_pending_assignee(task, test_user.secure_code, test_org.secure_code) is False
