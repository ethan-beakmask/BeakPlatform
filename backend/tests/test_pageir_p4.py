"""Page IR v3 P4 portal SQLite resolver tests."""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask
from markupsafe import escape
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.pageir import PageIrRenderError, render_page_ir, validate_page_ir
from app.pageir.context import clear_render_context, set_render_context
from app.pageir.registry import (
    _PROVIDERS,
    _RESOURCES,
    register_resource,
    register_resource_provider,
    get_resource,
)

os.environ.setdefault("SYSTEM_ORG_CODE", "system.local")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


@pytest.fixture
def pir_app():
    app = Flask(__name__, template_folder="../app/templates")
    app.secret_key = "test-secret"
    app.jinja_env.globals["_"] = lambda text, **kwargs: text % kwargs if kwargs else text
    app.jinja_env.globals["egress_visibility"] = lambda resource, context, field: "clear"
    app.jinja_env.globals["egress_value"] = (
        lambda resource, context, record_sc, field, value: escape(value)
    )
    app.jinja_env.filters["tz_format"] = lambda value, fmt="%Y-%m-%d %H:%M": "DATE"
    return app


@pytest.fixture(autouse=True)
def reset_pageir_registry():
    old_resources = dict(_RESOURCES)
    old_providers = dict(_PROVIDERS)
    _RESOURCES.clear()
    _PROVIDERS.clear()
    yield
    _RESOURCES.clear()
    _RESOURCES.update(old_resources)
    _PROVIDERS.clear()
    _PROVIDERS.update(old_providers)


def _doc(widgets):
    return {
        "ir_version": 3,
        "page": {
            "id": "p4-page",
            "title_i18n": {"zh-TW": "P4"},
            "widgets": widgets,
        },
    }


def _table_widget(resource="fake", fields=None):
    fields = fields or ["name", "email"]
    return {
        "id": "tbl",
        "type": "table",
        "binding": {"resource": resource, "view": "list", "fields": fields},
        "columns": [
            {"field": fields[0], "label_i18n": {"zh-TW": "姓名"}, "sortable": True},
        ],
        "page_size": 20,
    }


def test_registry_worlds_are_mutually_exclusive(pir_app):
    register_resource("user", {"fields": ["name"], "views": ["list"]})
    seen = {}

    def provider(code, ctx):
        seen["code"] = code
        seen["ctx"] = ctx
        return {"fields": ["name"], "views": ["list"], "egress_resource": None}

    with pir_app.test_request_context("/"):
        assert get_resource("portal:abc") is None

        set_render_context("portal", sub_system_sc="ss_123")
        assert get_resource("user") is None
        register_resource_provider("portal", provider)
        assert get_resource("portal:abc")["fields"] == ["name"]
        assert get_resource("other:abc") is None
        assert seen["ctx"]["sub_system_sc"] == "ss_123"
        clear_render_context()


def test_schema_resource_ref_allows_only_portal_prefix_exception():
    doc = _doc([_table_widget(resource="portal:AbCd1234xyz")])
    ok, errors = validate_page_ir(doc)
    assert ok, errors

    for resource in ("bogus:xxx", "PORTAL:xxx"):
        invalid = _doc([_table_widget(resource=resource)])
        ok, _ = validate_page_ir(invalid)
        assert not ok

    invalid_view = _doc([_table_widget(resource="portal:AbCd1234xyz")])
    invalid_view["page"]["widgets"][0]["binding"]["view"] = "list:detail"
    ok, _ = validate_page_ir(invalid_view)
    assert not ok


def test_portal_context_rejects_platform_table_resource(pir_app):
    register_resource(
        "fake",
        {
            "fields": ["name", "email"],
            "egress_resource": None,
            "views": ["list"],
            "fetch_list": lambda *args: ([{"_sc": "1", "name": "Alice"}], 1),
        },
    )

    with pir_app.test_request_context("/"):
        set_render_context("portal", sub_system_sc="ss_123")
        with pytest.raises(PageIrRenderError):
            render_page_ir(_doc([_table_widget(resource="fake")]))
        clear_render_context()


def test_portal_resolver_fetch_list_whitelists_fields_and_adds_sc(tmp_path, monkeypatch):
    from modules.nocode_builder.services import pageir_portal_resources as portal_resources

    view = SimpleNamespace(
        secure_code="View1234",
        name="Guests",
        org_secure_code="org_1",
        data_source="portal_data",
        table_name="guests",
        columns_config=[
            {"column": "id", "visible": True, "is_pk": True, "sort_order": 0},
            {"column": "name", "visible": True, "sort_order": 1},
            {"column": "secret", "visible": False, "sort_order": 2},
        ],
        soft_delete_column=None,
        fixed_filters={},
        default_sort_column="id",
        default_sort_dir="ASC",
    )
    sub_system = SimpleNamespace(secure_code="ss_123", org_secure_code="org_1")

    class FakeQuery:
        def __init__(self, value):
            self.value = value

        def filter_by(self, **kwargs):
            return self

        def first(self):
            return self.value

    monkeypatch.setattr(portal_resources, "DcCrudView", SimpleNamespace(query=FakeQuery(view)))
    monkeypatch.setattr(portal_resources, "DcSubSystem", SimpleNamespace(query=FakeQuery(sub_system)))

    db_path = tmp_path / "portal_data.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        poolclass=NullPool,
        connect_args={"check_same_thread": False},
    )
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE guests (id INTEGER PRIMARY KEY, name TEXT, secret TEXT)"))
        conn.execute(text("INSERT INTO guests (id, name, secret) VALUES (1, 'Alice', 'hidden')"))
        conn.execute(text("INSERT INTO guests (id, name, secret) VALUES (2, 'Bob', 'hidden')"))
    factory = sessionmaker(bind=engine)

    class FakeManager:
        @contextmanager
        def get_session(self, sub_system_sc, source_type):
            assert sub_system_sc == "ss_123"
            assert source_type == "portal_data"
            session = factory()
            try:
                yield session
            finally:
                session.close()

    monkeypatch.setattr(portal_resources, "DataSourceManager", FakeManager)

    config = portal_resources._resolve_portal_resource(
        "portal:View1234",
        {"world": "portal", "sub_system_sc": "ss_123"},
    )
    assert config is not None
    assert config["fields"] == ["id", "name"]

    rows, total = config["fetch_list"](["id", "name", "secret"], 1, 20, "secret", "desc")
    assert total == 2
    assert rows == [
        {"id": 2, "name": "Bob", "_sc": "2"},
        {"id": 1, "name": "Alice", "_sc": "1"},
    ]


def test_portal_binding_fields_outside_resolver_whitelist_fails_closed(pir_app):
    register_resource_provider(
        "portal",
        lambda code, ctx: {
            "fields": ["name"],
            "egress_resource": None,
            "views": ["list"],
            "fetch_list": lambda *args: ([{"_sc": "1", "name": "Alice"}], 1),
        },
    )
    doc = _doc([
        _table_widget(resource="portal:AbCd1234xyz", fields=["name", "secret"])
    ])

    with pir_app.test_request_context("/"):
        set_render_context("portal", sub_system_sc="ss_123")
        with pytest.raises(PageIrRenderError):
            render_page_ir(doc)
        clear_render_context()
