"""
BeakPlatform - Module Permission Service
模組權限註冊服務

負責：
1. 將模組定義的權限同步到 Permission 資料表
2. 管理模組權限的生命週期（新增、更新、停用）
"""
import logging
from typing import Dict, List, Any, Optional

from .. import db
from ..models import Permission
from ..models.permission import PermissionLevel

logger = logging.getLogger(__name__)


class ModulePermissionService:
    """模組權限服務"""

    @classmethod
    def register_module_permissions(
        cls,
        module_name: str,
        permissions: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """
        註冊模組的權限定義到資料庫

        Args:
            module_name: 模組名稱
            permissions: 權限定義列表，每個權限為 dict:
                - code: 權限代碼（必填，如 'form_workflow.form.create'）
                - name: 權限名稱（必填，如 '建立表單'）
                - description: 權限描述（選填）
                - level: 權限層級（選填，預設 MODULE）

        Returns:
            {'created': n, 'updated': n, 'unchanged': n}
        """
        result = {'created': 0, 'updated': 0, 'unchanged': 0}

        if not permissions:
            return result

        for perm_def in permissions:
            code = perm_def.get('code')
            name = perm_def.get('name')

            if not code or not name:
                logger.warning(
                    f"Module {module_name}: Invalid permission definition "
                    f"(missing code or name): {perm_def}"
                )
                continue

            # 確保權限代碼以模組名稱開頭（避免衝突）
            if not code.startswith(f"{module_name}."):
                logger.warning(
                    f"Module {module_name}: Permission code '{code}' "
                    f"should start with '{module_name}.'"
                )
                # 不強制修改，但記錄警告

            # 解析權限代碼為 resource_type 和 action
            resource_type, action = cls._parse_permission_code(code, module_name)

            # 取得權限層級
            level_str = perm_def.get('level', 'MODULE')
            level = getattr(PermissionLevel, level_str, PermissionLevel.MODULE)

            # 檢查權限是否已存在
            existing = Permission.query.filter_by(
                code=code,
                is_deleted=False
            ).first()

            if existing:
                # 更新現有權限
                changed = False
                if existing.name != name:
                    existing.name = name
                    changed = True
                if existing.description != perm_def.get('description'):
                    existing.description = perm_def.get('description')
                    changed = True
                if existing.permission_level != level:
                    existing.permission_level = level
                    changed = True
                if not existing.is_active:
                    existing.is_active = True
                    changed = True

                if changed:
                    result['updated'] += 1
                    logger.debug(f"Updated permission: {code}")
                else:
                    result['unchanged'] += 1
            else:
                # 建立新權限
                new_permission = Permission(
                    resource_type=resource_type,
                    action=action,
                    code=code,
                    name=name,
                    description=perm_def.get('description'),
                    permission_level=level,
                    is_system_permission=False,  # 模組權限不是系統權限
                    is_active=True
                )
                db.session.add(new_permission)
                result['created'] += 1
                logger.debug(f"Created permission: {code}")

        try:
            db.session.commit()
            logger.info(
                f"Module {module_name}: Registered {result['created']} new, "
                f"{result['updated']} updated, {result['unchanged']} unchanged permissions"
            )
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to register permissions for {module_name}: {e}")
            raise

        return result

    @classmethod
    def sync_all_module_permissions(cls, module_loader) -> Dict[str, Dict[str, int]]:
        """
        同步所有模組的權限

        Args:
            module_loader: ModuleLoader 實例

        Returns:
            {module_name: {'created': n, 'updated': n, 'unchanged': n}}
        """
        results = {}

        for module in module_loader.get_loaded_modules():
            if module.permissions:
                try:
                    result = cls.register_module_permissions(
                        module.name,
                        module.permissions
                    )
                    results[module.name] = result
                except Exception as e:
                    logger.error(f"Failed to sync permissions for {module.name}: {e}")
                    results[module.name] = {'error': str(e)}

        return results

    @classmethod
    def deactivate_module_permissions(cls, module_name: str) -> int:
        """
        停用模組的所有權限

        當模組被停用或移除時呼叫

        Args:
            module_name: 模組名稱

        Returns:
            停用的權限數量
        """
        # 停用以模組名稱開頭的所有權限
        count = Permission.query.filter(
            Permission.code.like(f"{module_name}.%"),
            Permission.is_deleted == False,
            Permission.is_active == True
        ).update(
            {'is_active': False},
            synchronize_session=False
        )

        try:
            db.session.commit()
            logger.info(f"Deactivated {count} permissions for module {module_name}")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to deactivate permissions for {module_name}: {e}")
            raise

        return count

    @classmethod
    def get_module_permissions(cls, module_name: str) -> List[Permission]:
        """
        取得模組的所有權限

        Args:
            module_name: 模組名稱

        Returns:
            Permission 列表
        """
        return Permission.query.filter(
            Permission.code.like(f"{module_name}.%"),
            Permission.is_deleted == False
        ).all()

    @classmethod
    def _parse_permission_code(cls, code: str, module_name: str) -> tuple:
        """
        解析權限代碼為 resource_type 和 action

        模組權限格式：{module_name}.{resource}.{action}
        例如：
        - nocode_builder.view → resource: NOCODE_BUILDER, action: VIEW
        - form_workflow.form.create → resource: FORM_WORKFLOW_FORM, action: CREATE

        Args:
            code: 權限代碼
            module_name: 模組名稱

        Returns:
            (resource_type, action)
        """
        parts = code.split('.')

        if len(parts) == 2:
            # 簡單格式：module.action
            resource_type = module_name.upper()
            action = parts[1].upper()
        elif len(parts) >= 3:
            # 完整格式：module.resource.action
            resource_type = '_'.join(parts[:-1]).upper()
            action = parts[-1].upper()
        else:
            # 無效格式，使用預設值
            resource_type = module_name.upper()
            action = 'ACCESS'

        return resource_type, action
