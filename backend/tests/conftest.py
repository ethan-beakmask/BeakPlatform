"""
BeakPlatform Test Configuration
pytest fixtures and configuration
"""
import pytest
from flask import session
from flask_login import login_user
from app import create_app, db
from app.models import User, Organization


@pytest.fixture(scope='function')
def app():
    """Create application for testing."""
    app = create_app('testing')

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture(scope='function')
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture(scope='function')
def db_session(app):
    """Create database session for testing."""
    yield db.session


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


@pytest.fixture
def test_org(app):
    """Create test organization."""
    org = Organization(
        secure_code='test_org_00000000001',
        code='TEST_ORG',
        name='Test Organization',
        domain_name='test.local',
        is_active=True,
        is_deleted=False
    )
    db.session.add(org)
    db.session.commit()
    # Refresh to ensure all attributes are loaded
    db.session.refresh(org)
    return org


@pytest.fixture
def test_user(app, test_org):
    """Create test user."""
    user = User(
        secure_code='test_user_0000000001',
        org_secure_code=test_org.secure_code,
        username='testuser',
        email='test@example.com',
        display_name='Test User',
        is_active=True,
        is_deleted=False
    )
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()
    db.session.refresh(user)
    return user


@pytest.fixture
def test_admin(app, test_org):
    """Create test admin user."""
    from app.models.user import UserType
    admin = User(
        secure_code='test_admin_0000000001',
        org_secure_code=test_org.secure_code,
        username='testadmin',
        email='admin@example.com',
        display_name='Test Admin',
        user_type=UserType.ORG_ADMIN,
        is_active=True,
        is_deleted=False
    )
    admin.set_password('password123')
    db.session.add(admin)
    db.session.commit()
    db.session.refresh(admin)
    return admin


@pytest.fixture
def system_admin(app, test_org):
    """Create system admin user."""
    from app.models.user import UserType
    admin = User(
        secure_code='sys_admin_00000000001',
        org_secure_code=test_org.secure_code,
        username='sysadmin',
        email='sysadmin@example.com',
        display_name='System Admin',
        user_type=UserType.SYSTEM_ADMIN,
        is_active=True,
        is_deleted=False
    )
    admin.set_password('password123')
    db.session.add(admin)
    db.session.commit()
    db.session.refresh(admin)
    return admin


@pytest.fixture
def auth_client(client, app, test_user, test_org):
    """
    Create authenticated test client.

    使用 session_transaction 直接設置登入狀態，
    繞過 HTTP 登入流程，避免 Flask-Session 在 CI 環境中的問題。
    """
    _login_user_directly(client, app, test_user, test_org)
    return client


@pytest.fixture
def admin_client(client, app, test_admin, test_org):
    """
    Create authenticated admin test client.
    """
    _login_user_directly(client, app, test_admin, test_org)
    return client
