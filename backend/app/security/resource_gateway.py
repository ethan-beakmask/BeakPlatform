"""
BeakMask Resource Gateway
統一資源存取閘道

[標準 TENANT-02] 資源閘道
API 層不直接查詢資料庫，必須經過 ResourceGateway

所有資源的 CRUD 操作都必須透過這個閘道：
1. 自動套用租戶過濾
2. 自動檢查權限
3. 記錄存取日誌
4. 驗證 secure_code 格式
"""
import logging
import re
from typing import Any, Dict, List, Optional, Type, TypeVar

from flask import g
from sqlalchemy import select
from sqlalchemy.orm import Query

from .tenant_isolation import get_current_tenant

# secure_code 格式驗證 (10-32 字元的 URL-safe 字串)
SECURE_CODE_PATTERN = re.compile(r'^[A-Za-z0-9_-]{10,32}$')

# Model 到資源類型的映射
MODEL_RESOURCE_TYPE_MAP = {
    'User': 'user',
    'Organization': 'organization',
    'OrganizationalUnit': 'department',
    'Role': 'role',
    'Module': 'module',
    'MenuItem': 'module_content',
    # 未來擴展
    # 'FormTemplate': 'form_template',
    # 'FormInstance': 'form_instance',
    # 'FlowDefinition': 'flow_definition',
    # 'FlowInstance': 'flow_instance',
}

logger = logging.getLogger(__name__)

T = TypeVar('T')


class ResourceGateway:
    """
    統一資源存取閘道。

    Usage:
        # Get single resource
        form = ResourceGateway.get(Form, form_secure_code)

        # Get list with filters
        forms = ResourceGateway.list(Form, status='active')

        # Create
        form = ResourceGateway.create(Form, name='New Form', ...)

        # Update
        ResourceGateway.update(form, name='Updated Name')

        # Delete
        ResourceGateway.delete(form)
    """

    @staticmethod
    def get(
        model_class: Type[T],
        secure_code: str,
        *,
        raise_on_not_found: bool = True,
        check_permission: bool = True
    ) -> Optional[T]:
        """
        透過 secure_code 取得單一資源。

        Args:
            model_class: Model class
            secure_code: 資源的 secure_code
            raise_on_not_found: 找不到時是否拋出例外
            check_permission: 是否檢查權限

        Returns:
            Model instance or None

        Raises:
            ResourceNotFoundError: 找不到資源 (如果 raise_on_not_found=True)
            PermissionDeniedError: 沒有權限
        """
        # 驗證 secure_code 格式 (防止惡意輸入)
        if not secure_code or not SECURE_CODE_PATTERN.match(secure_code):
            logger.warning(
                f"Invalid secure_code format: {secure_code!r} "
                f"model={model_class.__name__}"
            )
            if raise_on_not_found:
                from ..exceptions import ResourceNotFoundError
                raise ResourceNotFoundError(model_class.__name__, secure_code)
            return None

        tenant = get_current_tenant()

        # Build query with tenant filter
        query = model_class.query.filter_by(secure_code=secure_code)

        # Apply tenant filter if model has org_secure_code
        if hasattr(model_class, 'org_secure_code') and tenant:
            query = query.filter_by(org_secure_code=tenant)

        resource = query.first()

        if resource is None:
            if raise_on_not_found:
                logger.warning(
                    f"Resource not found: {model_class.__name__} "
                    f"secure_code={secure_code} tenant={tenant}"
                )
                from ..exceptions import ResourceNotFoundError
                raise ResourceNotFoundError(model_class.__name__, secure_code)
            return None

        # Permission check
        if check_permission:
            ResourceGateway._check_view_permission(model_class, resource)

        return resource

    @staticmethod
    def get_by(
        model_class: Type[T],
        *,
        raise_on_not_found: bool = False,
        check_permission: bool = True,
        skip_tenant_filter: bool = False,
        **filters
    ) -> Optional[T]:
        """
        透過其他欄位取得單一資源。

        Args:
            model_class: Model class
            raise_on_not_found: 找不到時是否拋出例外
            check_permission: 是否檢查權限
            skip_tenant_filter: 是否跳過租戶過濾（僅限系統管理員 API）
            **filters: 過濾條件

        Returns:
            Model instance or None
        """
        tenant = get_current_tenant()

        query = model_class.query

        # Apply tenant filter
        if hasattr(model_class, 'org_secure_code') and tenant and not skip_tenant_filter:
            query = query.filter_by(org_secure_code=tenant)

        # Apply filters
        for key, value in filters.items():
            if hasattr(model_class, key):
                query = query.filter(getattr(model_class, key) == value)

        resource = query.first()

        if resource is None:
            if raise_on_not_found:
                from ..exceptions import ResourceNotFoundError
                raise ResourceNotFoundError(model_class.__name__, str(filters))
            return None

        if check_permission:
            ResourceGateway._check_view_permission(model_class, resource)

        return resource

    @staticmethod
    def exists(model_class: Type[T], skip_tenant_filter: bool = False, **filters) -> bool:
        """
        檢查資源是否存在。

        Args:
            model_class: Model class
            skip_tenant_filter: 是否跳過租戶過濾
            **filters: 過濾條件

        Returns:
            bool: 是否存在
        """
        tenant = get_current_tenant()

        query = model_class.query

        # Apply tenant filter
        if hasattr(model_class, 'org_secure_code') and tenant and not skip_tenant_filter:
            query = query.filter_by(org_secure_code=tenant)

        # Apply filters
        for key, value in filters.items():
            if hasattr(model_class, key):
                query = query.filter(getattr(model_class, key) == value)

        return query.first() is not None

    @staticmethod
    def count(model_class: Type[T], skip_tenant_filter: bool = False, **filters) -> int:
        """
        計算資源數量。

        Args:
            model_class: Model class
            skip_tenant_filter: 是否跳過租戶過濾
            **filters: 過濾條件

        Returns:
            int: 數量
        """
        tenant = get_current_tenant()

        query = model_class.query

        # Apply tenant filter
        if hasattr(model_class, 'org_secure_code') and tenant and not skip_tenant_filter:
            query = query.filter_by(org_secure_code=tenant)

        # Apply filters
        for key, value in filters.items():
            if hasattr(model_class, key):
                query = query.filter(getattr(model_class, key) == value)

        return query.count()

    @staticmethod
    def filter(
        model_class: Type[T],
        *,
        order_by: str = None,
        limit: int = None,
        skip_tenant_filter: bool = False,
        **filters
    ) -> List[T]:
        """
        過濾資源（不分頁）。

        Args:
            model_class: Model class
            order_by: 排序欄位（-field 表示降序）
            limit: 限制數量
            skip_tenant_filter: 是否跳過租戶過濾
            **filters: 過濾條件

        Returns:
            List of Model instances
        """
        tenant = get_current_tenant()

        query = model_class.query

        # Apply tenant filter
        if hasattr(model_class, 'org_secure_code') and tenant and not skip_tenant_filter:
            query = query.filter_by(org_secure_code=tenant)

        # Apply filters
        for key, value in filters.items():
            if hasattr(model_class, key) and value is not None:
                query = query.filter(getattr(model_class, key) == value)

        # Apply ordering (supports comma-separated fields, prefix '-' for DESC)
        if order_by:
            for field in order_by.split(','):
                field = field.strip()
                if not field:
                    continue
                if field.startswith('-'):
                    query = query.order_by(getattr(model_class, field[1:]).desc())
                else:
                    query = query.order_by(getattr(model_class, field))

        # Apply limit
        if limit:
            query = query.limit(limit)

        return query.all()

    @staticmethod
    def list(
        model_class: Type[T],
        *,
        page: int = 1,
        per_page: int = 20,
        order_by: str = None,
        skip_tenant_filter: bool = False,
        **filters
    ) -> Dict[str, Any]:
        """
        取得資源列表（分頁）。

        Args:
            model_class: Model class
            page: 頁碼 (1-based)
            per_page: 每頁數量
            order_by: 排序欄位
            skip_tenant_filter: 是否跳過租戶過濾
            **filters: 過濾條件

        Returns:
            {
                'items': [...],
                'total': 100,
                'page': 1,
                'per_page': 20,
                'pages': 5
            }
        """
        tenant = get_current_tenant()

        # Build base query
        query = model_class.query

        # Apply tenant filter
        if hasattr(model_class, 'org_secure_code') and tenant and not skip_tenant_filter:
            query = query.filter_by(org_secure_code=tenant)

        # Apply additional filters
        for key, value in filters.items():
            if hasattr(model_class, key) and value is not None:
                query = query.filter(getattr(model_class, key) == value)

        # Apply ordering (supports comma-separated fields, prefix '-' for DESC)
        if order_by:
            for field in order_by.split(','):
                field = field.strip()
                if not field:
                    continue
                if field.startswith('-'):
                    query = query.order_by(getattr(model_class, field[1:]).desc())
                else:
                    query = query.order_by(getattr(model_class, field))

        # Paginate
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        return {
            'items': pagination.items,
            'total': pagination.total,
            'page': pagination.page,
            'per_page': pagination.per_page,
            'pages': pagination.pages
        }

    @staticmethod
    def create(
        model_class: Type[T],
        *,
        check_permission: bool = True,
        **data
    ) -> T:
        """
        建立新資源。

        Args:
            model_class: Model class
            check_permission: 是否檢查權限
            **data: 資源資料

        Returns:
            新建立的 Model instance
        """
        tenant = get_current_tenant()

        # Permission check
        if check_permission:
            ResourceGateway._check_create_permission(model_class)

        # Auto-set tenant
        if hasattr(model_class, 'org_secure_code'):
            if 'org_secure_code' not in data:
                if tenant is None:
                    raise ValueError("Cannot create resource without tenant context")
                data['org_secure_code'] = tenant

        # Auto-generate secure_code
        if hasattr(model_class, 'secure_code') and 'secure_code' not in data:
            from ..utils.security import generate_secure_code
            data['secure_code'] = generate_secure_code()

        # Create instance
        resource = model_class(**data)
        from .. import db
        db.session.add(resource)

        logger.info(
            f"Resource created: {model_class.__name__} "
            f"tenant={tenant} user={getattr(g, 'current_user_id', None)}"
        )

        return resource

    @staticmethod
    def update(resource: T, *, check_permission: bool = True, **data) -> T:
        """
        更新資源。

        Args:
            resource: Model instance
            check_permission: 是否檢查權限
            **data: 要更新的資料

        Returns:
            更新後的 Model instance
        """
        if check_permission:
            ResourceGateway._check_edit_permission(type(resource), resource)

        # Prevent updating critical fields
        protected_fields = {'id', 'secure_code', 'org_secure_code', 'created_at'}
        for field in protected_fields:
            data.pop(field, None)

        # Update fields
        for key, value in data.items():
            if hasattr(resource, key):
                setattr(resource, key, value)

        logger.info(
            f"Resource updated: {type(resource).__name__} "
            f"id={resource.id} user={getattr(g, 'current_user_id', None)}"
        )

        return resource

    @staticmethod
    def delete(resource: T, *, check_permission: bool = True, soft: bool = True) -> None:
        """
        刪除資源。

        Args:
            resource: Model instance
            check_permission: 是否檢查權限
            soft: 是否軟刪除 (預設 True)
        """
        if check_permission:
            ResourceGateway._check_delete_permission(type(resource), resource)

        if soft and hasattr(resource, 'is_deleted'):
            resource.is_deleted = True
            logger.info(
                f"Resource soft deleted: {type(resource).__name__} "
                f"id={resource.id} user={getattr(g, 'current_user_id', None)}"
            )
        else:
            from .. import db
            db.session.delete(resource)
            logger.info(
                f"Resource hard deleted: {type(resource).__name__} "
                f"id={resource.id} user={getattr(g, 'current_user_id', None)}"
            )

    @staticmethod
    def commit() -> None:
        """提交所有變更。"""
        from .. import db
        db.session.commit()

    @staticmethod
    def rollback() -> None:
        """回滾所有變更。"""
        from .. import db
        db.session.rollback()

    # Permission check methods
    @staticmethod
    def _get_resource_type(model_class: Type[T]) -> Optional[str]:
        """取得 Model 對應的資源類型"""
        return MODEL_RESOURCE_TYPE_MAP.get(model_class.__name__)

    @staticmethod
    def _get_current_user():
        """取得當前用戶"""
        from flask_login import current_user
        if current_user and current_user.is_authenticated:
            return current_user
        return None

    @staticmethod
    def _check_view_permission(model_class: Type[T], resource: T) -> None:
        """
        檢查檢視權限。

        Raises:
            PermissionDeniedError: 沒有權限
        """
        user = ResourceGateway._get_current_user()
        if user is None:
            # 無用戶上下文，跳過權限檢查（由認證層處理）
            return

        resource_type = ResourceGateway._get_resource_type(model_class)
        if resource_type is None:
            # 未配置的資源類型，跳過權限檢查
            return

        from ..services.permission_service import PermissionService
        if not PermissionService.can_view(user, resource_type, resource):
            from ..exceptions import PermissionDeniedError
            raise PermissionDeniedError(
                f"No permission to view {model_class.__name__}"
            )

    @staticmethod
    def _check_create_permission(model_class: Type[T]) -> None:
        """
        檢查建立權限。

        Raises:
            PermissionDeniedError: 沒有權限
        """
        user = ResourceGateway._get_current_user()
        if user is None:
            return

        resource_type = ResourceGateway._get_resource_type(model_class)
        if resource_type is None:
            return

        from ..services.permission_service import PermissionService
        if not PermissionService.can_create(user, resource_type):
            from ..exceptions import PermissionDeniedError
            raise PermissionDeniedError(
                f"No permission to create {model_class.__name__}"
            )

    @staticmethod
    def _check_edit_permission(model_class: Type[T], resource: T) -> None:
        """
        檢查編輯權限。

        Raises:
            PermissionDeniedError: 沒有權限
        """
        user = ResourceGateway._get_current_user()
        if user is None:
            return

        resource_type = ResourceGateway._get_resource_type(model_class)
        if resource_type is None:
            return

        from ..services.permission_service import PermissionService
        if not PermissionService.can_edit(user, resource_type, resource):
            from ..exceptions import PermissionDeniedError
            raise PermissionDeniedError(
                f"No permission to edit {model_class.__name__}"
            )

    @staticmethod
    def _check_delete_permission(model_class: Type[T], resource: T) -> None:
        """
        檢查刪除權限。

        Raises:
            PermissionDeniedError: 沒有權限
        """
        user = ResourceGateway._get_current_user()
        if user is None:
            return

        resource_type = ResourceGateway._get_resource_type(model_class)
        if resource_type is None:
            return

        from ..services.permission_service import PermissionService
        if not PermissionService.can_delete(user, resource_type, resource):
            from ..exceptions import PermissionDeniedError
            raise PermissionDeniedError(
                f"No permission to delete {model_class.__name__}"
            )
