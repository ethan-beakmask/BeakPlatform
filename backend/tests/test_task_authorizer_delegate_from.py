from datetime import timedelta
import sys
from pathlib import Path

from sqlalchemy import event

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db
from app.models import Delegation, DelegationStatus, DelegationType, User, UserType
from modules.form_workflow.models import FwFormInstance, FwFormTemplate, FwNodeExecutionQueue
from modules.form_workflow.services.task_authorizer import (
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


def _delegation(org, delegator, delegate, start, end,
                delegation_type=DelegationType.FULL, allowed_form_templates=None):
    row = Delegation(
        org_secure_code=org.secure_code,
        delegator_secure_code=delegator.secure_code,
        delegate_secure_code=delegate.secure_code,
        delegation_type=delegation_type,
        effective_from=start,
        effective_until=end,
        status=DelegationStatus.ACTIVE,
        created_by='test',
    )
    row.set_allowed_form_templates(allowed_form_templates or [])
    db.session.add(row)
    db.session.commit()
    return row


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


def test_self_assignment_resolves_self(test_org, test_user):
    task = _waiting_task(test_org, [test_user.secure_code])

    identity = resolve_acting_identity(
        task, test_user.secure_code, test_org.secure_code
    )

    assert identity['via'] == 'self'
    assert identity['delegator_secure_code'] is None
    assert can_act_on_task(task, test_user.secure_code, test_org.secure_code) is True


def test_full_delegation_resolves_delegator(test_org, test_user):
    today = test_org.local_today()
    boss = _user('boss_full_0000000000001', test_org, 'bossfull', 'Boss Full')
    _delegation(
        test_org, boss, test_user, today - timedelta(days=1), today + timedelta(days=1)
    )
    task = _waiting_task(test_org, [boss.secure_code])

    identity = resolve_acting_identity(
        task, test_user.secure_code, test_org.secure_code
    )

    assert identity['via'] == 'delegation'
    assert identity['delegator_secure_code'] == boss.secure_code
    assert can_act_on_task(task, test_user.secure_code, test_org.secure_code) is True


def test_self_wins_when_self_and_delegator_both_match(test_org, test_user):
    today = test_org.local_today()
    boss = _user('boss_both_0000000000001', test_org, 'bossboth', 'Boss Both')
    _delegation(test_org, boss, test_user, today, today)
    task = _waiting_task(test_org, [test_user.secure_code, boss.secure_code])

    identity = resolve_acting_identity(
        task, test_user.secure_code, test_org.secure_code
    )

    assert identity == {
        'via': 'self',
        'delegator_secure_code': None,
        'acted_as_role_code': None,
        'acted_as_kind': None,
    }


def test_expired_delegation_does_not_authorize(test_org, test_user):
    today = test_org.local_today()
    expired_boss = _user('boss_expired_0000000001', test_org, 'bossexpired', 'Boss Expired')
    _delegation(
        test_org,
        expired_boss,
        test_user,
        today - timedelta(days=2),
        today - timedelta(days=1),
    )

    expired_task = _waiting_task(test_org, [expired_boss.secure_code])

    assert resolve_acting_identity(
        expired_task, test_user.secure_code, test_org.secure_code
    ) is None


def test_specific_delegation_only_authorizes_allowed_form_template(test_org, test_user):
    today = test_org.local_today()
    boss = _user('boss_specific_000000001', test_org, 'bossspecific', 'Boss Specific')
    template_a = _form_template(test_org, 'ft_specific_a_000000001', 'FORM-A', 'Form A')
    template_b = _form_template(test_org, 'ft_specific_b_000000001', 'FORM-B', 'Form B')
    instance_a = _form_instance(test_org, 'fi_specific_a_000000001', template_a)
    instance_b = _form_instance(test_org, 'fi_specific_b_000000001', template_b)
    _delegation(
        test_org, boss, test_user, today, today,
        DelegationType.SPECIFIC, [template_a.secure_code],
    )

    task_a = _waiting_task(test_org, [boss.secure_code],
                           form_instance_secure_code=instance_a.secure_code)
    task_b = _waiting_task(test_org, [boss.secure_code],
                           form_instance_secure_code=instance_b.secure_code)
    task_without_instance = _waiting_task(test_org, [boss.secure_code])
    actor = build_actor(test_user.secure_code, test_org.secure_code)

    assert can_act_on_task(task_a, test_user.secure_code, test_org.secure_code, actor) is True
    assert can_act_on_task(task_b, test_user.secure_code, test_org.secure_code, actor) is False
    assert can_act_on_task(
        task_without_instance, test_user.secure_code, test_org.secure_code, actor
    ) is False


def test_specific_empty_scope_is_ignored_and_full_overrides_scope(test_org, test_user):
    today = test_org.local_today()
    boss = _user('boss_specific_full_00001', test_org, 'bossspecificfull', 'Boss Specific Full')
    template_a = _form_template(test_org, 'ft_specific_full_a_001', 'FORM-A2', 'Form A2')
    template_b = _form_template(test_org, 'ft_specific_full_b_001', 'FORM-B2', 'Form B2')
    instance_a = _form_instance(test_org, 'fi_specific_full_a_001', template_a)
    instance_b = _form_instance(test_org, 'fi_specific_full_b_001', template_b)
    task_a = _waiting_task(test_org, [boss.secure_code],
                           form_instance_secure_code=instance_a.secure_code)
    task_b = _waiting_task(test_org, [boss.secure_code],
                           form_instance_secure_code=instance_b.secure_code)

    _delegation(test_org, boss, test_user, today, today, DelegationType.SPECIFIC, [])
    actor = build_actor(test_user.secure_code, test_org.secure_code)

    assert can_act_on_task(task_a, test_user.secure_code, test_org.secure_code, actor) is False
    assert can_act_on_task(task_b, test_user.secure_code, test_org.secure_code, actor) is False

    _delegation(test_org, boss, test_user, today, today, DelegationType.FULL)
    actor = build_actor(test_user.secure_code, test_org.secure_code)

    assert can_act_on_task(task_a, test_user.secure_code, test_org.secure_code, actor) is True
    assert can_act_on_task(task_b, test_user.secure_code, test_org.secure_code, actor) is True


def test_specific_delegation_form_template_lookup_is_cached(test_org, test_user):
    today = test_org.local_today()
    boss = _user('boss_specific_cache_001', test_org, 'bossspecificcache', 'Boss Specific Cache')
    template = _form_template(test_org, 'ft_specific_cache_0001', 'FORM-CACHE', 'Form Cache')
    instance = _form_instance(test_org, 'fi_specific_cache_0001', template)
    _delegation(
        test_org, boss, test_user, today, today,
        DelegationType.SPECIFIC, [template.secure_code],
    )
    task = _waiting_task(test_org, [boss.secure_code],
                         form_instance_secure_code=instance.secure_code)
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


def test_legacy_actor_shape_treats_delegations_as_unscoped(test_org, test_user):
    today = test_org.local_today()
    boss = _user('boss_legacy_actor_0001', test_org, 'bosslegacyactor', 'Boss Legacy Actor')
    _delegation(test_org, boss, test_user, today, today)
    task = _waiting_task(test_org, [boss.secure_code])
    actor = {
        'user_sc': test_user.secure_code,
        'role_codes': set(),
        'delegations': {boss.secure_code: set()},
    }

    assert can_act_on_task(task, test_user.secure_code, test_org.secure_code, actor) is True


def test_multiple_delegators_are_resolved_by_secure_code_order(test_org, test_user):
    today = test_org.local_today()
    boss_a = _user('boss_a_000000000000001', test_org, 'bossa', 'Boss A')
    boss_b = _user('boss_b_000000000000001', test_org, 'bossb', 'Boss B')
    _delegation(test_org, boss_b, test_user, today, today)
    _delegation(test_org, boss_a, test_user, today, today)
    task = _waiting_task(test_org, [boss_b.secure_code, boss_a.secure_code])

    first = resolve_acting_identity(task, test_user.secure_code, test_org.secure_code)
    second = resolve_acting_identity(task, test_user.secure_code, test_org.secure_code)

    assert first['delegator_secure_code'] == boss_a.secure_code
    assert second['delegator_secure_code'] == boss_a.secure_code


def test_delegate_from_fields_name_and_fallbacks(test_org):
    boss = _user('boss_fields_00000000001', test_org, 'bossfields', 'Boss Fields')

    assert delegate_from_fields(
        {'via': 'self', 'delegator_secure_code': None}, test_org.secure_code
    ) == {}

    fields = delegate_from_fields(
        {'via': 'delegation', 'delegator_secure_code': boss.secure_code},
        test_org.secure_code,
    )
    assert fields['delegate_from_secure_code'] == boss.secure_code
    assert fields['delegate_from_name'] == boss.display_name

    boss.is_active = False
    db.session.commit()
    inactive_fields = delegate_from_fields(
        {'via': 'delegation', 'delegator_secure_code': boss.secure_code},
        test_org.secure_code,
    )
    assert inactive_fields['delegate_from_name'] == boss.display_name

    missing_sc = 'missing_delegator_0000001'
    missing_fields = delegate_from_fields(
        {'via': 'delegation', 'delegator_secure_code': missing_sc},
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
