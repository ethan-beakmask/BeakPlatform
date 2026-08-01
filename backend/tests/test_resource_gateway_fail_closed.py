"""ResourceGateway fail-closed RBAC tests."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.exceptions import PermissionDeniedError
from app.security.resource_gateway import ResourceGateway


class UnknownModel:
    pass


class DcSubSystem:
    pass


class User:
    pass


CRUD_CHECKS = (
    (ResourceGateway._check_view_permission, (UnknownModel, object())),
    (ResourceGateway._check_create_permission, (UnknownModel,)),
    (ResourceGateway._check_edit_permission, (UnknownModel, object())),
    (ResourceGateway._check_delete_permission, (UnknownModel, object())),
)

EXEMPT_CRUD_CHECKS = (
    (ResourceGateway._check_view_permission, (DcSubSystem, object())),
    (ResourceGateway._check_create_permission, (DcSubSystem,)),
    (ResourceGateway._check_edit_permission, (DcSubSystem, object())),
    (ResourceGateway._check_delete_permission, (DcSubSystem, object())),
)


@pytest.mark.parametrize(("check", "args"), CRUD_CHECKS)
def test_crud_permission_fail_closed_for_unknown_model_with_user(check, args):
    with patch.object(ResourceGateway, "_get_current_user", return_value=object()):
        with pytest.raises(PermissionDeniedError) as exc_info:
            check(*args)

    assert "Unregistered model for ResourceGateway RBAC: UnknownModel" in str(exc_info.value)


@pytest.mark.parametrize(("check", "args"), EXEMPT_CRUD_CHECKS)
def test_crud_permission_allows_exempt_model_with_user(check, args):
    with patch.object(ResourceGateway, "_get_current_user", return_value=object()):
        check(*args)


@pytest.mark.parametrize(("check", "args"), CRUD_CHECKS)
def test_crud_permission_allows_unknown_model_without_user_context(check, args):
    with patch.object(ResourceGateway, "_get_current_user", return_value=None):
        check(*args)


def test_collection_permission_fail_closed_for_unknown_model_with_user():
    with patch.object(ResourceGateway, "_get_current_user", return_value=object()):
        with pytest.raises(PermissionDeniedError) as exc_info:
            ResourceGateway._check_collection_permission(
                UnknownModel,
                require_permission=None,
                check_permission=True,
            )

    assert "Unregistered model for ResourceGateway list RBAC: UnknownModel" in str(
        exc_info.value
    )


def test_collection_permission_allows_unknown_model_when_check_disabled():
    with patch.object(ResourceGateway, "_get_current_user", return_value=object()):
        ResourceGateway._check_collection_permission(
            UnknownModel,
            require_permission=None,
            check_permission=False,
        )


def test_collection_permission_uses_explicit_required_permission():
    with patch.object(ResourceGateway, "_check_list_permission") as check_list_permission:
        ResourceGateway._check_collection_permission(
            UnknownModel,
            require_permission="custom:read",
            check_permission=True,
        )

    check_list_permission.assert_called_once_with("custom:read")


def test_collection_permission_allows_exempt_model():
    with patch.object(ResourceGateway, "_get_current_user", return_value=object()):
        ResourceGateway._check_collection_permission(
            DcSubSystem,
            require_permission=None,
            check_permission=True,
        )


def test_collection_permission_checks_enforced_model_read_permission():
    with patch.object(ResourceGateway, "_check_list_permission") as check_list_permission:
        ResourceGateway._check_collection_permission(
            User,
            require_permission=None,
            check_permission=True,
        )

    check_list_permission.assert_called_once_with("user:read")


def test_collection_permission_allows_unknown_model_without_user_context():
    with patch.object(ResourceGateway, "_get_current_user", return_value=None):
        ResourceGateway._check_collection_permission(
            UnknownModel,
            require_permission=None,
            check_permission=True,
        )
