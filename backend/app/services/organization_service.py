"""
BeakPlatform Organization Service
企業管理服務
"""
import logging
from datetime import date
from typing import Optional, Dict, Any, Tuple

from ..models import (
    Organization, CustomerType,
    Contract, ContractStatus,
    User, UserType,
    Role, RoleType, ScopeType,
    BlockedEmailDomain,
    OrganizationalUnit, UnitType
)
from .. import db

logger = logging.getLogger(__name__)

# 密碼規則
MIN_PASSWORD_LENGTH = 12
DEFAULT_ADMIN_PASSWORD = 'ChangeMe123!'  # 預設密碼 (首次登入必須變更)


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
            admin_user = OrganizationService._create_default_admin(
                org=org,
                username=admin_username,
                password=admin_password or DEFAULT_ADMIN_PASSWORD,
                created_by=created_by
            )

            # 建立預設角色
            OrganizationService._create_default_roles(org)

            # 建立預設單位（管理員專用）
            OrganizationService._create_default_units(org)

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
            is_manager=True,
            is_system_role=True,
            is_active=True
        )
        org_admin_role.update_full_path()
        db.session.add(org_admin_role)
        roles['org_admin'] = org_admin_role

        # 部門主管角色 (通用，可套用到任何部門)
        dept_manager_role = Role(
            org_secure_code=org.secure_code,
            role_type=RoleType.POSITION,
            scope_type=ScopeType.DEPARTMENT,
            code='DEPT_MANAGER',
            name='部門主管',
            description='部門管理者',
            is_manager=True,
            is_system_role=True,
            is_active=True
        )
        dept_manager_role.update_full_path()
        db.session.add(dept_manager_role)
        roles['dept_manager'] = dept_manager_role

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

        # 群組召集人角色
        group_convener_role = Role(
            org_secure_code=org.secure_code,
            role_type=RoleType.ROLE,
            scope_type=ScopeType.GROUP,
            code='GROUP_CONVENER',
            name='群組召集人',
            description='群組管理者',
            is_manager=True,
            is_system_role=True,
            is_active=True
        )
        group_convener_role.update_full_path()
        db.session.add(group_convener_role)
        roles['group_convener'] = group_convener_role

        # 一般員工角色
        employee_role = Role(
            org_secure_code=org.secure_code,
            role_type=RoleType.ROLE,
            scope_type=ScopeType.GLOBAL,
            code='EMPLOYEE',
            name='一般員工',
            description='一般員工權限',
            is_manager=False,
            is_system_role=True,
            is_active=True
        )
        employee_role.update_full_path()
        db.session.add(employee_role)
        roles['employee'] = employee_role

        logger.info(f"Default roles created for org {org.code}")

        return roles

    @staticmethod
    def _create_default_units(org: Organization) -> Dict[str, OrganizationalUnit]:
        """
        建立預設單位

        包含「管理員專用」系統保留單位，用於表單分類的權限控制。

        Returns:
            Dict[str, OrganizationalUnit]: 單位字典
        """
        units = {}

        # 管理員專用單位
        admin_only_unit = OrganizationalUnit(
            org_secure_code=org.secure_code,
            unit_type=UnitType.GROUP,
            code='ADMIN_ONLY',
            name='管理員專用',
            description='系統保留群組，僅管理員可見',
            is_system_unit=True,
            is_active=True,
            sort_order=9999
        )
        admin_only_unit.update_full_path()
        db.session.add(admin_only_unit)
        db.session.flush()  # 取得 secure_code
        units['admin_only'] = admin_only_unit

        logger.info(f"Default units created for org {org.code}")

        return units

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

        系統企業 (system.local) 是特殊企業，永久有效，不受合約限制。
        用於存放系統管理員帳號。

        Returns:
            Tuple[Organization, User]: (系統企業, 系統管理員)
        """
        # 檢查是否已存在
        existing = Organization.query.filter(
            Organization.domain_name == 'system.local',
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
            name='BeakPlatform System',
            domain_name='system.local',
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
            email='admin@system.local',
            display_name='系統管理員',
            user_type=UserType.SYSTEM_ADMIN,
            is_active=True
        )
        admin.set_password('admin123')  # 開發環境預設密碼
        db.session.add(admin)

        # 建立預設角色
        OrganizationService._create_default_roles(org)

        db.session.commit()

        logger.info("System organization initialized")

        return org, admin
