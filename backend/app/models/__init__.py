"""
BeakPlatform Models
SQLAlchemy Models with security features
"""
# 基礎模型
from .base import BaseModel, TenantBaseModel

# 核心模型
from .conglomerate import Conglomerate
from .conglomerate_log import ConglomerateLog
from .user import User, UserType
from .organization import Organization, CustomerType
from .contract import Contract, ContractStatus
from .blocked_email_domain import BlockedEmailDomain

# 組織架構模型
from .organizational_unit import OrganizationalUnit, UnitType
from .role import Role, RoleType, ScopeType, RoleLevel, ExclusiveGroup

# RBAC/ABAC 權限模型
from .permission import (
    Permission, ResourceType, ActionType, PermissionLevel,
    DEFAULT_PERMISSIONS
)
from .role_permission import RolePermission
from .rbac_default import RbacDefault
from .permission_condition import (
    PermissionCondition, ConditionType,
    DEFAULT_CONDITIONS
)

# 職等職系模型 (人資架構)
from .job_level import JobLevel, DEFAULT_JOB_LEVELS
from .job_family import JobFamily, JobFamilyType, DEFAULT_JOB_FAMILIES
from .job_title import JobTitle, DEFAULT_JOB_TITLES
from .employee_position import EmployeePosition, PositionType
from .delegation import Delegation, DelegationType, DelegationStatus
from .approval_category import (
    ApprovalCategory,
    JobLevelApprovalLimit,
    DEFAULT_APPROVAL_CATEGORIES
)

# 職務管理（部門職責標籤）
from .duty import Duty, DutyCategory, DEFAULT_DUTY_CATEGORIES

# 關聯表
from .associations import UserUnitAssignment, UserRoleAssignment

# 成員關係（跨部門/社群）
from .user_unit_membership import (
    UserUnitMembership,
    MembershipType,
    MembershipRole
)

# 功能模型
from .module import Module
from .menu_item import MenuItem
from .menu_permission import MenuPermission
from .menu_role_requirement import MenuRoleRequirement
from .menu_default import MenuDefault
from .page import Page

# 通用選項清單
from .lookup_category import LookupCategory
from .lookup_item import LookupItem
from .broadcast_acknowledgment import BroadcastAcknowledgment

# 系統設定
from .system_setting import SystemSetting
from .smtp_config import SmtpConfig
from .telegram_config import TelegramConfig
from .recipient_group import RecipientGroup

# 認證相關
from .password_reset_token import PasswordResetToken
from .password_history import PasswordHistory

# 稽核日誌
from .audit_log import AuditLog

# 檔案管理
from .platform_file import PlatformFile

# 用戶編號規則
from .user_numbering_rule import (
    UserNumberingRule,
    UserNumberingCounter,
    UsedUserNumber,
    NumberingElementType,
    NumberingResetPeriod,
    NumberingUsageScope
)

# 模組使用權控制
from .module_access_control import ModuleAccessControl, TargetType

# 時間管理（班表、排班）
from .work_schedule import WorkSchedule, DEFAULT_WORK_SCHEDULES
from .schedule_holiday import ScheduleHoliday, DEFAULT_TW_HOLIDAYS_2026
from .shift_type import ShiftType, DEFAULT_SHIFT_TYPES
from .personal_schedule import PersonalSchedule
from .schedule_adjustment import ScheduleAdjustment

__all__ = [
    # 基礎
    'BaseModel',
    'TenantBaseModel',
    # 核心
    'Conglomerate',
    'ConglomerateLog',
    'User',
    'UserType',
    'Organization',
    'CustomerType',
    'Contract',
    'ContractStatus',
    'BlockedEmailDomain',
    # 組織架構
    'OrganizationalUnit',
    'UnitType',
    'Role',
    'RoleType',
    'ScopeType',
    'RoleLevel',
    'ExclusiveGroup',
    # RBAC/ABAC 權限
    'Permission',
    'ResourceType',
    'ActionType',
    'PermissionLevel',
    'DEFAULT_PERMISSIONS',
    'RolePermission',
    'RbacDefault',
    'PermissionCondition',
    'ConditionType',
    'DEFAULT_CONDITIONS',
    # 職等職系 (人資架構)
    'JobLevel',
    'DEFAULT_JOB_LEVELS',
    'JobFamily',
    'JobFamilyType',
    'DEFAULT_JOB_FAMILIES',
    'JobTitle',
    'DEFAULT_JOB_TITLES',
    'EmployeePosition',
    'PositionType',
    'Delegation',
    'DelegationType',
    'DelegationStatus',
    'ApprovalCategory',
    'JobLevelApprovalLimit',
    'DEFAULT_APPROVAL_CATEGORIES',
    # 職務管理
    'Duty',
    'DutyCategory',
    'DEFAULT_DUTY_CATEGORIES',
    # 關聯表
    'UserUnitAssignment',
    'UserRoleAssignment',
    # 成員關係
    'UserUnitMembership',
    'MembershipType',
    'MembershipRole',
    # 通用選項清單
    'LookupCategory',
    'LookupItem',
    # 功能
    'Module',
    'MenuItem',
    'MenuPermission',
    'MenuRoleRequirement',
    'MenuDefault',
    'Page',
    # 系統設定
    'SystemSetting',
    'SmtpConfig',
    'TelegramConfig',
    'RecipientGroup',
    # 認證相關
    'PasswordResetToken',
    'PasswordHistory',
    # 稽核日誌
    'AuditLog',
    # 檔案管理
    'PlatformFile',
    # 用戶編號規則
    'UserNumberingRule',
    'UserNumberingCounter',
    'UsedUserNumber',
    'NumberingElementType',
    'NumberingResetPeriod',
    'NumberingUsageScope',
    # 模組使用權控制
    'ModuleAccessControl',
    'TargetType',
    # 時間管理
    'WorkSchedule',
    'DEFAULT_WORK_SCHEDULES',
    'ScheduleHoliday',
    'DEFAULT_TW_HOLIDAYS_2026',
    'ShiftType',
    'DEFAULT_SHIFT_TYPES',
    'PersonalSchedule',
    'ScheduleAdjustment',
]
