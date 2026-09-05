from datetime import timedelta
from html import unescape
import re

from app import db
from app.models import (
    EmployeePosition,
    JobFamily,
    JobFamilyType,
    JobLevel,
    JobTitle,
    OrganizationalUnit,
    PositionType,
    Role,
    RoleType,
    UnitType,
    User,
    UserRoleAssignment,
    UserType,
)


PREFIX = '/beakplatform'


def _employee(org, username, display_name, is_active=True):
    user = User(
        secure_code=f'{username}_posdisp',
        org_secure_code=org.secure_code,
        username=username,
        email=f'{username}@{org.domain_name}',
        display_name=display_name,
        password_hash='test-password-hash',
        user_type=UserType.EMPLOYEE,
        is_active=is_active,
        is_deleted=False,
    )
    db.session.add(user)
    db.session.flush()
    return user


def _position_context(org, suffix='base'):
    level = JobLevel(
        secure_code=f'level_{suffix}_posdisp',
        org_secure_code=org.secure_code,
        code=f'L-{suffix}',
        name=f'職等 {suffix}',
        level_order=1,
        is_active=True,
        is_deleted=False,
    )
    family = JobFamily(
        secure_code=f'family_{suffix}_posdisp',
        org_secure_code=org.secure_code,
        family_type=JobFamilyType.PROFESSIONAL,
        code=f'F-{suffix}',
        name=f'職系 {suffix}',
        is_active=True,
        is_deleted=False,
    )
    unit = OrganizationalUnit(
        secure_code=f'unit_{suffix}_posdisp',
        org_secure_code=org.secure_code,
        unit_type=UnitType.DEPARTMENT,
        code=f'D-{suffix}',
        name=f'部門 {suffix}',
        is_active=True,
        is_deleted=False,
    )
    db.session.add_all([level, family, unit])
    db.session.flush()
    title = JobTitle(
        secure_code=f'title_{suffix}_posdisp',
        org_secure_code=org.secure_code,
        code=f'T-{suffix}',
        name=f'職稱 {suffix}',
        job_level_secure_code=level.secure_code,
        job_family_secure_code=family.secure_code,
        is_active=True,
        is_deleted=False,
    )
    db.session.add(title)
    db.session.flush()
    return title, unit


def _assign_position(
    org,
    user,
    title,
    unit,
    secure_code,
    position_type=PositionType.PRIMARY,
    effective_until=None,
):
    position = EmployeePosition(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        user_secure_code=user.secure_code,
        job_title_secure_code=title.secure_code,
        unit_secure_code=unit.secure_code,
        position_type=position_type,
        effective_from=org.local_today() - timedelta(days=10),
        effective_until=effective_until,
        is_active=True,
        is_deleted=False,
    )
    db.session.add(position)
    db.session.flush()
    return position


def _dept_manager_role(org):
    role = Role(
        secure_code='role_mgr_posdisp',
        org_secure_code=org.secure_code,
        code='DEPT_MANAGER',
        name='部門主管',
        role_type=RoleType.POSITION,
        scope_type='DEPARTMENT',
        is_active=True,
        is_deleted=False,
    )
    db.session.add(role)
    db.session.flush()
    return role


def _assign_role(user, role, unit):
    assignment = UserRoleAssignment(
        org_secure_code=user.org_secure_code,
        user_secure_code=user.secure_code,
        role_secure_code=role.secure_code,
        unit_secure_code=unit.secure_code,
        is_deleted=False,
    )
    db.session.add(assignment)
    db.session.flush()
    return assignment


def _list_row(html, display_name):
    match = re.search(
        rf'<tr[^>]*>.*?<td>{re.escape(display_name)}</td>.*?</tr>',
        html,
        re.S,
    )
    assert match is not None
    return unescape(match.group(0))


def test_primary_position_appears_in_list_and_detail_link(admin_client, test_org):
    user = _employee(test_org, 'primary_member', 'Primary Member')
    title, unit = _position_context(test_org, 'primary')
    position = _assign_position(
        test_org, user, title, unit, secure_code='pos_primary_posdisp'
    )
    db.session.commit()

    list_html = admin_client.get(f'{PREFIX}/users/').get_data(as_text=True)
    assert '職稱 primary' in _list_row(list_html, 'Primary Member')

    response = admin_client.get(f'{PREFIX}/users/{user.secure_code}')
    detail_html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert f'href="/beakplatform/positions/{position.secure_code}"' in detail_html
    assert '主要' in detail_html and '部門 primary' in detail_html


def test_acting_position_adds_type_note_on_list(admin_client, test_org):
    user = _employee(test_org, 'acting_member', 'Acting Member')
    title, unit = _position_context(test_org, 'acting')
    _assign_position(
        test_org,
        user,
        title,
        unit,
        secure_code='pos_acting_posdisp',
        position_type=PositionType.ACTING,
    )
    db.session.commit()

    html = admin_client.get(f'{PREFIX}/users/').get_data(as_text=True)
    assert '職稱 acting（代理）' in _list_row(html, 'Acting Member')


def test_expired_position_is_ignored_on_list_and_detail(admin_client, test_org):
    user = _employee(test_org, 'expired_member', 'Expired Member')
    title, unit = _position_context(test_org, 'expired')
    _assign_position(
        test_org,
        user,
        title,
        unit,
        secure_code='pos_expired_posdisp',
        effective_until=test_org.local_today() - timedelta(days=1),
    )
    db.session.commit()

    list_row = _list_row(
        admin_client.get(f'{PREFIX}/users/').get_data(as_text=True),
        'Expired Member',
    )
    assert re.search(r'<td>\s*-\s*</td>\s*<td style="text-align: center;">', list_row)

    detail_html = admin_client.get(f'{PREFIX}/users/{user.secure_code}').get_data(as_text=True)
    assert '尚未指派' in detail_html


def test_position_detail_shows_department_derived_manager(admin_client, test_org):
    manager = _employee(test_org, 'derived_mgr', 'Derived Manager')
    user = _employee(test_org, 'managed_member', 'Managed Member')
    title, unit = _position_context(test_org, 'managed')
    position = _assign_position(
        test_org,
        user,
        title,
        unit,
        secure_code='pos_managed_posdisp',
    )
    role = _dept_manager_role(test_org)
    _assign_role(manager, role, unit)
    db.session.commit()

    response = admin_client.get(f'{PREFIX}/positions/{position.secure_code}')
    detail_html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'Derived Manager' in detail_html
    assert '直屬主管（依部門推導）' in detail_html
    assert f'href="/beakplatform/users/{manager.secure_code}"' in detail_html


def test_position_detail_without_manager_shows_placeholder(admin_client, test_org):
    user = _employee(test_org, 'no_mgr_member', 'No Manager Member')
    title, unit = _position_context(test_org, 'nomgr')
    position = _assign_position(
        test_org,
        user,
        title,
        unit,
        secure_code='pos_nomgr_posdisp',
    )
    db.session.commit()

    response = admin_client.get(f'{PREFIX}/positions/{position.secure_code}')
    detail_html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert '所屬部門及其上層都沒有在職主管' in detail_html
    assert '（部門 ' not in detail_html


def test_user_detail_position_row_has_no_manager_segment(admin_client, test_org):
    user = _employee(test_org, 'row_member', 'Row Member')
    title, unit = _position_context(test_org, 'row')
    _assign_position(
        test_org,
        user,
        title,
        unit,
        secure_code='pos_row_posdisp',
    )
    db.session.commit()

    detail_html = admin_client.get(f'{PREFIX}/users/{user.secure_code}').get_data(as_text=True)
    row = re.search(r'主要\s*<a[^>]*>職稱 row</a>(.*?)</div>', detail_html, re.S)
    assert row is not None
    assert unescape(row.group(0)).count('／') == 2
