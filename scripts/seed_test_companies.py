#!/usr/bin/env python3
"""
BeakMask 測試企業種子資料
建立三家虛擬企業的完整資料：企業、合約、編號規則、職等、職系、職稱、部門、帳號、職位指派

使用方式:
    cd /opt/BeakPlatform
    source venv/bin/activate
    python scripts/seed_test_companies.py          # 顯示說明
    python scripts/seed_test_companies.py --run     # 執行建立
    python scripts/seed_test_companies.py --clean   # 清除本腳本建立的資料
    python scripts/seed_test_companies.py --dry-run # 預覽不寫入

測試資料標準:
    - 網域: 主名 + example 綴尾 + .com.zz (ISO 3166 保留國碼)
    - 中文姓氏: 晧、霄、燁、琥、翎、璃、嵐、灃、珩、澈 (虛構姓)
    - 密碼統一: Test1234! (測試環境)
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from datetime import date, datetime
from decimal import Decimal

from app import create_app, db
from app.models import (
    Organization, CustomerType,
    Contract, ContractStatus,
    User, UserType,
    OrganizationalUnit, UnitType,
    JobLevel, JobFamily, JobFamilyType, JobTitle,
    UserNumberingRule,
)
from app.models.employee_position import EmployeePosition, PositionType
from app.models.user_numbering_rule import (
    UserNumberingCounter, UsedUserNumber,
    NumberingUsageScope, NumberingDefaultFor, NumberingElementType,
)
from app.services.organization_service import OrganizationService

# ============================================================================
# 常數
# ============================================================================

TEST_PASSWORD = 'Test1234!'
CONTRACT_START = date(2026, 1, 1)
CONTRACT_END = date(2027, 1, 1)

# 虛構姓氏 (查無百家姓/戶政記錄，用於截圖避免法律爭議)
FAKE_SURNAMES = ['晧', '霄', '燁', '琥', '翎', '璃', '嵐', '灃', '珩', '澈']

# 標記用：方便清除
SEED_TAG = 'seed_test_companies_v1'


# ============================================================================
# 三家企業定義
# ============================================================================

COMPANIES = [
    # --- 1. 大型旅行業 ---
    {
        'code': 'GHTRAVEL',
        'name': '環宇國際旅行社',
        'domain': 'ghtravelexample.com.zz',
        'display_name': 'Global Horizon Travel',
        'contact_person': '晧志遠',
        'contact_email': 'contact@ghtravelexample.com.zz',
        'contact_phone': '02-2700-0001',
        'description': '大型旅行業 -- 團體旅遊、自由行、企業旅遊',
        'user_limit': 50,
        # 員工編號格式: GH + 4位序號
        'numbering': {
            'employee': {
                'name': '員工編號',
                'elements': {
                    'components': [
                        {'type': 'prefix', 'order': 1, 'values': ['GH']},
                        {'type': 'sequence', 'order': 2, 'start': 1, 'digits': 4, 'reset_period': 'never'},
                    ],
                    'total_length': 6,
                },
            },
            'external': {
                'name': '外部廠商編號',
                'elements': {
                    'components': [
                        {'type': 'prefix', 'order': 1, 'values': ['GHX']},
                        {'type': 'sequence', 'order': 2, 'start': 1, 'digits': 3, 'reset_period': 'never'},
                    ],
                    'total_length': 6,
                },
            },
        },
        # 職系 (除預設外的額外職系)
        'extra_families': [
            ('TOUR', '領隊導遊職', 'Tour Guide Position', JobFamilyType.PROFESSIONAL, 'PROF', '帶團領隊與導遊專業人員'),
            ('MKT', '行銷職', 'Marketing Position', JobFamilyType.PROFESSIONAL, 'PROF', '行銷企劃與品牌推廣'),
        ],
        # 額外職稱 (除預設通用職稱外)
        'extra_titles': [
            ('TOUR_LEADER', '領隊', 'Tour Leader', 'L200', 'TOUR', False),
            ('TOUR_GUIDE', '導遊', 'Tour Guide', 'L200', 'TOUR', False),
            ('TRAVEL_PLANNER', '旅遊規劃師', 'Travel Planner', 'L200', 'PROF', False),
            ('TRAVEL_OP', '旅遊作業人員', 'Travel Operator', 'L100', 'PROF', False),
            ('SR_TOUR_LEADER', '資深領隊', 'Senior Tour Leader', 'L300', 'TOUR', False),
            ('MKT_SPEC', '行銷專員', 'Marketing Specialist', 'L100', 'MKT', False),
            ('SR_MKT_SPEC', '高級行銷專員', 'Senior Marketing Specialist', 'L200', 'MKT', False),
            ('MKT_MGR', '行銷經理', 'Marketing Manager', 'L500', 'MGR', True),
        ],
        # 部門結構 (name, code, parent_code, level)
        'departments': [
            ('總經理室', 'GM', None),
            ('行政管理部', 'ADMIN_DEPT', 'GM'),
            ('財務部', 'FIN', 'GM'),
            ('業務處', 'SALES_DIV', None),
            ('團體旅遊部', 'GROUP_TOUR', 'SALES_DIV'),
            ('自由行部', 'FIT', 'SALES_DIV'),
            ('企業旅遊部', 'CORP_TOUR', 'SALES_DIV'),
            ('產品開發處', 'PROD_DIV', None),
            ('國內旅遊部', 'DOMESTIC', 'PROD_DIV'),
            ('海外旅遊部', 'OVERSEAS', 'PROD_DIV'),
            ('客服部', 'CS_DEPT', None),
            ('行銷企劃部', 'MKT_DEPT', None),
            ('資訊部', 'IT_DEPT', None),
        ],
        # 帳號: (username, native_name, english_name, dept_code, title_code, is_unit_head)
        'employees': [
            ('david.hao', '晧志遠', 'David Hao', 'GM', 'PRES', True),
            ('amy.xiao', '霄雅慧', 'Amy Xiao', 'SALES_DIV', 'DIR', True),
            ('kevin.ye', '燁凱文', 'Kevin Ye', 'GROUP_TOUR', 'MGR', True),
            ('linda.hu', '琥琳達', 'Linda Hu', 'FIT', 'MGR', True),
            ('jason.ling', '翎傑森', 'Jason Ling', 'CORP_TOUR', 'ASST_MGR', True),
            ('sophia.li', '璃心怡', 'Sophia Li', 'PROD_DIV', 'DIR', True),
            ('ryan.lan', '嵐瑞恩', 'Ryan Lan', 'DOMESTIC', 'MGR', True),
            ('emma.feng', '灃艾瑪', 'Emma Feng', 'OVERSEAS', 'MGR', True),
            ('leo.heng', '珩立歐', 'Leo Heng', 'CS_DEPT', 'MGR', True),
            ('mia.che', '澈美雅', 'Mia Che', 'MKT_DEPT', 'MKT_MGR', True),
            ('tom.hao', '晧志明', 'Tom Hao', 'ADMIN_DEPT', 'SUPV', True),
            ('nina.xiao', '霄妮娜', 'Nina Xiao', 'FIN', 'SUPV', True),
            ('peter.ye', '燁彼得', 'Peter Ye', 'IT_DEPT', 'SUPV', True),
            ('alice.hu', '琥愛麗', 'Alice Hu', 'GROUP_TOUR', 'SR_TOUR_LEADER', False),
            ('brian.ling', '翎柏瑞', 'Brian Ling', 'GROUP_TOUR', 'TOUR_LEADER', False),
            ('cathy.li', '璃凱西', 'Cathy Li', 'OVERSEAS', 'TRAVEL_PLANNER', False),
            ('derek.lan', '嵐德瑞', 'Derek Lan', 'DOMESTIC', 'TRAVEL_OP', False),
            ('fiona.feng', '灃菲歐', 'Fiona Feng', 'FIT', 'SR_SPEC', False),
            ('gary.heng', '珩嘉瑞', 'Gary Heng', 'CS_DEPT', 'CSR', False),
            ('helen.che', '澈海倫', 'Helen Che', 'MKT_DEPT', 'MKT_SPEC', False),
        ],
    },

    # --- 2. 資訊公司 ---
    {
        'code': 'BRIGHTCODE',
        'name': '耀達科技股份有限公司',
        'domain': 'brightcodeexample.com.zz',
        'display_name': 'BrightCode Technology',
        'contact_person': '霄伯達',
        'contact_email': 'contact@brightcodeexample.com.zz',
        'contact_phone': '02-2700-0002',
        'description': '資訊公司 -- 軟體研發、系統整合、專案管理',
        'user_limit': 50,
        'numbering': {
            'employee': {
                'name': '員工編號',
                'elements': {
                    'components': [
                        {'type': 'prefix', 'order': 1, 'values': ['BC']},
                        {'type': 'sequence', 'order': 2, 'start': 1, 'digits': 4, 'reset_period': 'never'},
                    ],
                    'total_length': 6,
                },
            },
            'external': {
                'name': '外部廠商編號',
                'elements': {
                    'components': [
                        {'type': 'prefix', 'order': 1, 'values': ['BCX']},
                        {'type': 'sequence', 'order': 2, 'start': 1, 'digits': 3, 'reset_period': 'never'},
                    ],
                    'total_length': 6,
                },
            },
        },
        'extra_families': [
            ('PROD_FAM', '產品職', 'Product Position', JobFamilyType.PROFESSIONAL, 'PROF', '產品策略與用戶體驗'),
            ('DESIGN', '設計職', 'Design Position', JobFamilyType.PROFESSIONAL, 'PROF', 'UI/UX 設計'),
        ],
        'extra_titles': [
            ('FE_ENG', '前端工程師', 'Frontend Engineer', 'L100', 'TECH', False),
            ('BE_ENG', '後端工程師', 'Backend Engineer', 'L100', 'TECH', False),
            ('QA_ENG', 'QA 工程師', 'QA Engineer', 'L100', 'TECH', False),
            ('SR_FE_ENG', '高級前端工程師', 'Senior Frontend Engineer', 'L200', 'TECH', False),
            ('SR_BE_ENG', '高級後端工程師', 'Senior Backend Engineer', 'L200', 'TECH', False),
            ('SR_QA_ENG', '高級 QA 工程師', 'Senior QA Engineer', 'L200', 'TECH', False),
            ('UX_DESIGNER', 'UX 設計師', 'UX Designer', 'L200', 'DESIGN', False),
            ('PROD_MGR', '產品經理', 'Product Manager', 'L500', 'PROD_FAM', False),
            ('SCRUM_MASTER', 'Scrum Master', 'Scrum Master', 'L300', 'PROF', False),
            ('DEVOPS_ENG', 'DevOps 工程師', 'DevOps Engineer', 'L200', 'TECH', False),
            ('ARCHITECT', '系統架構師', 'System Architect', 'L400', 'TECH', False),
            ('TECH_LEAD', '技術主管', 'Tech Lead', 'L300', 'TECH', True),
        ],
        'departments': [
            ('總經理室', 'GM', None),
            ('行政管理部', 'ADMIN_DEPT', 'GM'),
            ('財務部', 'FIN', 'GM'),
            ('研發處', 'RD_DIV', None),
            ('前端開發部', 'FE_DEPT', 'RD_DIV'),
            ('後端開發部', 'BE_DEPT', 'RD_DIV'),
            ('品質保證部', 'QA_DEPT', 'RD_DIV'),
            ('產品部', 'PROD_DEPT', None),
            ('專案管理部', 'PM_DEPT', None),
            ('業務部', 'SALES_DEPT', None),
            ('資訊部', 'IT_DEPT', None),
        ],
        'employees': [
            ('howard.xiao', '霄伯達', 'Howard Xiao', 'GM', 'PRES', True),
            ('irene.ye', '燁艾琳', 'Irene Ye', 'RD_DIV', 'DIR', True),
            ('jack.hu', '琥杰克', 'Jack Hu', 'FE_DEPT', 'TECH_LEAD', True),
            ('karen.ling', '翎凱倫', 'Karen Ling', 'BE_DEPT', 'TECH_LEAD', True),
            ('leon.li', '璃立昂', 'Leon Li', 'QA_DEPT', 'MGR', True),
            ('monica.lan', '嵐夢妮', 'Monica Lan', 'PROD_DEPT', 'PROD_MGR', True),
            ('neil.feng', '灃尼爾', 'Neil Feng', 'PM_DEPT', 'MGR', True),
            ('olive.heng', '珩歐莉', 'Olive Heng', 'SALES_DEPT', 'MGR', True),
            ('paul.che', '澈保羅', 'Paul Che', 'ADMIN_DEPT', 'SUPV', True),
            ('quinn.hao', '晧昆恩', 'Quinn Hao', 'FIN', 'SUPV', True),
            ('sam.xiao', '霄山姆', 'Sam Xiao', 'FE_DEPT', 'SR_FE_ENG', False),
            ('tina.ye', '燁蒂娜', 'Tina Ye', 'FE_DEPT', 'FE_ENG', False),
            ('victor.hu', '琥維克', 'Victor Hu', 'BE_DEPT', 'SR_BE_ENG', False),
            ('wendy.ling', '翎溫蒂', 'Wendy Ling', 'BE_DEPT', 'BE_ENG', False),
            ('xavier.li', '璃乍維', 'Xavier Li', 'QA_DEPT', 'SR_QA_ENG', False),
            ('yuki.lan', '嵐悠希', 'Yuki Lan', 'QA_DEPT', 'QA_ENG', False),
            ('zack.feng', '灃乍克', 'Zack Feng', 'PROD_DEPT', 'UX_DESIGNER', False),
            ('anna.heng', '珩安娜', 'Anna Heng', 'PM_DEPT', 'SCRUM_MASTER', False),
            ('bruce.che', '澈布魯', 'Bruce Che', 'IT_DEPT', 'DEVOPS_ENG', False),
            ('diana.hao', '晧黛安', 'Diana Hao', 'RD_DIV', 'ARCHITECT', False),
        ],
    },

    # --- 3. 資安公司 ---
    {
        'code': 'SHIELDEDGE',
        'name': '盾策資安科技股份有限公司',
        'domain': 'shieldedgeexample.com.zz',
        'display_name': 'ShieldEdge Security',
        'contact_person': '燁守誠',
        'contact_email': 'contact@shieldedgeexample.com.zz',
        'contact_phone': '02-2700-0003',
        'description': '資安公司 -- SOC 監控、滲透測試、資安顧問、威脅情報',
        'user_limit': 50,
        'numbering': {
            'employee': {
                'name': '員工編號',
                'elements': {
                    'components': [
                        {'type': 'prefix', 'order': 1, 'values': ['SE']},
                        {'type': 'sequence', 'order': 2, 'start': 1, 'digits': 4, 'reset_period': 'never'},
                    ],
                    'total_length': 6,
                },
            },
            'external': {
                'name': '外部廠商編號',
                'elements': {
                    'components': [
                        {'type': 'prefix', 'order': 1, 'values': ['SEX']},
                        {'type': 'sequence', 'order': 2, 'start': 1, 'digits': 3, 'reset_period': 'never'},
                    ],
                    'total_length': 6,
                },
            },
        },
        'extra_families': [
            ('SECTECH', '資安技術職', 'Security Technical Position', JobFamilyType.PROFESSIONAL, 'PROF', '資安技術研究與攻防測試'),
            ('CONSULT', '顧問職', 'Consulting Position', JobFamilyType.PROFESSIONAL, 'PROF', '資安顧問與稽核服務'),
        ],
        'extra_titles': [
            ('SOC_ANALYST', 'SOC 分析師', 'SOC Analyst', 'L100', 'SECTECH', False),
            ('SR_SOC_ANALYST', '高級 SOC 分析師', 'Senior SOC Analyst', 'L200', 'SECTECH', False),
            ('PENTEST_ENG', '滲透測試工程師', 'Penetration Tester', 'L200', 'SECTECH', False),
            ('SR_PENTEST_ENG', '高級滲透測試工程師', 'Senior Penetration Tester', 'L300', 'SECTECH', False),
            ('THREAT_HUNTER', '威脅獵人', 'Threat Hunter', 'L300', 'SECTECH', False),
            ('MALWARE_ANALYST', '惡意程式分析師', 'Malware Analyst', 'L200', 'SECTECH', False),
            ('DFIR_INVEST', 'DFIR 調查員', 'DFIR Investigator', 'L200', 'SECTECH', False),
            ('SEC_CONSULT', '資安顧問', 'Security Consultant', 'L300', 'CONSULT', False),
            ('SR_SEC_CONSULT', '高級資安顧問', 'Senior Security Consultant', 'L400', 'CONSULT', False),
            ('SEC_AUDITOR', '資安稽核員', 'Security Auditor', 'L200', 'CONSULT', False),
            ('TOOL_DEV', '工具開發工程師', 'Tool Developer', 'L200', 'TECH', False),
            ('CTI_ANALYST', '威脅情報分析師', 'CTI Analyst', 'L200', 'SECTECH', False),
        ],
        'departments': [
            ('總經理室', 'GM', None),
            ('行政管理部', 'ADMIN_DEPT', 'GM'),
            ('財務部', 'FIN', 'GM'),
            ('SOC 監控中心', 'SOC', None),
            ('滲透測試部', 'PENTEST', None),
            ('資安顧問部', 'SEC_CONSULT', None),
            ('研發處', 'RD_DIV', None),
            ('威脅情報部', 'CTI', 'RD_DIV'),
            ('工具開發部', 'TOOL_DEV', 'RD_DIV'),
            ('業務部', 'SALES_DEPT', None),
        ],
        'employees': [
            ('ethan.ye', '燁守誠', 'Ethan Ye', 'GM', 'PRES', True),
            ('frank.hu', '琥復安', 'Frank Hu', 'SOC', 'DIR', True),
            ('grace.ling', '翎格瑞', 'Grace Ling', 'PENTEST', 'MGR', True),
            ('henry.li', '璃亨利', 'Henry Li', 'SEC_CONSULT', 'MGR', True),
            ('iris.lan', '嵐愛瑞', 'Iris Lan', 'RD_DIV', 'DIR', True),
            ('james.feng', '灃詹姆', 'James Feng', 'CTI', 'SUPV', True),
            ('kate.heng', '珩凱特', 'Kate Heng', 'TOOL_DEV', 'SUPV', True),
            ('luke.che', '澈路克', 'Luke Che', 'SALES_DEPT', 'MGR', True),
            ('mary.hao', '晧瑪麗', 'Mary Hao', 'ADMIN_DEPT', 'SUPV', True),
            ('noah.xiao', '霄諾亞', 'Noah Xiao', 'FIN', 'SUPV', True),
            ('oscar.ye', '燁奧斯', 'Oscar Ye', 'SOC', 'SR_SOC_ANALYST', False),
            ('penny.hu', '琥佩妮', 'Penny Hu', 'SOC', 'SOC_ANALYST', False),
            ('ray.ling', '翎雷恩', 'Ray Ling', 'PENTEST', 'SR_PENTEST_ENG', False),
            ('sara.li', '璃莎菈', 'Sara Li', 'PENTEST', 'PENTEST_ENG', False),
            ('tony.lan', '嵐東尼', 'Tony Lan', 'SEC_CONSULT', 'SR_SEC_CONSULT', False),
            ('uma.feng', '灃尤瑪', 'Uma Feng', 'SEC_CONSULT', 'SEC_AUDITOR', False),
            ('vince.heng', '珩文森', 'Vince Heng', 'CTI', 'THREAT_HUNTER', False),
            ('wendy.che', '澈雯蒂', 'Wendy Che', 'CTI', 'CTI_ANALYST', False),
            ('yolanda.hao', '晧尤蘭', 'Yolanda Hao', 'TOOL_DEV', 'TOOL_DEV', False),
            ('zane.xiao', '霄乍恩', 'Zane Xiao', 'TOOL_DEV', 'MALWARE_ANALYST', False),
        ],
    },
]

# ============================================================================
# 標準職等/職系/職稱 (每家企業都建)
# ============================================================================

STANDARD_JOB_LEVELS = [
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

STANDARD_JOB_FAMILIES = [
    ('MGR', '管理職', 'People Manager', JobFamilyType.MANAGER, None, '帶人主管，負責團隊管理與人員發展'),
    ('PROF', '專業職', 'Individual Contributor', JobFamilyType.PROFESSIONAL, None, '不帶人的專業人員'),
    ('SALES', '業務職', 'Sales Position', JobFamilyType.PROFESSIONAL, 'PROF', '業務開發與客戶關係維護'),
    ('CS', '客服職', 'Customer Service Position', JobFamilyType.PROFESSIONAL, 'PROF', '客戶服務與問題處理'),
    ('ADMIN', '行政職', 'Administration Position', JobFamilyType.PROFESSIONAL, 'PROF', '行政支援與內部管理'),
    ('TECH', '工程技術職', 'Technical Position', JobFamilyType.PROFESSIONAL, 'PROF', '技術研發與工程實作'),
]

STANDARD_JOB_TITLES = [
    ('PRES', '總經理', 'President', 'L900', 'MGR', True),
    ('VP', '副總經理', 'Vice President', 'L800', 'MGR', True),
    ('DIR', '處長', 'Director', 'L700', 'MGR', True),
    ('DEP_DIR', '副處長', 'Deputy Director', 'L600', 'MGR', True),
    ('MGR', '經理', 'Manager', 'L500', 'MGR', True),
    ('ASST_MGR', '副理', 'Assistant Manager', 'L400', 'MGR', True),
    ('SUPV', '主任', 'Supervisor', 'L300', 'MGR', True),
    ('SR_SPEC', '高級專員', 'Senior Specialist', 'L200', 'PROF', False),
    ('SR_ENG', '高級工程師', 'Senior Engineer', 'L200', 'TECH', False),
    ('SR_SALES', '高級業務代表', 'Senior Sales Rep', 'L200', 'SALES', False),
    ('SPEC', '專員', 'Specialist', 'L100', 'PROF', False),
    ('ENG', '工程師', 'Engineer', 'L100', 'TECH', False),
    ('SALES_REP', '業務代表', 'Sales Representative', 'L100', 'SALES', False),
    ('CSR', '客服代表', 'Customer Service Rep', 'L100', 'CS', False),
    ('ADMIN_SPEC', '行政專員', 'Admin Specialist', 'L100', 'ADMIN', False),
]


# ============================================================================
# 建立函式
# ============================================================================

def create_job_levels(org_sc):
    """建立標準職等"""
    levels = {}
    for i, (code, name, name_en, order, limit, is_mgr, scope) in enumerate(STANDARD_JOB_LEVELS):
        level = JobLevel(
            org_secure_code=org_sc,
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
            is_active=True,
        )
        db.session.add(level)
        db.session.flush()
        levels[code] = level
    return levels


def create_job_families(org_sc, extra_families=None):
    """建立職系 (標準 + 額外)"""
    families = {}
    all_families = STANDARD_JOB_FAMILIES + (extra_families or [])
    for i, (code, name, name_en, ftype, parent_code, desc) in enumerate(all_families):
        family = JobFamily(
            org_secure_code=org_sc,
            code=code,
            name=name,
            name_en=name_en,
            family_type=ftype,
            parent_secure_code=families[parent_code].secure_code if parent_code else None,
            description=desc,
            sort_order=(i + 1) * 10,
            is_system_default=(i < len(STANDARD_JOB_FAMILIES)),
            is_active=True,
        )
        db.session.add(family)
        db.session.flush()
        families[code] = family
    return families


def create_job_titles(org_sc, levels, families, extra_titles=None):
    """建立職稱 (標準 + 額外)"""
    titles = {}
    all_titles = STANDARD_JOB_TITLES + (extra_titles or [])
    for i, (code, name, name_en, level_code, family_code, is_supv) in enumerate(all_titles):
        if level_code not in levels:
            print(f"  [WARN] 職等 {level_code} 不存在，跳過職稱 {code}")
            continue
        if family_code not in families:
            print(f"  [WARN] 職系 {family_code} 不存在，跳過職稱 {code}")
            continue
        title = JobTitle(
            org_secure_code=org_sc,
            code=code,
            name=name,
            name_en=name_en,
            job_level_secure_code=levels[level_code].secure_code,
            job_family_secure_code=families[family_code].secure_code,
            is_supervisor=is_supv,
            sort_order=(i + 1),
            is_system_default=(i < len(STANDARD_JOB_TITLES)),
            is_active=True,
        )
        db.session.add(title)
        db.session.flush()
        titles[code] = title
    return titles


def create_numbering_rules(org_sc, numbering_config):
    """建立編號規則 (公司特定，非預設)"""
    rules = {}
    for key, cfg in numbering_config.items():
        # 公司特定規則不設為預設 (預設規則由 create_default_numbering_rule 建立)
        default_for = NumberingDefaultFor.EXTERNAL if key == 'external' else None
        usage_scope = NumberingUsageScope.INTERNAL_ONLY if key == 'employee' else NumberingUsageScope.EXTERNAL_ONLY
        rule = UserNumberingRule(
            org_secure_code=org_sc,
            name=cfg['name'],
            description=f"測試企業 {key} 編號規則",
            elements=cfg['elements'],
            usage_scope=usage_scope,
            default_for=default_for,
            is_active=True,
        )
        db.session.add(rule)
        db.session.flush()
        rules[key] = rule
    return rules


def create_default_numbering_rule(org_sc):
    """建立預設 4 位數員工編號規則 (0001, 0002, ...)

    此規則模擬新企業建立時自動產生的預設編號規則。
    後續會移植到 OrganizationService.create_organization() 內。
    """
    rule = UserNumberingRule(
        org_secure_code=org_sc,
        name='預設員工編號',
        description='4 位數序號 (新企業預設)',
        elements={
            'components': [
                {'type': 'sequence', 'order': 1, 'start': 1, 'digits': 4, 'reset_period': 'never'},
            ],
            'total_length': 4,
        },
        usage_scope=NumberingUsageScope.INTERNAL_ONLY,
        default_for=NumberingDefaultFor.EMPLOYEE,
        is_active=True,
    )
    db.session.add(rule)
    db.session.flush()
    return rule


def create_departments(org_sc, dept_list):
    """建立部門"""
    depts = {}
    for name, code, parent_code in dept_list:
        dept = OrganizationalUnit(
            org_secure_code=org_sc,
            unit_type=UnitType.DEPARTMENT,
            code=code,
            name=name,
            is_active=True,
            sort_order=len(depts) * 10,
            parent_secure_code=depts[parent_code].secure_code if parent_code else None,
        )
        dept.update_full_path()
        db.session.add(dept)
        db.session.flush()
        depts[code] = dept
    return depts


def generate_employee_id(rule, seq_num):
    """根據編號規則產生員工編號"""
    parts = []
    for comp in sorted(rule.elements.get('components', []), key=lambda x: x.get('order', 0)):
        ctype = comp.get('type')
        if ctype == 'prefix':
            parts.append(comp['values'][0])
        elif ctype == 'sequence':
            digits = comp.get('digits', 4)
            parts.append(str(seq_num).zfill(digits))
    return ''.join(parts)


def create_employees(org, org_sc, domain, emp_list, depts, titles, numbering_rules):
    """建立員工帳號 + 職位指派 + 員工編號"""
    employee_rule = numbering_rules.get('employee')
    users = {}

    for i, (username, native_name, english_name, dept_code, title_code, is_head) in enumerate(emp_list):
        seq = i + 1
        emp_id = generate_employee_id(employee_rule, seq) if employee_rule else f'{seq:04d}'

        email = f'{username}@{domain}'
        user = User(
            org_secure_code=org_sc,
            username=username,
            email=email,
            display_name=native_name,
            native_name=native_name,
            english_name=english_name,
            user_type=UserType.EMPLOYEE,
            is_active=True,
            employee_id=emp_id,
            must_change_password=False,
        )
        user.set_password(TEST_PASSWORD)
        db.session.add(user)
        db.session.flush()
        users[username] = user

        # 記錄已使用的編號
        UsedUserNumber.record_number(
            org_secure_code=org_sc,
            number=emp_id,
            user_secure_code=user.secure_code,
            rule_secure_code=employee_rule.secure_code if employee_rule else None,
        )

        # 建立職位指派
        if dept_code in depts and title_code in titles:
            position = EmployeePosition(
                org_secure_code=org_sc,
                user_secure_code=user.secure_code,
                job_title_secure_code=titles[title_code].secure_code,
                unit_secure_code=depts[dept_code].secure_code,
                position_type=PositionType.PRIMARY,
                is_unit_head=is_head,
                effective_from=date(2026, 1, 1),
                is_active=True,
            )
            db.session.add(position)

            # 設定 primary_unit
            user.primary_unit_secure_code = depts[dept_code].secure_code

    # 更新計數器
    if employee_rule:
        counter = UserNumberingCounter(
            org_secure_code=org_sc,
            rule_secure_code=employee_rule.secure_code,
            period_key='forever',
            current_seq=len(emp_list),
        )
        db.session.add(counter)

    return users


def create_admin_accounts(org, org_sc, domain):
    """建立 2 個企業管理員 (admin 已由 OrganizationService 建立，再建 admin2)"""
    admin2_email = f'admin2@{domain}'
    admin2 = User(
        org_secure_code=org_sc,
        username='admin2',
        email=admin2_email,
        display_name=f'{org.name} 管理員2',
        user_type=UserType.ORG_ADMIN,
        is_active=True,
        must_change_password=False,
    )
    admin2.set_password(TEST_PASSWORD)
    db.session.add(admin2)
    db.session.flush()
    return admin2


# ============================================================================
# 主流程
# ============================================================================

def seed_one_company(company_def):
    """建立一家企業的完整資料"""
    code = company_def['code']
    name = company_def['name']
    domain = company_def['domain']

    print(f"\n{'='*60}")
    print(f"  建立企業: {name} ({code})")
    print(f"{'='*60}")

    # 1. 企業 + 合約 + 原始管理員
    print(f"  [1/9] 企業 + 合約 + 原始管理員...")
    org, admin_user, contract = OrganizationService.create_organization_with_contract(
        code=code,
        name=name,
        domain_name=domain,
        display_name=company_def.get('display_name'),
        contract_start_date=CONTRACT_START,
        contract_end_date=CONTRACT_END,
        customer_type=CustomerType.FORMAL,
        user_limit=company_def.get('user_limit', 50),
        admin_password=TEST_PASSWORD,
        created_by='nH5liUKQikH1NM2osVVXuF',  # 系統管理員 secure_code
        description=company_def.get('description'),
        contact_person=company_def.get('contact_person'),
        contact_email=company_def.get('contact_email'),
        contact_phone=company_def.get('contact_phone'),
    )
    db.session.flush()
    org_sc = org.secure_code
    print(f"         org_sc: {org_sc}")
    print(f"         admin: admin@{domain}")

    # 2. 第二管理員
    print(f"  [2/9] 第二管理員...")
    admin2 = create_admin_accounts(org, org_sc, domain)
    print(f"         admin2: admin2@{domain}")

    # 3. 編號規則
    print(f"  [3/9] 預設編號規則...")
    default_rule = create_default_numbering_rule(org_sc)
    print(f"         default: {default_rule.name} (0001, 0002, ...)")

    print(f"  [4/9] 公司編號規則...")
    numbering_rules = create_numbering_rules(org_sc, company_def['numbering'])
    for key, rule in numbering_rules.items():
        print(f"         {key}: {rule.name}")

    # 5. 職等
    print(f"  [5/9] 職等 (10 級)...")
    levels = create_job_levels(org_sc)

    # 6. 職系
    extra_fam = company_def.get('extra_families', [])
    print(f"  [6/9] 職系 ({len(STANDARD_JOB_FAMILIES) + len(extra_fam)} 個)...")
    families = create_job_families(org_sc, extra_fam)

    # 7. 職稱
    extra_titles = company_def.get('extra_titles', [])
    print(f"  [7/9] 職稱 ({len(STANDARD_JOB_TITLES) + len(extra_titles)} 個)...")
    titles = create_job_titles(org_sc, levels, families, extra_titles)

    # 8. 部門
    dept_list = company_def['departments']
    print(f"  [8/9] 部門 ({len(dept_list)} 個)...")
    depts = create_departments(org_sc, dept_list)

    # 9. 員工帳號 + 職位
    emp_list = company_def['employees']
    print(f"  [9/9] 員工帳號 ({len(emp_list)} 人) + 職位指派...")
    users = create_employees(org, org_sc, domain, emp_list, depts, titles, numbering_rules)

    db.session.commit()

    print(f"\n  完成! 企業 {name}:")
    print(f"    管理員: admin@{domain}, admin2@{domain}")
    print(f"    員工: {len(users)} 人")
    print(f"    密碼: {TEST_PASSWORD}")

    return org


def clean_test_companies():
    """清除本腳本建立的三家測試企業資料"""
    from sqlalchemy import text

    domains = [c['domain'] for c in COMPANIES]

    print("清除測試企業資料...")
    for domain in domains:
        org = Organization.query.filter(
            Organization.domain_name == domain,
            Organization.is_deleted == False,
        ).first()
        if not org:
            print(f"  {domain}: 不存在，跳過")
            continue

        org_sc = org.secure_code
        print(f"  清除 {org.name} ({domain})...")

        # 完整按 FK 依賴順序刪除 (葉表先刪)
        # Phase 1: 葉表 (有 org_secure_code，無其他表依賴它們)
        phase1_tables = [
            'employee_positions',
            'user_role_assignments',
            'user_unit_assignments',
            'user_unit_memberships',
            'used_user_numbers',
            'user_numbering_counters',
            'job_level_approval_limits',
            'audit_logs',
            'delegations',
            'personal_schedules',
            'schedule_adjustments',
            'timeout_trackers',
            'approval_categories',
            'duties',
            'duty_categories',
            'lookup_items',
            'lookup_categories',
            'workflow_node_definitions',
            'workflow_node_categories',
            'work_schedules',
            'shift_types',
            'conglomerate_logs',
            'module_access_control',
            'modules',
            'pages',
            'recipient_groups',
            'smtp_configs',
            'telegram_configs',
        ]
        for table in phase1_tables:
            db.session.execute(
                text(f"DELETE FROM {table} WHERE org_secure_code = :osc"),
                {'osc': org_sc}
            )

        # menu_permissions 透過 menu_items 子查詢 (無 org_secure_code)
        db.session.execute(
            text("DELETE FROM menu_permissions WHERE menu_secure_code IN "
                 "(SELECT secure_code FROM menu_items WHERE org_secure_code = :osc)"),
            {'osc': org_sc}
        )

        # password_history 透過 user_secure_code (無 org_secure_code)
        db.session.execute(
            text("DELETE FROM password_history WHERE user_secure_code IN "
                 "(SELECT secure_code FROM users WHERE org_secure_code = :osc)"),
            {'osc': org_sc}
        )

        # Phase 2: 中層表
        phase2_tables = [
            'menu_items',
            'user_numbering_rules',
            'job_titles',
            'job_families',
            'job_levels',
            'roles',
        ]
        for table in phase2_tables:
            db.session.execute(
                text(f"DELETE FROM {table} WHERE org_secure_code = :osc"),
                {'osc': org_sc}
            )

        # Phase 3: users (先清自參照和部門 FK)
        db.session.execute(
            text("UPDATE users SET bound_employee_secure_code = NULL, "
                 "primary_unit_secure_code = NULL WHERE org_secure_code = :osc"),
            {'osc': org_sc}
        )
        db.session.execute(
            text("DELETE FROM organizational_units WHERE org_secure_code = :osc"),
            {'osc': org_sc}
        )

        # contracts 有 FK 到 users (created_by, modified_by)，先清
        db.session.execute(
            text("UPDATE contracts SET created_by_secure_code = NULL, "
                 "modified_by_secure_code = NULL WHERE org_secure_code = :osc"),
            {'osc': org_sc}
        )
        db.session.execute(
            text("DELETE FROM users WHERE org_secure_code = :osc"),
            {'osc': org_sc}
        )

        # Phase 4: 企業核心
        db.session.execute(
            text("DELETE FROM contracts WHERE org_secure_code = :osc"),
            {'osc': org_sc}
        )
        db.session.execute(
            text("DELETE FROM organizations WHERE secure_code = :osc"),
            {'osc': org_sc}
        )

    db.session.commit()
    print("清除完成")


def dry_run():
    """預覽模式"""
    for company in COMPANIES:
        print(f"\n{'='*60}")
        print(f"企業: {company['name']} ({company['code']})")
        print(f"網域: {company['domain']}")
        print(f"{'='*60}")
        print(f"  管理員: admin@{company['domain']}, admin2@{company['domain']}")
        print(f"  編號規則: {len(company['numbering'])} 組")
        print(f"  職系: {len(STANDARD_JOB_FAMILIES) + len(company.get('extra_families', []))} 個")
        print(f"  職稱: {len(STANDARD_JOB_TITLES) + len(company.get('extra_titles', []))} 個")
        print(f"  部門: {len(company['departments'])} 個")
        print(f"  員工: {len(company['employees'])} 人")
        print(f"  部門結構:")
        dept_map = {}
        for name, code, parent in company['departments']:
            dept_map[code] = (name, parent)
        for name, code, parent in company['departments']:
            indent = '    '
            if parent:
                indent = '      '
            print(f"{indent}{name} ({code})")
        print(f"  員工列表:")
        for username, native, english, dept, title, head in company['employees']:
            head_mark = ' [主管]' if head else ''
            print(f"    {native} ({english}) - {dept}/{title}{head_mark}")


def main():
    parser = argparse.ArgumentParser(
        description='BeakMask 測試企業種子資料',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python scripts/seed_test_companies.py --dry-run   預覽資料結構
  python scripts/seed_test_companies.py --run        執行建立
  python scripts/seed_test_companies.py --clean      清除測試企業

建立的企業:
  1. 環宇國際旅行社 (GHTRAVEL) - ghtravelexample.com.zz
  2. 耀達科技 (BRIGHTCODE) - brightcodeexample.com.zz
  3. 盾策資安 (SHIELDEDGE) - shieldedgeexample.com.zz

每家企業包含:
  - 2 個管理員 (admin / admin2)
  - 20 個員工帳號 (含職位指派)
  - 編號規則、職等、職系、職稱、部門
  - 密碼統一: Test1234!
        """,
    )
    parser.add_argument('--run', action='store_true', help='執行建立測試資料')
    parser.add_argument('--clean', action='store_true', help='清除本腳本建立的測試企業')
    parser.add_argument('--dry-run', action='store_true', help='預覽資料結構，不寫入')

    args = parser.parse_args()

    if not any([args.run, args.clean, args.dry_run]):
        parser.print_help()
        return

    if args.dry_run:
        dry_run()
        return

    app = create_app()
    with app.app_context():
        if args.clean:
            clean_test_companies()
            return

        if args.run:
            # 檢查是否已存在
            for company in COMPANIES:
                existing = Organization.query.filter(
                    Organization.domain_name == company['domain'],
                    Organization.is_deleted == False,
                ).first()
                if existing:
                    print(f"企業 {company['name']} ({company['domain']}) 已存在!")
                    print(f"請先執行 --clean 清除後再重新建立")
                    return

            print("=" * 60)
            print("  BeakMask 測試企業種子資料")
            print("=" * 60)

            for company in COMPANIES:
                seed_one_company(company)

            print("\n" + "=" * 60)
            print("  全部完成!")
            print("=" * 60)
            print(f"\n共建立 {len(COMPANIES)} 家企業，每家 2 管理員 + 20 員工")
            print(f"統一密碼: {TEST_PASSWORD}")
            print(f"\n登入方式:")
            for company in COMPANIES:
                print(f"  admin@{company['domain']}")
                print(f"  admin2@{company['domain']}")


if __name__ == '__main__':
    main()
