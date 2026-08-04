"""
Tests for Authentication Interceptor
[標準 AUTH-01] 全域認證攔截測試
"""
import pytest

# app 掛在 DispatcherMiddleware 的 APP_PREFIX（預設 /beakplatform）之下，
# 測試 client 的路徑必須帶前綴，否則一律 404。
# 這 9 個測試從前綴改造起就全數 404 假失敗，直到 2026-08-05 才修。
PREFIX = '/beakplatform'


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
