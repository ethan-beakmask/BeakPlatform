from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db
from app.models import AuditLog, Organization, PasswordResetToken, User, UserType
from app.services.user_rename_service import rename_user
from modules.form_workflow.services.node_handlers.base import BaseNodeHandler


PREFIX = '/beakplatform'


def _user(org, secure_code, username, *, user_type=UserType.EMPLOYEE,
          active=True, deleted=False, backup_email=None, display_name=None):
    email = username if user_type == UserType.EXTERNAL else f'{username}@{org.domain_name}'
    user = User(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        username=username,
        email=email,
        display_name=display_name or username,
        password_hash='test-password-hash',
        user_type=user_type,
        is_active=active,
        is_deleted=deleted,
        backup_email_1=backup_email,
    )
    db.session.add(user)
    db.session.flush()
    return user


def _token(org, email, code, *, used_at=None):
    token = PasswordResetToken(
        secure_code=f'tok_{code}',
        org_secure_code=org.secure_code,
        email=email,
        verification_url_token=f'url_{code}',
        verification_code='123456',
        expires_at=datetime.utcnow() + timedelta(minutes=15),
        used_at=used_at,
    )
    db.session.add(token)
    db.session.flush()
    return token


def test_employee_rename_preserves_identity_and_updates_matching_backup(test_org, test_admin):
    matching = _user(
        test_org, 'rename_match_001', 'alice', backup_email='ALICE@test.local'
    )
    custom = _user(
        test_org, 'rename_custom_01', 'bob', backup_email='notify@example.net'
    )
    original_matching_code = matching.secure_code
    original_custom_code = custom.secure_code

    first = rename_user(matching, actor=test_admin, new_username=' Alice.Left2026 ')
    second = rename_user(custom, actor=test_admin, new_username='bob.left2026')
    db.session.commit()

    assert first['changed'] is True
    assert (matching.username, matching.email, matching.secure_code) == (
        'alice.left2026', 'alice.left2026@test.local', original_matching_code
    )
    assert matching.backup_email_1 == 'alice.left2026@test.local'
    assert second['success'] is True
    assert (custom.username, custom.email, custom.secure_code) == (
        'bob.left2026', 'bob.left2026@test.local', original_custom_code
    )
    assert custom.backup_email_1 == 'notify@example.net'


def test_rename_duplicate_checks_deleted_disabled_and_tenant_scope(test_org, test_admin):
    target = _user(test_org, 'rename_dup_target', 'rename-target')
    _user(test_org, 'rename_dup_deleted', 'retired', deleted=True, display_name='Deleted Owner')
    _user(test_org, 'rename_dup_disabled', 'paused', active=False, display_name='Disabled Owner')
    other_org = Organization(
        secure_code='rename_other_org',
        code='RENAME_OTHER',
        name='Rename Other',
        domain_name='other.test',
        is_active=True,
        is_deleted=False,
    )
    db.session.add(other_org)
    db.session.flush()
    _user(other_org, 'rename_other_user', 'available')

    deleted_result = rename_user(target, actor=test_admin, new_username='retired')
    disabled_result = rename_user(target, actor=test_admin, new_username='paused')
    allowed_result = rename_user(target, actor=test_admin, new_username='available')

    assert deleted_result['success'] is False
    assert '已刪除' in deleted_result['message']
    assert disabled_result['success'] is False
    assert '停用' in disabled_result['message']
    assert allowed_result['success'] is True
    assert target.email == 'available@test.local'


def test_rename_invalidates_only_unused_old_email_tokens(test_org, test_admin):
    target = _user(test_org, 'rename_token_user', 'token-owner')
    unused_a = _token(test_org, 'token-owner@test.local', 'unused_a')
    unused_b = _token(test_org, 'TOKEN-OWNER@TEST.LOCAL', 'unused_b')
    prior_used_at = datetime.utcnow() - timedelta(minutes=3)
    already_used = _token(
        test_org, 'token-owner@test.local', 'already_used', used_at=prior_used_at
    )
    original_used_expiry = already_used.expires_at

    before = datetime.utcnow()
    result = rename_user(target, actor=test_admin, new_username='token-owner-old')
    db.session.commit()
    db.session.expire_all()

    assert result['success'] is True
    for token_code in (unused_a.secure_code, unused_b.secure_code):
        invalidated = PasswordResetToken.query.filter_by(secure_code=token_code).one()
        assert invalidated.used_at is not None
        assert invalidated.expires_at >= before
        assert invalidated.expires_at <= datetime.utcnow()
    unchanged = PasswordResetToken.query.filter_by(secure_code=already_used.secure_code).one()
    assert unchanged.used_at == prior_used_at
    assert unchanged.expires_at == original_used_expiry


def test_protected_account_categories_return_distinct_rejections(test_org, test_admin):
    original = _user(test_org, 'rename_original', 'original')
    original.is_original_admin = True
    system = _user(
        test_org, 'rename_system', 'system', user_type=UserType.SYSTEM_ADMIN
    )
    service = _user(test_org, 'rename_service', 'service')
    service.is_service_account = True

    original_result = rename_user(original, actor=test_admin, new_username='new-original')
    system_result = rename_user(system, actor=test_admin, new_username='new-system')
    service_result = rename_user(service, actor=test_admin, new_username='new-service')
    self_result = rename_user(test_admin, actor=test_admin, new_username='new-self')

    assert original_result['message'] == '原始管理員帳號不可變更'
    assert system_result['message'] == '系統管理員帳號不可變更'
    assert service_result['message'] == '服務帳號不可變更'
    assert self_result['message'] == '不可變更自己的帳號'


def test_reserved_employee_names_are_rejected(test_org, test_admin):
    target = _user(test_org, 'rename_reserved', 'ordinary')

    reserved = rename_user(target, actor=test_admin, new_username=' admin ')
    admin_prefix = rename_user(target, actor=test_admin, new_username='admin-departed')

    assert reserved['success'] is False
    assert reserved['message'] == '此帳號名稱為系統保留字'
    assert admin_prefix['success'] is False
    assert admin_prefix['message'] == '只有企業管理員可使用 admin- 開頭的帳號'
    assert target.username == 'ordinary'


def test_successful_rename_writes_rename_audit(test_org, test_admin):
    target = _user(test_org, 'rename_audit_user', 'audit-before')

    result = rename_user(
        target, actor=test_admin, new_username='audit-after', reason='人員離職'
    )
    db.session.commit()
    audit = AuditLog.query.filter_by(
        org_secure_code=test_org.secure_code,
        resource_id=target.secure_code,
        action='RENAME',
    ).one()

    assert result['changed'] is True
    assert audit.resource_type == 'USER'
    assert audit.user_secure_code == test_admin.secure_code
    assert 'audit-before -> audit-after' in audit.details
    assert '人員離職' in audit.details


def test_external_rename_uses_email_for_username(test_org, test_admin):
    target = _user(
        test_org,
        'rename_external',
        'vendor@outside.example',
        user_type=UserType.EXTERNAL,
        backup_email='vendor@outside.example',
    )

    result = rename_user(
        target, actor=test_admin, new_email=' New.Vendor@Outside.Example '
    )
    db.session.commit()

    assert result['new_email'] == 'new.vendor@outside.example'
    assert target.username == target.email == 'new.vendor@outside.example'
    assert target.backup_email_1 == 'new.vendor@outside.example'
    assert AuditLog.query.filter_by(
        resource_id=target.secure_code, resource_type='EXTERNAL_USER', action='RENAME'
    ).count() == 1


class _ApplicantEmailHandler(BaseNodeHandler):
    def handle(self):
        return {}


def test_applicant_email_resolves_current_address_then_snapshot(test_org, test_admin):
    applicant = _user(test_org, 'rename_fi_user', 'form-owner')
    old_email = applicant.email
    result = rename_user(applicant, actor=test_admin, new_username='form-owner-new')
    assert result['success'] is True

    handler = _ApplicantEmailHandler(SimpleNamespace(node_config={}))
    handler._form_instance = SimpleNamespace(
        applicant_secure_code=applicant.secure_code,
        applicant_email=old_email,
        org_secure_code=test_org.secure_code,
    )
    current_v2 = handler._resolve_fi('fi.applicant_email')
    current_legacy = handler._legacy_resolve_form('form.applicant_email')
    handler._form_instance.applicant_secure_code = None
    snapshot = handler._resolve_fi('fi.applicant_email')

    assert current_v2 == 'form-owner-new@test.local'
    assert current_legacy == 'form-owner-new@test.local'
    assert snapshot == old_email


def test_non_admin_cannot_post_rename(auth_client, test_org):
    target = _user(test_org, 'rename_route_denied', 'route-denied')
    db.session.commit()

    response = auth_client.post(
        f'{PREFIX}/users/{target.secure_code}/rename',
        data={'new_username': 'should-not-change'},
    )

    assert response.status_code == 403
    assert User.query.filter_by(secure_code=target.secure_code).one().username == 'route-denied'


def test_admin_rename_route_commits_and_redirects(admin_client, test_org):
    target = _user(test_org, 'rename_route_ok', 'route-before')
    db.session.commit()

    response = admin_client.post(
        f'{PREFIX}/users/{target.secure_code}/rename',
        data={'new_username': 'route-after', 'reason': '帳號重新發放'},
    )
    db.session.expire_all()
    renamed = User.query.filter_by(secure_code=target.secure_code).one()

    assert response.status_code == 302
    assert response.headers['Location'].endswith(
        f'/users/{target.secure_code}/edit'
    )
    assert (renamed.username, renamed.email) == ('route-after', 'route-after@test.local')
    edit_response = admin_client.get(response.headers['Location'])
    edit_html = edit_response.get_data(as_text=True)
    assert edit_response.status_code == 200
    assert f'action="{PREFIX}/users/{target.secure_code}/rename"' in edit_html
    assert '<details id="rename-account"' in edit_html
