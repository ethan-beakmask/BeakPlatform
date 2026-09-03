from datetime import timedelta
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db
from app.models import Delegation, DelegationStatus, DelegationType, User, UserType
from modules.form_workflow.models import FwNodeExecutionQueue
from modules.form_workflow.services.task_authorizer import (
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
                delegation_type=DelegationType.FULL):
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
    db.session.add(row)
    db.session.commit()
    return row


def _waiting_task(org, assignees, assignee_type='USER'):
    task = FwNodeExecutionQueue(
        org_secure_code=org.secure_code,
        workflow_instance_secure_code=f'wfi_{assignees[0][-12:]}',
        node_id=f'node_{assignees[0][-8:]}',
        node_type='FormAdapter',
        status='WAITING',
        result={'data': {
            'assignee_type': assignee_type,
            'assignee_value': assignees[0],
            'assignees': assignees,
        }},
    )
    db.session.add(task)
    db.session.commit()
    return task


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

    assert identity == {'via': 'self', 'delegator_secure_code': None}


def test_specific_and_expired_delegations_do_not_authorize(test_org, test_user):
    today = test_org.local_today()
    specific_boss = _user('boss_specific_000000001', test_org, 'bossspecific', 'Boss Specific')
    expired_boss = _user('boss_expired_0000000001', test_org, 'bossexpired', 'Boss Expired')
    _delegation(test_org, specific_boss, test_user, today, today, DelegationType.SPECIFIC)
    _delegation(
        test_org,
        expired_boss,
        test_user,
        today - timedelta(days=2),
        today - timedelta(days=1),
    )

    specific_task = _waiting_task(test_org, [specific_boss.secure_code])
    expired_task = _waiting_task(test_org, [expired_boss.secure_code])

    assert resolve_acting_identity(
        specific_task, test_user.secure_code, test_org.secure_code
    ) is None
    assert can_act_on_task(specific_task, test_user.secure_code, test_org.secure_code) is False
    assert resolve_acting_identity(
        expired_task, test_user.secure_code, test_org.secure_code
    ) is None


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

    assert identity == {'via': 'self', 'delegator_secure_code': None}
    assert is_pending_assignee(task, test_user.secure_code, test_org.secure_code) is False
