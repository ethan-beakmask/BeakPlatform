#!/usr/bin/env python3
"""
BeakMask Seed Data Script
使用 Model 建立種子資料，secure_code 由 Model 自動生成

使用方式:
    cd /opt/BeakMask
    source venv/bin/activate
    python scripts/seed_data.py

注意: 會清除現有資料！
"""
import sys
import os

# 加入專案路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from datetime import date, datetime
from decimal import Decimal

# 初始化 Flask app
from app import create_app, db
from app.models import (
    Organization, User, UserType,
    JobLevel, JobFamily, JobFamilyType, JobTitle,
    Module, MenuItem, MenuPermission,
    Role, RoleType, ScopeType, RoleLevel, ExclusiveGroup,
    Permission, RolePermission, PermissionCondition,
)
from app.models.permission import (
    DEFAULT_PERMISSIONS, ResourceType, ActionType, PermissionLevel
)
from app.models.permission_condition import DEFAULT_CONDITIONS
from app.utils.security import generate_secure_code
from app.constants import SYSTEM_ORG_CODE


def clear_existing_data():
    """清除現有資料 (按照外鍵順序)"""
    print("清除現有資料...")

    # 刪除順序很重要 (先刪除有外鍵依賴的表)
    tables = [
        # RBAC 相關 (新增)
        'role_permissions',
        'permission_conditions',
        'permissions',
        # 選單相關
        'menu_permissions',
        'menu_items',
        'modules',
        'pages',
        # HR 結構相關
        'employee_positions',
        'delegations',
        'job_titles',
        'job_families',
        'job_levels',
        # 用戶角色相關
        'user_role_assignments',
        'user_unit_assignments',
        'roles',
        'organizational_units',
        'contracts',
        'users',
        'organizations',
    ]

    for table in tables:
        try:
            db.session.execute(db.text(f"DELETE FROM {table}"))
        except Exception as e:
            print(f"  跳過 {table}: {e}")

    db.session.commit()
    print("  已清除")


def seed_system_org():
    """
    建立系統企業

    系統企業是特殊企業，用於：
    - 定義系統級共用選單 (is_shared=True)
    - 管理跨企業的系統功能
    - 作為「虛擬公司」承載全局設定
    """
    print(f"建立 {SYSTEM_ORG_CODE} 系統企業...")

    system_org = Organization(
        code='SYSTEM',
        name='系統管理',
        domain_name=SYSTEM_ORG_CODE,
        customer_type='SYSTEM',
        user_limit=10,
        description='系統級虛擬企業，用於承載跨企業共用功能',
        is_active=True,
        is_system_org=True
    )
    system_org.secure_code = SYSTEM_ORG_CODE
    db.session.add(system_org)
    db.session.commit()

    print(f"  企業: {system_org.name}")
    print(f"  secure_code: {system_org.secure_code}")
    return system_org


def seed_organization():
    """建立預設企業"""
    print("建立預設企業...")

    org = Organization(
        code='DEFAULT',
        name='預設企業',
        domain_name='beakmask.local',
        customer_type='TRIAL',
        user_limit=100,
        description='系統預設測試企業',
        is_active=True
    )
    db.session.add(org)
    db.session.commit()

    print(f"  企業: {org.name}")
    print(f"  secure_code: {org.secure_code}")
    return org


def seed_admin_user(org):
    """建立管理員帳號

    重要：系統管理員必須歸屬系統企業（SYSTEM_ORG_CODE），
    而不是預設企業。這確保系統管理員與企業級帳號完全分離。

    系統級 vs 企業級：
    - 系統級 (SYSTEM_ADMIN): org_secure_code = SYSTEM_ORG_CODE
    - 企業級 (ORG_ADMIN/EMPLOYEE): org_secure_code = 企業的 secure_code
    """
    print("建立管理員帳號...")

    admin = User(
        org_secure_code=SYSTEM_ORG_CODE,
        username='admin',
        email='admin@beakmask.local',
        display_name='系統管理員',
        user_type=UserType.SYSTEM_ADMIN,
        is_active=True
    )
    admin.set_password('admin123')
    db.session.add(admin)
    db.session.commit()

    print(f"  帳號: admin@beakmask.local")
    print(f"  密碼: admin123")
    print(f"  歸屬: {SYSTEM_ORG_CODE} (系統管理)")
    print(f"  secure_code: {admin.secure_code}")
    return admin


def seed_job_levels(org):
    """建立職等資料"""
    print("建立職等資料...")

    levels_data = [
        ('L900', '總經理級', 'President Level', 900, None, True, '全公司'),
        ('L800', '副總經理級', 'Vice President Level', 800, Decimal('50000000'), True, '多處室/事業部'),
        ('L700', '處長級', 'Director Level', 700, Decimal('10000000'), True, '單一處室'),
        ('L600', '副處長級', 'Deputy Director Level', 600, Decimal('5000000'), True, '協助處室管理'),
        ('L500', '經理級', 'Manager Level', 500, Decimal('1000000'), True, '單一部門'),
        ('L400', '副理級', 'Assistant Manager Level', 400, Decimal('500000'), True, '協助部門管理'),
        ('L300', '主任級', 'Supervisor Level', 300, Decimal('100000'), True, '小組/專案'),
        ('L200', '高級職員級', 'Senior Staff Level', 200, Decimal('50000'), False, None),
        ('L100', '職員級', 'Staff Level', 100, Decimal('10000'), False, None),
        ('L000', '外部廠商', 'External', 0, Decimal('0'), False, None),
    ]

    levels = {}
    for i, (code, name, name_en, order, limit, is_mgr, scope) in enumerate(levels_data):
        level = JobLevel(
            org_secure_code=org.secure_code,
            code=code,
            name=name,
            name_en=name_en,
            level_order=order,
            approval_limit=limit,
            approval_currency='TWD',
            is_manager_level=is_mgr,
            management_scope=scope,
            sort_order=(i + 1) * 10,
            is_system_default=True,
            is_active=True
        )
        db.session.add(level)
        levels[code] = level

    db.session.commit()
    print(f"  建立 {len(levels)} 個職等")
    return levels


def seed_job_families(org):
    """建立職系資料"""
    print("建立職系資料...")

    families_data = [
        ('MGR', '管理職', 'People Manager', JobFamilyType.MANAGER, None, '帶人主管，負責團隊管理與人員發展'),
        ('PROF', '專業職', 'Individual Contributor', JobFamilyType.PROFESSIONAL, None, '不帶人的專業人員，專注於專業技能發展'),
        ('SALES', '業務職', 'Sales Position', JobFamilyType.PROFESSIONAL, 'PROF', '負責業務開發與客戶關係維護'),
        ('CS', '客服職', 'Customer Service Position', JobFamilyType.PROFESSIONAL, 'PROF', '負責客戶服務與問題處理'),
        ('ADMIN', '行政職', 'Administration Position', JobFamilyType.PROFESSIONAL, 'PROF', '負責行政支援與內部管理'),
        ('TECH', '工程技術職', 'Technical Position', JobFamilyType.PROFESSIONAL, 'PROF', '負責技術研發與工程實作'),
    ]

    families = {}
    for i, (code, name, name_en, ftype, parent_code, desc) in enumerate(families_data):
        family = JobFamily(
            org_secure_code=org.secure_code,
            code=code,
            name=name,
            name_en=name_en,
            family_type=ftype,
            parent_secure_code=families[parent_code].secure_code if parent_code else None,
            description=desc,
            sort_order=(i + 1) * 10,
            is_system_default=True,
            is_active=True
        )
        db.session.add(family)
        db.session.flush()  # 取得 secure_code
        families[code] = family

    db.session.commit()
    print(f"  建立 {len(families)} 個職系")
    return families


def seed_job_titles(org, levels, families):
    """建立職稱資料"""
    print("建立職稱資料...")

    titles_data = [
        # (code, name, name_en, level_code, family_code, is_supervisor)
        # L900
        ('PRES', '總經理', 'President', 'L900', 'MGR', True),
        ('EVP', '執行副總經理', 'Executive Vice President', 'L900', 'MGR', True),
        # L800
        ('SVP', '資深副總經理', 'Senior Vice President', 'L800', 'MGR', True),
        ('VP', '副總經理', 'Vice President', 'L800', 'MGR', True),
        ('SR_CONSULT', '資深顧問', 'Senior Consultant', 'L800', 'PROF', False),
        ('CHIEF_ENG', '總工程師', 'Chief Engineer', 'L800', 'TECH', False),
        # L700
        ('SR_DIR', '資深處長', 'Senior Director', 'L700', 'MGR', True),
        ('DIR', '處長', 'Director', 'L700', 'MGR', True),
        ('SR_SA', '資深特別助理', 'Senior Special Assistant', 'L700', 'PROF', False),
        # L600
        ('DEP_DIR', '副處長', 'Deputy Director', 'L600', 'MGR', True),
        ('SA', '特別助理', 'Special Assistant', 'L600', 'PROF', False),
        # L500
        ('MGR', '經理', 'Manager', 'L500', 'MGR', True),
        ('PM', '專案經理', 'Project Manager', 'L500', 'PROF', False),
        ('PM_TECH', '技術專案經理', 'Technical Project Manager', 'L500', 'TECH', False),
        # L400
        ('ASST_MGR', '副理', 'Assistant Manager', 'L400', 'MGR', True),
        ('ASST_PM', '專案副理', 'Assistant Project Manager', 'L400', 'PROF', False),
        # L300
        ('SUPV', '主任', 'Supervisor', 'L300', 'MGR', True),
        ('PL', '專案主任', 'Project Leader', 'L300', 'PROF', False),
        ('PRIN_ENG', '主任工程師', 'Principal Engineer', 'L300', 'TECH', False),
        # L200
        ('SR_SPEC', '高級專員', 'Senior Specialist', 'L200', 'PROF', False),
        ('SR_SALES', '高級業務代表', 'Senior Sales Representative', 'L200', 'SALES', False),
        ('SR_CS', '高級客服代表', 'Senior Customer Service Rep', 'L200', 'CS', False),
        ('SR_ADMIN', '高級行政專員', 'Senior Admin Specialist', 'L200', 'ADMIN', False),
        ('SR_ENG', '高級工程師', 'Senior Engineer', 'L200', 'TECH', False),
        # L100
        ('SPEC', '專員', 'Specialist', 'L100', 'PROF', False),
        ('SALES', '業務代表', 'Sales Representative', 'L100', 'SALES', False),
        ('CSR', '客服代表', 'Customer Service Rep', 'L100', 'CS', False),
        ('ADMIN_SPEC', '行政專員', 'Admin Specialist', 'L100', 'ADMIN', False),
        ('ENG', '工程師', 'Engineer', 'L100', 'TECH', False),
        # L000
        ('CONTRACTOR', '約聘人員', 'Contractor', 'L000', 'PROF', False),
        ('INTERN', '實習生', 'Intern', 'L000', 'PROF', False),
        ('VENDOR', '廠商代表', 'Vendor Representative', 'L000', 'PROF', False),
    ]

    for i, (code, name, name_en, level_code, family_code, is_supv) in enumerate(titles_data):
        title = JobTitle(
            org_secure_code=org.secure_code,
            code=code,
            name=name,
            name_en=name_en,
            job_level_secure_code=levels[level_code].secure_code,
            job_family_secure_code=families[family_code].secure_code,
            is_supervisor=is_supv,
            sort_order=(i + 1),
            is_system_default=True,
            is_active=True
        )
        db.session.add(title)

    db.session.commit()
    print(f"  建立 {len(titles_data)} 個職稱")


def seed_modules(org):
    """建立系統模組"""
    print("建立系統模組...")

    module = Module(
        org_secure_code=org.secure_code,
        code='system',
        name='系統管理',
        description='系統內建管理模組',
        is_system_module=True,
        display_order=0,
        is_active=True
    )
    db.session.add(module)
    db.session.commit()

    print(f"  模組: {module.name}")
    print(f"  secure_code: {module.secure_code}")
    return module


def seed_menu_items(org, module):
    """建立選單項目"""
    print("建立選單項目...")

    # (code, title, link_type, link_target, order, level)
    # level: 0=系統管理員, 1=企業管理員, 2=一般用戶
    menus_data = [
        ('dashboard', '儀表板', 'route', 'main.dashboard', 0, 2),
        ('admin', '企業管理', 'route', 'admin.index', 1, 1),
        ('system_settings', '系統設定', 'route', 'admin.settings', 2, 1),
        ('users', '用戶管理', 'route', 'users.list_users', 3, 1),
        ('roles', '角色權限', 'route', 'roles.list_roles', 4, 1),
        ('modules', '模組管理', 'route', 'modules.list_modules', 6, 1),
        ('organizations', '企業總覽', 'route', 'organizations.list_orgs', 7, 0),
    ]

    menus_data.insert(5, ('menu_manage', '選單管理', 'route', 'menu.list_menu', 5, 0))

    menus = []
    for code, title, link_type, link_target, order, level in menus_data:
        menu = MenuItem(
            org_secure_code=org.secure_code,
            module_secure_code=module.secure_code,
            code=code,
            title=title,
            link_type=link_type,
            link_target=link_target,
            display_order=order,
            depth=0,
            required_level=level,
            is_active=True
        )
        db.session.add(menu)
        menus.append(menu)

    db.session.commit()
    print(f"  建立 {len(menus)} 個選單")
    return menus


def seed_menu_permissions(menus):
    """建立選單權限"""
    print("建立選單權限...")

    count = 0
    for menu in menus:
        # 根據 required_level 設定權限
        user_types = []
        if menu.required_level <= 0:
            user_types = [UserType.SYSTEM_ADMIN]
        elif menu.required_level <= 1:
            user_types = [UserType.SYSTEM_ADMIN, UserType.ORG_ADMIN]
        else:
            user_types = [UserType.SYSTEM_ADMIN, UserType.ORG_ADMIN, UserType.EMPLOYEE]

        for utype in user_types:
            perm = MenuPermission(
                menu_secure_code=menu.secure_code,
                user_type=utype
            )
            db.session.add(perm)
            count += 1

    db.session.commit()
    print(f"  建立 {count} 筆權限")


def seed_system_menus(system_org):
    """
    建立系統企業的共用選單

    共用選單 (is_shared=True) 會出現在所有企業用戶的選單中。
    這些選單可以設定 required_permission 來控制可見性。
    """
    print("建立系統共用選單...")

    # 先建立一個系統模組
    system_module = Module(
        org_secure_code=system_org.secure_code,
        code='system_core',
        name='系統核心',
        description='系統級共用功能',
        is_system_module=True,
        is_active=True
    )
    db.session.add(system_module)
    db.session.flush()

    # 共用選單資料：(code, title, link_type, link_target, order, is_shared, required_permission)
    menus_data = [
        # 說明中心 - 所有人可見
        ('help_center', '說明中心', 'url', 'https://docs.beakmask.local/help', 100, True, None),
        # 系統公告 - 所有人可見
        ('announcements', '系統公告', 'route', 'main.announcements', 101, True, None),
        # 伺服器設定 - 僅系統管理員可見 (is_shared=False，只在系統企業顯示)
        ('server_settings', '伺服器設定', 'route', 'portal.server_settings', 200, False, None),
    ]

    menus = []
    for code, title, link_type, link_target, order, is_shared, required_perm in menus_data:
        menu = MenuItem(
            org_secure_code=system_org.secure_code,
            module_secure_code=system_module.secure_code,
            code=code,
            title=title,
            link_type=link_type,
            link_target=link_target,
            display_order=order,
            depth=0,
            required_level=2,  # 基礎 user_type 權限
            is_active=True,
            is_shared=is_shared,
            required_permission=required_perm
        )
        db.session.add(menu)
        menus.append(menu)

    db.session.commit()
    print(f"  建立 {len(menus)} 個系統選單")

    # 為選單設定 MenuPermission
    count = 0
    for menu in menus:
        if menu.is_shared:
            # 共用選單 - 所有 user_type 都可見
            user_types = [UserType.SYSTEM_ADMIN, UserType.ORG_ADMIN, UserType.EMPLOYEE, UserType.EXTERNAL]
        else:
            # 非共用選單（如伺服器設定）- 僅系統管理員可見
            user_types = [UserType.SYSTEM_ADMIN]

        for utype in user_types:
            perm = MenuPermission(
                menu_secure_code=menu.secure_code,
                user_type=utype
            )
            db.session.add(perm)
            count += 1

    db.session.commit()
    print(f"  建立 {count} 筆 MenuPermission")

    return menus


# =============================================================================
# RBAC 種子資料
# =============================================================================

def seed_permissions():
    """
    建立系統預設權限

    權限是全局的，不屬於特定企業。
    共 62 個預設權限，定義在 app/models/permission.py 的 DEFAULT_PERMISSIONS。
    """
    print("建立系統權限...")

    permissions = {}
    for i, perm_data in enumerate(DEFAULT_PERMISSIONS):
        code = Permission.generate_code(
            perm_data['resource_type'],
            perm_data['action']
        )

        perm = Permission(
            resource_type=perm_data['resource_type'],
            action=perm_data['action'],
            code=code,
            name=perm_data['name'],
            description=perm_data.get('description'),
            permission_level=perm_data['level'],
            is_system_permission=True,
            is_active=True
        )
        db.session.add(perm)
        permissions[code] = perm

    db.session.commit()
    print(f"  建立 {len(permissions)} 個權限")
    return permissions


def seed_permission_conditions():
    """
    建立系統預設 ABAC 條件

    條件是全局的，不屬於特定企業。
    共 13 個預設條件，定義在 app/models/permission_condition.py 的 DEFAULT_CONDITIONS。
    """
    print("建立 ABAC 條件...")

    import json
    conditions = {}
    for i, cond_data in enumerate(DEFAULT_CONDITIONS):
        cond = PermissionCondition(
            code=cond_data['code'],
            name=cond_data['name'],
            description=cond_data.get('description'),
            condition_type=cond_data['condition_type'],
            expression=json.dumps(cond_data['expression'], ensure_ascii=False) if cond_data.get('expression') else None,
            requires_param=cond_data.get('requires_param', False),
            param_description=cond_data.get('param_description'),
            is_system_condition=True,
            is_active=True
        )
        db.session.add(cond)
        conditions[cond_data['code']] = cond

    db.session.commit()
    print(f"  建立 {len(conditions)} 個條件")
    return conditions


def seed_default_roles(org):
    """
    建立系統預設角色

    角色層級說明：
    - SYSTEM: 系統級 (系統管理員)
    - ORG: 企業級 (企業管理員、表單流程管理者)
    - MODULE: 模組級 (模組管理員、模組作者、模組讀者)
    - MEMBER: 成員級 (部門成員、群組成員、企業成員...)

    互斥群組說明：
    - EMPLOYEE: 企業成員類角色，不能同時是 EXTERNAL
    - EXTERNAL: 外部廠商類，不能同時是 EMPLOYEE
    """
    print("建立預設角色...")

    roles_data = [
        # 系統級角色
        {
            'code': 'SYSTEM_ADMIN',
            'name': '系統管理員',
            'description': '管理所有企業、系統設定、商店管理',
            'role_type': RoleType.ROLE,
            'scope_type': ScopeType.GLOBAL,
            'role_level': RoleLevel.SYSTEM,
            'exclusive_group': None,
            'is_manager': True,
            'is_system_role': True,
        },
        # 企業級角色
        {
            'code': 'ORG_ADMIN',
            'name': '企業管理員',
            'description': '管理企業設定、組織架構、帳號、角色、模組',
            'role_type': RoleType.ROLE,
            'scope_type': ScopeType.GLOBAL,
            'role_level': RoleLevel.ORG,
            'exclusive_group': ExclusiveGroup.IDENTITY_TYPE,
            'is_manager': True,
            'is_system_role': True,
        },
        {
            'code': 'FORM_FLOW_ADMIN',
            'name': '表單流程管理者',
            'description': '設計表單、流程，指定開發者',
            'role_type': RoleType.ROLE,
            'scope_type': ScopeType.GLOBAL,
            'role_level': RoleLevel.ORG,
            'exclusive_group': None,
            'is_manager': False,
            'is_system_role': True,
        },
        # 模組級角色
        {
            'code': 'MODULE_ADMIN',
            'name': '模組管理員',
            'description': '管理模組成員、角色、刪除文章',
            'role_type': RoleType.ROLE,
            'scope_type': ScopeType.GLOBAL,
            'role_level': RoleLevel.MODULE,
            'exclusive_group': None,
            'is_manager': True,
            'is_system_role': True,
        },
        {
            'code': 'MODULE_AUTHOR',
            'name': '模組作者',
            'description': '可建立新文件、隱藏自己文章、留言',
            'role_type': RoleType.ROLE,
            'scope_type': ScopeType.GLOBAL,
            'role_level': RoleLevel.MODULE,
            'exclusive_group': None,
            'is_manager': False,
            'is_system_role': True,
            'inherits_from': 'MODULE_READER',  # 繼承模組讀者權限
        },
        {
            'code': 'MODULE_READER',
            'name': '模組讀者',
            'description': '只可閱讀模組管理員開放的項目',
            'role_type': RoleType.ROLE,
            'scope_type': ScopeType.GLOBAL,
            'role_level': RoleLevel.MODULE,
            'exclusive_group': None,
            'is_manager': False,
            'is_system_role': True,
        },
        # 成員級角色
        {
            'code': 'DEPT_MANAGER',
            'name': '部門主管',
            'description': '部門管理者，有部門內的管理權限',
            'role_type': RoleType.POSITION,
            'scope_type': ScopeType.DEPARTMENT,
            'role_level': RoleLevel.MEMBER,
            'exclusive_group': None,
            'is_manager': True,
            'is_system_role': True,
        },
        {
            'code': 'DEPT_MEMBER',
            'name': '部門成員',
            'description': '一般部門成員',
            'role_type': RoleType.POSITION,
            'scope_type': ScopeType.DEPARTMENT,
            'role_level': RoleLevel.MEMBER,
            'exclusive_group': None,
            'is_manager': False,
            'is_system_role': True,
        },
        {
            'code': 'GROUP_MANAGER',
            'name': '社群團長',
            'description': '社群管理者',
            'role_type': RoleType.ROLE,
            'scope_type': ScopeType.GROUP,
            'role_level': RoleLevel.MEMBER,
            'exclusive_group': None,
            'is_manager': True,
            'is_system_role': True,
        },
        {
            'code': 'GROUP_MEMBER',
            'name': '群組成員',
            'description': '一般群組成員',
            'role_type': RoleType.ROLE,
            'scope_type': ScopeType.GROUP,
            'role_level': RoleLevel.MEMBER,
            'exclusive_group': None,
            'is_manager': False,
            'is_system_role': True,
        },
        {
            'code': 'EMPLOYEE',
            'name': '企業成員',
            'description': '基本企業成員角色',
            'role_type': RoleType.ROLE,
            'scope_type': ScopeType.GLOBAL,
            'role_level': RoleLevel.MEMBER,
            'exclusive_group': ExclusiveGroup.IDENTITY_TYPE,
            'is_manager': False,
            'is_system_role': True,
        },
        {
            'code': 'RESTRICTED_EMPLOYEE',
            'name': '受限制企業成員',
            'description': '臨時雇員，權限受限',
            'role_type': RoleType.ROLE,
            'scope_type': ScopeType.GLOBAL,
            'role_level': RoleLevel.MEMBER,
            'exclusive_group': ExclusiveGroup.IDENTITY_TYPE,
            'is_manager': False,
            'is_system_role': True,
        },
        {
            'code': 'EXTERNAL_CONSULTANT',
            'name': '外部顧問',
            'description': '外部顧問，只能存取被邀請的群組（非雇傭關係）',
            'role_type': RoleType.ROLE,
            'scope_type': ScopeType.EXTERNAL,
            'role_level': RoleLevel.MEMBER,
            'exclusive_group': ExclusiveGroup.IDENTITY_TYPE,
            'is_manager': False,
            'is_system_role': True,
        },
        {
            'code': 'EXTERNAL_VENDOR',
            'name': '廠商代表',
            'description': '外部廠商代表，只能存取被邀請的群組（非雇傭關係）',
            'role_type': RoleType.ROLE,
            'scope_type': ScopeType.EXTERNAL,
            'role_level': RoleLevel.MEMBER,
            'exclusive_group': ExclusiveGroup.IDENTITY_TYPE,
            'is_manager': False,
            'is_system_role': True,
        },
    ]

    roles = {}
    # 第一輪：建立所有角色（不含繼承關係）
    for i, role_data in enumerate(roles_data):
        role = Role(
            org_secure_code=org.secure_code,
            code=role_data['code'],
            name=role_data['name'],
            description=role_data.get('description'),
            role_type=role_data['role_type'],
            scope_type=role_data['scope_type'],
            role_level=role_data['role_level'],
            exclusive_group=role_data.get('exclusive_group'),
            is_manager=role_data.get('is_manager', False),
            is_system_role=role_data.get('is_system_role', False),
            sort_order=(i + 1) * 10,
            is_active=True
        )
        role.update_full_path()
        db.session.add(role)
        db.session.flush()  # 取得 secure_code
        roles[role_data['code']] = role

    # 第二輪：設定繼承關係
    for role_data in roles_data:
        if 'inherits_from' in role_data:
            parent_code = role_data['inherits_from']
            if parent_code in roles:
                roles[role_data['code']].inherits_from_secure_code = roles[parent_code].secure_code

    db.session.commit()
    print(f"  建立 {len(roles)} 個角色")
    return roles


def seed_role_permissions(roles, permissions):
    """
    建立角色-權限關聯

    注意：
    - SYSTEM_ADMIN 和 ORG_ADMIN 在 PermissionService 中直接 bypass，不需要關聯
    - 但為了完整性和未來擴展，這裡還是建立關聯

    ABAC 條件範例：
    {
        "conditions": [{"code": "OWNER"}],
        "logic": "OR"
    }
    """
    print("建立角色-權限關聯...")

    # 角色-權限對應定義
    # 格式: { 'ROLE_CODE': ['perm:code', ...] } 或 { 'ROLE_CODE': {'perms': [...], 'conditions': {...}} }
    ROLE_PERMISSION_MAP = {
        # =========================================
        # 企業級角色
        # =========================================
        'FORM_FLOW_ADMIN': [
            # 表單範本管理
            'form_template:create',
            'form_template:read',
            'form_template:update',
            'form_template:delete',
            'form_template:publish',
            # 流程定義管理
            'flow_definition:create',
            'flow_definition:read',
            'flow_definition:update',
            'flow_definition:delete',
            'flow_definition:activate',
            # 檢視表單填報與流程實例（唯讀）
            'form_instance:read',
            'flow_instance:read',
        ],

        # =========================================
        # 模組級角色
        # =========================================
        'MODULE_ADMIN': [
            'module:read',
            'module:manage',
            'module_content:create',
            'module_content:read',
            'module_content:update',
            'module_content:delete',
        ],

        'MODULE_AUTHOR': [
            # 繼承 MODULE_READER，這裡只加額外權限
            'module_content:create',
            'module_content:update',
            # 刪除自己的內容（需 ABAC 條件）
            {
                'code': 'module_content:delete',
                'conditions': {
                    'conditions': [{'code': 'OWNER'}],
                    'logic': 'OR'
                }
            },
        ],

        'MODULE_READER': [
            'module:read',
            'module_content:read',
        ],

        # =========================================
        # 成員級角色
        # =========================================
        'DEPT_MANAGER': [
            # 檢視部門、用戶、角色
            'user:read',
            'department:read',
            'role:read',
            # 表單填報（部門內）
            'form_instance:create',
            'form_instance:read',
            {
                'code': 'form_instance:update',
                'conditions': {
                    'conditions': [{'code': 'OWNER'}, {'code': 'SUB_DEPT'}],
                    'logic': 'OR'
                }
            },
            # 流程審核
            'flow_instance:read',
            'flow_instance:approve',
            'flow_instance:reject',
            'flow_instance:transfer',
            'flow_instance:remind',
        ],

        'DEPT_MEMBER': [
            # 填寫表單
            'form_instance:create',
            'form_instance:read',
            {
                'code': 'form_instance:update',
                'conditions': {
                    'conditions': [{'code': 'OWNER'}],
                    'logic': 'OR'
                }
            },
            # 檢視自己的流程
            'flow_instance:read',
        ],

        'GROUP_LEADER': [
            # 類似部門主管
            'user:read',
            'role:read',
            'form_instance:create',
            'form_instance:read',
            {
                'code': 'form_instance:update',
                'conditions': {
                    'conditions': [{'code': 'OWNER'}],
                    'logic': 'OR'
                }
            },
            'flow_instance:read',
            'flow_instance:approve',
            'flow_instance:reject',
        ],

        'GROUP_MEMBER': [
            # 類似部門成員
            'form_instance:create',
            'form_instance:read',
            {
                'code': 'form_instance:update',
                'conditions': {
                    'conditions': [{'code': 'OWNER'}],
                    'logic': 'OR'
                }
            },
            'flow_instance:read',
        ],

        'EMPLOYEE': [
            # 基本企業成員權限
            'form_instance:create',
            'form_instance:read',
            {
                'code': 'form_instance:update',
                'conditions': {
                    'conditions': [{'code': 'OWNER'}],
                    'logic': 'OR'
                }
            },
            'flow_instance:read',
            'module:read',
            'module_content:read',
        ],

        'RESTRICTED_EMPLOYEE': [
            # 受限企業成員 - 只有最基本權限
            'form_instance:read',
            'flow_instance:read',
        ],

        'EXTERNAL_CONSULTANT': [
            # 外部顧問 - 被邀請的群組內權限
            'form_instance:create',
            'form_instance:read',
            {
                'code': 'form_instance:update',
                'conditions': {
                    'conditions': [{'code': 'OWNER'}],
                    'logic': 'OR'
                }
            },
        ],

        'EXTERNAL_VENDOR': [
            # 廠商代表 - 被邀請的群組內權限
            'form_instance:create',
            'form_instance:read',
            {
                'code': 'form_instance:update',
                'conditions': {
                    'conditions': [{'code': 'OWNER'}],
                    'logic': 'OR'
                }
            },
        ],
    }

    count = 0
    for role_code, perm_list in ROLE_PERMISSION_MAP.items():
        role = roles.get(role_code)
        if not role:
            print(f"  警告: 角色 {role_code} 不存在，跳過")
            continue

        for perm_item in perm_list:
            # 解析權限項目
            if isinstance(perm_item, str):
                perm_code = perm_item
                conditions = None
            else:
                perm_code = perm_item['code']
                conditions = perm_item.get('conditions')

            # 取得權限
            perm = permissions.get(perm_code)
            if not perm:
                print(f"  警告: 權限 {perm_code} 不存在，跳過")
                continue

            # 建立關聯
            import json
            role_perm = RolePermission(
                role_secure_code=role.secure_code,
                permission_secure_code=perm.secure_code,
                condition_json=json.dumps(conditions, ensure_ascii=False) if conditions else None,
                is_active=True
            )
            db.session.add(role_perm)
            count += 1

    db.session.commit()
    print(f"  建立 {count} 筆角色-權限關聯")
    return count


def main():
    """主程式"""
    print("=" * 60)
    print("BeakMask Seed Data Script")
    print("=" * 60)
    print()

    app = create_app()

    with app.app_context():
        # 確認執行
        print("警告: 此操作會清除現有資料！")
        confirm = input("確定要繼續嗎？(yes/no): ")
        if confirm.lower() != 'yes':
            print("已取消")
            return

        print()

        # 清除並重建
        clear_existing_data()

        # =============================================
        # 1. 全局資料（不屬於特定企業）
        # =============================================
        permissions = seed_permissions()       # 62 個權限
        conditions = seed_permission_conditions()  # 13 個條件

        # =============================================
        # 2. 系統企業
        # =============================================
        system_org = seed_system_org()
        system_menus = seed_system_menus(system_org)

        # =============================================
        # 3. 企業與用戶
        # =============================================
        org = seed_organization()
        admin = seed_admin_user(org)

        # =============================================
        # 4. HR 結構
        # =============================================
        levels = seed_job_levels(org)
        families = seed_job_families(org)
        seed_job_titles(org, levels, families)

        # =============================================
        # 5. 角色與權限
        # =============================================
        roles = seed_default_roles(org)        # 14 個角色
        role_perm_count = seed_role_permissions(roles, permissions)

        # =============================================
        # 6. 模組與選單
        # =============================================
        module = seed_modules(org)
        menus = seed_menu_items(org, module)
        seed_menu_permissions(menus)

        print()
        print("=" * 60)
        print("Seed 完成！")
        print("=" * 60)
        print()
        print("資料摘要:")
        print(f"  權限: {len(permissions)} 個")
        print(f"  ABAC 條件: {len(conditions)} 個")
        print(f"  系統共用選單: {len(system_menus)} 個")
        print(f"  角色: {len(roles)} 個")
        print(f"  角色-權限關聯: {role_perm_count} 筆")
        print(f"  職等: {len(levels)} 個")
        print(f"  職系: {len(families)} 個")
        print(f"  企業選單: {len(menus)} 個")
        print()
        print("登入資訊:")
        print(f"  URL: http://localhost:7000/auth/login")
        print(f"  帳號: admin@{SYSTEM_ORG_CODE}")
        print(f"  密碼: admin123")


if __name__ == '__main__':
    main()
