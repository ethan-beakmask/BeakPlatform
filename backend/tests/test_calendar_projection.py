from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app import db
from app.constants import SYSTEM_ORG_CODE
from app.models import (
    CalendarEvent,
    CalendarKind,
    CalendarVisibility,
    Delegation,
    DelegationStatus,
    DelegationType,
    EmployeePosition,
    JobFamily,
    JobFamilyType,
    JobLevel,
    JobTitle,
    MenuItem,
    MenuPermission,
    MenuRoleRequirement,
    Organization,
    OrganizationalUnit,
    Permission,
    PositionType,
    Role,
    RoleLevel,
    RoleType,
    ScheduleHoliday,
    ScopeType,
    User,
    UserRoleAssignment,
    UserType,
    WorkSchedule,
)
from app.services.calendar_projection_service import CalendarProjectionService


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


def _event(org, **kwargs):
    defaults = {
        'org_secure_code': org.secure_code,
        'calendar_kind': CalendarKind.ORG,
        'event_type': 'MEETING',
        'title': 'Event',
        'starts_at': datetime(2026, 9, 2, 1, 0),
        'ends_at': datetime(2026, 9, 2, 2, 0),
        'all_day': False,
        'visibility': CalendarVisibility.BUSY,
    }
    defaults.update(kwargs)
    event = CalendarEvent(**defaults)
    db.session.add(event)
    db.session.commit()
    return event


def _build(org, viewer, scope='org', start=date(2026, 9, 1), end=date(2026, 9, 7)):
    return CalendarProjectionService.build(org, viewer, scope, start, end)


def _default_schedule(org):
    schedule = WorkSchedule(
        secure_code=f'sched_{org.secure_code[-8:]}',
        org_secure_code=org.secure_code,
        schedule_code='STD',
        name='Standard',
        timezone='Asia/Taipei',
        weekly_hours={
            'mon': ['09:00-12:00'],
            'tue': ['09:00-12:00'],
            'wed': ['09:00-12:00'],
            'thu': ['09:00-12:00'],
            'fri': ['09:00-12:00'],
            'sat': None,
            'sun': None,
        },
        is_default=True,
        is_active=True,
    )
    db.session.add(schedule)
    db.session.commit()
    return schedule


def _ensure_work_schedule_read_permission():
    db.session.add(Permission(
        secure_code='perm_work_schedule_read_calendar',
        resource_type='work_schedule',
        action='read',
        code='work_schedule:read',
        name='檢視班表',
        permission_level='ORG',
        is_system_permission=True,
        is_active=True,
        is_deleted=False,
    ))
    db.session.commit()


def test_calendar_event_create_to_dict_and_range_constraint(test_org):
    event = _event(test_org, title='Board sync')
    data = event.to_dict()
    assert data['secure_code'] == event.secure_code
    assert data['title'] == 'Board sync'
    assert 'org_secure_code' not in data

    db.session.add(CalendarEvent(
        org_secure_code=test_org.secure_code,
        calendar_kind=CalendarKind.ORG,
        event_type='MEETING',
        title='Bad range',
        starts_at=datetime(2026, 9, 2, 3, 0),
        ends_at=datetime(2026, 9, 2, 2, 0),
    ))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_personal_event_visibility_public_busy_private(test_org, test_user, test_admin):
    owner = _user('owner_user_0000000001', test_org, 'owner', 'Owner')
    _event(test_org, calendar_kind=CalendarKind.PERSONAL, owner_user_secure_code=owner.secure_code,
           title='Public detail', visibility=CalendarVisibility.PUBLIC)
    _event(test_org, calendar_kind=CalendarKind.PERSONAL, owner_user_secure_code=owner.secure_code,
           title='Busy detail', visibility=CalendarVisibility.BUSY)
    private = _event(test_org, calendar_kind=CalendarKind.PERSONAL,
                     owner_user_secure_code=owner.secure_code,
                     title='Private detail', visibility=CalendarVisibility.PRIVATE)

    employee_events = _build(test_org, test_user)['events']
    assert any(e['title'] == 'Public detail' and e['masked'] is False for e in employee_events)
    busy = next(e for e in employee_events if e['event_type'] == 'BUSY')
    assert busy['masked'] is True and busy['title'] is None and busy['owner_name'] == 'Owner'
    assert all(e['source_secure_code'] != private.secure_code for e in employee_events)

    admin_events = _build(test_org, test_admin)['events']
    assert all(e['source_secure_code'] != private.secure_code for e in admin_events)

    owner_events = _build(test_org, owner)['events']
    assert any(e['title'] == 'Private detail' and e['masked'] is False for e in owner_events)


def test_days_use_schedule_holidays_and_missing_schedule_is_unknown(test_org, test_user):
    schedule = _default_schedule(test_org)
    db.session.add_all([
        ScheduleHoliday(schedule_secure_code=schedule.secure_code, holiday_date=date(2026, 9, 2),
                        holiday_type='COMP_OFF', description='Company rest'),
        ScheduleHoliday(schedule_secure_code=schedule.secure_code, holiday_date=date(2026, 9, 5),
                        holiday_type='WORKDAY', work_periods=['09:00-12:00'], description='Make up'),
    ])
    db.session.commit()

    days = {d['date']: d for d in _build(test_org, test_user, 'org')['days']}
    assert days['2026-09-02']['is_workday'] is False
    assert days['2026-09-02']['holiday']['type'] == 'COMP_OFF'
    assert days['2026-09-05']['is_workday'] is True
    assert days['2026-09-06']['is_workday'] is False

    org2 = Organization(
        secure_code='no_schedule_org_000001',
        code='NO_SCHEDULE',
        name='No Schedule Org',
        domain_name='noschedule.local',
        is_active=True,
        is_deleted=False,
    )
    db.session.add(org2)
    db.session.commit()
    viewer = _user('no_sched_user_000001', org2, 'nosched', 'No Schedule')
    # 沒班表：平日 None（不知道），六、日預設非工作日（Ethan 2026-09-03 定案）
    days2 = {d['date']: d for d in
             CalendarProjectionService.build(org2, viewer, 'org', date(2026, 9, 1), date(2026, 9, 6))['days']}
    assert days2['2026-09-01']['is_workday'] is None
    assert days2['2026-09-04']['is_workday'] is None
    assert days2['2026-09-05']['is_workday'] is False
    assert days2['2026-09-06']['is_workday'] is False


def test_comp_off_projects_as_holiday_event(test_org, test_user):
    schedule = _default_schedule(test_org)
    holiday = ScheduleHoliday(
        schedule_secure_code=schedule.secure_code,
        holiday_date=date(2026, 9, 2),
        holiday_type='COMP_OFF',
        description='Rest day',
    )
    db.session.add(holiday)
    db.session.commit()

    events = _build(test_org, test_user, 'org')['events']
    assert any(e['source_type'] == 'holiday' and e['event_type'] == 'HOLIDAY'
               and e['source_secure_code'] == holiday.secure_code for e in events)


def test_delegation_audience_filters_without_mask(test_org, test_user, test_admin):
    other = _user('other_user_000000001', test_org, 'other', 'Other')
    today = date(2026, 9, 2)
    delegation = Delegation(
        org_secure_code=test_org.secure_code,
        delegator_secure_code=test_admin.secure_code,
        delegate_secure_code=test_user.secure_code,
        delegation_type=DelegationType.FULL,
        status=DelegationStatus.PENDING,
        effective_from=today,
        effective_until=today + timedelta(days=1),
    )
    db.session.add(delegation)
    db.session.commit()

    assert any(e['source_type'] == 'delegation' for e in _build(test_org, test_user)['events'])
    assert any(e['source_type'] == 'delegation' for e in _build(test_org, test_admin)['events'])
    assert all(e['source_type'] != 'delegation' and e['masked'] is not True
               for e in _build(test_org, other)['events'])


def test_position_audience_and_ignores_open_ended_positions(test_org, test_user, test_admin):
    other = _user('position_other_000001', test_org, 'posother', 'Position Other')
    unit = OrganizationalUnit(org_secure_code=test_org.secure_code, code='ENG', name='Engineering')
    level = JobLevel(org_secure_code=test_org.secure_code, code='L100', name='Staff', level_order=100)
    family = JobFamily(org_secure_code=test_org.secure_code, code='GEN', name='General',
                       family_type=JobFamilyType.PROFESSIONAL)
    db.session.add_all([unit, level, family])
    db.session.commit()
    title = JobTitle(org_secure_code=test_org.secure_code, code='ENG', name='Engineer',
                     job_level_secure_code=level.secure_code,
                     job_family_secure_code=family.secure_code)
    db.session.add(title)
    db.session.commit()
    bounded = EmployeePosition(
        org_secure_code=test_org.secure_code,
        user_secure_code=test_user.secure_code,
        job_title_secure_code=title.secure_code,
        unit_secure_code=unit.secure_code,
        position_type=PositionType.PRIMARY,
        effective_from=date(2026, 9, 1),
        effective_until=date(2026, 9, 30),
    )
    open_ended = EmployeePosition(
        org_secure_code=test_org.secure_code,
        user_secure_code=test_user.secure_code,
        job_title_secure_code=title.secure_code,
        unit_secure_code=unit.secure_code,
        position_type=PositionType.CONCURRENT,
        effective_from=date(2026, 9, 1),
        effective_until=None,
    )
    db.session.add_all([bounded, open_ended])
    db.session.commit()

    assert any(e['source_type'] == 'position' and e['source_secure_code'] == bounded.secure_code
               for e in _build(test_org, test_user, 'me')['events'])
    assert all(e['source_secure_code'] != bounded.secure_code for e in _build(test_org, other)['events'])
    assert any(e['source_secure_code'] == bounded.secure_code for e in _build(test_org, test_admin)['events'])
    assert all(e['source_secure_code'] != open_ended.secure_code for e in _build(test_org, test_admin)['events'])


def test_event_dates_follow_organization_timezone(test_org, test_user):
    event = _event(
        test_org,
        starts_at=datetime(2026, 9, 1, 12, 30),
        ends_at=datetime(2026, 9, 1, 12, 30),
        title='Timezone point',
    )
    test_org.set_setting('timezone', 'Pacific/Kiritimati')
    db.session.commit()
    kiritimati_event = next(e for e in _build(test_org, test_user, 'org', date(2026, 9, 2), date(2026, 9, 2))['events']
                            if e['source_secure_code'] == event.secure_code)
    assert kiritimati_event['start_date'] == '2026-09-02'

    test_org.set_setting('timezone', 'Pacific/Pago_Pago')
    db.session.commit()
    pago_event = next(e for e in _build(test_org, test_user, 'org', date(2026, 9, 1), date(2026, 9, 1))['events']
                      if e['source_secure_code'] == event.secure_code)
    assert pago_event['start_date'] == '2026-09-01'


def test_projection_range_validation(test_org, test_user):
    with pytest.raises(ValueError):
        CalendarProjectionService.build(test_org, test_user, 'org', date(2026, 9, 2), date(2026, 9, 1))
    with pytest.raises(ValueError):
        CalendarProjectionService.build(test_org, test_user, 'org', date(2026, 1, 1), date(2026, 3, 5))


def _login(client, user, org):
    with client.session_transaction() as sess:
        sess['_user_id'] = user.get_id()
        sess['_fresh'] = True
        sess['org_secure_code'] = org.secure_code
        sess['org_domain'] = org.domain_name


def test_calendar_api_admin_success_and_bad_request(admin_client, test_org):
    _default_schedule(test_org)
    ok = admin_client.get('/beakplatform/api/calendar/org/events?start=2026-09-01&end=2026-09-02')
    assert ok.status_code == 200
    body = ok.get_json()
    assert body['success'] is True and 'days' in body and 'events' in body and body['timezone'] == 'Asia/Taipei'

    missing = admin_client.get('/beakplatform/api/calendar/org/events?start=2026-09-01')
    assert missing.status_code == 400


def test_calendar_api_employee_fail_closed_then_menu_role_allows(auth_client, test_org, test_user):
    _default_schedule(test_org)
    forbidden = auth_client.get('/beakplatform/api/calendar/org/events?start=2026-09-01&end=2026-09-02')
    assert forbidden.status_code == 403

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
    menu = MenuItem(
        secure_code='calendar_menu_test_sc',
        org_secure_code=SYSTEM_ORG_CODE,
        code='calendar',
        title='企業行事曆',
        title_i18n={'en': 'Company Calendar'},
        link_type='route',
        link_target='calendar_web.org_calendar',
        display_order=0,
        depth=1,
        required_level=2,
        is_shared=False,
        is_active=True,
    )
    permission = MenuPermission(menu_secure_code=menu.secure_code, user_type='EMPLOYEE')
    role = Role(
        secure_code='employee_role_test_sc',
        org_secure_code=test_org.secure_code,
        code='EMPLOYEE',
        name='Employee',
        role_type=RoleType.ROLE,
        scope_type=ScopeType.GLOBAL,
        role_level=RoleLevel.MEMBER,
        is_active=True,
    )
    req = MenuRoleRequirement(
        org_secure_code=test_org.secure_code,
        menu_secure_code=menu.secure_code,
        role_secure_code=role.secure_code,
    )
    assign = UserRoleAssignment(
        org_secure_code=test_org.secure_code,
        user_secure_code=test_user.secure_code,
        role_secure_code=role.secure_code,
    )
    db.session.add_all([menu, permission, role, req, assign])
    db.session.commit()

    employee_ok = auth_client.get('/beakplatform/api/calendar/org/events?start=2026-09-01&end=2026-09-02')
    assert employee_ok.status_code == 200


def test_user_role_assignment_valid_on_uses_org_local_day(test_org, test_user):
    test_org.set_setting('timezone', 'Pacific/Kiritimati')
    db.session.commit()
    valid_until = test_org.local_today()
    role = Role(
        secure_code='role_sc_for_validity',
        org_secure_code=test_org.secure_code,
        code='VALIDITY_ROLE',
        name='Validity Role',
        is_active=True,
    )
    db.session.add(role)
    db.session.commit()
    assignment = UserRoleAssignment(
        org_secure_code=test_org.secure_code,
        user_secure_code=test_user.secure_code,
        role_secure_code=role.secure_code,
        valid_from=valid_until,
        valid_until=valid_until,
    )
    db.session.add(assignment)
    db.session.commit()
    assert assignment.is_valid_on(valid_until) is True
    assert assignment.is_valid is True

    test_org.set_setting('timezone', 'Pacific/Pago_Pago')
    db.session.commit()
    db.session.refresh(assignment)
    assert assignment._org_today() != valid_until
    assert assignment.is_valid is False


def test_comp_off_work_schedule_api_and_batch(admin_client, test_org):
    _ensure_work_schedule_read_permission()
    schedule = _default_schedule(test_org)
    single = admin_client.post(
        f'/beakplatform/api/admin/work-schedules/{schedule.secure_code}/holidays',
        json={'holiday_date': '2026-09-02', 'holiday_type': 'COMP_OFF', 'description': 'Comp rest'},
    )
    assert single.status_code == 201
    assert schedule.get_day_periods(date(2026, 9, 2)) == []

    batch = admin_client.post(
        f'/beakplatform/api/admin/work-schedules/{schedule.secure_code}/holidays/batch',
        json={'holidays': [{'date': '2026-09-03', 'type': 'COMP_OFF', 'description': 'Batch rest'}]},
    )
    assert batch.status_code == 200
    assert batch.get_json()['imported'] == 1


def test_workflow_queue_projects_only_delay_never_approval(test_org, test_user, test_admin):
    """待簽核任務刻意不投影（Ethan 2026-09-03 定案）：沒有確定時間的是待辦不是行事曆。
    流程佇列只投影 Delay 到期，且只給 ORG_ADMIN 的 org 視圖。"""
    from modules.form_workflow.models import FwNodeExecutionQueue

    scheduled = datetime(2026, 9, 2, 2, 0, 0)  # UTC，落在 range 內
    approve = FwNodeExecutionQueue(
        secure_code='q_cal_approve_0000001',
        org_secure_code=test_org.secure_code,
        workflow_instance_secure_code='wi_cal_test_00000001',
        node_id='approve-1',
        node_type='Approve',
        node_name='簽核',
        status='WAITING',
        scheduled_at=scheduled,
        is_deleted=False,
    )
    delay = FwNodeExecutionQueue(
        secure_code='q_cal_delay_00000001',
        org_secure_code=test_org.secure_code,
        workflow_instance_secure_code='wi_cal_test_00000001',
        node_id='delay-1',
        node_type='Delay',
        node_name='等待',
        status='WAITING',
        scheduled_at=scheduled,
        is_deleted=False,
    )
    db.session.add_all([approve, delay])
    db.session.commit()

    for viewer in (test_user, test_admin):
        for scope in ('me', 'org'):
            events = _build(test_org, viewer, scope=scope)['events']
            assert all(e['source_type'] != 'approval_task' and e['event_type'] != 'APPROVAL'
                       and e['source_secure_code'] != approve.secure_code for e in events), (viewer.secure_code, scope)

    admin_org = _build(test_org, test_admin, scope='org')['events']
    assert any(e['source_type'] == 'flow_delay' and e['source_secure_code'] == delay.secure_code
               for e in admin_org)
    for viewer, scope in ((test_admin, 'me'), (test_user, 'org'), (test_user, 'me')):
        assert all(e['source_type'] != 'flow_delay' for e in _build(test_org, viewer, scope=scope)['events'])
