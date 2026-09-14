"""
Tests for Authentication Interceptor
[標準 AUTH-01] 全域認證攔截測試
"""
import pytest

from app import db

# app 掛在 DispatcherMiddleware 的 APP_PREFIX（預設 /beakplatform）之下，
# 測試 client 的路徑必須帶前綴，否則一律 404。
# 這 9 個測試從前綴改造起就全數 404 假失敗，直到 2026-08-05 才修。
PREFIX = '/beakplatform'


def _login_user_directly(client, app, user, org):
    """
    直接模擬登入狀態，繞過 HTTP 登入流程。
    這樣可以避免 Flask-Session 在 CI 容器環境中的問題。
    """
    with client.session_transaction() as sess:
        # Flask-Login 使用 _user_id 來追蹤登入用戶
        sess['_user_id'] = user.get_id()
        sess['_fresh'] = True
        # 應用程式自定義的 session 資料
        sess['org_secure_code'] = org.secure_code
        sess['org_domain'] = org.domain_name


class TestAuthInterceptor:
    """Test global authentication interceptor."""

    def test_public_route_accessible_without_auth(self, client):
        """Public routes should be accessible without authentication."""
        response = client.get(f'{PREFIX}/health')
        assert response.status_code == 200

    def test_protected_route_requires_auth(self, client):
        """Protected routes should return 401 without authentication."""
        response = client.get(f'{PREFIX}/api/users/')
        assert response.status_code == 401

    def test_protected_route_accessible_with_auth(self, auth_client):
        """Protected routes should be accessible with authentication."""
        response = auth_client.get(f'{PREFIX}/auth/me')
        assert response.status_code == 200

    def test_login_route_is_public(self, client):
        """Login route should be accessible without authentication."""
        response = client.get(f'{PREFIX}/auth/login')
        assert response.status_code == 200

    def test_invalid_credentials_returns_401(self, client):
        """Invalid credentials should return 401."""
        response = client.post(f'{PREFIX}/auth/login', json={
            'account': 'nonexistent@invalid.local',
            'password': 'wrongpassword'
        })
        assert response.status_code == 401


class TestAuthDecorators:
    """Test authentication decorators."""

    def test_login_required_without_auth(self, client):
        """@login_required should reject unauthenticated requests."""
        response = client.get(f'{PREFIX}/auth/me')
        assert response.status_code == 401

    def test_login_required_with_auth(self, auth_client):
        """@login_required should allow authenticated requests."""
        response = auth_client.get(f'{PREFIX}/auth/me')
        assert response.status_code == 200

    def test_admin_required_for_regular_user(self, auth_client):
        """@admin_required should reject regular users."""
        response = auth_client.get(f'{PREFIX}/api/users/')
        assert response.status_code == 403

    def test_admin_required_for_admin(self, admin_client):
        """@admin_required should allow admin users."""
        response = admin_client.get(f'{PREFIX}/api/users/')
        assert response.status_code == 200


class TestForcedPasswordChange:
    """Test AUTH-04 forced password change interception."""

    def _force_password_change_and_login(self, client, app, test_user, test_org):
        test_user.must_change_password = True
        db.session.commit()
        _login_user_directly(client, app, test_user, test_org)

    def test_page_redirects_to_change_password(self, client, app, test_user, test_org):
        self._force_password_change_and_login(client, app, test_user, test_org)

        response = client.get(f'{PREFIX}/dashboard')

        assert response.status_code == 302
        assert '/auth/change-password' in response.headers['Location']

    def test_api_returns_403_password_change_required(self, client, app, test_user, test_org):
        self._force_password_change_and_login(client, app, test_user, test_org)

        response = client.get(f'{PREFIX}/api/users/')

        body = response.get_json()
        assert response.status_code == 403
        assert body['error'] == 'password_change_required'
        assert '/auth/change-password' in body['redirect']

    def test_change_password_page_allowed(self, client, app, test_user, test_org):
        self._force_password_change_and_login(client, app, test_user, test_org)

        response = client.get(f'{PREFIX}/auth/change-password')

        assert response.status_code == 200

    def test_logout_allowed(self, client, app, test_user, test_org):
        self._force_password_change_and_login(client, app, test_user, test_org)

        response = client.post(f'{PREFIX}/auth/logout')

        assert response.status_code != 403

    def test_cleared_flag_restores_access(self, client, app, test_user, test_org):
        self._force_password_change_and_login(client, app, test_user, test_org)
        test_user.must_change_password = False
        db.session.commit()

        response = client.get(f'{PREFIX}/dashboard')

        assert not (
            response.status_code == 302
            and '/auth/change-password' in response.headers.get('Location', '')
        )

    def test_original_admin_setup_paths_allowed(self, client, app, test_user, test_org):
        test_user.must_change_password = True
        test_user.is_original_admin = True
        db.session.commit()
        _login_user_directly(client, app, test_user, test_org)

        response = client.get(f'{PREFIX}/users/check-username')
        body = response.get_json(silent=True) or {}

        assert not (
            response.status_code == 302
            and '/auth/change-password' in response.headers.get('Location', '')
        )
        assert not (
            response.status_code == 403
            and body.get('error') == 'password_change_required'
        )
