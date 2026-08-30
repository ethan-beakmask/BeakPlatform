from app import db
from app.models.organization import (
    DEFAULT_ORG_USER_LIMIT,
    Organization,
    counts_toward_user_limit,
)
from app.models.user import User, UserType


def _create_org(code='LIMITED', user_limit=2):
    org = Organization(
        code=code,
        name=f'{code} Organization',
        domain_name=f'{code.lower()}.local',
        user_limit=user_limit,
        is_active=True,
        is_deleted=False,
    )
    db.session.add(org)
    db.session.flush()
    return org


def _create_user(org, username, user_type=UserType.EMPLOYEE, is_active=True,
                 is_deleted=False, is_service_account=False):
    user = User(
        org_secure_code=org.secure_code,
        username=username,
        email=f'{username}@{org.domain_name}',
        display_name=username,
        password_hash='test-password-hash',
        user_type=user_type,
        is_active=is_active,
        is_deleted=is_deleted,
        is_service_account=is_service_account,
    )
    db.session.add(user)
    db.session.flush()
    return user


def test_active_user_count_excludes_administrators(app, db_session):
    org = _create_org()
    _create_user(org, 'employee', UserType.EMPLOYEE)
    _create_user(org, 'external', UserType.EXTERNAL)
    _create_user(org, 'org-admin', UserType.ORG_ADMIN)
    _create_user(org, 'sys-admin', UserType.SYSTEM_ADMIN)

    assert org.get_active_user_count() == 2


def test_active_user_count_excludes_inactive_and_deleted_users(app, db_session):
    org = _create_org(user_limit=5)
    _create_user(org, 'active-employee', UserType.EMPLOYEE)
    _create_user(org, 'inactive-employee', UserType.EMPLOYEE, is_active=False)
    _create_user(org, 'deleted-external', UserType.EXTERNAL, is_deleted=True)

    assert org.get_active_user_count() == 1


def test_active_user_count_excludes_service_accounts(app, db_session):
    """NoCode portal 的公用送件帳號是 EXTERNAL，但不是人頭、也不出現在外部廠商列表"""
    org = _create_org(user_limit=5)
    _create_user(org, 'external', UserType.EXTERNAL)
    _create_user(org, 'nocode-svc', UserType.EXTERNAL, is_service_account=True)

    assert org.get_active_user_count() == 1


def test_can_create_user_returns_true_before_limit(app, db_session):
    org = _create_org(user_limit=2)
    _create_user(org, 'employee', UserType.EMPLOYEE)

    assert org.can_create_user() is True


def test_can_create_user_returns_false_at_limit(app, db_session):
    org = _create_org(user_limit=2)
    _create_user(org, 'employee', UserType.EMPLOYEE)
    _create_user(org, 'external', UserType.EXTERNAL)

    assert org.can_create_user() is False


def test_can_create_org_admin_when_count_is_over_limit(app, db_session):
    org = _create_org(user_limit=1)
    _create_user(org, 'employee', UserType.EMPLOYEE)
    _create_user(org, 'external', UserType.EXTERNAL)

    assert org.can_create_user(UserType.ORG_ADMIN) is True


def test_can_create_system_admin_when_count_is_over_limit(app, db_session):
    org = _create_org(user_limit=1)
    _create_user(org, 'employee', UserType.EMPLOYEE)
    _create_user(org, 'external', UserType.EXTERNAL)

    assert org.can_create_user(UserType.SYSTEM_ADMIN) is True


def test_employee_user_type_matches_default_can_create_semantics(app, db_session):
    org = _create_org(user_limit=1)
    _create_user(org, 'employee', UserType.EMPLOYEE)

    assert org.can_create_user(UserType.EMPLOYEE) == org.can_create_user()


def test_deactivating_employee_releases_user_limit_slot(app, db_session):
    org = _create_org(user_limit=1)
    user = _create_user(org, 'employee', UserType.EMPLOYEE)
    assert org.can_create_user() is False

    user.is_active = False
    db.session.flush()

    assert org.get_active_user_count() == 0
    assert org.can_create_user() is True


def test_counts_toward_user_limit_for_all_user_types():
    assert counts_toward_user_limit(UserType.EMPLOYEE) is True
    assert counts_toward_user_limit(UserType.EXTERNAL) is True
    assert counts_toward_user_limit(UserType.ORG_ADMIN) is False
    assert counts_toward_user_limit(UserType.SYSTEM_ADMIN) is False


def test_default_org_user_limit_constant_and_model_default(app, db_session):
    org = Organization(
        code='DEFAULT_LIMIT',
        name='Default Limit Organization',
        domain_name='default-limit.local',
        is_active=True,
        is_deleted=False,
    )
    db.session.add(org)
    db.session.flush()

    assert DEFAULT_ORG_USER_LIMIT == 50
    assert org.user_limit == DEFAULT_ORG_USER_LIMIT
