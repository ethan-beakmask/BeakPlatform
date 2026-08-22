"""
BeakMask Organization Service
企業管理服務
"""
import json
import logging
from datetime import date
from typing import Optional, Dict, Any, Tuple

from ..models import (
    Organization, CustomerType,
    Contract, ContractStatus,
    User, UserType,
    Role, RoleType, ScopeType, ExclusiveGroup,
    BlockedEmailDomain,
    UserNumberingRule,
)
from ..models.organizational_unit import OrganizationalUnit, UnitType
from ..models.user_numbering_rule import (
    NumberingUsageScope, NumberingDefaultFor, NumberingElementType
)
from ..constants import SYSTEM_ORG_CODE
from .. import db

logger = logging.getLogger(__name__)

# 密碼規則
MIN_PASSWORD_LENGTH = 12
DEFAULT_ADMIN_PASSWORD = None  # 已棄用：建立企業時密碼為必填


class OrganizationService:
    """企業管理服務"""

    @staticmethod
    def create_organization(
        code: str,
        name: str,
        domain_name: str,
        display_name: str = None,
        customer_type: str = CustomerType.TRIAL,
        user_limit: int = 5,
        description: str = None,
        contact_person: str = None,
        contact_email: str = None,
        contact_phone: str = None,
        address: str = None,
        create_admin: bool = True,
        admin_username: str = 'admin',
        admin_password: str = None,
        created_by: str = None
    ) -> Tuple[Organization, Optional[User]]:
        """
        建立企業

        Args:
            code: 企業代碼
            name: 企業名稱
            domain_name: 登入網域
            display_name: 顯示名稱（多語言）
            customer_type: 客戶類型
            user_limit: 帳號上限
            description: 描述
            contact_person: 聯絡人
            contact_email: 聯絡 Email
            contact_phone: 聯絡電話
            address: 地址
            create_admin: 是否建立預設管理員
            admin_username: 管理員帳號名稱（預設 admin）
            admin_password: 管理員密碼 (預設 ChangeMe123!)
            created_by: 建立者

        Returns:
            Tuple[Organization, User]: (企業, 企業管理員)

        Raises:
            ValueError: 如果 code 或 domain_name 已存在，或 domain 被封鎖
        """
        domain_name = domain_name.lower().strip()

        # 檢查 domain 是否在黑名單
        if BlockedEmailDomain.is_blocked(domain_name):
            reason = BlockedEmailDomain.get_blocked_reason(domain_name)
            raise ValueError(f'此 Domain ({domain_name}) 不允許註冊: {reason or "公共信箱"}')

        # 檢查 code 是否重複
        existing = Organization.query.filter(
            Organization.code == code,
            Organization.is_deleted == False
        ).first()
        if existing:
            raise ValueError(f'企業代碼 {code} 已存在')

        # 檢查 domain_name 是否重複
        existing = Organization.query.filter(
            Organization.domain_name == domain_name,
            Organization.is_deleted == False
        ).first()
        if existing:
            raise ValueError(f'登入網域 {domain_name} 已存在')

        # 建立企業
        org = Organization(
            code=code.upper(),
            name=name,
            display_name=display_name,
            domain_name=domain_name,
            customer_type=customer_type,
            user_limit=user_limit,
            description=description,
            contact_person=contact_person,
            contact_email=contact_email,
            contact_phone=contact_phone,
            address=address,
            is_active=True
        )
        db.session.add(org)
        db.session.flush()  # 取得 secure_code

        admin_user = None

        if create_admin:
            # 建立預設企業管理員（原始管理員）
            if not admin_password:
                raise ValueError('管理員密碼為必填')
            admin_user = OrganizationService._create_default_admin(
                org=org,
                username=admin_username,
                password=admin_password,
                created_by=created_by
            )

            # 建立預設角色
            default_roles = OrganizationService._create_default_roles(org)

            # 為預設角色配置權限
            db.session.flush()  # 確保角色有 secure_code
            OrganizationService._assign_default_role_permissions(org, default_roles)

            # 指派 ORG_ADMIN 角色給管理員（雙鑰匙需要）
            from ..models.associations import UserRoleAssignment
            from sqlalchemy import text
            db.session.execute(text("SET LOCAL app.is_system_admin = 'true'"))
            db.session.flush()  # 確保 admin_user 和角色都有 secure_code
            org_admin_role = default_roles.get('org_admin')
            if org_admin_role:
                assignment = UserRoleAssignment(
                    user_secure_code=admin_user.secure_code,
                    role_secure_code=org_admin_role.secure_code,
                    org_secure_code=org.secure_code,
                )
                db.session.add(assignment)

            # 為 ORG_ADMIN 限定的選單建立角色需求（雙鑰匙第二層）
            OrganizationService._create_default_menu_role_requirements(
                org, default_roles
            )

            # 建立預設編號規則
            OrganizationService._create_default_numbering_rules(org)

            # 建立預設外部廠商群組
            OrganizationService._create_default_external_group(org)

        from ..defaults.od_protected_defaults import seed_org_builtin_protected_targets
        seed_org_builtin_protected_targets(org.secure_code)

        logger.info(f"Organization created: {org.code} ({org.domain_name}) by {created_by}")

        return org, admin_user

    @staticmethod
    def _create_default_admin(
        org: Organization,
        username: str,
        password: str,
        created_by: str = None
    ) -> User:
        """
        建立預設企業管理員（原始管理員）

        帳號格式: {username}@{domain_name}

        原始管理員特性:
        - is_original_admin=True (無合約時仍可登入)
        - must_change_password=True (首次登入必須變更密碼)
        """
        admin_email = f'{username}@{org.domain_name}'

        admin_user = User(
            org_secure_code=org.secure_code,
            username=username,
            email=admin_email,
            display_name=f'{org.name} 管理員',
            user_type=UserType.ORG_ADMIN,
            is_active=True,
            is_original_admin=True,
            must_change_password=True
        )
        admin_user.set_password(password)
        db.session.add(admin_user)

        logger.info(f"Original admin created: {admin_email} for org {org.code}")

        return admin_user

    @staticmethod
    def _create_default_roles(org: Organization) -> Dict[str, Role]:
        """
        建立預設角色

        Returns:
            Dict[str, Role]: 角色字典
        """
        roles = {}

        # 企業管理員角色
        org_admin_role = Role(
            org_secure_code=org.secure_code,
            role_type=RoleType.ROLE,
            scope_type=ScopeType.GLOBAL,
            code='ORG_ADMIN',
            name='企業管理員',
            description='管理整個企業的權限',
            exclusive_group=ExclusiveGroup.IDENTITY_TYPE,
            is_manager=True,
            is_system_role=True,
            is_active=True
        )
        org_admin_role.update_full_path()
        db.session.add(org_admin_role)
        roles['org_admin'] = org_admin_role

        # 部門成員角色 (基底，部門內所有人都有)
        dept_member_role = Role(
            org_secure_code=org.secure_code,
            role_type=RoleType.ROLE,
            scope_type=ScopeType.DEPARTMENT,
            code='DEPT_MEMBER',
            name='部門成員',
            description='部門通用成員角色，部門內所有人(主管+員工)皆擁有',
            is_manager=False,
            is_system_role=True,
            is_active=True
        )
        dept_member_role.update_full_path()
        db.session.add(dept_member_role)
        roles['dept_member'] = dept_member_role

        # 部門主管角色 (與 DEPT_EMPLOYEE 互斥，per-unit)
        dept_manager_role = Role(
            org_secure_code=org.secure_code,
            role_type=RoleType.POSITION,
            scope_type=ScopeType.DEPARTMENT,
            code='DEPT_MANAGER',
            name='部門主管',
            description='部門管理者，與部門員工互斥(同一部門下擇一)',
            exclusive_group=ExclusiveGroup.DEPT_POSITION,
            is_manager=True,
            is_system_role=True,
            is_active=True
        )
        dept_manager_role.update_full_path()
        db.session.add(dept_manager_role)
        roles['dept_manager'] = dept_manager_role

        # 部門員工角色 (與 DEPT_MANAGER 互斥，per-unit)
        dept_employee_role = Role(
            org_secure_code=org.secure_code,
            role_type=RoleType.ROLE,
            scope_type=ScopeType.DEPARTMENT,
            code='DEPT_EMPLOYEE',
            name='部門員工',
            description='部門一般員工，與部門主管互斥(同一部門下擇一)',
            exclusive_group=ExclusiveGroup.DEPT_POSITION,
            is_manager=False,
            is_system_role=True,
            is_active=True
        )
        dept_employee_role.update_full_path()
        db.session.add(dept_employee_role)
        roles['dept_employee'] = dept_employee_role

        # 部門副主管角色
        dept_deputy_role = Role(
            org_secure_code=org.secure_code,
            role_type=RoleType.POSITION,
            scope_type=ScopeType.DEPARTMENT,
            code='DEPT_DEPUTY',
            name='副主管',
            description='部門副主管',
            is_manager=True,
            is_system_role=True,
            is_active=True
        )
        dept_deputy_role.update_full_path()
        db.session.add(dept_deputy_role)
        roles['dept_deputy'] = dept_deputy_role

        # 部門代理人1角色
        dept_proxy1_role = Role(
            org_secure_code=org.secure_code,
            role_type=RoleType.POSITION,
            scope_type=ScopeType.DEPARTMENT,
            code='DEPT_PROXY1',
            name='代理人(一)',
            description='部門代理人，主管不在時代為簽核',
            is_manager=False,
            is_system_role=True,
            is_active=True
        )
        dept_proxy1_role.update_full_path()
        db.session.add(dept_proxy1_role)
        roles['dept_proxy1'] = dept_proxy1_role

        # 部門代理人2角色
        dept_proxy2_role = Role(
            org_secure_code=org.secure_code,
            role_type=RoleType.POSITION,
            scope_type=ScopeType.DEPARTMENT,
            code='DEPT_PROXY2',
            name='代理人(二)',
            description='部門代理人，主管不在時代為簽核',
            is_manager=False,
            is_system_role=True,
            is_active=True
        )
        dept_proxy2_role.update_full_path()
        db.session.add(dept_proxy2_role)
        roles['dept_proxy2'] = dept_proxy2_role

        # 社群成員角色 (基底，社群內所有人都有)
        group_member_role = Role(
            org_secure_code=org.secure_code,
            role_type=RoleType.ROLE,
            scope_type=ScopeType.GROUP,
            code='GROUP_MEMBER',
            name='社群成員',
            description='社群通用成員角色，社群內所有人(團長+團員)皆擁有',
            is_manager=False,
            is_system_role=True,
            is_active=True
        )
        group_member_role.update_full_path()
        db.session.add(group_member_role)
        roles['group_member'] = group_member_role

        # 社群團長角色 (與 GROUP_EMPLOYEE 互斥，per-unit)
        group_manager_role = Role(
            org_secure_code=org.secure_code,
            role_type=RoleType.ROLE,
            scope_type=ScopeType.GROUP,
            code='GROUP_MANAGER',
            name='社群團長',
            description='社群管理者，與社群團員互斥(同一社群下擇一)',
            exclusive_group=ExclusiveGroup.GROUP_POSITION,
            is_manager=True,
            is_system_role=True,
            is_active=True
        )
        group_manager_role.update_full_path()
        db.session.add(group_manager_role)
        roles['group_manager'] = group_manager_role

        # 社群團員角色 (與 GROUP_MANAGER 互斥，per-unit)
        group_employee_role = Role(
            org_secure_code=org.secure_code,
            role_type=RoleType.ROLE,
            scope_type=ScopeType.GROUP,
            code='GROUP_EMPLOYEE',
            name='社群團員',
            description='社群一般團員，與社群團長互斥(同一社群下擇一)',
            exclusive_group=ExclusiveGroup.GROUP_POSITION,
            is_manager=False,
            is_system_role=True,
            is_active=True
        )
        group_employee_role.update_full_path()
        db.session.add(group_employee_role)
        roles['group_employee'] = group_employee_role

        # 表單設計師角色
        form_editor_role = Role(
            org_secure_code=org.secure_code,
            role_type=RoleType.ROLE,
            scope_type=ScopeType.GLOBAL,
            code='FORM_DESIGNER',
            name='表單設計師',
            description='管理表單範本、流程設計，並可試行未發行的設計稿',
            is_manager=False,
            is_system_role=True,
            is_active=True
        )
        form_editor_role.update_full_path()
        db.session.add(form_editor_role)
        roles['form_designer'] = form_editor_role

        # 流程設計師角色
        flow_designer_role = Role(
            org_secure_code=org.secure_code,
            role_type=RoleType.ROLE,
            scope_type=ScopeType.GLOBAL,
            code='FLOW_DESIGNER',
            name='流程設計師',
            description='設計與管理簽核流程',
            is_manager=False,
            is_system_role=True,
            is_active=True
        )
        flow_designer_role.update_full_path()
        db.session.add(flow_designer_role)
        roles['flow_designer'] = flow_designer_role

        # 規格管理師角色
        spec_designer_role = Role(
            org_secure_code=org.secure_code,
            role_type=RoleType.ROLE,
            scope_type=ScopeType.GLOBAL,
            code='SPEC_DESIGNER',
            name='規格管理師',
            description='管理系統規格與參數定義',
            is_manager=False,
            is_system_role=True,
            is_active=True
        )
        spec_designer_role.update_full_path()
        db.session.add(spec_designer_role)
        roles['spec_designer'] = spec_designer_role

        # 子系統架構師角色
        subsys_designer_role = Role(
            org_secure_code=org.secure_code,
            role_type=RoleType.ROLE,
            scope_type=ScopeType.GLOBAL,
            code='SUBSYS_DESIGNER',
            name='子系統架構師',
            description='管理子系統架構與模組配置',
            is_manager=False,
            is_system_role=True,
            is_active=True
        )
        subsys_designer_role.update_full_path()
        db.session.add(subsys_designer_role)
        roles['subsys_designer'] = subsys_designer_role

        # 企業成員角色
        employee_role = Role(
            org_secure_code=org.secure_code,
            role_type=RoleType.ROLE,
            scope_type=ScopeType.GLOBAL,
            code='EMPLOYEE',
            name='企業成員',
            description='企業成員權限',
            exclusive_group=ExclusiveGroup.IDENTITY_TYPE,
            is_manager=False,
            is_system_role=True,
            is_active=True
        )
        employee_role.update_full_path()
        db.session.add(employee_role)
        roles['employee'] = employee_role

        # 外部廠商角色（非雇傭關係，受限存取）
        external_users_role = Role(
            org_secure_code=org.secure_code,
            role_type=RoleType.ROLE,
            scope_type=ScopeType.EXTERNAL,
            code='EXTERNAL_USERS',
            name='外部廠商',
            description='外部廠商帳號權限（非雇傭關係，受限存取）',
            exclusive_group=ExclusiveGroup.IDENTITY_TYPE,
            is_manager=False,
            is_system_role=True,
            is_active=True
        )
        external_users_role.update_full_path()
        db.session.add(external_users_role)
        roles['external_users'] = external_users_role

        # 弱點風險管制員角色
        risk_controller_role = Role(
            org_secure_code=org.secure_code,
            role_type=RoleType.ROLE,
            scope_type=ScopeType.GLOBAL,
            code='RISK_CONTROLLER',
            name='弱點風險管制員',
            description='管理弱點生命週期、風險調整審核與資產弱點追蹤',
            is_manager=False,
            is_system_role=True,
            is_active=True
        )
        risk_controller_role.update_full_path()
        db.session.add(risk_controller_role)
        roles['risk_controller'] = risk_controller_role

        logger.info(f"Default roles created for org {org.code}")

        return roles

    @staticmethod
    def _assign_default_role_permissions(org: Organization, roles: dict) -> None:
        """
        為新企業的預設角色配置權限。

        權限分配原則：
        - EMPLOYEE: 基本表單使用權限（填寫、檢視、簽核）
        - FORM_DESIGNER: 表單範本檢視/管理/發行 + 試行設計稿
        - FLOW_DESIGNER: 流程檢視/管理 + 試行設計稿
        - ORG_ADMIN: 透過 module_access_required 直接放行，不需配 role_permissions
        """
        from ..models.permission import Permission
        from ..models.role_permission import RolePermission

        # 角色 → 權限對照表
        role_perm_map = {
            'employee': [
                'form_workflow.form.create',
                'form_workflow.form.view',
                'form_workflow.approval.approve',
                'form_workflow.approval.transfer',
            ],
            'form_designer': [
                'form_workflow.template.view',
                'form_workflow.template.manage',
                'form_workflow.template.publish',
                'form_workflow.design.tryout',
            ],
            'flow_designer': [
                'form_workflow.workflow.view',
                'form_workflow.workflow.manage',
                'form_workflow.design.tryout',
            ],
            'risk_controller': [
                'vuln_lifecycle.dashboard.view',
                'vuln_lifecycle.asset.view',
                'vuln_lifecycle.finding.view',
                'vuln_lifecycle.risk.view',
                'vuln_lifecycle.risk.adjust',
                'vuln_lifecycle.risk.approve',
            ],
        }

        # 收集所有需要的權限代碼
        all_perm_codes = set()
        for codes in role_perm_map.values():
            all_perm_codes.update(codes)

        # 批次查詢權限
        perms = Permission.query.filter(
            Permission.code.in_(list(all_perm_codes)),
            Permission.is_deleted == False,
            Permission.is_active == True
        ).all()
        perm_by_code = {p.code: p for p in perms}

        assigned = 0
        for role_key, perm_codes in role_perm_map.items():
            role = roles.get(role_key)
            if not role:
                continue
            for code in perm_codes:
                perm = perm_by_code.get(code)
                if not perm:
                    continue
                rp = RolePermission(
                    role_secure_code=role.secure_code,
                    permission_secure_code=perm.secure_code,
                    is_active=True,
                )
                db.session.add(rp)
                assigned += 1

        logger.info(f"Default role permissions assigned for org {org.code}: {assigned} permissions")

    @staticmethod
    def _create_default_menu_role_requirements(
        org: Organization, default_roles: dict
    ):
        """
        為新企業建立預設選單角色需求（雙鑰匙 Key2）。

        使用 MENU_ROLE_DEFAULTS 定義，為每個選單建立完整的角色需求，
        包含 ORG_ADMIN、EMPLOYEE、EXTERNAL_USERS、FORM_DESIGNER 等角色。

        委託給 MenuService.seed_org_role_requirements() 統一處理。
        """
        from .menu_service import MenuService

        db.session.flush()  # 確保角色都有 secure_code

        count = MenuService.seed_org_role_requirements(org.secure_code)
        if count:
            logger.info(
                f"Created {count} menu role requirements for org {org.code}"
            )

    @staticmethod
    def _create_default_numbering_rules(org: Organization) -> UserNumberingRule:
        """
        建立預設編號規則（5 個）

        新企業建立時自動產生。格式刻意不完美，
        半強迫管理員進入 /admin/numbering 認真規劃自家編號系統。
        """
        # 1. 預設企業成員編號 — 純 4 位序號
        employee_rule = UserNumberingRule(
            org_secure_code=org.secure_code,
            name='預設企業成員編號',
            description='4 位數序號',
            elements={
                'components': [
                    {'type': NumberingElementType.SEQUENCE, 'order': 1,
                     'start': 1, 'digits': 4, 'reset_period': 'never'},
                ],
                'total_length': 4,
            },
            usage_scope=NumberingUsageScope.INTERNAL_ONLY,
            default_for=NumberingDefaultFor.EMPLOYEE,
            is_active=True,
        )
        db.session.add(employee_rule)

        # 2. 外部廠商編號 — 賓 + 4 位序號 + (臨)
        ext_rule = UserNumberingRule(
            org_secure_code=org.secure_code,
            name='外部廠商編號',
            description='前綴「賓」+ 4 位序號 + 後綴「(臨)」',
            elements={
                'components': [
                    {'type': NumberingElementType.PREFIX, 'order': 1,
                     'values': ['賓']},
                    {'type': NumberingElementType.SEQUENCE, 'order': 5,
                     'start': 1, 'digits': 4, 'reset_period': 'never'},
                    {'type': NumberingElementType.SUFFIX, 'order': 6,
                     'values': ['(臨)']},
                ],
                'total_length': 0,
            },
            usage_scope=NumberingUsageScope.EXTERNAL_ONLY,
            default_for=NumberingDefaultFor.EXTERNAL,
            is_active=True,
        )
        db.session.add(ext_rule)

        # 3. 預設表單編號 — Form-YYMM + 5 位序號（每月重置）
        form_rule = UserNumberingRule(
            org_secure_code=org.secure_code,
            name='預設表單編號',
            description='Form- + 年月 + 5 位序號（每月重置）',
            elements={
                'components': [
                    {'type': NumberingElementType.PREFIX, 'order': 1,
                     'values': ['Form-']},
                    {'type': NumberingElementType.YEAR, 'order': 2,
                     'format': 'yy'},
                    {'type': NumberingElementType.MONTH, 'order': 4,
                     'format': 'mm'},
                    {'type': NumberingElementType.SEQUENCE, 'order': 5,
                     'start': 1, 'digits': 5, 'reset_period': 'monthly'},
                ],
                'total_length': 0,
            },
            usage_scope=NumberingUsageScope.INTERNAL_ONLY,
            default_for=NumberingDefaultFor.FORM,
            is_active=True,
        )
        db.session.add(form_rule)

        # 4. 門禁卡實體卡號 — 純 4 位序號（內部通用）
        card_rule = UserNumberingRule(
            org_secure_code=org.secure_code,
            name='門禁卡實體卡號',
            description='4 位數序號（內部通用）',
            elements={
                'components': [
                    {'type': NumberingElementType.SEQUENCE, 'order': 5,
                     'start': 1, 'digits': 4, 'reset_period': 'never'},
                ],
                'total_length': 0,
            },
            usage_scope=NumberingUsageScope.INTERNAL_UNIVERSAL,
            is_active=True,
        )
        db.session.add(card_rule)

        # 5. 行政資產編號 — ADMN- + 年碼 + 4 位序號
        asset_rule = UserNumberingRule(
            org_secure_code=org.secure_code,
            name='行政資產編號',
            description='ADMN- + 年碼 + 4 位序號',
            elements={
                'components': [
                    {'type': NumberingElementType.PREFIX, 'order': 1,
                     'values': ['ADMN-']},
                    {'type': NumberingElementType.YEAR, 'order': 2,
                     'format': 'yy'},
                    {'type': NumberingElementType.SEQUENCE, 'order': 5,
                     'start': 1, 'digits': 4, 'reset_period': 'never'},
                ],
                'total_length': 0,
            },
            usage_scope=NumberingUsageScope.INTERNAL_ONLY,
            is_active=True,
        )
        db.session.add(asset_rule)

        logger.info(f"Default numbering rules (5) created for org {org.code}")

        return employee_rule

    @staticmethod
    def _create_default_external_group(org: Organization) -> OrganizationalUnit:
        """
        建立預設外部廠商群組

        系統級群組，is_system_unit=True，企業管理員不可刪除。
        所有外部廠商帳號預設歸屬此群組或其子群組。
        """
        group = OrganizationalUnit(
            org_secure_code=org.secure_code,
            unit_type=UnitType.GROUP,
            code='EXTERNAL_VENDORS',
            name='外部廠商專用群組',
            description='外部廠商帳號預設歸屬群組',
            is_system_unit=True,
            is_active=True,
        )
        group.update_full_path()
        db.session.add(group)

        logger.info(f"Default external vendors group created for org {org.code}")

        return group

    @staticmethod
    def create_contract(
        org_secure_code: str,
        start_date: date,
        end_date: date,
        name: str = None,
        description: str = None,
        amount: float = None,
        modules_config: str = None,
        notes: str = None,
        created_by: str = None
    ) -> Contract:
        """
        建立合約

        Args:
            org_secure_code: 企業 secure_code
            start_date: 開始日期
            end_date: 結束日期
            name: 合約名稱
            description: 描述
            amount: 金額
            modules_config: 模組配置 (JSON)
            notes: 備註
            created_by: 建立者

        Returns:
            Contract: 建立的合約

        Raises:
            ValueError: 如果企業不存在或日期無效
        """
        # 檢查企業是否存在
        org = Organization.query.filter(
            Organization.secure_code == org_secure_code,
            Organization.is_deleted == False
        ).first()

        if not org:
            raise ValueError('企業不存在')

        # 檢查日期
        if end_date < start_date:
            raise ValueError('結束日期不可早於開始日期')

        # 產生合約編號
        contract_number = Contract.generate_contract_number()

        contract = Contract(
            org_secure_code=org_secure_code,
            contract_number=contract_number,
            name=name or f'{org.name} 合約',
            description=description,
            start_date=start_date,
            end_date=end_date,
            amount=amount,
            status=ContractStatus.ACTIVE,
            modules_config=modules_config,
            notes=notes,
            created_by_secure_code=created_by  # 稽核欄位
        )
        db.session.add(contract)

        # 依合約模組清單種入模組預設角色與 Key2（碰撞跳過，冪等）
        if modules_config:
            from .module_role_service import ModuleRoleService
            try:
                module_codes = json.loads(modules_config)
            except (json.JSONDecodeError, TypeError):
                module_codes = []
            if isinstance(module_codes, list) and module_codes:
                ModuleRoleService.seed_contract_module_roles(
                    org_secure_code, module_codes
                )

        logger.info(f"Contract created: {contract_number} for org {org.code} by {created_by}")

        return contract

    @staticmethod
    def create_organization_with_contract(
        code: str,
        name: str,
        domain_name: str,
        contract_start_date: date,
        contract_end_date: date,
        display_name: str = None,
        customer_type: str = CustomerType.FORMAL,
        user_limit: int = 50,
        contract_amount: float = None,
        admin_username: str = 'admin',
        admin_password: str = None,
        created_by: str = None,
        **org_kwargs
    ) -> Tuple[Organization, User, Contract]:
        """
        建立企業並同時建立合約

        Returns:
            Tuple[Organization, User, Contract]: (企業, 管理員, 合約)
        """
        # 建立企業
        org, admin_user = OrganizationService.create_organization(
            code=code,
            name=name,
            domain_name=domain_name,
            display_name=display_name,
            customer_type=customer_type,
            user_limit=user_limit,
            create_admin=True,
            admin_username=admin_username,
            admin_password=admin_password,
            created_by=created_by,
            **org_kwargs
        )

        # 建立合約
        contract = OrganizationService.create_contract(
            org_secure_code=org.secure_code,
            start_date=contract_start_date,
            end_date=contract_end_date,
            amount=contract_amount,
            created_by=created_by
        )

        return org, admin_user, contract

    @staticmethod
    def init_system_organization() -> Tuple[Organization, User]:
        """
        初始化系統企業

        系統企業 (SYSTEM_ORG_CODE) 是特殊企業，永久有效，不受合約限制。
        用於存放系統管理員帳號。

        Returns:
            Tuple[Organization, User]: (系統企業, 系統管理員)
        """
        # 檢查是否已存在
        existing = Organization.query.filter(
            Organization.domain_name == SYSTEM_ORG_CODE,
            Organization.is_deleted == False
        ).first()

        if existing:
            logger.info("System organization already exists")
            # 找到系統管理員
            admin = User.query.filter(
                User.org_secure_code == existing.secure_code,
                User.user_type == UserType.SYSTEM_ADMIN,
                User.is_deleted == False
            ).first()
            return existing, admin

        # 建立系統企業
        org = Organization(
            code='SYSTEM',
            name='BeakMask System',
            domain_name=SYSTEM_ORG_CODE,
            customer_type=CustomerType.FORMAL,
            user_limit=100,
            description='系統管理企業',
            is_active=True
        )
        db.session.add(org)
        db.session.flush()

        # 建立系統管理員
        admin = User(
            org_secure_code=org.secure_code,
            username='admin',
            email=f'admin@{SYSTEM_ORG_CODE}',
            display_name='系統管理員',
            user_type=UserType.SYSTEM_ADMIN,
            is_active=True
        )
        admin.set_password('admin123')  # 開發環境預設密碼
        db.session.add(admin)

        # 建立預設角色
        OrganizationService._create_default_roles(org)

        from ..defaults.od_protected_defaults import seed_org_builtin_protected_targets
        seed_org_builtin_protected_targets(org.secure_code)

        db.session.commit()

        logger.info("System organization initialized")

        return org, admin
