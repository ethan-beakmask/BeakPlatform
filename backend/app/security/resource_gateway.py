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
    'JobFamily': 'job_family',
    'DutyCategory': 'duty_category',
    'JobLevel': 'job_level',
    'JobTitle': 'job_title',
    'Duty': 'duty',
    'WorkSchedule': 'work_schedule',
    'ApprovalCategory': 'approval_category',
    'JobLevelApprovalLimit': 'job_level_approval_limit',
    'SmtpConfig': 'smtp_config',
    'TelegramConfig': 'telegram_config',
    'RecipientGroup': 'recipient_group',
    'UserNumberingRule': 'user_numbering_rule',
    'DcPageTemplate': 'dc_page_template',
    'DcSiteMapNode': 'dc_site_map_node',
    'Delegation': 'delegation',
    'EmployeePosition': 'employee_position',
    'UserRoleAssignment': 'user_role_assignment',
    'Contract': 'contract',
    # 未來擴展
    # 'FormTemplate': 'form_template',
    # 'FormInstance': 'form_instance',
    # 'FlowDefinition': 'flow_definition',
    # 'FlowInstance': 'flow_instance',
}

# list()/filter() 預設 RBAC 檢查的啟用清單（階段 B 漸進推進）
#
# 列在這裡的 model，list()/filter() 未帶 require_permission 時
# 自動檢查 '{resource_type}:read'。
#
# 新增 model 前置條件（缺一不可，否則連 ORG_ADMIN 都會被拒）：
# 1. permissions 表已有該類型的權限代碼
#    （scripts/migrations/seed_resource_permissions.py）
# 2. 已加入上方 MODEL_RESOURCE_TYPE_MAP
# 3. 已確認該 model 所有 list/filter 呼叫端的身分可達性
#    （EMPLOYEE 可達的端點需先授權或加 check_permission=False）
LIST_RBAC_ENFORCED_MODELS = {
    'JobFamily',
    'DutyCategory',
    'JobLevel',
    'JobTitle',
    'Duty',
    'WorkSchedule',
    'ApprovalCategory',
    'JobLevelApprovalLimit',
    'SmtpConfig',
    'TelegramConfig',
    'RecipientGroup',
    'UserNumberingRule',
    'DcPageTemplate',
    'DcSiteMapNode',
    'Delegation',
    'EmployeePosition',
    'UserRoleAssignment',
    'User',
    'Role',
    'OrganizationalUnit',
    'Module',
    'MenuItem',
    'Organization',
    'Contract',
}

# 明確豁免平台 RBAC 檢查的 model（階段 B fail-closed 翻轉時的白名單依據）
#
# 這些 model 不註冊 MODEL_RESOURCE_TYPE_MAP、不進 LIST_RBAC_ENFORCED_MODELS。
# 豁免必須有理由，禁止只因「加了會壞」就放進來——先確認閘門在哪裡。
RBAC_EXEMPT_MODELS = {
    # nocode_builder 子系統家族：閘門為模組合約 + 模組 ACL（@module_access_required）
    # + 子系統自身的權限政策（site map 存取檢查、developer 檢查）。
    # 端用戶 portal（module_access check_acl=False）與設計師流程（ACL）皆為
    # 會員層級可達，疊加平台 {type}:read 會癱瘓 portal。
    'DcSubSystem': 'nocode 模組 ACL + 子系統權限政策把關',
    'DcCrudView': 'nocode 模組 ACL + 子系統權限政策把關',
    'DcPageLayout': 'nocode 模組 ACL 把關；/p/<sc> 發佈頁為全登入用戶可達',
    'DcSubSystemPage': 'nocode 模組 ACL + 子系統權限政策把關',
    'DcBackground': 'nocode 模組 ACL 把關（設計師資源）',
    # 動態頁面：閘門為 page_permission_service.check_page_access 本身，
    # /p/<sc> 與 /api/pages 為全登入用戶可達，疊 {type}:read 會癱瘓動態頁面。
    'Page': 'page_permission_service 自身即為閘門',
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
    def exists(
        model_class: Type[T],
        skip_tenant_filter: bool = False,
        require_permission: str = None,
        **filters
    ) -> bool:
        """
        檢查資源是否存在。

        Args:
            model_class: Model class
            skip_tenant_filter: 是否跳過租戶過濾
            require_permission: 要求的權限代碼（如 'user:read'），未通過拋 PermissionDeniedError
            **filters: 過濾條件

        Returns:
            bool: 是否存在
        """
        if require_permission:
            ResourceGateway._check_list_permission(require_permission)

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
    def count(
        model_class: Type[T],
        skip_tenant_filter: bool = False,
        require_permission: str = None,
        **filters
    ) -> int:
        """
        計算資源數量。

        Args:
            model_class: Model class
            skip_tenant_filter: 是否跳過租戶過濾
            require_permission: 要求的權限代碼（如 'user:read'），未通過拋 PermissionDeniedError
            **filters: 過濾條件

        Returns:
            int: 數量
        """
        if require_permission:
            ResourceGateway._check_list_permission(require_permission)

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
        require_permission: str = None,
        check_permission: bool = True,
        **filters
    ) -> List[T]:
        """
        過濾資源（不分頁）。

        Args:
            model_class: Model class
            order_by: 排序欄位（-field 表示降序）
            limit: 限制數量
            skip_tenant_filter: 是否跳過租戶過濾
            require_permission: 要求的權限代碼（如 'user:read'），未通過拋 PermissionDeniedError
            check_permission: LIST_RBAC_ENFORCED_MODELS 內的 model 是否自動檢查 '{type}:read'
            **filters: 過濾條件

        Returns:
            List of Model instances
        """
        ResourceGateway._check_collection_permission(
            model_class, require_permission, check_permission
        )

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
        require_permission: str = None,
        check_permission: bool = True,
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
            require_permission: 要求的權限代碼（如 'user:read'），未通過拋 PermissionDeniedError
            check_permission: LIST_RBAC_ENFORCED_MODELS 內的 model 是否自動檢查 '{type}:read'
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
        ResourceGateway._check_collection_permission(
            model_class, require_permission, check_permission
        )

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
    def _check_collection_permission(
        model_class: Type[T],
        require_permission: Optional[str],
        check_permission: bool
    ) -> None:
        """
        集合查詢（list/filter）的權限檢查入口。

        優先序：
        1. require_permission 明確指定 -> 檢查該代碼
        2. model 在 LIST_RBAC_ENFORCED_MODELS 且 check_permission=True
           -> 自動檢查 '{resource_type}:read'
        3. 其餘 -> 不檢查（fail-open，待階段 B 分批收斂）
        """
        if require_permission:
            ResourceGateway._check_list_permission(require_permission)
            return

        if check_permission and model_class.__name__ in LIST_RBAC_ENFORCED_MODELS:
            resource_type = ResourceGateway._get_resource_type(model_class)
            if resource_type:
                ResourceGateway._check_list_permission(f"{resource_type}:read")

    @staticmethod
    def _check_list_permission(permission_code: str) -> None:
        """
        檢查集合查詢的資源類型層級權限（list/filter/count/exists 的 opt-in 檢查）。

        無用戶上下文時跳過（比照 _check_view_permission，由認證層把關）。

        Raises:
            PermissionDeniedError: 沒有權限
        """
        user = ResourceGateway._get_current_user()
        if user is None:
            return

        from ..services.permission_service import PermissionService
        result = PermissionService.check(user, permission_code)
        if not result.allowed:
            logger.warning(
                f"List permission denied: {permission_code} "
                f"user={user.secure_code} reason={result.reason}"
            )
            from ..exceptions import PermissionDeniedError
            raise PermissionDeniedError(
                f"No permission to list resources: {permission_code}"
            )

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
