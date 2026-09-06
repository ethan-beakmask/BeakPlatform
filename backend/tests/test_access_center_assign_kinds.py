"""PF-251 第 3a 期：權限中心指派 API 收性質欄位、撤銷依 assignment_secure_code、role-holders 只回 regular 持有者。"""
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db  # noqa: E402
from app.models import AssignmentKind, Role, RoleType, ScopeType, User, UserRoleAssignment, UserType  # noqa: E402

ASSIGN = '/beakplatform/api/access/assign'
REVOKE = '/beakplatform/api/access/revoke'
HOLDERS = '/beakplatform/api/access/role-holders'


def _role(org, code):
    role = Role(org_secure_code=org.secure_code, code=code, name=code, role_type=RoleType.ROLE,
                scope_type=ScopeType.GLOBAL, is_active=True, is_deleted=False)
    db.session.add(role)
    db.session.commit()
    return role


def _user(org, sc, username, user_type=UserType.EMPLOYEE):
    user = User(secure_code=sc, org_secure_code=org.secure_code, username=username,
                email=f'{username}@example.com', display_name=username, user_type=user_type,
                is_active=True, is_deleted=False)
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()
    return user


def _regular(org, user, role):
    row = UserRoleAssignment(org_secure_code=org.secure_code, user_secure_code=user.secure_code,
                             role_secure_code=role.secure_code, assignment_kind=AssignmentKind.REGULAR, is_deleted=False)
    db.session.add(row)
    db.session.commit()
    return row


def test_assign_proxy_then_revoke_by_assignment_secure_code(admin_client, test_org):
    role = _role(test_org, 'AC_STAFF')
    boss = _user(test_org, 'ac_boss_0000000000001', 'acboss')
    agent = _user(test_org, 'ac_agent_000000000001', 'acagent')
    _regular(test_org, boss, role)
    today = test_org.local_today()

    res = admin_client.post(ASSIGN, json={
        'user_secure_code': agent.secure_code, 'role_secure_code': role.secure_code, 'kind': 'proxy',
        'acting_for_secure_code': boss.secure_code,
        'valid_from': today.isoformat(), 'valid_until': (today + timedelta(days=3)).isoformat(),
        'allowed_form_templates': ['TPL_A', 'TPL_A', ''], 'grant_reason': '出差代理',
    })
    body = res.get_json()
    assert res.status_code == 200, body
    assignment_sc = body['assignment_secure_code']

    db.session.expire_all()
    row = UserRoleAssignment.query.filter_by(secure_code=assignment_sc).one()
    assert row.assignment_kind == 'proxy'
    assert row.acting_for_user_secure_code == boss.secure_code
    assert row.allowed_form_templates == ['TPL_A']
    assert row.grant_reason == '出差代理'
    assert row.source_ref.startswith('admin:')

    # 缺事由 → 400；kind 非法 → 400
    bad = admin_client.post(ASSIGN, json={
        'user_secure_code': agent.secure_code, 'role_secure_code': role.secure_code, 'kind': 'standby',
    })
    assert bad.status_code == 400 and bad.get_json()['success'] is False
    assert admin_client.post(ASSIGN, json={
        'user_secure_code': agent.secure_code, 'role_secure_code': role.secure_code, 'kind': 'magic', 'grant_reason': 'x',
    }).status_code == 400

    # 撤銷：缺 assignment_secure_code → 400；依 sc → 軟刪
    assert admin_client.post(REVOKE, json={'user_secure_code': agent.secure_code, 'role_secure_code': role.secure_code}).status_code == 400
    ok = admin_client.post(REVOKE, json={'assignment_secure_code': assignment_sc})
    assert ok.status_code == 200, ok.get_json()
    db.session.expire_all()
    assert UserRoleAssignment.query.filter_by(secure_code=assignment_sc).one().is_deleted is True
    assert admin_client.post(REVOKE, json={'assignment_secure_code': assignment_sc}).status_code == 400


def test_role_holders_lists_only_regular_holders(admin_client, test_org):
    role = _role(test_org, 'AC_HOLDER')
    boss = _user(test_org, 'ac_h_boss_00000000001', 'achboss')
    agent = _user(test_org, 'ac_h_agent_0000000001', 'achagent')
    inactive = _user(test_org, 'ac_h_off_000000000001', 'achoff')
    _regular(test_org, boss, role)
    _regular(test_org, inactive, role)
    inactive.is_active = False
    db.session.add(UserRoleAssignment(org_secure_code=test_org.secure_code, user_secure_code=agent.secure_code,
                                      role_secure_code=role.secure_code, assignment_kind=AssignmentKind.PROXY,
                                      acting_for_user_secure_code=boss.secure_code, is_deleted=False))
    db.session.commit()

    res = admin_client.get(f'{HOLDERS}?role_secure_code={role.secure_code}')
    body = res.get_json()
    assert res.status_code == 200, body
    assert [h['secure_code'] for h in body['holders']] == [boss.secure_code]
    assert admin_client.get(HOLDERS).status_code == 400
