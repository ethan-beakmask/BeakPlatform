from app.services.email_service import EmailService


def test_send_new_account_password_includes_login_url(monkeypatch):
    sent = {}

    def fake_send_email(to_email, subject, body):
        sent['to_email'] = to_email
        sent['subject'] = subject
        sent['body'] = body
        return True

    monkeypatch.setattr(EmailService, 'send_email', fake_send_email)

    ok = EmailService.send_new_account_password(
        to_email='member@example.com',
        org_name='Example Org',
        account='alice@example.com',
        temp_password='TempPass123!',
        login_url='https://example.com/beakplatform/login/example',
    )

    assert ok is True
    assert sent['to_email'] == 'member@example.com'
    assert sent['subject'] == '[Example Org] 新帳號密碼通知'
    assert 'alice@example.com' in sent['body']
    assert 'TempPass123!' in sent['body']
    assert '登入網址：https://example.com/beakplatform/login/example' in sent['body']


def test_send_new_account_password_omits_login_url_when_none(monkeypatch):
    sent = {}

    def fake_send_email(to_email, subject, body):
        sent['to_email'] = to_email
        sent['subject'] = subject
        sent['body'] = body
        return True

    monkeypatch.setattr(EmailService, 'send_email', fake_send_email)

    ok = EmailService.send_new_account_password(
        to_email='member@example.com',
        org_name='Example Org',
        account='alice@example.com',
        temp_password='TempPass123!',
        login_url=None,
    )

    assert ok is True
    assert sent['subject'] == '[Example Org] 新帳號密碼通知'
    assert 'alice@example.com' in sent['body']
    assert 'TempPass123!' in sent['body']
    assert '登入網址' not in sent['body']


def test_send_new_account_password_returns_false(monkeypatch):
    def fake_send_email(to_email, subject, body):
        return False

    monkeypatch.setattr(EmailService, 'send_email', fake_send_email)

    ok = EmailService.send_new_account_password(
        to_email='member@example.com',
        org_name='Example Org',
        account='alice@example.com',
        temp_password='TempPass123!',
    )

    assert ok is False
