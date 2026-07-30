"""Platform fixed_filters variable fail-closed tests."""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("SYSTEM_ORG_CODE", "system.local")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from modules.nocode_builder.services.crud_service import (
    FilterVariableNotSupported,
    resolve_filter_variables as resolve_postgres_filter_variables,
)
from modules.nocode_builder.services.sqlite_crud_service import (
    resolve_filter_variables as resolve_sqlite_filter_variables,
)


@pytest.fixture(params=[resolve_postgres_filter_variables, resolve_sqlite_filter_variables])
def resolve_filter_variables(request):
    return request.param


@pytest.mark.parametrize(
    ("variable", "expected"),
    [
        ("$CURRENT_USER", "platform_user_sc"),
        ("$CURRENT_USER_NAME", "platform_user"),
        ("$CURRENT_ORG", "platform_org_sc"),
    ],
)
def test_platform_context_resolves_current_user_variables(
    resolve_filter_variables,
    variable,
    expected,
):
    user = SimpleNamespace(
        secure_code="platform_user_sc",
        username="platform_user",
        org_secure_code="platform_org_sc",
        is_authenticated=True,
    )

    assert resolve_filter_variables({"owner": variable}, user=user) == {"owner": expected}


def test_platform_context_rejects_unknown_variables(resolve_filter_variables):
    with pytest.raises(FilterVariableNotSupported):
        resolve_filter_variables({"owner": "$FOO"})


@pytest.mark.parametrize("variable", ["$CURRENT_USER", "$CURRENT_USER_NAME", "$CURRENT_ORG"])
def test_platform_context_rejects_identity_variables_without_user(
    resolve_filter_variables,
    variable,
):
    with pytest.raises(FilterVariableNotSupported):
        resolve_filter_variables({"owner": variable}, user=None)


@pytest.mark.parametrize("variable", ["$CURRENT_USER", "$CURRENT_USER_NAME", "$CURRENT_ORG"])
def test_platform_context_rejects_anonymous_user(resolve_filter_variables, variable):
    anonymous_user = SimpleNamespace(is_authenticated=False)

    with pytest.raises(FilterVariableNotSupported):
        resolve_filter_variables({"owner": variable}, user=anonymous_user)


def test_platform_context_allows_today_variable(resolve_filter_variables):
    assert resolve_filter_variables({"created_on": "$TODAY"}) == {
        "created_on": date.today().isoformat()
    }


def test_platform_context_allows_literal_values(resolve_filter_variables):
    filters = {"status": "ACTIVE", "count": 1, "missing": None}

    assert resolve_filter_variables(filters) == filters


@pytest.mark.parametrize("filters", [{}, None])
def test_platform_context_empty_filters_return_empty_dict(resolve_filter_variables, filters):
    assert resolve_filter_variables(filters) == {}
