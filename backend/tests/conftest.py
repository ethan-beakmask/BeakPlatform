"""
BeakMask Test Configuration
pytest fixtures and configuration
"""
import os

import pytest
from flask import session
from flask_login import login_user
from app import create_app, db
from app.models import User, Organization


def pytest_configure(config):
    """整個 session 開跑前先擋。

    放在這裡而不是只放 app fixture，是因為 test_smoke.py /
    test_page_template_instantiate.py / test_page_template_scope.py
    都各自定義了會 drop_all() 的 app fixture，覆蓋掉本檔的版本。
    """
    del config
    _assert_disposable_database(os.getenv('DATABASE_URL', 'sqlite:///:memory:'))


def _assert_disposable_database(uri: str) -> None:
    """擋下「測試跑在非拋棄式資料庫」的情況。

    TestingConfig 的 URI 是 os.getenv('DATABASE_URL', 'sqlite:///:memory:')，
    而專案的標準操作是先 `set -a && source .env && set +a` 再跑 flask/pytest。
    .env 的 DATABASE_URL 指向開發庫 beakplatform_dev，於是整組測試會直接跑在
    開發資料庫上，而底下的 app fixture 收尾時會呼叫 db.drop_all()。

    2026-08-05 之前一直沒出事，只是因為 drop_all() 被大量 FK 相依擋下來而拋例外
    （症狀就是那批 "ERROR at teardown"），不是設計上有防護。同一批 error 的另一半
    "ERROR at setup" 則是前一次跑測試留在開發庫裡的 test_org 撞 unique。

    允許的目標只有兩種：SQLite（含 in-memory）、或名稱以 _test 結尾的資料庫。
    CI 本來就用 beakplatform_test，符合。
    """
    if uri.startswith('sqlite'):
        return
    db_name = uri.rsplit('/', 1)[-1].split('?', 1)[0]
    if db_name.endswith('_test'):
        return
    pytest.exit(
        f"拒絕在非測試資料庫上執行測試：{db_name}\n"
        "app fixture 會呼叫 db.drop_all()，跑在開發庫上等於準備刪光它。\n"
        "請改成：\n"
        "  DATABASE_URL=postgresql://beakplatform:yourpassword@localhost/beakplatform_test \\\n"
        "    ../venv/bin/python -m pytest ...\n"
        "（測試庫不存在時：sudo -u postgres createdb -O beakplatform beakplatform_test）",
        returncode=1,
    )


@pytest.fixture(scope='function')
def app():
    """Create application for testing."""
    app = create_app('testing')
    _assert_disposable_database(app.config.get('SQLALCHEMY_DATABASE_URI', ''))

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
def rbac_seed(app):
    """種入出廠權限定義（PF-34，2026-09-06）。

    測試庫是 db.create_all() 建的空表，permissions 表沒有任何定義。
    PermissionService.check() 第一步是查定義、查不到就 return False，
    ORG_ADMIN 的 bypass 在第二步輪不到——所以 admin 打任何走 ResourceGateway
    的端點都 403（症狀：Unknown permission code: user:read）。

    權威清單是 app/models/permission.py 的 DEFAULT_PERMISSIONS（PF-241 起），
    透過 seed_system_permissions() 種入，不另外手寫會漂移的清單。
    刻意做成 opt-in、不掛在 app fixture：test_permission_defaults.py 斷言
    「第一次 seed 建出全部筆數」，自動種入會讓它變 0。

    PermissionService 的快取是類別層級、跨測試存活，而測試之間會 drop_all()，
    前後都要清，否則上一個測試的 Permission 物件會漂進下一個測試。
    """
    from app.defaults.permission_defaults import seed_system_permissions
    from app.services.permission_service import PermissionService

    PermissionService.clear_cache()
    seed_system_permissions()
    yield
    PermissionService.clear_cache()


@pytest.fixture
def admin_client(client, app, test_admin, test_org, rbac_seed):
    """
    Create authenticated admin test client.

    依賴 rbac_seed：經 HTTP 以管理員身分測的端點，都該在有出廠權限的環境下跑，
    這才是真實環境（開發庫與 fresh install 都有這批定義）。
    """
    _login_user_directly(client, app, test_admin, test_org)
    return client
