"""
Tests for Tenant Isolation
[標準 TENANT-01] 強制企業隔離測試
"""
import pytest
from app.security.tenant_isolation import TenantContext, get_current_tenant

class TestTenantContext:
    """Test tenant context management."""

    def test_tenant_context_sets_tenant(self):
        """TenantContext should set the current tenant."""
        with TenantContext('test_org_123'):
            assert get_current_tenant() == 'test_org_123'

    def test_tenant_context_clears_on_exit(self):
        """TenantContext should clear tenant on exit."""
        with TenantContext('test_org_123'):
            pass
        assert get_current_tenant() is None

    def test_nested_tenant_context(self):
        """Nested TenantContext should work correctly."""
        with TenantContext('org_a'):
            assert get_current_tenant() == 'org_a'
            with TenantContext('org_b'):
                assert get_current_tenant() == 'org_b'
            assert get_current_tenant() == 'org_a'


class TestCrossTenantIsolation:
    """Test that users cannot access other tenants' data."""

    def test_user_sees_only_own_org_users(self, auth_client, test_user, test_org, app):
        """User should only see users from their own organization."""
        # Create user in different org
        from app.models import Organization, User
        from app import db

        # The app fixture already has an app_context open
        other_org = Organization(
            secure_code='other_org_0000000001',
            code='OTHER_ORG',
            name='Other Organization',
            domain_name='other.local'
        )
        db.session.add(other_org)
        db.session.commit()

        other_user = User(
            secure_code='other_user_0000000001',
            org_secure_code=other_org.secure_code,
            username='otheruser',
            email='other@example.com',
            display_name='Other User'
        )
        other_user.set_password('password123')
        db.session.add(other_user)
        db.session.commit()

        # Try to access other user
        response = auth_client.get(f'/api/users/{other_user.secure_code}')

        # Should not find the user (404) or forbidden (403)
        assert response.status_code in (403, 404)
