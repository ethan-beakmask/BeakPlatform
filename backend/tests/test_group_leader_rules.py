"""Group leader eligibility and account lifecycle integration."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db
from backend.tests.conftest import _login_user_directly
from backend.tests.test_oidc_members import group, user, membership, P


def test_group_leader_write_paths(admin_client, test_org):
    unit = group(test_org, 'VENDOR_TEAM', group(test_org, 'EXTERNAL_VENDORS'))
    external = user(test_org, 'vendor-leader', 'EXTERNAL')
    inactive = user(test_org, 'inactive-leader', active=False)
    employee = user(test_org, 'employee-leader')
    db.session.commit()
    path = P + f'/api/units/{unit.secure_code}/cross-members'
    def add(account, role):
        return admin_client.post(path, json={'user_id': account.secure_code, 'role_type': role})
    assert add(external, 'MANAGER').status_code == 400
    added = add(external, 'MEMBER')
    assert added.status_code == 201
    sc = added.get_json()['membership']['id']
    assert admin_client.put(path + '/' + sc, json={'role_type': 'DEPUTY'}).status_code == 400
    from app.models import UserUnitMembership
    row = UserUnitMembership.query.filter_by(secure_code=sc).one()
    row.is_deleted = True; db.session.commit()
    assert add(external, 'PROXY1').status_code == 400
    assert row.is_deleted is True
    assert add(inactive, 'MANAGER').status_code == 400
    assert add(employee, 'MANAGER').status_code == 201
    assert add(employee, 'BOSS').status_code == 400


def test_disable_and_delete_vacate_only_group_leaders(admin_client, test_org):
    leader = user(test_org, 'to-disable')
    deleted = user(test_org, 'to-delete')
    unit = group(test_org, 'LEADERS')
    other = group(test_org, 'MEMBERS')
    manager = membership(test_org, unit, leader, 'MANAGER')
    member = membership(test_org, other, leader)
    membership(test_org, unit, deleted, 'DEPUTY')
    db.session.commit()
    response = admin_client.post(P + f'/users/{leader.secure_code}/toggle-status')
    assert response.status_code == 302
    db.session.refresh(manager); db.session.refresh(member)
    assert manager.is_deleted is True and member.is_deleted is False
    with admin_client.session_transaction(path=P + '/users/') as sess:
        assert sess['vacated_groups_notice'] == [unit.name]
    enabled = admin_client.post(P + f'/users/{leader.secure_code}/toggle-status')
    assert enabled.status_code == 302
    db.session.refresh(manager)
    assert manager.is_deleted is True
    deleted_response = admin_client.delete(P + f'/api/users/{deleted.secure_code}')
    assert deleted_response.status_code == 200
    assert deleted_response.get_json()['vacated_groups'] == [
        {'key': unit.secure_code, 'name': unit.name, 'role_type': 'DEPUTY'}]


def test_external_candidates_denied(client, app, test_org):
    external = user(test_org, 'candidate-vendor', 'EXTERNAL')
    db.session.commit()
    _login_user_directly(client, app, external, test_org)
    assert client.get(P + '/api/units/group-member-candidates').status_code == 403
