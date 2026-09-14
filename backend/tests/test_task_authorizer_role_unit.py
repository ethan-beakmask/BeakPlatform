import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import event

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db  # noqa: E402
from app.models import (  # noqa: E402
    MembershipType,
    Organization,
    OrganizationalUnit,
    Role,
    RoleType,
    ScheduleAdjustment,
    UnitType,
    User,
    AssignmentKind,
    UserRoleAssignment,
    UserType,
    UserUnitMembership,
)
from app.services.unit_resolver import get_unit_ancestor_codes, resolve_user_unit  # noqa: E402
from modules.form_workflow.models import FwFormInstance, FwFormTemplate, FwNodeExecutionQueue  # noqa: E402
from modules.form_workflow.services.task_authorizer import (  # noqa: E402
    build_actor,
    can_act_on_task,
    delegate_from_fields,
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


def _assign(
    user,
    role,
    unit=None,
    valid_from=None,
    valid_until=None,
    *,
    kind='regular',
    acting_for=None,
    allowed_form_templates=None,
):
    row = UserRoleAssignment(
        user_secure_code=user.secure_code,
        role_secure_code=role.secure_code,
        org_secure_code=user.org_secure_code,
        unit_secure_code=unit.secure_code if unit else None,
        valid_from=valid_from,
        valid_until=valid_until,
        assignment_kind=kind,
        acting_for_user_secure_code=acting_for.secure_code if acting_for else None,
        allowed_form_templates=allowed_form_templates,
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
        'head': _role(org, 'DEPT_HEAD', RoleType.POSITION),
        'manager': _role(org, 'DEPT_MANAGER', RoleType.POSITION),
        'deputy': _role(org, 'DEPT_DEPUTY', RoleType.POSITION),
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
        'acted_as_kind': 'regular',
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


def test_head_role_allows_manager_and_deputy_without_manager_fallback(test_org):
    env = _role_unit_env(test_org)
    manager = _user('ru_dep_mgr', test_org, 'rudepmgr', 'Manager')
    deputy = _user('ru_deputy', test_org, 'rudeputy', 'Deputy')
    _assign(manager, env['manager'], env['mkt'])
    _assign(manager, env['head'], env['mkt'])
    _assign(deputy, env['deputy'], env['mkt'])
    _assign(deputy, env['head'], env['mkt'])
    head_task = _role_task(test_org, env['head'], env['mkt'], RoleType.POSITION)
    manager_task = _role_task(test_org, env['manager'], env['mkt'], RoleType.POSITION)

    manager_identity = resolve_acting_identity(head_task, manager.secure_code, test_org.secure_code)
    deputy_identity = resolve_acting_identity(head_task, deputy.secure_code, test_org.secure_code)

    assert manager_identity['acted_as_kind'] == 'regular'
    assert manager_identity['acted_as_role_code'] is None
    assert manager_identity['delegator_secure_code'] is None
    assert deputy_identity['acted_as_kind'] == 'regular'
    assert deputy_identity['acted_as_role_code'] is None
    assert deputy_identity['delegator_secure_code'] is None
    assert resolve_acting_identity(manager_task, deputy.secure_code, test_org.secure_code) is None


def test_standby_role_requires_no_available_regular_or_proxy_holder(test_org):
    env = _role_unit_env(test_org)
    manager = _user('ru_proxy_mgr', test_org, 'ruproxymgr', 'Manager')
    standby = _user('ru_proxy1', test_org, 'ruproxy1', 'Standby')
    manager_assignment = _assign(manager, env['manager'], env['mkt'])
    _assign(standby, env['manager'], env['mkt'], kind='standby')
    task = _role_task(test_org, env['manager'], env['mkt'], RoleType.POSITION)

    assert resolve_acting_identity(task, standby.secure_code, test_org.secure_code) is None

    manager_assignment.is_deleted = True
    db.session.commit()

    identity = resolve_acting_identity(task, standby.secure_code, test_org.secure_code)
    assert identity['acted_as_kind'] == 'standby'
    assert identity['acted_as_role_code'] == 'DEPT_MANAGER'


def test_manager_presence_checks_active_user_validity_and_global_assignment(test_org):
    env = _role_unit_env(test_org)
    today = test_org.local_today()
    manager = _user('ru_presence_mgr', test_org, 'rupresencemgr', 'Manager')
    standby = _user('ru_presence_p1', test_org, 'rupresencep1', 'Standby')
    manager_assignment = _assign(manager, env['manager'], env['mkt'])
    _assign(standby, env['manager'], env['mkt'], kind='standby')
    task = _role_task(test_org, env['manager'], env['mkt'], RoleType.POSITION)

    manager.is_active = False
    db.session.commit()
    assert resolve_acting_identity(
        task, standby.secure_code, test_org.secure_code
    )['acted_as_kind'] == 'standby'

    manager.is_active = True
    manager_assignment.valid_until = today - timedelta(days=1)
    db.session.commit()
    assert resolve_acting_identity(
        task, standby.secure_code, test_org.secure_code
    )['acted_as_kind'] == 'standby'

    manager_assignment.unit_secure_code = None
    manager_assignment.valid_until = None
    db.session.commit()
    assert resolve_acting_identity(task, standby.secure_code, test_org.secure_code) is None


def test_absence_fallback_config_no_longer_changes_role_holding(test_org):
    env = _role_unit_env(test_org)
    manager = _user('ru_fb_mgr', test_org, 'rufbmgr', 'Manager')
    deputy = _user('ru_fb_deputy', test_org, 'rufbdeputy', 'Deputy')
    standby = _user('ru_fb_standby', test_org, 'rufbstandby', 'Standby')
    manager_assignment = _assign(manager, env['manager'], env['mkt'])
    _assign(deputy, env['deputy'], env['mkt'])
    _assign(standby, env['manager'], env['mkt'], kind='standby')

    tasks = [
        _role_task(test_org, env['manager'], env['mkt'], RoleType.POSITION, absence_fallback=True),
        _role_task(test_org, env['manager'], env['mkt'], RoleType.POSITION, absence_fallback=False),
        _role_task(test_org, env['manager'], env['mkt'], RoleType.POSITION),
    ]
    for task in tasks:
        assert resolve_acting_identity(task, deputy.secure_code, test_org.secure_code) is None
        assert resolve_acting_identity(task, standby.secure_code, test_org.secure_code) is None

    manager_assignment.is_deleted = True
    db.session.commit()
    for task in tasks:
        identity = resolve_acting_identity(task, standby.secure_code, test_org.secure_code)
        assert identity['acted_as_kind'] == 'standby'


def test_standby_does_not_bubble_but_proxy_bubbles_like_role(test_org):
    env = _role_unit_env(test_org)
    regular = _user('ru_other_regular', test_org, 'ruotherregular', 'Regular')
    proxy = _user('ru_other_proxy', test_org, 'ruotherproxy', 'Proxy')
    standby = _user('ru_other_standby', test_org, 'ruotherstandby', 'Standby')
    position_proxy = _user('ru_pos_proxy', test_org, 'ruposproxy', 'Position Proxy')
    manager = _user('ru_pos_manager', test_org, 'ruposmanager', 'Position Manager')
    _assign(regular, env['member'], env['sw'])
    _assign(proxy, env['member'], env['sw'], kind='proxy')
    _assign(standby, env['member'], env['sw'], kind='standby')
    _assign(position_proxy, env['manager'], env['sw'], kind='proxy', acting_for=manager)

    role_task = _role_task(test_org, env['member'], env['info'], RoleType.ROLE)
    position_task = _role_task(test_org, env['manager'], env['info'], RoleType.POSITION)

    assert resolve_acting_identity(role_task, regular.secure_code, test_org.secure_code)['acted_as_kind'] == 'regular'
    assert resolve_acting_identity(role_task, proxy.secure_code, test_org.secure_code)['acted_as_kind'] == 'proxy'
    assert resolve_acting_identity(role_task, standby.secure_code, test_org.secure_code) is None
    assert resolve_acting_identity(position_task, position_proxy.secure_code, test_org.secure_code) is None


def test_proxy_uses_role_unit_identity(test_org, test_user):
    env = _role_unit_env(test_org)
    today = test_org.local_today()
    delegator = _user('ru_delegator', test_org, 'rudelegator', 'Delegator')
    _assign(delegator, env['manager'], env['mkt'])
    _assign(
        test_user,
        env['manager'],
        env['mkt'],
        valid_from=today,
        valid_until=today,
        kind=AssignmentKind.PROXY,
        acting_for=delegator,
    )
    task = _role_task(test_org, env['manager'], env['mkt'], RoleType.POSITION)

    manager_identity = resolve_acting_identity(
        task, test_user.secure_code, test_org.secure_code)
    assert manager_identity == {
        'via': 'self',
        'delegator_secure_code': delegator.secure_code,
        'acted_as_role_code': 'DEPT_MANAGER',
        'acted_as_kind': 'proxy',
    }


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


def test_snapshot_only_user_is_denied_but_proxy_records_acting_for(test_org):
    """新規格 ROLE@unit 不再用快照放行；proxy 依即時持有記錄歸因。"""
    env = _role_unit_env(test_org)
    manager = _user('ru_snap_mgr', test_org, 'rusnapmgr', 'Manager')
    proxy = _user('ru_snap_deputy', test_org, 'rusnapdeputy', 'Proxy')
    stranger = _user('ru_snap_stranger', test_org, 'rusnapstranger', 'Stranger')
    _assign(manager, env['manager'], env['mkt'])
    _assign(proxy, env['manager'], env['mkt'], kind='proxy', acting_for=manager)
    task = _task(test_org, {
        'assignee_type': 'ROLE',
        'assignee_value': env['manager'].secure_code,
        'assignee_unit_secure_code': env['mkt'].secure_code,
        'assignee_role_type': RoleType.POSITION,
        'assignees': [manager.secure_code, proxy.secure_code, stranger.secure_code],
    })

    manager_identity = resolve_acting_identity(task, manager.secure_code, test_org.secure_code)
    proxy_identity = resolve_acting_identity(task, proxy.secure_code, test_org.secure_code)
    stranger_identity = resolve_acting_identity(task, stranger.secure_code, test_org.secure_code)

    assert manager_identity['acted_as_role_code'] is None
    assert proxy_identity['acted_as_kind'] == 'proxy'
    assert proxy_identity['acted_as_role_code'] == 'DEPT_MANAGER'
    assert proxy_identity['delegator_secure_code'] == manager.secure_code
    assert delegate_from_fields(proxy_identity, test_org.secure_code) == {
        'delegate_from_secure_code': manager.secure_code,
        'delegate_from_name': manager.display_name,
    }
    assert stranger_identity is None
    assert can_act_on_task(task, stranger.secure_code, test_org.secure_code) is False


def test_standby_in_snapshot_loses_access_when_manager_returns_from_leave(test_org):
    env = _role_unit_env(test_org)
    today = date(2026, 9, 5)
    manager = _user('ru_return_mgr', test_org, 'rureturnmgr', 'Return Manager')
    standby = _user('ru_return_p1', test_org, 'rureturnp1', 'Return Standby')
    _assign(manager, env['manager'], env['mkt'])
    _assign(standby, env['manager'], env['mkt'], kind='standby')
    task = _task(test_org, {
        'assignee_type': 'ROLE',
        'assignee_value': env['manager'].secure_code,
        'assignee_unit_secure_code': env['mkt'].secure_code,
        'assignee_role_type': RoleType.POSITION,
        'assignees': [manager.secure_code, standby.secure_code],
    })

    present_actor = build_actor(standby.secure_code, test_org.secure_code)
    present_actor['_local_now'] = datetime(2026, 9, 5, 14, 0)
    assert resolve_acting_identity(task, standby.secure_code, test_org.secure_code, present_actor) is None

    leave = _leave(manager, today, [])
    leave_actor = build_actor(standby.secure_code, test_org.secure_code)
    leave_actor['_local_now'] = datetime(2026, 9, 5, 14, 0)
    assert resolve_acting_identity(
        task, standby.secure_code, test_org.secure_code, leave_actor
    )['acted_as_kind'] == 'standby'

    leave.is_deleted = True
    db.session.commit()
    returned_actor = build_actor(standby.secure_code, test_org.secure_code)
    returned_actor['_local_now'] = datetime(2026, 9, 5, 14, 0)
    assert resolve_acting_identity(task, standby.secure_code, test_org.secure_code, returned_actor) is None


def test_legacy_queue_without_unit_key_still_grants_snapshot(test_org):
    env = _role_unit_env(test_org)
    snapshot_user = _user('ru_old_snap', test_org, 'ruoldsnap', 'Old Snapshot')
    task = _task(test_org, {
        'assignee_type': 'ROLE',
        'assignee_value': env['manager'].secure_code,
        'assignee_role_type': RoleType.POSITION,
        'assignees': [snapshot_user.secure_code],
    })

    identity = resolve_acting_identity(task, snapshot_user.secure_code, test_org.secure_code)

    assert identity == {
        'via': 'self',
        'delegator_secure_code': None,
        'acted_as_role_code': None,
        'acted_as_kind': None,
    }


def test_global_spec_with_null_unit_key_ignores_snapshot(test_org):
    env = _role_unit_env(test_org)
    snapshot_user = _user('ru_global_snap', test_org, 'ruglobalsnap', 'Global Snapshot')
    holder = _user('ru_global_holder', test_org, 'ruglobalholder', 'Global Holder')
    _assign(holder, env['manager'], env['sw'])
    task = _task(test_org, {
        'assignee_type': 'ROLE',
        'assignee_value': env['manager'].secure_code,
        'assignee_unit_secure_code': None,
        'assignee_role_type': RoleType.ROLE,
        'assignees': [snapshot_user.secure_code, holder.secure_code],
    })

    assert resolve_acting_identity(task, snapshot_user.secure_code, test_org.secure_code) is None
    assert can_act_on_task(task, holder.secure_code, test_org.secure_code) is True


def test_manager_full_day_leave_allows_standby_but_manager_still_act(test_org):
    env = _role_unit_env(test_org)
    manager = _user('ru_leave_mgr', test_org, 'ruleavemgr', 'Leave Manager')
    deputy = _user('ru_leave_dep', test_org, 'ruleavedep', 'Leave Deputy')
    standby = _user('ru_leave_p1', test_org, 'ruleavep1', 'Leave Standby')
    _assign(manager, env['manager'], env['mkt'])
    _assign(deputy, env['deputy'], env['mkt'])
    _assign(standby, env['manager'], env['mkt'], kind='standby')
    _leave(manager, date(2026, 9, 5), [])
    task = _role_task(test_org, env['manager'], env['mkt'], RoleType.POSITION)

    for user in (manager, deputy, standby):
        actor = build_actor(user.secure_code, test_org.secure_code)
        actor['_local_now'] = datetime(2026, 9, 5, 14, 0)
        identity = resolve_acting_identity(task, user.secure_code, test_org.secure_code, actor)
        if user == manager:
            assert identity['acted_as_kind'] == 'regular'
            assert identity['acted_as_role_code'] is None
        elif user == deputy:
            assert identity is None
        else:
            assert identity['acted_as_kind'] == 'standby'
            assert identity['acted_as_role_code'] == 'DEPT_MANAGER'


def test_standby_permission_follows_manager_partial_leave_time(test_org):
    env = _role_unit_env(test_org)
    manager = _user('ru_part_mgr', test_org, 'rupartmgr', 'Partial Manager')
    standby = _user('ru_part_p1', test_org, 'rupartp1', 'Partial Standby')
    _assign(manager, env['manager'], env['mkt'])
    _assign(standby, env['manager'], env['mkt'], kind='standby')
    _leave(
        manager,
        date(2026, 9, 5),
        ['09:00-12:00'],
        ['09:00-12:00', '13:00-18:00'],
    )
    task = _role_task(test_org, env['manager'], env['mkt'], RoleType.POSITION)

    leave_actor = build_actor(standby.secure_code, test_org.secure_code)
    leave_actor['_local_now'] = datetime(2026, 9, 5, 14, 0)
    assert resolve_acting_identity(
        task, standby.secure_code, test_org.secure_code, leave_actor
    )['acted_as_kind'] == 'standby'

    present_actor = build_actor(standby.secure_code, test_org.secure_code)
    present_actor['_local_now'] = datetime(2026, 9, 5, 10, 0)
    assert resolve_acting_identity(
        task, standby.secure_code, test_org.secure_code, present_actor
    ) is None


def test_any_present_manager_blocks_standby_when_another_manager_is_on_leave(test_org):
    env = _role_unit_env(test_org)
    leave_manager = _user('ru_multi_leave_mgr', test_org, 'rumultileavemgr', 'Leave Manager')
    present_manager = _user('ru_multi_present_mgr', test_org, 'rumultipresentmgr', 'Present Manager')
    standby = _user('ru_multi_p1', test_org, 'rumultip1', 'Multi Standby')
    _assign(leave_manager, env['manager'], env['mkt'])
    _assign(present_manager, env['manager'], env['mkt'])
    _assign(standby, env['manager'], env['mkt'], kind='standby')
    _leave(leave_manager, date(2026, 9, 5), [])
    task = _role_task(test_org, env['manager'], env['mkt'], RoleType.POSITION)
    actor = build_actor(standby.secure_code, test_org.secure_code)
    actor['_local_now'] = datetime(2026, 9, 5, 14, 0)

    assert resolve_acting_identity(task, standby.secure_code, test_org.secure_code, actor) is None


def test_leave_on_another_date_does_not_allow_standby(test_org):
    env = _role_unit_env(test_org)
    manager = _user('ru_tomorrow_mgr', test_org, 'rutomorrowmgr', 'Tomorrow Manager')
    standby = _user('ru_tomorrow_p1', test_org, 'rutomorrowp1', 'Tomorrow Standby')
    _assign(manager, env['manager'], env['mkt'])
    _assign(standby, env['manager'], env['mkt'], kind='standby')
    _leave(manager, date(2026, 9, 6), [])
    task = _role_task(test_org, env['manager'], env['mkt'], RoleType.POSITION)
    actor = build_actor(standby.secure_code, test_org.secure_code)
    actor['_local_now'] = datetime(2026, 9, 5, 14, 0)

    assert resolve_acting_identity(task, standby.secure_code, test_org.secure_code, actor) is None


def test_absence_fallback_false_ignores_manager_leave_for_non_standby(test_org):
    env = _role_unit_env(test_org)
    manager = _user('ru_nofb_mgr', test_org, 'runofbmgr', 'No Fallback Manager')
    deputy = _user('ru_nofb_dep', test_org, 'runofbdep', 'No Fallback Deputy')
    standby = _user('ru_nofb_p1', test_org, 'runofbp1', 'No Fallback Standby')
    _assign(manager, env['manager'], env['mkt'])
    _assign(deputy, env['deputy'], env['mkt'])
    _assign(standby, env['manager'], env['mkt'], kind='standby')
    _leave(manager, date(2026, 9, 5), [])
    task = _role_task(
        test_org, env['manager'], env['mkt'], RoleType.POSITION, absence_fallback=False)

    for user in (deputy,):
        actor = build_actor(user.secure_code, test_org.secure_code)
        actor['_local_now'] = datetime(2026, 9, 5, 14, 0)
        assert resolve_acting_identity(task, user.secure_code, test_org.secure_code, actor) is None
    actor = build_actor(standby.secure_code, test_org.secure_code)
    actor['_local_now'] = datetime(2026, 9, 5, 14, 0)
    assert resolve_acting_identity(task, standby.secure_code, test_org.secure_code, actor)['acted_as_kind'] == 'standby'


def test_legacy_actor_without_local_now_is_populated_for_standby_availability(test_org, monkeypatch):
    env = _role_unit_env(test_org)
    manager = _user('ru_oldactor_mgr', test_org, 'ruoldactormgr', 'Old Actor Manager')
    standby = _user('ru_oldactor_p1', test_org, 'ruoldactorp1', 'Old Actor Standby')
    _assign(manager, env['manager'], env['mkt'])
    _assign(standby, env['manager'], env['mkt'], kind='standby')
    _leave(manager, date(2026, 9, 5), [])
    task = _role_task(test_org, env['manager'], env['mkt'], RoleType.POSITION)
    actor = build_actor(standby.secure_code, test_org.secure_code)
    actor.pop('_local_now')

    monkeypatch.setattr(
        'modules.form_workflow.services.task_authorizer.org_local_now',
        lambda org_sc: datetime(2026, 9, 5, 14, 0),
    )

    identity = resolve_acting_identity(task, standby.secure_code, test_org.secure_code, actor)

    assert identity['acted_as_kind'] == 'standby'


def test_proxy_valid_period_bounds(test_org):
    env = _role_unit_env(test_org)
    manager = _user('ru_bounds_mgr', test_org, 'ruboundsmgr', 'Bounds Manager')
    proxy = _user('ru_bounds_proxy', test_org, 'ruboundsproxy', 'Bounds Proxy')
    today = test_org.local_today()
    row = _assign(
        proxy, env['manager'], env['mkt'],
        today + timedelta(days=1), today + timedelta(days=2),
        kind='proxy', acting_for=manager,
    )
    task = _role_task(test_org, env['manager'], env['mkt'], RoleType.POSITION)

    assert resolve_acting_identity(task, proxy.secure_code, test_org.secure_code) is None

    row.valid_from = today
    row.valid_until = today
    db.session.commit()
    inside = build_actor(proxy.secure_code, test_org.secure_code)
    identity = resolve_acting_identity(task, proxy.secure_code, test_org.secure_code, inside)
    assert identity['acted_as_kind'] == 'proxy'

    row.valid_from = today - timedelta(days=2)
    row.valid_until = today - timedelta(days=1)
    db.session.commit()
    assert resolve_acting_identity(task, proxy.secure_code, test_org.secure_code) is None


def test_proxy_allowed_form_templates_scope(test_org):
    env = _role_unit_env(test_org)
    manager = _user('ru_scope_mgr', test_org, 'ruscopemgr', 'Scope Manager')
    proxy = _user('ru_scope_proxy', test_org, 'ruscopeproxy', 'Scope Proxy')
    template_a = _form_template(test_org, 'tpl_scope_a', 'TPLA', 'Template A')
    template_b = _form_template(test_org, 'tpl_scope_b', 'TPLB', 'Template B')
    form_a = _form_instance(test_org, 'fi_scope_a', template_a)
    form_b = _form_instance(test_org, 'fi_scope_b', template_b)
    _assign(
        proxy, env['manager'], env['mkt'],
        kind='proxy', acting_for=manager,
        allowed_form_templates=[template_a.secure_code],
    )

    data = {
        'assignee_type': 'ROLE',
        'assignee_value': env['manager'].secure_code,
        'assignee_unit_secure_code': env['mkt'].secure_code,
        'assignee_role_type': RoleType.POSITION,
        'assignees': [],
    }
    assert resolve_acting_identity(
        _task(test_org, data.copy(), form_a.secure_code),
        proxy.secure_code,
        test_org.secure_code,
    )['acted_as_kind'] == 'proxy'
    assert resolve_acting_identity(
        _task(test_org, data.copy(), form_b.secure_code),
        proxy.secure_code,
        test_org.secure_code,
    ) is None
    assert resolve_acting_identity(
        _task(test_org, data.copy()),
        proxy.secure_code,
        test_org.secure_code,
    ) is None


def test_standby_also_honours_allowed_form_templates(test_org):
    env = _role_unit_env(test_org)
    template_a = _form_template(test_org, 'tpl_standby_a', 'STBA', 'Standby A')
    template_b = _form_template(test_org, 'tpl_standby_b', 'STBB', 'Standby B')
    form_a = _form_instance(test_org, 'fi_standby_a', template_a)
    form_b = _form_instance(test_org, 'fi_standby_b', template_b)
    standby = _user('ru_standby_scope', test_org, 'rustandbyscope', 'Standby Scope')
    _assign(
        standby, env['manager'], env['mkt'],
        kind='standby',
        allowed_form_templates=[template_a.secure_code],
    )

    task_data = {
        'assignee_type': 'ROLE',
        'assignee_value': env['manager'].secure_code,
        'assignee_unit_secure_code': env['mkt'].secure_code,
        'assignee_role_type': RoleType.POSITION,
        'assignees': [],
    }
    assert resolve_acting_identity(
        _task(test_org, task_data.copy(), form_a.secure_code),
        standby.secure_code,
        test_org.secure_code,
    )['acted_as_kind'] == 'standby'
    assert resolve_acting_identity(
        _task(test_org, task_data.copy(), form_b.secure_code),
        standby.secure_code,
        test_org.secure_code,
    ) is None


def test_regular_and_proxy_coexist_for_same_person(test_org):
    env = _role_unit_env(test_org)
    manager = _user('ru_co_mgr', test_org, 'rucomgr', 'Co Manager')
    user = _user('ru_co_user', test_org, 'rucouser', 'Co User')
    _assign(user, env['deputy'], env['mkt'])
    _assign(user, env['manager'], env['mkt'], kind='proxy', acting_for=manager)

    manager_identity = resolve_acting_identity(
        _role_task(test_org, env['manager'], env['mkt'], RoleType.POSITION),
        user.secure_code,
        test_org.secure_code,
    )
    deputy_identity = resolve_acting_identity(
        _role_task(test_org, env['deputy'], env['mkt'], RoleType.POSITION),
        user.secure_code,
        test_org.secure_code,
    )
    assert manager_identity['acted_as_kind'] == 'proxy'
    assert deputy_identity['acted_as_kind'] == 'regular'


def test_kind_priority_regular_before_proxy(test_org):
    env = _role_unit_env(test_org)
    manager = _user('ru_prio_mgr', test_org, 'rupriomgr', 'Priority Manager')
    user = _user('ru_prio_user', test_org, 'rupriouser', 'Priority User')
    _assign(user, env['manager'], env['mkt'])
    _assign(user, env['manager'], env['mkt'], kind='proxy', acting_for=manager)
    task = _role_task(test_org, env['manager'], env['mkt'], RoleType.POSITION)

    identity = resolve_acting_identity(task, user.secure_code, test_org.secure_code)

    assert identity['acted_as_kind'] == 'regular'
    assert identity['acted_as_role_code'] is None


def test_standby_global_assignment_for_null_unit_spec(test_org):
    env = _role_unit_env(test_org)
    manager = _user('ru_global_stb_mgr', test_org, 'ruglobalstbmgr', 'Global Manager')
    standby = _user('ru_global_stb', test_org, 'ruglobalstb', 'Global Standby')
    _assign(standby, env['manager'], kind='standby')
    task = _task(test_org, {
        'assignee_type': 'ROLE',
        'assignee_value': env['manager'].secure_code,
        'assignee_unit_secure_code': None,
        'assignee_role_type': RoleType.POSITION,
        'assignees': [],
    })

    assert resolve_acting_identity(task, standby.secure_code, test_org.secure_code)['acted_as_kind'] == 'standby'

    _assign(manager, env['manager'])
    assert resolve_acting_identity(task, standby.secure_code, test_org.secure_code) is None


def test_get_active_assignments_excludes_standby_by_default(test_org):
    env = _role_unit_env(test_org)
    manager = _user('ru_active_mgr', test_org, 'ruactivemgr', 'Active Manager')
    user = _user('ru_active_user', test_org, 'ruactiveuser', 'Active User')
    _assign(user, env['manager'], env['mkt'], kind='proxy', acting_for=manager)
    _assign(user, env['deputy'], env['mkt'], kind='standby')

    default_codes = UserRoleAssignment.get_active_role_secure_codes(user.secure_code)
    all_codes = UserRoleAssignment.get_active_role_secure_codes(user.secure_code, kinds=None)

    assert env['manager'].secure_code in default_codes
    assert env['deputy'].secure_code not in default_codes
    assert env['deputy'].secure_code in all_codes
