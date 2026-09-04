from app import db
from app.models import Delegation, Permission, User
from app.services.permission_service import PermissionService
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # `modules` 套件要 repo root 在 sys.path（同 test_task_authorizer_delegate_from.py）
from modules.form_workflow.models import FwFormTemplate  # noqa: E402


def test_create_delegation_prefills_from_query(admin_client, test_user):
    resp = admin_client.get(
        f'/beakplatform/delegations/create?delegator={test_user.secure_code}'
        '&effective_from=2026-10-01&effective_until=2026-10-03'
        '&reason=Trip&next=/beakplatform/calendar/me'
    )
    body = resp.get_data(as_text=True)
    option_at = body.index(f'value="{test_user.secure_code}"')

    assert resp.status_code == 200
    assert 'selected' in body[option_at:option_at + 140]
    assert 'name="effective_from" required style="width: 100%;"\n                       value="2026-10-01"' in body
    assert 'name="effective_until" required style="width: 100%;"\n                       value="2026-10-03"' in body
    assert '>Trip</textarea>' in body
    assert 'name="next" value="/beakplatform/calendar/me"' in body


def test_create_delegation_redirects_to_safe_next(admin_client, test_user, test_admin):
    delegate = _other_user(test_user.org_secure_code)

    resp = admin_client.post('/beakplatform/delegations/create', data={
        'delegator_secure_code': test_user.secure_code,
        'delegate_secure_code': delegate.secure_code,
        'delegation_type': 'FULL',
        'effective_from': '2026-10-01',
        'effective_until': '2026-10-03',
        'reason': 'Trip',
        'next': '/beakplatform/calendar/me',
    })

    assert resp.status_code == 302
    assert resp.headers['Location'].endswith('/beakplatform/calendar/me')
    assert Delegation.query.filter_by(delegator_secure_code=test_user.secure_code,
                                      delegate_secure_code=delegate.secure_code).count() == 1


def test_create_delegation_rejects_external_next(admin_client, test_user):
    delegate = _other_user(test_user.org_secure_code)
    targets = ['https://evil.example/', '//evil.example']

    locations = []
    for idx, target in enumerate(targets):
        resp = admin_client.post('/beakplatform/delegations/create', data={
            'delegator_secure_code': test_user.secure_code,
            'delegate_secure_code': delegate.secure_code,
            'delegation_type': 'FULL',
            'effective_from': f'2026-10-0{idx + 4}',
            'effective_until': f'2026-10-0{idx + 4}',
            'reason': 'Trip',
            'next': target,
        })
        locations.append(resp.headers['Location'])

    assert all(location.endswith('/beakplatform/delegations/') for location in locations)
    assert not any('evil.example' in location for location in locations)


def test_create_specific_requires_at_least_one_form(admin_client, test_user):
    delegate = _other_user(test_user.org_secure_code)
    before = Delegation.query.count()

    resp = admin_client.post('/beakplatform/delegations/create', data={
        'delegator_secure_code': test_user.secure_code,
        'delegate_secure_code': delegate.secure_code,
        'delegation_type': 'SPECIFIC',
        'effective_from': '2026-10-01',
        'effective_until': '2026-10-03',
        'reason': 'Trip',
    })
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert '特定代理至少要選一個表單' in body
    assert Delegation.query.count() == before


def test_create_specific_filters_forms_and_edit_clears_when_full(admin_client, test_user):
    _ensure_delegation_read_permission()
    delegate = _other_user(test_user.org_secure_code)
    template = _form_template(test_user.org_secure_code, 'del_specific_form_0001',
                              'SPEC-1', 'Specific Form')

    resp = admin_client.post('/beakplatform/delegations/create', data={
        'delegator_secure_code': test_user.secure_code,
        'delegate_secure_code': delegate.secure_code,
        'delegation_type': 'SPECIFIC',
        'allowed_form_templates': [template.secure_code, 'fake_form_secure_code'],
        'effective_from': '2026-10-01',
        'effective_until': '2026-10-03',
        'reason': 'Trip',
    })

    assert resp.status_code == 302
    delegation = Delegation.query.filter_by(
        delegator_secure_code=test_user.secure_code,
        delegate_secure_code=delegate.secure_code,
    ).one()
    assert delegation.get_allowed_form_templates() == [template.secure_code]

    edit_resp = admin_client.get(f'/beakplatform/delegations/{delegation.secure_code}/edit')
    edit_body = edit_resp.get_data(as_text=True)
    option_at = edit_body.index(f'value="{template.secure_code}"')

    assert edit_resp.status_code == 200
    assert 'selected' in edit_body[option_at:option_at + 160]

    full_resp = admin_client.post(f'/beakplatform/delegations/{delegation.secure_code}/edit', data={
        'delegation_type': 'FULL',
        'effective_from': '2026-10-01',
        'effective_until': '2026-10-03',
        'reason': 'Trip',
    })

    assert full_resp.status_code == 302
    db.session.refresh(delegation)
    assert delegation.allowed_process_types is None


def _other_user(org_secure_code):
    suffix = User.query.count()
    user = User(
        secure_code=f'del_prefill_user_{suffix:04d}',
        org_secure_code=org_secure_code,
        username=f'del-prefill-{suffix}',
        email=f'del-prefill-{suffix}@example.com',
        display_name=f'Delegation Prefill {suffix}',
        is_active=True,
        is_deleted=False,
    )
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()
    return user


def _form_template(org_secure_code, secure_code, code, name):
    template = FwFormTemplate(
        secure_code=secure_code,
        org_secure_code=org_secure_code,
        code=code,
        name=name,
        schema={'components': []},
        is_published=True,
        is_deleted=False,
    )
    db.session.add(template)
    db.session.commit()
    return template


def _ensure_delegation_read_permission():
    PermissionService._permission_cache.pop('delegation:read', None)
    if Permission.query.filter_by(code='delegation:read').first():
        return
    db.session.add(Permission(
        secure_code='perm_delegation_read_test',
        resource_type='delegation',
        action='read',
        code='delegation:read',
        name='檢視代理授權',
        permission_level='ORG',
        is_system_permission=True,
        is_active=True,
        is_deleted=False,
    ))
    db.session.commit()
