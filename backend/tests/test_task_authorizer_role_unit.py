import sys
from datetime import timedelta
from pathlib import Path

from sqlalchemy import event

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db  # noqa: E402
from app.models import (  # noqa: E402
    Delegation,
    DelegationStatus,
    DelegationType,
    MembershipType,
    Organization,
    OrganizationalUnit,
    Role,
    RoleType,
    UnitType,
    User,
    UserRoleAssignment,
    UserType,
    UserUnitMembership,
)
from app.services.unit_resolver import get_unit_ancestor_codes, resolve_user_unit  # noqa: E402
from modules.form_workflow.models import FwNodeExecutionQueue  # noqa: E402
from modules.form_workflow.services.task_authorizer import (  # noqa: E402
    build_actor,
    can_act_on_task,
    resolve_acting_identity,
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


def _assign(user, role, unit=None, valid_from=None, valid_until=None):
    row = UserRoleAssignment(
        user_secure_code=user.secure_code,
        role_secure_code=role.secure_code,
        org_secure_code=user.org_secure_code,
        unit_secure_code=unit.secure_code if unit else None,
        valid_from=valid_from,
        valid_until=valid_until,
        is_deleted=False,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _task(org, data, form_instance_secure_code=None):
    task = FwNodeExecutionQueue(
        org_secure_code=org.secure_code,
        workflow_instance_secure_code=f'wfi_{id(data)}',
        node_id=f'node_{id(data)}',
        node_type='FormAdapter',
        status='WAITING',
        form_instance_secure_code=form_instance_secure_code,
        result={'data': data},
    )
    db.session.add(task)
    db.session.commit()
    return task


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


def _role_unit_env(org):
    info = _unit(org, 'INFO', '資訊群')
    sw = _unit(org, 'SW', '軟體部', info)
    sw1 = _unit(org, 'SW1', '軟體一課', sw)
    mkt = _unit(org, 'MKT', '行銷部門')
    roles = {
        'member': _role(org, 'DEPT_MEMBER'),
        'manager': _role(org, 'DEPT_MANAGER', RoleType.POSITION),
        'deputy': _role(org, 'DEPT_DEPUTY', RoleType.POSITION),
        'proxy1': _role(org, 'DEPT_PROXY1', RoleType.POSITION),
        'proxy2': _role(org, 'DEPT_PROXY2', RoleType.POSITION),
    }
    return {'info': info, 'sw': sw, 'sw1': sw1, 'mkt': mkt, **roles}


def _role_task(org, role, unit, role_type='ROLE', absence_fallback=None):
    data = {
        'assignee_type': 'ROLE',
        'assignee_value': role.secure_code,
        'assignee_unit_secure_code': unit.secure_code,
        'assignee_role_code': role.code,
        'assignee_role_type': role_type,
        'assignees': [],
    }
    if absence_fallback is not None:
        data['absence_fallback'] = absence_fallback
    return _task(org, data)


def test_direct_role_unit_match_is_unit_specific(test_org):
    env = _role_unit_env(test_org)
    marketing_mgr = _user('ru_mkt_mgr', test_org, 'rumktmgr', 'Marketing Manager')
    software_mgr = _user('ru_sw_mgr', test_org, 'ruswmgr', 'Software Manager')
    outsider = _user('ru_none', test_org, 'runone', 'No Role')
    _assign(marketing_mgr, env['manager'], env['mkt'])
    _assign(software_mgr, env['manager'], env['sw'])
    task = _role_task(test_org, env['manager'], env['mkt'], RoleType.POSITION)

    identity = resolve_acting_identity(task, marketing_mgr.secure_code, test_org.secure_code)

    assert identity == {
        'via': 'self',
        'delegator_secure_code': None,
        'acted_as_role_code': None,
    }
    assert resolve_acting_identity(task, software_mgr.secure_code, test_org.secure_code) is None
    assert resolve_acting_identity(task, outsider.secure_code, test_org.secure_code) is None


def test_global_role_assignment_is_superset_for_unit_task(test_org):
    env = _role_unit_env(test_org)
    global_mgr = _user('ru_global_mgr', test_org, 'ruglobalmgr', 'Global Manager')
    _assign(global_mgr, env['manager'])
    task = _role_task(test_org, env['manager'], env['mkt'], RoleType.POSITION)

    assert can_act_on_task(task, global_mgr.secure_code, test_org.secure_code) is True


def test_legacy_role_queue_keeps_flat_role_behavior(test_org):
    env = _role_unit_env(test_org)
    software_mgr = _user('ru_legacy_mgr', test_org, 'rulegacymgr', 'Legacy Manager')
    snapshot_user = _user('ru_snapshot', test_org, 'rusnapshot', 'Snapshot User')
    outsider = _user('ru_legacy_none', test_org, 'rulegacynone', 'Legacy None')
    _assign(software_mgr, env['manager'], env['sw'])
    task = _task(test_org, {
        'assignee_type': 'ROLE',
        'assignee_value': env['manager'].secure_code,
        'assignees': [snapshot_user.secure_code],
    })

    assert can_act_on_task(task, software_mgr.secure_code, test_org.secure_code) is True
    assert can_act_on_task(task, snapshot_user.secure_code, test_org.secure_code) is True
    assert resolve_acting_identity(task, outsider.secure_code, test_org.secure_code) is None

    actor = {
        'user_sc': outsider.secure_code,
        'role_codes': {env['manager'].secure_code},
        'delegations': {},
    }
    assert can_act_on_task(task, outsider.secure_code, test_org.secure_code, actor) is True


def test_role_unit_bubbles_from_descendant_units(test_org):
    env = _role_unit_env(test_org)
    sw_member = _user('ru_sw_member', test_org, 'ruswmember', 'Software Member')
    sw1_member = _user('ru_sw1_member', test_org, 'rusw1member', 'Software One Member')
    mkt_member = _user('ru_mkt_member', test_org, 'rumktmember', 'Marketing Member')
    info_member = _user('ru_info_member', test_org, 'ruinfomember', 'Info Member')
    _assign(sw_member, env['member'], env['sw'])
    _assign(sw1_member, env['member'], env['sw1'])
    _assign(mkt_member, env['member'], env['mkt'])
    _assign(info_member, env['member'], env['info'])
    task = _role_task(test_org, env['member'], env['info'], RoleType.ROLE)

    results = {
        'child': can_act_on_task(task, sw_member.secure_code, test_org.secure_code),
        'grandchild': can_act_on_task(task, sw1_member.secure_code, test_org.secure_code),
        'other': resolve_acting_identity(task, mkt_member.secure_code, test_org.secure_code),
        'self': can_act_on_task(task, info_member.secure_code, test_org.secure_code),
    }
    assert results == {'child': True, 'grandchild': True, 'other': None, 'self': True}


def test_position_role_does_not_bubble_to_parent_unit(test_org):
    env = _role_unit_env(test_org)
    software_mgr = _user('ru_pos_sw_mgr', test_org, 'ruposswmgr', 'Software Position')
    _assign(software_mgr, env['manager'], env['sw'])
    task = _role_task(test_org, env['manager'], env['info'], RoleType.POSITION)

    assert resolve_acting_identity(task, software_mgr.secure_code, test_org.secure_code) is None


def test_deputy_can_always_act_for_department_manager(test_org):
    env = _role_unit_env(test_org)
    manager = _user('ru_dep_mgr', test_org, 'rudepmgr', 'Manager')
    deputy = _user('ru_deputy', test_org, 'rudeputy', 'Deputy')
    _assign(manager, env['manager'], env['mkt'])
    _assign(deputy, env['deputy'], env['mkt'])
    task = _role_task(test_org, env['manager'], env['mkt'], RoleType.POSITION)

    identity = resolve_acting_identity(task, deputy.secure_code, test_org.secure_code)

    assert identity['acted_as_role_code'] == 'DEPT_DEPUTY'


def test_proxy_roles_require_manager_vacancy(test_org):
    env = _role_unit_env(test_org)
    manager = _user('ru_proxy_mgr', test_org, 'ruproxymgr', 'Manager')
    proxy1 = _user('ru_proxy1', test_org, 'ruproxy1', 'Proxy 1')
    proxy2 = _user('ru_proxy2', test_org, 'ruproxy2', 'Proxy 2')
    manager_assignment = _assign(manager, env['manager'], env['mkt'])
    _assign(proxy1, env['proxy1'], env['mkt'])
    _assign(proxy2, env['proxy2'], env['mkt'])
    task = _role_task(test_org, env['manager'], env['mkt'], RoleType.POSITION)

    assert resolve_acting_identity(task, proxy1.secure_code, test_org.secure_code) is None
    assert resolve_acting_identity(task, proxy2.secure_code, test_org.secure_code) is None

    manager_assignment.is_deleted = True
    db.session.commit()

    proxy1_identity = resolve_acting_identity(task, proxy1.secure_code, test_org.secure_code)
    proxy2_identity = resolve_acting_identity(task, proxy2.secure_code, test_org.secure_code)
    assert proxy1_identity['acted_as_role_code'] == 'DEPT_PROXY1'
    assert proxy2_identity['acted_as_role_code'] == 'DEPT_PROXY2'


def test_manager_presence_checks_active_user_validity_and_global_assignment(test_org):
    env = _role_unit_env(test_org)
    today = test_org.local_today()
    manager = _user('ru_presence_mgr', test_org, 'rupresencemgr', 'Manager')
    proxy1 = _user('ru_presence_p1', test_org, 'rupresencep1', 'Proxy 1')
    manager_assignment = _assign(manager, env['manager'], env['mkt'])
    _assign(proxy1, env['proxy1'], env['mkt'])
    task = _role_task(test_org, env['manager'], env['mkt'], RoleType.POSITION)

    manager.is_active = False
    db.session.commit()
    assert resolve_acting_identity(
        task, proxy1.secure_code, test_org.secure_code
    )['acted_as_role_code'] == 'DEPT_PROXY1'

    manager.is_active = True
    manager_assignment.valid_until = today - timedelta(days=1)
    db.session.commit()
    assert resolve_acting_identity(
        task, proxy1.secure_code, test_org.secure_code
    )['acted_as_role_code'] == 'DEPT_PROXY1'

    manager_assignment.unit_secure_code = None
    manager_assignment.valid_until = None
    db.session.commit()
    assert resolve_acting_identity(task, proxy1.secure_code, test_org.secure_code) is None


def test_fallback_can_be_disabled_and_legacy_data_does_not_fallback(test_org):
    env = _role_unit_env(test_org)
    deputy = _user('ru_fb_deputy', test_org, 'rufbdeputy', 'Deputy')
    _assign(deputy, env['deputy'], env['mkt'])
    disabled = _role_task(
        test_org, env['manager'], env['mkt'], RoleType.POSITION, absence_fallback=False)
    legacy = _task(test_org, {
        'assignee_type': 'ROLE',
        'assignee_value': env['manager'].secure_code,
        'assignee_unit_secure_code': env['mkt'].secure_code,
        'assignees': [],
    })

    assert resolve_acting_identity(disabled, deputy.secure_code, test_org.secure_code) is None
    assert resolve_acting_identity(legacy, deputy.secure_code, test_org.secure_code) is None


def test_deputy_in_other_department_does_not_match(test_org):
    env = _role_unit_env(test_org)
    deputy = _user('ru_other_deputy', test_org, 'ruotherdeputy', 'Other Deputy')
    _assign(deputy, env['deputy'], env['sw'])
    task = _role_task(test_org, env['manager'], env['mkt'], RoleType.POSITION)

    assert resolve_acting_identity(task, deputy.secure_code, test_org.secure_code) is None


def test_delegation_uses_role_unit_identity_and_fallback(test_org, test_user):
    env = _role_unit_env(test_org)
    today = test_org.local_today()
    delegator = _user('ru_delegator', test_org, 'rudelegator', 'Delegator')
    _assign(delegator, env['manager'], env['mkt'])
    _delegation(test_org, delegator, test_user, today, today)
    task = _role_task(test_org, env['manager'], env['mkt'], RoleType.POSITION)

    manager_identity = resolve_acting_identity(
        task, test_user.secure_code, test_org.secure_code)
    assert manager_identity == {
        'via': 'delegation',
        'delegator_secure_code': delegator.secure_code,
        'acted_as_role_code': None,
    }

    UserRoleAssignment.query.filter_by(user_secure_code=delegator.secure_code).delete()
    manager = _user('ru_delegate_mgr', test_org, 'rudelegatemgr', 'Manager')
    _assign(manager, env['manager'], env['mkt'])
    _assign(delegator, env['deputy'], env['mkt'])
    db.session.commit()

    deputy_identity = resolve_acting_identity(
        task, test_user.secure_code, test_org.secure_code)
    assert deputy_identity['via'] == 'delegation'
    assert deputy_identity['acted_as_role_code'] == 'DEPT_DEPUTY'


def test_department_assignee_is_dept_member_alias(test_org):
    env = _role_unit_env(test_org)
    old_member = _user('ru_old_member', test_org, 'ruoldmember', 'Old Member')
    current_member = _user('ru_current_member', test_org, 'rucurrentmember', 'Current Member')
    outsider = _user('ru_dept_none', test_org, 'rudeptnone', 'Department None')
    _assign(current_member, env['member'], env['sw'])
    task = _task(test_org, {
        'assignee_type': 'DEPARTMENT',
        'assignee_value': env['info'].secure_code,
        'assignees': [old_member.secure_code],
    })

    assert can_act_on_task(task, old_member.secure_code, test_org.secure_code) is True
    assert can_act_on_task(task, current_member.secure_code, test_org.secure_code) is True
    assert resolve_acting_identity(task, outsider.secure_code, test_org.secure_code) is None

    org2 = Organization(
        secure_code='ru_org2',
        code='RU_ORG2',
        name='Role Unit Org 2',
        domain_name='role-unit-2.local',
        is_active=True,
        is_deleted=False,
    )
    db.session.add(org2)
    db.session.commit()
    unit2 = _unit(org2, 'INFO2', 'Second Info')
    member2 = _user('ru_org2_member', org2, 'ruorg2member', 'Org2 Member')
    org2_task = _task(org2, {
        'assignee_type': 'DEPARTMENT',
        'assignee_value': unit2.secure_code,
        'assignees': [],
    })

    assert resolve_acting_identity(org2_task, member2.secure_code, org2.secure_code) is None


def test_resolve_user_unit_prefers_solid_primary_then_earliest(test_org, test_user):
    env = _role_unit_env(test_org)
    today = test_org.local_today()
    _membership(test_user, env['mkt'], start_date=today)

    assert resolve_user_unit(test_user.secure_code, test_org.secure_code, today) == env['mkt'].secure_code

    _membership(test_user, env['sw'], start_date=today - timedelta(days=2))
    test_user.primary_unit_secure_code = env['mkt'].secure_code
    db.session.commit()
    assert resolve_user_unit(test_user.secure_code, test_org.secure_code, today) == env['mkt'].secure_code

    test_user.primary_unit_secure_code = None
    db.session.commit()
    assert resolve_user_unit(test_user.secure_code, test_org.secure_code, today) == env['sw'].secure_code

    UserUnitMembership.query.filter_by(user_secure_code=test_user.secure_code).delete()
    db.session.commit()
    _membership(
        test_user, env['mkt'], start_date=today - timedelta(days=4),
        end_date=today - timedelta(days=1))
    _membership(test_user, env['info'], membership_type=MembershipType.DOTTED)
    # EmployeePosition fallback needs JobFamily/JobLevel/JobTitle setup and is covered in PF-247 phase 4.
    assert resolve_user_unit(test_user.secure_code, test_org.secure_code, today) is None

    org2 = Organization(
        secure_code='ru_resolver_org2',
        code='RU_RESOLVER_ORG2',
        name='Resolver Org 2',
        domain_name='resolver-org-2.local',
        is_active=True,
        is_deleted=False,
    )
    db.session.add(org2)
    db.session.commit()
    unit2 = _unit(org2, 'OTHER', 'Other Org')
    other_user = _user('ru_resolver_user2', org2, 'ruresolveruser2', 'Other User')
    _membership(other_user, unit2)
    cross_org_membership = UserUnitMembership(
        org_secure_code=org2.secure_code,
        user_secure_code=test_user.secure_code,
        unit_secure_code=unit2.secure_code,
        membership_type=MembershipType.SOLID,
        start_date=today - timedelta(days=1),
        is_deleted=False,
    )
    db.session.add(cross_org_membership)
    db.session.commit()
    assert resolve_user_unit(test_user.secure_code, test_org.secure_code, today) is None

    empty_user = _user('ru_resolver_empty', test_org, 'ruresolverempty', 'Empty User')
    assert resolve_user_unit(empty_user.secure_code, test_org.secure_code, today) is None


def test_get_unit_ancestor_codes_handles_deleted_and_missing_units(test_org):
    env = _role_unit_env(test_org)

    assert get_unit_ancestor_codes(env['sw1'].secure_code, test_org.secure_code) == [
        env['sw'].secure_code,
        env['info'].secure_code,
    ]
    assert get_unit_ancestor_codes(env['info'].secure_code, test_org.secure_code) == []
    assert get_unit_ancestor_codes('missing_unit_sc', test_org.secure_code) == []

    env['sw'].is_deleted = True
    db.session.commit()
    assert get_unit_ancestor_codes(env['sw1'].secure_code, test_org.secure_code) == []


def test_unit_ancestor_lookup_is_cached_in_actor(test_org):
    env = _role_unit_env(test_org)
    member = _user('ru_cache_member', test_org, 'rucachemember', 'Cache Member')
    _assign(member, env['member'], env['sw1'])
    actor = build_actor(member.secure_code, test_org.secure_code)
    tasks = [
        _role_task(test_org, env['member'], env['info'], RoleType.ROLE),
        _role_task(test_org, env['member'], env['info'], RoleType.ROLE),
        _role_task(test_org, env['member'], env['info'], RoleType.ROLE),
    ]
    calls = {'count': 0}

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        del conn, cursor, parameters, context, executemany
        if 'organizational_units' in statement.lower():
            calls['count'] += 1

    event.listen(db.engine, 'before_cursor_execute', before_cursor_execute)
    try:
        assert can_act_on_task(tasks[0], member.secure_code, test_org.secure_code, actor) is True
        first_count = calls['count']
        assert can_act_on_task(tasks[1], member.secure_code, test_org.secure_code, actor) is True
        assert can_act_on_task(tasks[2], member.secure_code, test_org.secure_code, actor) is True
    finally:
        event.remove(db.engine, 'before_cursor_execute', before_cursor_execute)

    assert first_count > 0
    assert calls['count'] == first_count


def test_deputy_in_snapshot_still_records_acted_as(test_org):
    """第 2 期起快照含副主管；快照命中不得蓋掉 acted_as_role_code（第 3 期驗收踩到）。"""
    env = _role_unit_env(test_org)
    manager = _user('ru_snap_mgr', test_org, 'rusnapmgr', 'Manager')
    deputy = _user('ru_snap_deputy', test_org, 'rusnapdeputy', 'Deputy')
    _assign(manager, env['manager'], env['mkt'])
    _assign(deputy, env['deputy'], env['mkt'])
    task = _task(test_org, {
        'assignee_type': 'ROLE',
        'assignee_value': env['manager'].secure_code,
        'assignee_unit_secure_code': env['mkt'].secure_code,
        'assignee_role_type': RoleType.POSITION,
        'assignees': [manager.secure_code, deputy.secure_code],
    })

    manager_identity = resolve_acting_identity(task, manager.secure_code, test_org.secure_code)
    deputy_identity = resolve_acting_identity(task, deputy.secure_code, test_org.secure_code)

    assert manager_identity['acted_as_role_code'] is None
    assert deputy_identity['acted_as_role_code'] == 'DEPT_DEPUTY'
