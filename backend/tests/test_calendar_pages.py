"""企業行事曆頁面路由（PF-229 第一期）。

雙鑰匙守門：ORG_ADMIN bypass；EMPLOYEE 在沒有選單資料的測試庫是 fail-closed 403。
"""


def test_org_calendar_page_renders_for_admin(admin_client):
    resp = admin_client.get('/beakplatform/calendar/')
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert '__CALENDAR_CONFIG' in body
    assert 'scope: "org"' in body
    assert 'js/calendar.js' in body


def test_my_calendar_page_renders_for_admin(admin_client):
    resp = admin_client.get('/beakplatform/calendar/me')
    assert resp.status_code == 200
    assert 'scope: "me"' in resp.get_data(as_text=True)


def test_calendar_page_fail_closed_for_employee_without_menu(auth_client):
    assert auth_client.get('/beakplatform/calendar/').status_code == 403
    assert auth_client.get('/beakplatform/calendar/me').status_code == 403


def test_calendar_page_requires_login(client):
    resp = client.get('/beakplatform/calendar/')
    assert resp.status_code in (401, 302)
