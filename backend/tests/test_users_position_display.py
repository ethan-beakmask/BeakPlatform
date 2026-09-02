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
    Permission,
    PermissionLevel,
    PositionType,
    UnitType,
    User,
    UserType,
)


PREFIX = '/beakplatform'


def _ensure_user_read_permission():
    permission = Permission(
        secure_code='perm_user_read_posdisp',
        resource_type='user',
        action='read',
        code='user:read',
        name='檢視用戶',
        permission_level=PermissionLevel.ORG,
        is_system_permission=True,
        is_active=True,
        is_deleted=False,
    )
    db.session.add(permission)
    db.session.flush()


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
    direct_manager=None,
    effective_until=None,
):
    position = EmployeePosition(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        user_secure_code=user.secure_code,
        job_title_secure_code=title.secure_code,
        unit_secure_code=unit.secure_code,
        position_type=position_type,
        direct_manager_secure_code=direct_manager.secure_code if direct_manager else None,
        effective_from=org.local_today() - timedelta(days=10),
        effective_until=effective_until,
        is_active=True,
        is_deleted=False,
    )
    db.session.add(position)
    db.session.flush()
    return position


def _list_row(html, display_name):
    match = re.search(
        rf'<tr[^>]*>.*?<td>{re.escape(display_name)}</td>.*?</tr>',
        html,
        re.S,
    )
    assert match is not None
    return unescape(match.group(0))


def test_primary_position_appears_in_list_and_detail_link(admin_client, test_org):
    _ensure_user_read_permission()
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
    _ensure_user_read_permission()
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


def test_inactive_direct_manager_name_is_hidden(admin_client, test_org):
    _ensure_user_read_permission()
    manager = _employee(test_org, 'inactive_mgr', 'Inactive Manager', is_active=False)
    user = _employee(test_org, 'managed_member', 'Managed Member')
    title, unit = _position_context(test_org, 'managed')
    _assign_position(
        test_org,
        user,
        title,
        unit,
        secure_code='pos_managed_posdisp',
        direct_manager=manager,
    )
    db.session.commit()

    detail_html = admin_client.get(f'{PREFIX}/users/{user.secure_code}').get_data(as_text=True)
    assert '職稱 managed' in detail_html
    assert 'Inactive Manager' not in detail_html
