"""Portal SQLite row-level ownership tests."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("SYSTEM_ORG_CODE", "system.local")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from modules.nocode_builder.services.sqlite_crud_service import (
    OWNER_REF_PLATFORM,
    PortalFilterNotSupported,
    SqliteCrudService,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Session = sessionmaker(bind=engine)
    sess = Session()
    sess.execute(
        text(
            """
            CREATE TABLE feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                portal_user_ref TEXT,
                is_deleted INTEGER DEFAULT 0
            )
            """
        )
    )
    sess.execute(
        text(
            """
            INSERT INTO feedback (title, portal_user_ref, is_deleted)
            VALUES
                ('mine', 'u:1', 0),
                ('other', 'u:2', 0),
                ('null-owner', NULL, 0)
            """
        )
    )
    try:
        yield sess
    finally:
        sess.close()
        engine.dispose()


def _view(scope="own", table_name="feedback", soft_delete_column=None):
    return SimpleNamespace(
        secure_code="view_sc",
        table_name=table_name,
        columns_config=[
            {"column": "id", "db_type": "INTEGER", "is_pk": True, "visible": True},
            {"column": "title", "db_type": "TEXT", "visible": True, "visible_in_form": True},
            {"column": "portal_user_ref", "db_type": "TEXT", "visible": True, "visible_in_form": True},
            {"column": "is_deleted", "db_type": "INTEGER", "visible": True, "visible_in_form": True},
        ],
        fixed_filters={},
        soft_delete_column=soft_delete_column,
        default_sort_column="id",
        default_sort_dir="ASC",
        row_owner_scope=scope,
    )


def _title(session, row_id):
    return session.execute(
        text("SELECT title FROM feedback WHERE id = :id"),
        {"id": row_id},
    ).scalar()


def _owner(session, row_id):
    return session.execute(
        text("SELECT portal_user_ref FROM feedback WHERE id = :id"),
        {"id": row_id},
    ).scalar()


def test_own_scope_query_rows_returns_only_owner_and_hides_null_owner(session):
    result = SqliteCrudService.query_rows(
        session=session,
        view=_view(),
        per_page=20,
        owner_ref="u:1",
    )

    assert [row["title"] for row in result["rows"]] == ["mine"]


def test_own_scope_get_row_for_other_owner_is_not_found(session):
    result = SqliteCrudService.get_row(session, _view(), "2", owner_ref="u:1")

    assert result == {"success": False, "error": "Row not found"}


def test_own_scope_update_other_owner_fails_and_does_not_modify_data(session):
    result = SqliteCrudService.update_row(
        session,
        _view(),
        "2",
        {"title": "changed"},
        owner_ref="u:1",
    )

    assert result == {"success": False, "error": "Row not found"}
    assert _title(session, 2) == "other"


def test_own_scope_delete_other_owner_fails_and_row_remains(session):
    result = SqliteCrudService.delete_row(session, _view(), "2", owner_ref="u:1")

    assert result == {"success": False, "error": "Row not found"}
    assert _title(session, 2) == "other"


def test_own_scope_create_fills_owner_and_ignores_payload_owner(session):
    result = SqliteCrudService.create_row(
        session,
        _view(),
        {"title": "new", "portal_user_ref": "u:999"},
        owner_ref="u:1",
    )

    assert result["success"] is True
    row_id = result["row_id"]
    assert _owner(session, row_id) == "u:1"


def test_own_scope_update_payload_cannot_change_owner(session):
    result = SqliteCrudService.update_row(
        session,
        _view(),
        "1",
        {"title": "changed", "portal_user_ref": "u:999"},
        owner_ref="u:1",
    )

    assert result["success"] is True
    assert _title(session, 1) == "changed"
    assert _owner(session, 1) == "u:1"


@pytest.mark.parametrize(
    "method,args",
    [
        ("query_rows", ()),
        ("get_row", ("1",)),
        ("create_row", ({"title": "new"},)),
        ("update_row", ("1", {"title": "changed"})),
        ("delete_row", ("1",)),
    ],
)
def test_own_scope_without_owner_ref_rejects_all_crud_methods(session, method, args):
    with pytest.raises(PortalFilterNotSupported):
        getattr(SqliteCrudService, method)(session, _view(), *args, owner_ref=None)


def test_platform_owner_ref_does_not_filter_and_create_leaves_owner_null(session):
    result = SqliteCrudService.query_rows(
        session=session,
        view=_view(),
        per_page=20,
        owner_ref=OWNER_REF_PLATFORM,
    )
    assert [row["title"] for row in result["rows"]] == ["mine", "other", "null-owner"]

    created = SqliteCrudService.create_row(
        session,
        _view(),
        {"title": "platform"},
        owner_ref=OWNER_REF_PLATFORM,
    )
    assert created["success"] is True
    assert _owner(session, created["row_id"]) is None


def test_all_scope_does_not_filter_for_any_owner_ref(session):
    result = SqliteCrudService.query_rows(
        session=session,
        view=_view(scope="all"),
        per_page=20,
        owner_ref="u:1",
    )

    assert [row["title"] for row in result["rows"]] == ["mine", "other", "null-owner"]


def test_own_scope_identity_owner_ref_requires_portal_user_ref_column(session):
    session.execute(text("CREATE TABLE legacy_feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT)"))
    session.execute(text("INSERT INTO legacy_feedback (title) VALUES ('legacy')"))

    with pytest.raises(PortalFilterNotSupported):
        SqliteCrudService.query_rows(
            session=session,
            view=_view(table_name="legacy_feedback"),
            owner_ref="u:1",
        )


def test_missing_row_owner_scope_attribute_defaults_to_own(session):
    view = _view()
    delattr(view, "row_owner_scope")

    result = SqliteCrudService.query_rows(
        session=session,
        view=view,
        per_page=20,
        owner_ref="u:1",
    )

    assert [row["title"] for row in result["rows"]] == ["mine"]
