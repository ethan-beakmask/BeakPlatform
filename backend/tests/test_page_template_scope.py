"""PF-25 page template scope API tests."""
from __future__ import annotations

import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.ext.compiler import compiles

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("SYSTEM_ORG_CODE", "system.local")
os.environ.setdefault("SKIP_MODULE_SYNC", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import create_app, db
from app.models import Organization, User
from app.models.user import UserType
from app.security.resource_gateway import ResourceGateway
from modules.nocode_builder.models import DcPageTemplate, DcSubSystem


API_PREFIX = "/beakplatform/api/nocode-builder"


@pytest.fixture(scope="function")
def app():
    from app.module_loader import module_loader

    module_loader._loaded = False
    module_loader.modules.clear()
    for name in list(sys.modules):
        if name == "modules.nocode_builder.api" or name.startswith("modules.nocode_builder.api."):
            del sys.modules[name]
    flask_app = create_app("testing")

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@compiles(JSONB, "sqlite")
def _compile_jsonb_on_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(INET, "sqlite")
def _compile_inet_on_sqlite(type_, compiler, **kw):
    return "TEXT"


@pytest.fixture(autouse=True)
def bypass_page_template_list_rbac(monkeypatch):
    monkeypatch.setattr(
        ResourceGateway,
        "_check_collection_permission",
        staticmethod(lambda *args, **kwargs: None),
    )


@pytest.fixture
def second_org_admin(app, db_session):
    org = Organization(
        secure_code="test_org_00000000002",
        code="TEST_ORG_2",
        name="Second Organization",
        domain_name="test2.local",
        is_active=True,
        is_deleted=False,
    )
    admin = User(
        secure_code="test_admin_0000000002",
        org_secure_code=org.secure_code,
        username="testadmin2",
        email="admin2@example.com",
        display_name="Second Admin",
        user_type=UserType.ORG_ADMIN,
        is_active=True,
        is_deleted=False,
    )
    admin.set_password("password123")
    db_session.add_all([org, admin])
    db_session.commit()
    return org, admin


def _login(client, user, org):
    with client.session_transaction() as sess:
        sess["_user_id"] = user.get_id()
        sess["_fresh"] = True
        sess["org_secure_code"] = org.secure_code
        sess["org_domain"] = org.domain_name


def _valid_layout():
    return {
        "ir_version": 3,
        "page": {
            "id": "template-test-page",
            "title_i18n": {"zh-TW": "樣板測試"},
            "widgets": [
                {
                    "id": "page-title",
                    "type": "text",
                    "level": "h1",
                    "content_i18n": {"zh-TW": "樣板測試"},
                }
            ],
        },
    }


def _payload(**overrides):
    data = {
        "name": "測試樣板",
        "description": "desc",
        "category": "常用",
        "layout_json": _valid_layout(),
        "style_config": {},
        "thumbnail_svg": "",
    }
    data.update(overrides)
    return data


def _template(
    db_session,
    *,
    secure_code,
    name,
    org_secure_code,
    scope="org",
    sub_system_secure_code=None,
    created_at=None,
):
    tpl = DcPageTemplate(
        secure_code=secure_code,
        org_secure_code=org_secure_code,
        scope=scope,
        sub_system_secure_code=sub_system_secure_code,
        name=name,
        category="常用",
        layout_json=_valid_layout(),
        style_config={},
        is_active=True,
        is_deleted=False,
        created_at=created_at or datetime.utcnow(),
    )
    db_session.add(tpl)
    db_session.commit()
    return tpl


def _sub_system(db_session, org_sc, secure_code="subsystem_00000001"):
    sub = DcSubSystem(
        secure_code=secure_code,
        org_secure_code=org_sc,
        code="SUB",
        name="子系統",
        is_active=True,
        is_deleted=False,
    )
    db_session.add(sub)
    db_session.commit()
    return sub


def test_create_without_scope_defaults_to_org(admin_client, db_session, test_org):
    resp = admin_client.post(f"{API_PREFIX}/templates", json=_payload())

    assert resp.status_code == 200
    secure_code = resp.get_json()["data"]["secure_code"]
    tpl = db_session.query(DcPageTemplate).filter_by(secure_code=secure_code).one()
    assert tpl.scope == "org"
    assert tpl.org_secure_code == test_org.secure_code
    assert tpl.sub_system_secure_code is None


def test_create_system_scope_is_rejected(admin_client):
    resp = admin_client.post(
        f"{API_PREFIX}/templates",
        json=_payload(scope="system"),
    )

    assert resp.status_code == 403


def test_create_sub_system_scope_requires_sub_system_secure_code(admin_client):
    resp = admin_client.post(
        f"{API_PREFIX}/templates",
        json=_payload(scope="sub_system"),
    )

    assert resp.status_code == 400


def test_create_sub_system_scope_rejects_missing_sub_system(admin_client):
    resp = admin_client.post(
        f"{API_PREFIX}/templates",
        json=_payload(scope="sub_system", sub_system_secure_code="missing_subsystem1"),
    )

    assert resp.status_code == 404


def test_list_without_sub_system_returns_system_and_org_only(
    admin_client,
    db_session,
    test_org,
):
    now = datetime.utcnow()
    _template(
        db_session,
        secure_code="system_tpl_000001",
        name="內建",
        org_secure_code=None,
        scope="system",
        created_at=now,
    )
    _template(
        db_session,
        secure_code="org_tpl_00000001",
        name="企業",
        org_secure_code=test_org.secure_code,
        scope="org",
        created_at=now - timedelta(minutes=1),
    )
    _template(
        db_session,
        secure_code="sub_tpl_00000001",
        name="子系統",
        org_secure_code=test_org.secure_code,
        scope="sub_system",
        sub_system_secure_code="subsystem_00000001",
        created_at=now - timedelta(minutes=2),
    )

    resp = admin_client.get(f"{API_PREFIX}/templates")

    assert resp.status_code == 200
    names = [item["name"] for item in resp.get_json()["data"]]
    assert names == ["內建", "企業"]


def test_list_with_sub_system_includes_private_templates(
    admin_client,
    db_session,
    test_org,
):
    now = datetime.utcnow()
    sub = _sub_system(db_session, test_org.secure_code)
    _template(
        db_session,
        secure_code="system_tpl_000002",
        name="內建",
        org_secure_code=None,
        scope="system",
        created_at=now,
    )
    _template(
        db_session,
        secure_code="org_tpl_00000002",
        name="企業",
        org_secure_code=test_org.secure_code,
        scope="org",
        created_at=now - timedelta(minutes=1),
    )
    _template(
        db_session,
        secure_code="sub_tpl_00000002",
        name="子系統",
        org_secure_code=test_org.secure_code,
        scope="sub_system",
        sub_system_secure_code=sub.secure_code,
        created_at=now - timedelta(minutes=2),
    )

    resp = admin_client.get(f"{API_PREFIX}/templates?sub_system={sub.secure_code}")

    assert resp.status_code == 200
    names = [item["name"] for item in resp.get_json()["data"]]
    assert names == ["內建", "企業", "子系統"]


def test_system_templates_are_shared_but_org_templates_remain_tenant_scoped(
    client,
    app,
    db_session,
    test_org,
    second_org_admin,
):
    second_org, second_admin = second_org_admin
    _template(
        db_session,
        secure_code="system_tpl_000003",
        name="跨企業內建",
        org_secure_code=None,
        scope="system",
    )
    _template(
        db_session,
        secure_code="org_tpl_00000003",
        name="第一企業自建",
        org_secure_code=test_org.secure_code,
        scope="org",
    )
    _login(client, second_admin, second_org)

    resp = client.get(f"{API_PREFIX}/templates")

    assert resp.status_code == 200
    names = [item["name"] for item in resp.get_json()["data"]]
    assert "跨企業內建" in names
    assert "第一企業自建" not in names


def test_update_and_delete_system_template_are_not_reachable_through_tenant_get(
    admin_client,
    db_session,
):
    tpl = _template(
        db_session,
        secure_code="system_tpl_000004",
        name="不可異動內建",
        org_secure_code=None,
        scope="system",
    )

    update_resp = admin_client.put(
        f"{API_PREFIX}/templates/{tpl.secure_code}",
        json={"name": "new name"},
    )
    delete_resp = admin_client.delete(f"{API_PREFIX}/templates/{tpl.secure_code}")

    # Current ResourceGateway.get() applies tenant filtering before the API's
    # second-defense system-scope guard, so system templates return 404 here.
    assert update_resp.status_code == 404
    assert delete_resp.status_code == 404
