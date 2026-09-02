"""職系設定的兩道守門：
1. 已直接掛有職稱的職系不能再新增子職系（否則直掛職稱會從職稱設定與矩陣上消失）
2. 連動刪除職稱時，任一職稱仍有成員職位指派就擋下（與單獨刪除職稱一致）
"""
from datetime import timedelta

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
)

PREFIX = '/beakplatform'
AJAX = {'X-Requested-With': 'XMLHttpRequest'}


def _ensure_job_family_read_permission():
    db.session.add(Permission(
        secure_code='perm_job_family_read_jfg',
        resource_type='job_family',
        action='read',
        code='job_family:read',
        name='檢視職系',
        permission_level=PermissionLevel.ORG,
        is_system_permission=True,
        is_active=True,
        is_deleted=False,
    ))
    db.session.flush()


def _family(org, code, parent=None):
    family = JobFamily(
        secure_code=f'family_{code}_jfg',
        org_secure_code=org.secure_code,
        family_type=JobFamilyType.PROFESSIONAL,
        code=code,
        name=f'職系 {code}',
        parent_secure_code=parent.secure_code if parent else None,
        is_active=True,
        is_deleted=False,
    )
    db.session.add(family)
    db.session.flush()
    return family


def _level(org):
    level = JobLevel(
        secure_code='level_jfg',
        org_secure_code=org.secure_code,
        code='L-JFG',
        name='職等 JFG',
        level_order=100,
        is_active=True,
        is_deleted=False,
    )
    db.session.add(level)
    db.session.flush()
    return level


def _title(org, family, level, code):
    title = JobTitle(
        secure_code=f'title_{code}_jfg',
        org_secure_code=org.secure_code,
        code=code,
        name=f'職稱 {code}',
        job_level_secure_code=level.secure_code,
        job_family_secure_code=family.secure_code,
        is_active=True,
        is_deleted=False,
    )
    db.session.add(title)
    db.session.flush()
    return title


def _position(org, user, title):
    unit = OrganizationalUnit(
        secure_code='unit_jfg',
        org_secure_code=org.secure_code,
        unit_type=UnitType.DEPARTMENT,
        code='D-JFG',
        name='部門 JFG',
        is_active=True,
        is_deleted=False,
    )
    db.session.add(unit)
    db.session.flush()
    position = EmployeePosition(
        secure_code='position_jfg',
        org_secure_code=org.secure_code,
        user_secure_code=user.secure_code,
        job_title_secure_code=title.secure_code,
        unit_secure_code=unit.secure_code,
        position_type=PositionType.PRIMARY,
        effective_from=org.local_today() - timedelta(days=1),
        is_active=True,
        is_deleted=False,
    )
    db.session.add(position)
    db.session.flush()
    return position


def test_create_child_under_parent_with_titles_is_rejected(admin_client, test_org):
    _ensure_job_family_read_permission()
    root = _family(test_org, 'ROOTA')
    _title(test_org, root, _level(test_org), 'T1')
    db.session.commit()

    resp = admin_client.post(f'{PREFIX}/job-families/create', headers=AJAX, data={
        'name': '子職系', 'family_type': 'PROFESSIONAL', 'parent_secure_code': root.secure_code,
    })

    assert resp.status_code == 400
    errors = resp.get_json()['errors']
    assert any('已直接掛有 1 個職稱' in e for e in errors)
    assert JobFamily.query.filter_by(parent_secure_code=root.secure_code, is_deleted=False).count() == 0


def test_create_child_under_empty_parent_succeeds(admin_client, test_org):
    _ensure_job_family_read_permission()
    root = _family(test_org, 'ROOTB')
    db.session.commit()

    resp = admin_client.post(f'{PREFIX}/job-families/create', headers=AJAX, data={
        'name': '子職系', 'code': 'SUBB', 'family_type': 'PROFESSIONAL', 'parent_secure_code': root.secure_code,
    })

    assert resp.status_code == 200
    assert resp.get_json()['success'] is True
    child = JobFamily.query.filter_by(code='SUBB', is_deleted=False).first()
    assert child is not None and child.parent_secure_code == root.secure_code


def test_edit_only_rechecks_when_parent_changes(admin_client, test_org):
    _ensure_job_family_read_permission()
    level = _level(test_org)
    root_a = _family(test_org, 'ROOTC')
    root_b = _family(test_org, 'ROOTD')
    _title(test_org, root_a, level, 'TA')
    _title(test_org, root_b, level, 'TB')
    child = _family(test_org, 'SUBC', parent=root_a)   # 舊資料：上層已掛職稱仍有子職系
    db.session.commit()

    keep = admin_client.post(f'{PREFIX}/job-families/{child.secure_code}/edit', headers=AJAX, data={
        'name': '改名而已', 'family_type': 'PROFESSIONAL', 'parent_secure_code': root_a.secure_code,
        'sort_order': '3', 'is_active': 'true',
    })
    assert keep.status_code == 200
    assert JobFamily.query.get(child.id).name == '改名而已'

    move = admin_client.post(f'{PREFIX}/job-families/{child.secure_code}/edit', headers=AJAX, data={
        'name': '改名而已', 'family_type': 'PROFESSIONAL', 'parent_secure_code': root_b.secure_code,
        'sort_order': '3', 'is_active': 'true',
    })
    assert move.status_code == 400
    assert any('職系 ROOTD' in e for e in move.get_json()['errors'])
    assert JobFamily.query.get(child.id).parent_secure_code == root_a.secure_code


def test_cascade_delete_blocked_while_title_assigned(admin_client, test_org, test_user):
    _ensure_job_family_read_permission()
    family = _family(test_org, 'ROOTE')
    title = _title(test_org, family, _level(test_org), 'TE')
    position = _position(test_org, test_user, title)
    db.session.commit()

    blocked = admin_client.post(f'{PREFIX}/job-families/{family.secure_code}/delete', headers=AJAX,
                                data={'cascade_delete': 'true'})
    assert blocked.status_code == 400
    assert any('職位指派' in e for e in blocked.get_json()['errors'])
    assert JobTitle.query.get(title.id).is_deleted is False

    position.is_deleted = True
    db.session.commit()
    ok = admin_client.post(f'{PREFIX}/job-families/{family.secure_code}/delete', headers=AJAX,
                           data={'cascade_delete': 'true'})
    assert ok.status_code == 200
    assert '1 個職稱' in ok.get_json()['message']
    assert JobTitle.query.get(title.id).is_deleted is True
    assert JobFamily.query.get(family.id).is_deleted is True
