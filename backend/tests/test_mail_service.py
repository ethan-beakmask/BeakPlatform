# -*- coding: utf-8 -*-
"""PF-218 system mail service tests."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db  # noqa: E402
from app.constants import SYSTEM_ORG_CODE  # noqa: E402
from app.models import Organization, PasswordResetToken, SmtpConfig  # noqa: E402
from app.models.system_setting import SystemSetting  # noqa: E402
from app.services.email_service import (  # noqa: E402
    MAIL_SERVICE_EMAILRELAY,
    MAIL_SERVICE_SMTP,
    SETTING_CATEGORY,
    SETTING_PRIMARY_KEY,
    SETTING_SEND_BOTH_KEY,
    EmailService,
)
from backend.tests.conftest import _login_user_directly  # noqa: E402


APP_PREFIX = '/beakplatform'


@pytest.fixture(autouse=True)
def mail_service_test_config(app):
    app.config['RATELIMIT_ENABLED'] = False
    app.config['WTF_CSRF_ENABLED'] = False


@pytest.fixture
def system_client(client, app, system_admin, test_org):
    _login_user_directly(client, app, system_admin, test_org)
    return client


def _set_mail_service(primary=None, send_both=False):
    if primary is not None:
        SystemSetting.set(
            SETTING_PRIMARY_KEY,
            primary,
            updated_by='TEST',
            value_type='string',
            category=SETTING_CATEGORY,
        )
    SystemSetting.set(
        SETTING_SEND_BOTH_KEY,
        send_both,
        updated_by='TEST',
        value_type='boolean',
        category=SETTING_CATEGORY,
    )


def _create_system_smtp(name='System SMTP'):
    system_org = Organization.query.filter_by(secure_code=SYSTEM_ORG_CODE).first()
    if not system_org:
        system_org = Organization(
            secure_code=SYSTEM_ORG_CODE,
            code='SYSTEM_ORG',
            name='System Organization',
            domain_name=SYSTEM_ORG_CODE,
            is_system_org=True,
            is_active=True,
            is_deleted=False,
        )
        db.session.add(system_org)
        db.session.commit()

    config = SmtpConfig(
        org_secure_code=SYSTEM_ORG_CODE,
        name=name,
        smtp_host='smtp.example',
        username='u',
        from_email='noreply@example.com',
        is_default=True,
        is_active=True,
    )
    config.set_password('x')
    db.session.add(config)
    db.session.commit()
    return config


def test_unselected_mail_service_is_not_ready_and_send_returns_false():
    readiness = EmailService.get_readiness()

    assert readiness['ready'] is False
    assert readiness['reason'] == 'not_selected'
    assert EmailService.send_email('a@example.com', 'Subject', 'Body') is False


def test_emailrelay_primary_reports_primary_not_ready(monkeypatch):
    _set_mail_service(MAIL_SERVICE_EMAILRELAY)

    monkeypatch.setattr(
        EmailService,
        'check_service',
        staticmethod(lambda service: {
            'ready': False,
            'reason': 'submit_missing',
            'detail': '/missing/emailrelay-submit',
        } if service == MAIL_SERVICE_EMAILRELAY else {
            'ready': True,
            'reason': None,
            'detail': 'System SMTP',
        }),
    )

    readiness = EmailService.get_readiness()

    assert readiness['primary'] == MAIL_SERVICE_EMAILRELAY
    assert readiness['services'][MAIL_SERVICE_EMAILRELAY]['reason'] == 'submit_missing'
    assert readiness['reason'] == 'primary_not_ready'


def test_smtp_primary_with_default_system_config_is_ready():
    smtp = _create_system_smtp(name='Default System SMTP')
    _set_mail_service(MAIL_SERVICE_SMTP)

    readiness = EmailService.get_readiness()

    assert readiness['ready'] is True
    assert readiness['services'][MAIL_SERVICE_SMTP]['detail'] == smtp.name
    assert readiness['reason'] is None


def test_send_both_requires_secondary_service(monkeypatch):
    _create_system_smtp()
    _set_mail_service(MAIL_SERVICE_SMTP, send_both=True)
    original_check = EmailService.check_service

    def fake_check(service):
        if service == MAIL_SERVICE_EMAILRELAY:
            return {'ready': False, 'reason': 'submit_missing', 'detail': '/nope'}
        return original_check(service)

    monkeypatch.setattr(EmailService, 'check_service', staticmethod(fake_check))

    readiness = EmailService.get_readiness()

    assert readiness['ready'] is False
    assert readiness['reason'] == 'secondary_not_ready'
    assert readiness['services'][MAIL_SERVICE_SMTP]['ready'] is True


def test_send_email_detailed_reports_partial_success_and_single_service(monkeypatch):
    _set_mail_service(MAIL_SERVICE_EMAILRELAY, send_both=True)
    monkeypatch.setattr(
        EmailService,
        '_send_via_emailrelay',
        staticmethod(lambda *args, **kwargs: (True, None)),
    )
    monkeypatch.setattr(
        EmailService,
        '_send_via_smtp',
        staticmethod(lambda *args, **kwargs: (False, 'boom')),
    )

    both_result = EmailService.send_email_detailed('a@example.com', 'Subject', 'Body')

    assert both_result['success'] is False
    assert both_result['any_success'] is True
    assert both_result['attempted'] == [MAIL_SERVICE_EMAILRELAY, MAIL_SERVICE_SMTP]
    assert both_result['results'][MAIL_SERVICE_SMTP]['error'] == 'boom'

    _set_mail_service(MAIL_SERVICE_EMAILRELAY, send_both=False)

    single_result = EmailService.send_email_detailed('a@example.com', 'Subject', 'Body')

    assert single_result['attempted'] == [MAIL_SERVICE_EMAILRELAY]
    assert single_result['success'] is True
    assert MAIL_SERVICE_SMTP not in single_result['results']


def test_primary_failure_does_not_fallback_to_smtp(monkeypatch):
    _set_mail_service(MAIL_SERVICE_EMAILRELAY, send_both=False)
    smtp_calls = {'count': 0}

    monkeypatch.setattr(
        EmailService,
        '_send_via_emailrelay',
        staticmethod(lambda *args, **kwargs: (False, 'relay down')),
    )

    def count_smtp(*args, **kwargs):
        smtp_calls['count'] += 1
        return True, None

    monkeypatch.setattr(EmailService, '_send_via_smtp', staticmethod(count_smtp))

    result = EmailService.send_email_detailed('a@example.com', 'Subject', 'Body')

    assert result['success'] is False
    assert result['attempted'] == [MAIL_SERVICE_EMAILRELAY]
    assert smtp_calls['count'] == 0


def test_mail_service_api_rejects_org_admin(admin_client):
    forbidden = admin_client.put(
        f'{APP_PREFIX}/api/system-settings/mail-service',
        json={'primary': MAIL_SERVICE_SMTP},
    )

    assert forbidden.status_code == 403


def test_mail_service_api_validation_and_persistence(system_client, monkeypatch):
    bogus = system_client.put(
        f'{APP_PREFIX}/api/system-settings/mail-service',
        json={'primary': 'bogus'},
    )
    assert bogus.status_code == 400
    assert 'E-MailRelay' in bogus.get_json()['message']

    missing_smtp = system_client.put(
        f'{APP_PREFIX}/api/system-settings/mail-service',
        json={'primary': MAIL_SERVICE_SMTP},
    )
    assert missing_smtp.status_code == 400
    assert '設為預設' in missing_smtp.get_json()['message']

    _create_system_smtp(name='API SMTP')
    saved = system_client.put(
        f'{APP_PREFIX}/api/system-settings/mail-service',
        json={'primary': MAIL_SERVICE_SMTP},
    )
    assert saved.status_code == 200
    assert saved.get_json()['data']['primary'] == MAIL_SERVICE_SMTP

    fetched = system_client.get(f'{APP_PREFIX}/api/system-settings/mail-service')
    fetched_data = fetched.get_json()['data']
    assert fetched_data['primary'] == MAIL_SERVICE_SMTP
    assert fetched_data['readiness']['ready'] is True

    original_check = EmailService.check_service

    def fake_check(service):
        if service == MAIL_SERVICE_EMAILRELAY:
            return {'ready': False, 'reason': 'submit_missing', 'detail': '/missing'}
        return original_check(service)

    monkeypatch.setattr(EmailService, 'check_service', staticmethod(fake_check))
    both_blocked = system_client.put(
        f'{APP_PREFIX}/api/system-settings/mail-service',
        json={'primary': MAIL_SERVICE_SMTP, 'send_both': True},
    )

    assert both_blocked.status_code == 400
    assert '另一個服務也必須就緒' in both_blocked.get_json()['message']


def test_password_policy_api_exposes_system_mail_ready_without_has_smtp(admin_client):
    res = admin_client.get(f'{APP_PREFIX}/api/admin/settings/password-policy')

    assert res.status_code == 200
    data = res.get_json()['data']
    assert isinstance(data['system_mail_ready'], bool)
    assert 'has_smtp' not in data


def test_forgot_password_stops_before_token_when_mail_service_not_ready(
    client,
    test_org,
    test_user,
    monkeypatch,
):
    monkeypatch.setattr(EmailService, 'is_ready', staticmethod(lambda: False))

    res = client.post(
        f'{APP_PREFIX}/auth/org/{test_org.domain_name}/forgot-password',
        data={'username': test_user.username},
        follow_redirects=True,
    )

    assert res.status_code == 200
    assert '系統發信服務尚未就緒'.encode() in res.data
    assert PasswordResetToken.query.count() == 0
