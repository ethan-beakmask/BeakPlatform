from datetime import date, datetime
from urllib.parse import parse_qs, urlparse

from app import db
from app.constants import SYSTEM_ORG_CODE
from app.models import (
    CalendarEvent,
    CalendarKind,
    CalendarVisibility,
    MenuItem,
    MenuPermission,
    MenuRoleRequirement,
    Organization,
    OrganizationalUnit,
    Role,
    RoleLevel,
    RoleType,
    ScheduleAdjustment,
    ScopeType,
    UnitType,
    User,
    UserRoleAssignment,
    UserType,
    WorkSchedule,
)
from app.services.schedule_service import ScheduleService
from app.services.calendar_projection_service import CalendarProjectionService


def _login(client, user, org):
    with client.session_transaction() as sess:
        sess.clear()
        sess['_user_id'] = user.get_id()
        sess['_fresh'] = True
        sess['org_secure_code'] = org.secure_code
        sess['org_domain'] = org.domain_name
        sess['_session_org'] = user.org_secure_code


def _user(sc, org, username, name, user_type=UserType.EMPLOYEE):
    user = User(
        secure_code=sc,
        org_secure_code=org.secure_code,
        username=username,
        email=f'{username}@example.com',
        display_name=name,
        user_type=user_type,
        is_active=True,
        is_deleted=False,
    )
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()
    return user


def _default_schedule(org):
    schedule = WorkSchedule(
        secure_code=f'cal_sched_{org.secure_code[-8:]}',
        org_secure_code=org.secure_code,
        schedule_code='CAL_STD',
        name='Calendar Standard',
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


def _grant_menu(user, org, menu_code):
    system_org = Organization.query.filter_by(secure_code=SYSTEM_ORG_CODE).first()
    if not system_org:
        system_org = Organization(
            secure_code=SYSTEM_ORG_CODE,
            code='SYSTEM',
            name='System',
            domain_name='system.local',
            is_system_org=True,
            is_active=True,
            is_deleted=False,
        )
        db.session.add(system_org)
        db.session.commit()

    menu = MenuItem.query.filter_by(code=menu_code, is_deleted=False).first()
    if not menu:
        menu = MenuItem(
            secure_code=f'{menu_code}_menu_sc',
            org_secure_code=SYSTEM_ORG_CODE,
            code=menu_code,
            title=menu_code,
            title_i18n={'en': menu_code},
            link_type='route',
            link_target='calendar_web.my_calendar' if menu_code == 'calendar_me' else 'calendar_web.org_calendar',
            display_order=0,
            depth=1,
            required_level=2,
            is_shared=False,
            is_active=True,
        )
        db.session.add(menu)
        db.session.flush()
    if not MenuPermission.query.filter_by(menu_secure_code=menu.secure_code, user_type='EMPLOYEE').first():
        db.session.add(MenuPermission(menu_secure_code=menu.secure_code, user_type='EMPLOYEE'))

    role_code = f'{menu_code}_{user.secure_code}_role'
    role = Role(
        secure_code=f'{role_code[:24]}',
        org_secure_code=org.secure_code,
        code=role_code[:30],
        name=role_code,
        role_type=RoleType.ROLE,
        scope_type=ScopeType.GLOBAL,
        role_level=RoleLevel.MEMBER,
        is_active=True,
    )
    db.session.add(role)
    db.session.flush()
    db.session.add_all([
        MenuRoleRequirement(
            org_secure_code=org.secure_code,
            menu_secure_code=menu.secure_code,
            role_secure_code=role.secure_code,
        ),
        UserRoleAssignment(
            org_secure_code=org.secure_code,
            user_secure_code=user.secure_code,
            role_secure_code=role.secure_code,
        ),
    ])
    db.session.commit()


def _client(client, user, org, *menus):
    for menu in menus:
        _grant_menu(user, org, menu)
    _login(client, user, org)
    return client


def _post_event(client, payload):
    return client.post('/beakplatform/api/calendar/events', json=payload)


def _personal_payload(**overrides):
    payload = {
        'calendar_kind': 'PERSONAL',
        'event_type': 'MEETING',
        'title': 'Team sync',
        'all_day': False,
        'start': '2026-09-10T09:00',
        'end': '2026-09-10T10:00',
        'visibility': 'BUSY',
        'note': 'Discuss plan',
    }
    payload.update(overrides)
    return payload


def _waiting_task(org, user_sc, node_type='FormAdapter'):
    from modules.form_workflow.models import FwNodeExecutionQueue

    task = FwNodeExecutionQueue(
        org_secure_code=org.secure_code,
        workflow_instance_secure_code=f'wfi_{user_sc[-12:]}',
        node_id=f'node_{user_sc[-8:]}',
        node_type=node_type,
        status='WAITING',
        result={'data': {
            'assignee_type': 'USER',
            'assignee_value': user_sc,
            'assignees': [user_sc],
        }},
    )
    db.session.add(task)
    db.session.commit()
    return task


def _published_workflow(org, suffix, workflow_snapshot):
    from modules.form_workflow.models import FwPublishedFormWorkflow

    row = FwPublishedFormWorkflow(
        org_secure_code=org.secure_code,
        source_mapping_id=1,
        source_mapping_secure_code=f'map_{suffix}',
        source_form_template_id=1,
        source_form_template_secure_code=f'form_{suffix}',
        source_form_version='1',
        source_form_revision=1,
        source_workflow_template_id=1,
        source_workflow_template_secure_code=f'wf_{suffix}',
        source_workflow_version='1',
        source_workflow_revision=1,
        publish_version=1,
        name=f'Published {suffix}',
        form_snapshot={'name': f'Form {suffix}'},
        workflow_snapshot=workflow_snapshot,
        status='Published',
    )
    db.session.add(row)
    db.session.commit()
    return row


def test_employee_creates_personal_and_busy_masks_for_other_employee(auth_client, test_org, test_user):
    _grant_menu(test_user, test_org, 'calendar_me')
    resp = _post_event(auth_client, _personal_payload(title='Private sync'))
    assert resp.status_code == 201

    mine = auth_client.get('/beakplatform/api/calendar/me/events?start=2026-09-10&end=2026-09-10').get_json()
    assert any(e['title'] == 'Private sync' and e['editable'] is True for e in mine['events'])

    other = _user('cal_other_user_00001', test_org, 'calother', 'Calendar Other')
    org_view = CalendarProjectionService.build(test_org, other, 'org', date(2026, 9, 10), date(2026, 9, 10))
    masked = [e for e in org_view['events'] if e.get('masked')]
    assert len(masked) == 1 and masked[0]['editable'] is False and masked[0]['title'] is None


def test_leave_hint_counts_pending_task_for_assignee(auth_client, test_org, test_user):
    _grant_menu(test_user, test_org, 'calendar_me')
    _waiting_task(test_org, test_user.secure_code)
    payload = _personal_payload(event_type='LEAVE', title='Annual leave', all_day=True,
                                start='2026-10-01', end='2026-10-03')

    resp = _post_event(auth_client, payload)

    hint = resp.get_json()['proxy_hint']
    assert resp.status_code == 201
    assert hint['needed'] is True
    assert hint['pending_count'] == 1
    assert hint['template_count'] == 0
    parsed = urlparse(hint['create_url'])
    query = parse_qs(parsed.query)
    assert parsed.path == '/beakplatform/personal-settings'
    assert query['proxy'] == ['new']
    assert query['effective_from'] == ['2026-10-01']
    assert query['effective_until'] == ['2026-10-03']
    assert query['reason'] == ['Annual leave']
    assert query['next'] == ['/beakplatform/calendar/me']
    assert parsed.fragment == 'my-proxy-assignments'
    assert (hint['start_date'], hint['end_date']) == ('2026-10-01', '2026-10-03')


def test_leave_hint_counts_published_role_assignee(client, test_org, test_user):
    role = Role(
        secure_code='cal_hint_role_sc',
        org_secure_code=test_org.secure_code,
        code='CAL_HINT_ROLE',
        name='Calendar Hint Role',
        role_type=RoleType.ROLE,
        scope_type=ScopeType.GLOBAL,
        role_level=RoleLevel.MEMBER,
        is_active=True,
    )
    db.session.add(role)
    db.session.flush()
    db.session.add(UserRoleAssignment(
        org_secure_code=test_org.secure_code,
        user_secure_code=test_user.secure_code,
        role_secure_code=role.secure_code,
    ))
    db.session.commit()
    _published_workflow(test_org, 'role_hint', {'graph': {'nodes': [
        {'id': 'n1', 'type': 'FormAdapter',
         'config': {'assignee_type': 'ROLE', 'assignee_value': role.secure_code}},
    ], 'edges': []}})
    client = _client(client, test_user, test_org, 'calendar_me')

    resp = _post_event(client, _personal_payload(event_type='TRIP', all_day=True,
                                                 start='2026-10-04', end='2026-10-04'))
    hint = resp.get_json()['proxy_hint']

    assert hint['pending_count'] == 0
    assert hint['template_count'] == 1
    assert hint['needed'] is True


def test_leave_hint_ignores_other_assignee_types_and_other_org(client, test_org, test_user):
    _published_workflow(test_org, 'initiator_hint', {'graph': {'nodes': [
        {'id': 'n1', 'type': 'Approve',
         'config': {'assignee_type': 'INITIATOR', 'assignee_value': test_user.secure_code}},
    ], 'edges': []}})
    other_org = Organization(
        secure_code='cal_hint_other_org',
        code='CAL_HINT_OTHER',
        name='Calendar Hint Other',
        domain_name='cal-hint-other.local',
        is_active=True,
        is_deleted=False,
    )
    db.session.add(other_org)
    db.session.commit()
    _published_workflow(other_org, 'other_org_hint', {'graph': {'nodes': [
        {'id': 'n2', 'type': 'FormAdapter',
         'config': {'assignee_type': 'USER', 'assignee_value': test_user.secure_code}},
    ], 'edges': []}})
    client = _client(client, test_user, test_org, 'calendar_me')

    hint = _post_event(client, _personal_payload(event_type='LEAVE', all_day=True,
                                                start='2026-10-05', end='2026-10-06')).get_json()['proxy_hint']

    assert hint['needed'] is False
    assert hint['pending_count'] == 0
    assert hint['template_count'] == 0


def test_leave_hint_suppressed_by_covering_proxy(client, test_org, test_user, test_admin):
    _waiting_task(test_org, test_user.secure_code)
    client = _client(client, test_user, test_org, 'calendar_me')
    unit = OrganizationalUnit(
        org_secure_code=test_org.secure_code,
        code='COV',
        name='Coverage Dept',
        unit_type=UnitType.DEPARTMENT,
        is_active=True,
        is_deleted=False,
    )
    role = Role(
        org_secure_code=test_org.secure_code,
        code='DEPT_MANAGER',
        name='部門正主管',
        role_type=RoleType.POSITION,
        scope_type=ScopeType.DEPARTMENT,
        is_active=True,
        is_deleted=False,
    )
    db.session.add_all([unit, role])
    db.session.flush()
    db.session.add_all([
        UserRoleAssignment(
            org_secure_code=test_org.secure_code,
            user_secure_code=test_user.secure_code,
            role_secure_code=role.secure_code,
            unit_secure_code=unit.secure_code,
            assignment_kind='regular',
            is_deleted=False,
        ),
        UserRoleAssignment(
            org_secure_code=test_org.secure_code,
            user_secure_code=test_admin.secure_code,
            role_secure_code=role.secure_code,
            unit_secure_code=unit.secure_code,
            assignment_kind='proxy',
            acting_for_user_secure_code=test_user.secure_code,
            valid_from=date(2026, 10, 1),
            valid_until=date(2026, 10, 10),
            is_deleted=False,
        ),
    ])
    menu_roles = UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == test_org.secure_code,
        UserRoleAssignment.user_secure_code == test_user.secure_code,
        UserRoleAssignment.assignment_kind == 'regular',
        UserRoleAssignment.role_secure_code != role.secure_code,
        UserRoleAssignment.is_deleted == False,  # noqa: E712
    ).all()
    for source in menu_roles:
        db.session.add(UserRoleAssignment(
            org_secure_code=test_org.secure_code,
            user_secure_code=test_admin.secure_code,
            role_secure_code=source.role_secure_code,
            unit_secure_code=source.unit_secure_code,
            assignment_kind='proxy',
            acting_for_user_secure_code=test_user.secure_code,
            valid_from=date(2026, 10, 1),
            valid_until=date(2026, 10, 10),
            is_deleted=False,
        ))
    db.session.commit()

    covered = _post_event(client, _personal_payload(event_type='LEAVE', title='Covered leave',
                                                   all_day=True, start='2026-10-02',
                                                   end='2026-10-03')).get_json()['proxy_hint']
    partial = _post_event(client, _personal_payload(event_type='LEAVE', title='Partial leave',
                                                   all_day=True, start='2026-10-09',
                                                   end='2026-10-12')).get_json()['proxy_hint']

    assert covered['already_covered'] is True
    assert covered['needed'] is False
    assert partial['already_covered'] is False
    assert partial['needed'] is True


def test_leave_hint_requires_all_regular_roles_covered(client, test_org, test_user, test_admin):
    _waiting_task(test_org, test_user.secure_code)
    unit = OrganizationalUnit(
        org_secure_code=test_org.secure_code,
        code='COV2',
        name='Coverage Dept 2',
        unit_type=UnitType.DEPARTMENT,
        is_active=True,
        is_deleted=False,
    )
    role_a = Role(org_secure_code=test_org.secure_code, code='DEPT_MANAGER', name='部門正主管',
                  role_type=RoleType.POSITION, scope_type=ScopeType.DEPARTMENT, is_active=True)
    role_b = Role(org_secure_code=test_org.secure_code, code='DEPT_HEAD', name='部門主管',
                  role_type=RoleType.POSITION, scope_type=ScopeType.DEPARTMENT, is_active=True)
    db.session.add_all([unit, role_a, role_b])
    db.session.flush()
    db.session.add_all([
        UserRoleAssignment(org_secure_code=test_org.secure_code, user_secure_code=test_user.secure_code,
                           role_secure_code=role_a.secure_code, unit_secure_code=unit.secure_code,
                           assignment_kind='regular', is_deleted=False),
        UserRoleAssignment(org_secure_code=test_org.secure_code, user_secure_code=test_user.secure_code,
                           role_secure_code=role_b.secure_code, unit_secure_code=unit.secure_code,
                           assignment_kind='regular', is_deleted=False),
        UserRoleAssignment(org_secure_code=test_org.secure_code, user_secure_code=test_admin.secure_code,
                           role_secure_code=role_a.secure_code, unit_secure_code=unit.secure_code,
                           assignment_kind='proxy', acting_for_user_secure_code=test_user.secure_code,
                           valid_from=date(2026, 10, 1), valid_until=date(2026, 10, 10),
                           is_deleted=False),
    ])
    db.session.commit()
    client = _client(client, test_user, test_org, 'calendar_me')

    hint = _post_event(client, _personal_payload(event_type='LEAVE', title='Partial roles leave',
                                                all_day=True, start='2026-10-02',
                                                end='2026-10-03')).get_json()['proxy_hint']

    assert hint['already_covered'] is False
    assert hint['needed'] is True


def test_non_leave_event_has_no_hint(client, admin_client, test_org, test_user):
    org_event = _post_event(admin_client, {
        'calendar_kind': 'ORG',
        'event_type': 'ORG_EVENT',
        'title': 'Company briefing',
        'all_day': True,
        'start': '2026-10-08',
        'end': '2026-10-08',
        'visibility': 'PUBLIC',
    }).get_json()
    client = _client(client, test_user, test_org, 'calendar_me')
    meeting = _post_event(client, _personal_payload(event_type='MEETING')).get_json()

    assert meeting['proxy_hint'] is None
    assert org_event['proxy_hint'] is None


def test_admin_leave_hint_has_prefilled_create_url(admin_client, test_org, test_admin):
    _waiting_task(test_org, test_admin.secure_code)

    resp = _post_event(admin_client, _personal_payload(event_type='LEAVE', title='Admin leave',
                                                       all_day=True, start='2026-10-11',
                                                       end='2026-10-12'))
    hint = resp.get_json()['proxy_hint']
    parsed = urlparse(hint['create_url'])
    query = parse_qs(parsed.query)

    assert parsed.path == '/beakplatform/personal-settings'
    assert query['proxy'] == ['new']
    assert query['effective_from'] == ['2026-10-11']
    assert query['effective_until'] == ['2026-10-12']
    assert query['next'] == ['/beakplatform/calendar/me']
    assert parsed.fragment == 'my-proxy-assignments'


def test_update_leave_returns_hint_too(client, test_org, test_user):
    _waiting_task(test_org, test_user.secure_code)
    client = _client(client, test_user, test_org, 'calendar_me')
    secure_code = _post_event(client, _personal_payload(event_type='LEAVE', all_day=True,
                                                       start='2026-10-13',
                                                       end='2026-10-13')).get_json()['event']['secure_code']

    resp = client.put(f'/beakplatform/api/calendar/events/{secure_code}',
                      json=_personal_payload(event_type='LEAVE', title='Updated leave',
                                             all_day=True, start='2026-10-13',
                                             end='2026-10-14'))
    hint = resp.get_json()['proxy_hint']

    assert resp.status_code == 200
    assert hint['needed'] is True
    assert hint['start_date'] == '2026-10-13'
    assert hint['end_date'] == '2026-10-14'


def test_employee_cannot_create_org(auth_client, test_org, test_user):
    _grant_menu(test_user, test_org, 'calendar_me')
    denied = _post_event(auth_client, _personal_payload(calendar_kind='ORG', event_type='ORG_EVENT'))
    assert denied.status_code == 403 and denied.get_json()['error'] == 'forbidden'


def test_admin_creates_org_event_as_public(admin_client):
    created = _post_event(admin_client, {
        'calendar_kind': 'ORG',
        'event_type': 'ORG_EVENT',
        'title': 'All hands',
        'all_day': True,
        'start': '2026-09-10',
        'end': '2026-09-10',
        'visibility': 'PRIVATE',
    })
    event = CalendarEvent.query.filter_by(secure_code=created.get_json()['event']['secure_code']).first()
    assert created.status_code == 201 and event.visibility == CalendarVisibility.PUBLIC


def test_personal_owner_payload_is_ignored(client, test_org, test_user):
    other = _user('cal_owner_ignored_01', test_org, 'ignored', 'Ignored Owner')
    client = _client(client, test_user, test_org, 'calendar_me')
    resp = _post_event(client, _personal_payload(owner_user_secure_code=other.secure_code))
    event = CalendarEvent.query.filter_by(secure_code=resp.get_json()['event']['secure_code']).first()
    assert event.owner_user_secure_code == test_user.secure_code


def test_non_owner_employee_cannot_update_or_delete_personal(auth_client, test_org, test_user):
    other = _user('cal_non_owner_00001', test_org, 'nonowner', 'Non Owner')
    event = CalendarEvent(
        org_secure_code=test_org.secure_code,
        calendar_kind=CalendarKind.PERSONAL,
        owner_user_secure_code=other.secure_code,
        event_type='MEETING',
        title='Other personal',
        starts_at=datetime(2026, 9, 10, 1, 0),
        ends_at=datetime(2026, 9, 10, 2, 0),
        all_day=False,
        visibility='BUSY',
    )
    db.session.add(event)
    db.session.commit()
    _grant_menu(test_user, test_org, 'calendar_me')

    put_resp = auth_client.put(f'/beakplatform/api/calendar/events/{event.secure_code}', json=_personal_payload(title='Steal'))
    del_resp = auth_client.delete(f'/beakplatform/api/calendar/events/{event.secure_code}')
    assert put_resp.status_code == 404 and del_resp.status_code == 404


def test_org_admin_cannot_update_other_personal_event(admin_client, test_org, test_user):
    event = CalendarEvent(
        org_secure_code=test_org.secure_code,
        calendar_kind=CalendarKind.PERSONAL,
        owner_user_secure_code=test_user.secure_code,
        event_type='MEETING',
        title='Employee personal',
        starts_at=datetime(2026, 9, 10, 1, 0),
        ends_at=datetime(2026, 9, 10, 2, 0),
        all_day=False,
        visibility='BUSY',
    )
    db.session.add(event)
    db.session.commit()
    resp = admin_client.put(f'/beakplatform/api/calendar/events/{event.secure_code}', json=_personal_payload(title='Admin edit'))
    assert resp.status_code == 404


def test_calendar_kind_is_immutable(client, test_org, test_user):
    client = _client(client, test_user, test_org, 'calendar_me')
    secure_code = _post_event(client, _personal_payload()).get_json()['event']['secure_code']
    resp = client.put(f'/beakplatform/api/calendar/events/{secure_code}', json=_personal_payload(calendar_kind='ORG'))
    assert resp.status_code == 400 and resp.get_json()['error'] == 'kind_immutable'


def test_validation_rejects_bad_ranges_types_and_title(client, test_org, test_user):
    client = _client(client, test_user, test_org, 'calendar_me')
    checks = [
        _personal_payload(start='2026-09-10T11:00', end='2026-09-10T10:00'),
        _personal_payload(event_type='HOLIDAY'),
        _personal_payload(title=''),
        _personal_payload(all_day=True, start='2026-01-01', end='2027-02-04'),
    ]
    results = [_post_event(client, payload) for payload in checks]
    assert [r.status_code for r in results] == [400, 400, 400, 400]


def test_all_day_leave_creates_adjustments_and_removes_work_periods(client, test_org, test_user):
    _default_schedule(test_org)
    client = _client(client, test_user, test_org, 'calendar_me')
    resp = _post_event(client, _personal_payload(
        event_type='LEAVE',
        title='Annual leave',
        all_day=True,
        start='2026-09-08',
        end='2026-09-10',
    ))
    secure_code = resp.get_json()['event']['secure_code']
    rows = ScheduleAdjustment.query.order_by(ScheduleAdjustment.adjust_date).all()
    assert len(rows) == 3 and all(r.status == 'APPROVED' and r.calendar_event_secure_code == secure_code for r in rows)
    assert all(ScheduleService.get_work_periods(test_user, d) == [] for d in [date(2026, 9, 8), date(2026, 9, 9), date(2026, 9, 10)])


def test_leave_update_shrinks_adjustments(client, test_org, test_user):
    _default_schedule(test_org)
    client = _client(client, test_user, test_org, 'calendar_me')
    secure_code = _post_event(client, _personal_payload(event_type='LEAVE', all_day=True, start='2026-09-08', end='2026-09-10')).get_json()['event']['secure_code']
    resp = client.put(f'/beakplatform/api/calendar/events/{secure_code}', json=_personal_payload(
        event_type='LEAVE',
        all_day=True,
        start='2026-09-08',
        end='2026-09-08',
    ))
    rows = {r.adjust_date: r for r in ScheduleAdjustment.query.all()}
    assert resp.status_code == 200 and rows[date(2026, 9, 8)].is_deleted is False
    assert rows[date(2026, 9, 9)].is_deleted is True and rows[date(2026, 9, 10)].is_deleted is True


def test_delete_leave_soft_deletes_and_same_day_reuses_unique_row(client, test_org, test_user):
    _default_schedule(test_org)
    client = _client(client, test_user, test_org, 'calendar_me')
    secure_code = _post_event(client, _personal_payload(event_type='LEAVE', all_day=True, start='2026-09-08', end='2026-09-10')).get_json()['event']['secure_code']
    assert client.delete(f'/beakplatform/api/calendar/events/{secure_code}').status_code == 200
    assert ScheduleAdjustment.query.filter_by(is_deleted=True).count() == 3

    new_code = _post_event(client, _personal_payload(event_type='LEAVE', all_day=True, start='2026-09-09', end='2026-09-09')).get_json()['event']['secure_code']
    row = ScheduleAdjustment.query.filter_by(adjust_date=date(2026, 9, 9)).first()
    assert row.is_deleted is False and row.calendar_event_secure_code == new_code and ScheduleAdjustment.query.count() == 3


def test_manual_adjustment_is_not_overwritten_or_deleted(client, test_org, test_user):
    _default_schedule(test_org)
    manual = ScheduleAdjustment(
        org_secure_code=test_org.secure_code,
        user_secure_code=test_user.secure_code,
        adjust_date=date(2026, 9, 9),
        adjust_type='LEAVE',
        status='APPROVED',
        calendar_event_secure_code=None,
    )
    db.session.add(manual)
    db.session.commit()
    client = _client(client, test_user, test_org, 'calendar_me')
    secure_code = _post_event(client, _personal_payload(event_type='LEAVE', all_day=True, start='2026-09-09', end='2026-09-09')).get_json()['event']['secure_code']
    client.delete(f'/beakplatform/api/calendar/events/{secure_code}')
    db.session.refresh(manual)
    assert manual.is_deleted is False and manual.calendar_event_secure_code is None


def test_soft_deleted_manual_leave_row_is_revived_by_calendar_leave(client, test_org, test_user):
    _default_schedule(test_org)
    manual = ScheduleAdjustment(
        org_secure_code=test_org.secure_code,
        user_secure_code=test_user.secure_code,
        adjust_date=date(2026, 9, 9),
        adjust_type='LEAVE',
        status='APPROVED',
        calendar_event_secure_code=None,
        is_deleted=True,
    )
    db.session.add(manual)
    db.session.commit()
    client = _client(client, test_user, test_org, 'calendar_me')
    secure_code = _post_event(client, _personal_payload(event_type='LEAVE', all_day=True, start='2026-09-09', end='2026-09-09')).get_json()['event']['secure_code']
    db.session.refresh(manual)
    assert manual.is_deleted is False and manual.calendar_event_secure_code == secure_code
    assert manual.adjusted_periods == [] and ScheduleAdjustment.query.filter_by(adjust_date=date(2026, 9, 9)).count() == 1


def test_trip_syncs_leave_and_type_change_recovers_adjustments(client, test_org, test_user):
    _default_schedule(test_org)
    client = _client(client, test_user, test_org, 'calendar_me')
    secure_code = _post_event(client, _personal_payload(event_type='TRIP', all_day=True, start='2026-09-09', end='2026-09-10')).get_json()['event']['secure_code']
    assert ScheduleAdjustment.query.filter_by(is_deleted=False).count() == 2
    client.put(f'/beakplatform/api/calendar/events/{secure_code}', json=_personal_payload(event_type='MEETING', all_day=True, start='2026-09-09', end='2026-09-10'))
    assert ScheduleAdjustment.query.filter_by(is_deleted=False).count() == 0


def test_partial_day_leave_spanning_midnight_creates_two_daily_adjustments(client, test_org, test_user):
    _default_schedule(test_org)
    client = _client(client, test_user, test_org, 'calendar_me')
    _post_event(client, _personal_payload(event_type='LEAVE', start='2026-09-10T14:00', end='2026-09-11T10:00'))
    rows = {
        r.adjust_date: r
        for r in ScheduleAdjustment.query.filter_by(is_deleted=False).all()
    }
    assert set(rows) == {date(2026, 9, 10), date(2026, 9, 11)}
    assert rows[date(2026, 9, 10)].adjusted_periods == ['09:00-12:00', '13:00-14:00']
    assert rows[date(2026, 9, 11)].adjusted_periods == ['10:00-12:00', '13:00-18:00']
    assert ScheduleService.get_work_periods(test_user, date(2026, 9, 10)) == ['09:00-12:00', '13:00-14:00']
    assert ScheduleService.get_work_periods(test_user, date(2026, 9, 11)) == ['10:00-12:00', '13:00-18:00']


def test_half_day_leave_keeps_remaining_periods_and_working_seconds(client, test_org, test_user):
    _default_schedule(test_org)
    client = _client(client, test_user, test_org, 'calendar_me')
    _post_event(client, _personal_payload(event_type='LEAVE', start='2026-09-10T09:00', end='2026-09-10T12:00'))

    row = ScheduleAdjustment.query.filter_by(adjust_date=date(2026, 9, 10), is_deleted=False).first()
    assert row.adjusted_periods == ['13:00-18:00']
    assert ScheduleService.get_work_periods(test_user, date(2026, 9, 10)) == ['13:00-18:00']
    assert ScheduleService.calculate_working_seconds(
        test_user,
        datetime(2026, 9, 10, 0, 0),
        datetime(2026, 9, 11, 0, 0),
    ) == 5 * 60 * 60


def test_same_day_leave_events_are_unioned_and_earliest_event_points_adjustment(client, test_org, test_user):
    _default_schedule(test_org)
    client = _client(client, test_user, test_org, 'calendar_me')
    first_code = _post_event(client, _personal_payload(
        event_type='LEAVE',
        title='Morning leave',
        start='2026-09-10T09:00',
        end='2026-09-10T10:00',
    )).get_json()['event']['secure_code']
    _post_event(client, _personal_payload(
        event_type='LEAVE',
        title='Midday leave',
        start='2026-09-10T11:00',
        end='2026-09-10T14:00',
    ))

    row = ScheduleAdjustment.query.filter_by(adjust_date=date(2026, 9, 10), is_deleted=False).first()
    assert row.adjusted_periods == ['10:00-11:00', '14:00-18:00']
    assert row.calendar_event_secure_code == first_code


def test_leave_update_recalculates_adjusted_periods(client, test_org, test_user):
    _default_schedule(test_org)
    client = _client(client, test_user, test_org, 'calendar_me')
    secure_code = _post_event(client, _personal_payload(
        event_type='LEAVE',
        start='2026-09-10T09:00',
        end='2026-09-10T12:00',
    )).get_json()['event']['secure_code']

    client.put(f'/beakplatform/api/calendar/events/{secure_code}', json=_personal_payload(
        event_type='LEAVE',
        all_day=True,
        start='2026-09-10',
        end='2026-09-10',
    ))
    row = ScheduleAdjustment.query.filter_by(adjust_date=date(2026, 9, 10)).first()
    assert row.adjusted_periods == []

    client.put(f'/beakplatform/api/calendar/events/{secure_code}', json=_personal_payload(
        event_type='LEAVE',
        start='2026-09-10T09:00',
        end='2026-09-10T12:00',
    ))
    db.session.refresh(row)
    assert row.adjusted_periods == ['13:00-18:00']


def test_existing_leave_adjustment_with_null_adjusted_periods_stays_full_day_leave(test_org, test_user):
    _default_schedule(test_org)
    db.session.add(ScheduleAdjustment(
        org_secure_code=test_org.secure_code,
        user_secure_code=test_user.secure_code,
        adjust_date=date(2026, 9, 10),
        adjust_type='LEAVE',
        status='APPROVED',
        calendar_event_secure_code=None,
        adjusted_periods=None,
    ))
    db.session.commit()

    assert ScheduleService.get_work_periods(test_user, date(2026, 9, 10)) == []


def test_busy_masks_merge_by_owner_only(client, test_org, test_user):
    viewer = _user('cal_viewer_0000001', test_org, 'viewer', 'Viewer')
    third = _user('cal_third_00000001', test_org, 'third', 'Third')
    db.session.add_all([
        CalendarEvent(org_secure_code=test_org.secure_code, calendar_kind=CalendarKind.PERSONAL, owner_user_secure_code=test_user.secure_code, event_type='MEETING', title='A1', starts_at=datetime(2026, 9, 10, 1, 0), ends_at=datetime(2026, 9, 10, 2, 0), all_day=False, visibility='BUSY'),
        CalendarEvent(org_secure_code=test_org.secure_code, calendar_kind=CalendarKind.PERSONAL, owner_user_secure_code=test_user.secure_code, event_type='MEETING', title='A2', starts_at=datetime(2026, 9, 10, 1, 30), ends_at=datetime(2026, 9, 10, 3, 0), all_day=False, visibility='BUSY'),
        CalendarEvent(org_secure_code=test_org.secure_code, calendar_kind=CalendarKind.PERSONAL, owner_user_secure_code=test_user.secure_code, event_type='MEETING', title='A3', starts_at=datetime(2026, 9, 10, 6, 0), ends_at=datetime(2026, 9, 10, 7, 0), all_day=False, visibility='BUSY'),
        CalendarEvent(org_secure_code=test_org.secure_code, calendar_kind=CalendarKind.PERSONAL, owner_user_secure_code=third.secure_code, event_type='MEETING', title='C1', starts_at=datetime(2026, 9, 10, 1, 15), ends_at=datetime(2026, 9, 10, 2, 15), all_day=False, visibility='BUSY'),
    ])
    db.session.commit()
    client = _client(client, viewer, test_org, 'calendar')
    events = client.get('/beakplatform/api/calendar/org/events?start=2026-09-10&end=2026-09-10').get_json()['events']
    owner_masks = [e for e in events if e.get('masked') and e['owner_user_secure_code'] == test_user.secure_code]
    all_masks = [e for e in events if e.get('masked')]
    assert len(owner_masks) == 2 and owner_masks[0]['start_local'] == '2026-09-10T09:00' and owner_masks[0]['end_local'] == '2026-09-10T11:00'
    assert len(all_masks) == 3


def test_unauthenticated_post_is_rejected(client):
    resp = client.post('/beakplatform/api/calendar/events', json=_personal_payload())
    assert resp.status_code in (401, 302)
