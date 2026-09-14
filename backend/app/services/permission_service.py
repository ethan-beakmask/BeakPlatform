"""
BeakMask Permission Service
權限檢查服務

[標準 AUTHZ-01] 資源級權限檢查
RBAC + ABAC 權限系統核心實作

權限檢查流程：
1. 系統管理員直接通過
2. 檢查用戶角色
3. 檢查角色權限（含繼承）
4. 評估 ABAC 條件
"""
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from flask import g
from flask_login import current_user

from ..models import (
    User, Role, Permission, RolePermission, PermissionCondition,
    RoleLevel, UserRoleAssignment
)
from .. import db

logger = logging.getLogger(__name__)


class PermissionCheckResult:
    """權限檢查結果"""

    def __init__(
        self,
        allowed: bool,
        reason: str = '',
        matched_role: Optional[str] = None,
        matched_permission: Optional[str] = None,
        conditions_evaluated: Optional[List[Dict]] = None
    ):
        self.allowed = allowed
        self.reason = reason
        self.matched_role = matched_role
        self.matched_permission = matched_permission
        self.conditions_evaluated = conditions_evaluated or []

    def __bool__(self):
        return self.allowed

    def to_dict(self) -> Dict[str, Any]:
        return {
            'allowed': self.allowed,
            'reason': self.reason,
            'matched_role': self.matched_role,
            'matched_permission': self.matched_permission,
            'conditions_evaluated': self.conditions_evaluated,
        }


class PermissionService:
    """
    權限檢查服務

    權限階層：
    1. System Admin: 可存取所有企業的所有資源
    2. Org Admin: 可存取本企業的所有資源
    3. User: 依據角色和 RBAC/ABAC 設定存取

    使用方式：
        # 檢查權限
        result = PermissionService.check(user, 'user:create')
        if result:
            # 有權限
            pass

        # 帶資源的權限檢查（ABAC）
        result = PermissionService.check(user, 'form_instance:update', resource=form)

        # 快捷方法
        if PermissionService.can(user, 'user', 'create'):
            # 有權限
            pass
    """

    # 權限代碼快取 (避免重複查詢)
    _permission_cache: Dict[str, Permission] = {}
    _condition_cache: Dict[str, PermissionCondition] = {}

    # ==========================================================================
    # 主要 API
    # ==========================================================================

    @classmethod
    def check(
        cls,
        user: User,
        permission_code: str,
        *,
        resource: Any = None,
        context: Optional[Dict[str, Any]] = None
    ) -> PermissionCheckResult:
        """
        檢查用戶是否有指定權限

        Args:
            user: 用戶實例
            permission_code: 權限代碼 (格式: resource_type:action)
            resource: 目標資源（用於 ABAC 條件評估）
            context: 額外上下文（用於 ABAC 條件評估）

        Returns:
            PermissionCheckResult: 權限檢查結果
        """
        if user is None:
            return PermissionCheckResult(False, 'User is None')

        # [SEC-02] SYSTEM_ADMIN 不享有特權，走正常 RBAC 流程
        # 已移除: 系統管理員直接通過

        # 1. 取得權限定義
        permission = cls._get_permission(permission_code)
        if permission is None:
            logger.warning(f"Unknown permission code: {permission_code}")
            return PermissionCheckResult(False, f'Unknown permission: {permission_code}')

        # 2. 企業管理員對企業級及以下權限直接通過
        if user.is_org_admin and permission.permission_level != 'SYSTEM':
            return PermissionCheckResult(
                True,
                'Org admin has org-level permissions',
                matched_role='ORG_ADMIN',
                matched_permission=permission_code
            )

        # 3. 取得用戶所有角色
        user_roles = cls._get_user_roles(user)
        if not user_roles:
            return PermissionCheckResult(False, 'User has no roles')

        # 5. 檢查角色權限（含繼承）
        for role in user_roles:
            # 取得角色鏈（含繼承）
            role_chain = cls._get_role_chain(role)

            for chain_role in role_chain:
                # 查詢角色-權限關聯
                role_permission = cls._get_role_permission(chain_role, permission)
                if role_permission is None:
                    continue

                if not role_permission.is_active:
                    continue

                # 6. 評估 ABAC 條件
                if role_permission.has_conditions:
                    condition_result = cls._evaluate_conditions(
                        role_permission,
                        user=user,
                        resource=resource,
                        context=context or {}
                    )
                    if condition_result:
                        return PermissionCheckResult(
                            True,
                            'Permission granted with conditions',
                            matched_role=chain_role.code,
                            matched_permission=permission_code,
                            conditions_evaluated=condition_result
                        )
                else:
                    # 無條件，直接通過
                    return PermissionCheckResult(
                        True,
                        'Permission granted',
                        matched_role=chain_role.code,
                        matched_permission=permission_code
                    )

        return PermissionCheckResult(
            False,
            f'No role grants permission: {permission_code}'
        )

    @classmethod
    def can(
        cls,
        user: User,
        resource_type: str,
        action: str,
        *,
        resource: Any = None,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        檢查權限的快捷方法

        Args:
            user: 用戶實例
            resource_type: 資源類型
            action: 操作類型
            resource: 目標資源
            context: 額外上下文

        Returns:
            bool: 是否有權限
        """
        permission_code = f"{resource_type.lower()}:{action.lower()}"
        result = cls.check(user, permission_code, resource=resource, context=context)
        return result.allowed

    @classmethod
    def can_view(cls, user: User, resource_type: str, resource: Any = None) -> bool:
        """檢查 view 權限"""
        return cls.can(user, resource_type, 'read', resource=resource)

    @classmethod
    def can_create(cls, user: User, resource_type: str) -> bool:
        """檢查 create 權限"""
        return cls.can(user, resource_type, 'create')

    @classmethod
    def can_edit(cls, user: User, resource_type: str, resource: Any) -> bool:
        """檢查 edit 權限"""
        return cls.can(user, resource_type, 'update', resource=resource)

    @classmethod
    def can_delete(cls, user: User, resource_type: str, resource: Any) -> bool:
        """檢查 delete 權限"""
        return cls.can(user, resource_type, 'delete', resource=resource)

    # ==========================================================================
    # 用戶權限查詢
    # ==========================================================================

    @classmethod
    def get_user_permissions(cls, user: User) -> List[str]:
        """
        取得用戶所有權限代碼（列表形式）

        Returns:
            權限代碼列表（已排序）
        """
        return sorted(cls.get_all_permission_codes(user))

    @classmethod
    def get_all_permission_codes(cls, user: User) -> Set[str]:
        """
        取得用戶所有權限代碼（集合形式）

        用於選單權限過濾等需要快速查找的場景。

        Returns:
            權限代碼集合
        """
        # [SEC-02] SYSTEM_ADMIN 不享有特權，走正常 RBAC 流程
        # 已移除: 系統管理員有所有權限

        permissions: Set[str] = set()

        # 企業管理員有所有非系統級權限
        if user.is_org_admin:
            org_perms = Permission.query.filter(
                Permission.permission_level != 'SYSTEM',
                Permission.is_active == True
            ).all()
            permissions.update(p.code for p in org_perms)

        # 從角色取得權限
        user_roles = cls._get_user_roles(user)
        for role in user_roles:
            role_chain = cls._get_role_chain(role)
            for chain_role in role_chain:
                role_perms = RolePermission.query.filter_by(
                    role_secure_code=chain_role.secure_code,
                    is_active=True,
                    is_deleted=False
                ).all()
                for rp in role_perms:
                    if rp.permission:
                        permissions.add(rp.permission.code)

        return permissions

    @classmethod
    def get_user_roles(cls, user: User) -> List[Dict[str, Any]]:
        """
        取得用戶所有角色資訊

        Returns:
            角色資訊列表
        """
        roles = cls._get_user_roles(user)
        return [
            {
                'code': r.code,
                'name': r.name,
                'role_level': r.role_level,
                'scope_type': r.scope_type,
                'is_manager': r.is_manager,
            }
            for r in roles
        ]

    # ==========================================================================
    # 內部方法
    # ==========================================================================

    @classmethod
    def _get_permission(cls, permission_code: str) -> Optional[Permission]:
        """取得權限定義（帶快取）"""
        if permission_code in cls._permission_cache:
            cached = cls._permission_cache[permission_code]
            # 重新關聯到當前 session（避免 DetachedInstanceError）
            return db.session.merge(cached, load=False)

        permission = Permission.query.filter_by(
            code=permission_code,
            is_active=True,
            is_deleted=False
        ).first()

        if permission:
            cls._permission_cache[permission_code] = permission

        return permission

    @classmethod
    def _get_condition(cls, condition_code: str) -> Optional[PermissionCondition]:
        """取得條件定義（帶快取）"""
        if condition_code in cls._condition_cache:
            cached = cls._condition_cache[condition_code]
            # 重新關聯到當前 session（避免 DetachedInstanceError）
            return db.session.merge(cached, load=False)

        condition = PermissionCondition.query.filter_by(
            code=condition_code,
            is_active=True,
            is_deleted=False
        ).first()

        if condition:
            cls._condition_cache[condition_code] = condition

        return condition

    @classmethod
    def _get_user_roles(cls, user: User) -> List[Role]:
        """
        取得用戶所有有效角色（僅啟用中的角色）

        指派有效性委派給 UserRoleAssignment.get_active_role_secure_codes
        （全站標準實作，Date 欄位以日曆日比較，含效期最後一日）。
        """
        role_scs = UserRoleAssignment.get_active_role_secure_codes(
            user.secure_code
        )
        if not role_scs:
            return []

        return Role.query.filter(
            Role.secure_code.in_(role_scs),
            Role.is_active == True,
            Role.is_deleted == False
        ).all()

    @classmethod
    def _get_role_chain(cls, role: Role) -> List[Role]:
        """
        取得角色繼承鏈

        例如：模組作者 繼承 模組讀者
        返回 [模組作者, 模組讀者]
        """
        chain = [role]
        visited = {role.secure_code}
        current = role

        while current.inherits_from_secure_code:
            if current.inherits_from_secure_code in visited:
                # 防止循環
                logger.warning(f"Circular role inheritance detected: {role.code}")
                break

            parent = Role.query.filter_by(
                secure_code=current.inherits_from_secure_code,
                is_active=True,
                is_deleted=False
            ).first()

            if parent is None:
                break

            chain.append(parent)
            visited.add(parent.secure_code)
            current = parent

        return chain

    @classmethod
    def _get_role_permission(
        cls,
        role: Role,
        permission: Permission
    ) -> Optional[RolePermission]:
        """取得角色-權限關聯"""
        return RolePermission.query.filter_by(
            role_secure_code=role.secure_code,
            permission_secure_code=permission.secure_code,
            is_deleted=False
        ).first()

    # ==========================================================================
    # ABAC 條件評估
    # ==========================================================================

    @classmethod
    def _evaluate_conditions(
        cls,
        role_permission: RolePermission,
        *,
        user: User,
        resource: Any,
        context: Dict[str, Any]
    ) -> Optional[List[Dict]]:
        """
        評估 ABAC 條件

        條件 JSON 格式：
        {
            "conditions": [
                {"type": "OWNERSHIP", "code": "OWNER"},
                {"type": "ORG", "code": "SAME_DEPT"}
            ],
            "logic": "OR"  # OR = 任一條件滿足, AND = 全部條件滿足
        }

        Returns:
            條件評估結果列表（如果通過），None（如果不通過）
        """
        conditions_data = role_permission.conditions
        if not conditions_data:
            return None

        condition_list = conditions_data.get('conditions', [])
        logic = conditions_data.get('logic', 'OR')

        if not condition_list:
            return None

        results = []
        for cond_item in condition_list:
            cond_code = cond_item.get('code')
            cond_param = cond_item.get('param')

            condition_def = cls._get_condition(cond_code)
            if condition_def is None:
                logger.warning(f"Unknown condition code: {cond_code}")
                results.append({
                    'code': cond_code,
                    'passed': False,
                    'reason': 'Unknown condition'
                })
                continue

            passed, reason = cls._evaluate_single_condition(
                condition_def,
                param=cond_param,
                user=user,
                resource=resource,
                context=context
            )

            results.append({
                'code': cond_code,
                'passed': passed,
                'reason': reason
            })

        # 根據邏輯判斷結果
        if logic == 'AND':
            # 全部通過
            if all(r['passed'] for r in results):
                return results
            return None
        else:
            # 任一通過 (OR)
            if any(r['passed'] for r in results):
                return results
            return None

    @classmethod
    def _evaluate_single_condition(
        cls,
        condition: PermissionCondition,
        *,
        param: Any,
        user: User,
        resource: Any,
        context: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        評估單一條件

        Returns:
            (是否通過, 原因)
        """
        expression = condition.expression_dict
        if not expression:
            return False, 'No expression defined'

        try:
            # 根據條件類型分派
            if condition.condition_type == 'OWNERSHIP':
                return cls._eval_ownership_condition(expression, user, resource)
            elif condition.condition_type == 'ORG':
                return cls._eval_org_condition(expression, user, resource)
            elif condition.condition_type == 'RANK':
                return cls._eval_rank_condition(expression, param, user, resource)
            elif condition.condition_type == 'TIME':
                return cls._eval_time_condition(expression, context)
            elif condition.condition_type == 'STATUS':
                return cls._eval_status_condition(expression, resource)
            else:
                return False, f'Unknown condition type: {condition.condition_type}'
        except Exception as e:
            logger.error(f"Error evaluating condition {condition.code}: {e}")
            return False, f'Evaluation error: {str(e)}'

    @classmethod
    def _eval_ownership_condition(
        cls,
        expression: Dict,
        user: User,
        resource: Any
    ) -> Tuple[bool, str]:
        """評估所有權條件 (OWNER, ASSIGNED)"""
        if resource is None:
            return False, 'No resource provided'

        field = expression.get('field')
        compare_to = expression.get('compare_to')

        if not field or not compare_to:
            return False, 'Invalid expression'

        # 取得資源欄位值
        resource_value = getattr(resource, field, None)
        if resource_value is None:
            return False, f'Resource has no field: {field}'

        # 取得比較值
        if compare_to == 'current_user.secure_code':
            compare_value = user.secure_code
        elif compare_to.startswith('current_user.'):
            attr = compare_to.split('.', 1)[1]
            compare_value = getattr(user, attr, None)
        else:
            compare_value = compare_to

        # 比較
        operator = expression.get('operator', 'eq')
        if operator == 'eq':
            passed = resource_value == compare_value
        elif operator == 'ne':
            passed = resource_value != compare_value
        else:
            return False, f'Unknown operator: {operator}'

        return passed, f'{field} {operator} {compare_to}'

    @classmethod
    def _eval_org_condition(
        cls,
        expression: Dict,
        user: User,
        resource: Any
    ) -> Tuple[bool, str]:
        """評估組織層級條件 (SAME_DEPT, SUB_DEPT, SUBORDINATE)"""
        if resource is None:
            return False, 'No resource provided'

        field = expression.get('field')
        operator = expression.get('operator', 'eq')
        compare_to = expression.get('compare_to')

        if not field:
            return False, 'Invalid expression'

        # 取得資源欄位值
        resource_value = getattr(resource, field, None)

        # 取得比較值
        if compare_to == 'current_user.primary_unit_secure_code':
            compare_value = user.primary_unit_secure_code
        elif compare_to == 'current_user.secure_code':
            compare_value = user.secure_code
        elif compare_to and compare_to.startswith('current_user.'):
            attr = compare_to.split('.', 1)[1]
            compare_value = getattr(user, attr, None)
        else:
            compare_value = compare_to

        if operator == 'eq':
            passed = resource_value == compare_value
        elif operator == 'in_subtree':
            # 檢查是否在子樹中（需要查詢組織單位）
            passed = cls._check_in_subtree(resource_value, compare_value)
        elif operator == 'is_subordinate_of':
            # 檢查是否為部屬
            passed = cls._check_is_subordinate(resource_value, compare_value)
        else:
            return False, f'Unknown operator: {operator}'

        return passed, f'{field} {operator} {compare_to}'

    @classmethod
    def _eval_rank_condition(
        cls,
        expression: Dict,
        param: Any,
        user: User,
        resource: Any
    ) -> Tuple[bool, str]:
        """評估職等條件 (MIN_RANK, LOWER_RANK)"""
        # TODO: 需要整合 JobLevel 模型
        # 目前返回 False，待實作
        return False, 'Rank condition not implemented'

    @classmethod
    def _eval_time_condition(
        cls,
        expression: Dict,
        context: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """評估時間條件 (WORK_HOURS, VALID_PERIOD)"""
        check = expression.get('check')

        if check == 'is_work_hours':
            now = datetime.now()
            work_start = expression.get('work_start', '09:00')
            work_end = expression.get('work_end', '18:00')
            work_days = expression.get('work_days', [1, 2, 3, 4, 5])

            # 檢查星期
            if now.isoweekday() not in work_days:
                return False, 'Not a work day'

            # 檢查時間
            current_time = now.strftime('%H:%M')
            if work_start <= current_time <= work_end:
                return True, 'Within work hours'
            return False, 'Outside work hours'

        # 其他時間條件
        field = expression.get('field')
        operator = expression.get('operator')
        compare_to = expression.get('compare_to')

        if compare_to == 'now':
            compare_value = datetime.utcnow()
        else:
            compare_value = compare_to

        # 從 context 取得欄位值
        field_value = context.get(field)
        if field_value is None:
            return False, f'No {field} in context'

        if operator == 'gte':
            passed = field_value >= compare_value
        elif operator == 'lte':
            passed = field_value <= compare_value
        else:
            return False, f'Unknown operator: {operator}'

        return passed, f'{field} {operator} {compare_to}'

    @classmethod
    def _eval_status_condition(
        cls,
        expression: Dict,
        resource: Any
    ) -> Tuple[bool, str]:
        """評估狀態條件 (STATUS_DRAFT, FLOW_PENDING)"""
        if resource is None:
            return False, 'No resource provided'

        field = expression.get('field')
        operator = expression.get('operator', 'eq')
        compare_to = expression.get('compare_to')

        if not field:
            return False, 'Invalid expression'

        resource_value = getattr(resource, field, None)

        if operator == 'eq':
            passed = resource_value == compare_to
        elif operator == 'ne':
            passed = resource_value != compare_to
        elif operator == 'in':
            passed = resource_value in compare_to
        elif operator == 'not_in':
            passed = resource_value not in compare_to
        else:
            return False, f'Unknown operator: {operator}'

        return passed, f'{field} {operator} {compare_to}'

    @classmethod
    def _check_in_subtree(
        cls,
        unit_secure_code: str,
        parent_secure_code: str
    ) -> bool:
        """檢查單位是否在父單位的子樹中"""
        if not unit_secure_code or not parent_secure_code:
            return False

        from ..models import OrganizationalUnit

        # 取得父單位的完整路徑
        parent = OrganizationalUnit.query.filter_by(
            secure_code=parent_secure_code,
            is_deleted=False
        ).first()

        if not parent:
            return False

        # 取得目標單位
        unit = OrganizationalUnit.query.filter_by(
            secure_code=unit_secure_code,
            is_deleted=False
        ).first()

        if not unit:
            return False

        # 檢查路徑包含
        if parent.full_path and unit.full_path:
            return unit.full_path.startswith(parent.full_path)

        return False

    @classmethod
    def _check_is_subordinate(
        cls,
        user_secure_code: str,
        manager_secure_code: str
    ) -> bool:
        """檢查用戶是否為某管理者的部屬"""
        # TODO: 需要透過 EmployeePosition 模型檢查直屬關係
        return False

    # ==========================================================================
    # 快取管理
    # ==========================================================================

    @classmethod
    def clear_cache(cls):
        """清除權限快取"""
        cls._permission_cache.clear()
        cls._condition_cache.clear()
        logger.info("Permission cache cleared")
