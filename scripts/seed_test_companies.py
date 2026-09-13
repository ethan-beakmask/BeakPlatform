#!/usr/bin/env python3
"""
BeakMask 測試企業種子資料
建立四家虛擬企業的完整資料：企業、合約、編號規則、職等、職系、職稱、部門、帳號、職位指派
並補齊簽核展示需要的部門成員關係與部門主管角色（直屬主管由此推導）、核決類別與職等上限、兼任/代理職位樣本。

使用方式:
    cd <BeakPlatform 專案目錄>
    source venv/bin/activate
    python scripts/seed_test_companies.py          # 顯示說明
    python scripts/seed_test_companies.py --run     # 執行建立
    python scripts/seed_test_companies.py --clean   # 清除本腳本建立的資料
    python scripts/seed_test_companies.py --dry-run # 預覽不寫入

測試資料標準:
    - 網域: 主名 + example 綴尾 + .com.zz (ISO 3166 保留國碼)
    - 中文姓氏: 晧、霄、燁、琥、翎、璃、嵐、灃、珩、澈 (虛構姓)
    - 密碼統一: SEED_ADMIN_PASSWORD (測試環境)
"""
import sys
import json
import os
import argparse
import re
import signal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
signal.signal(signal.SIGPIPE, signal.SIG_DFL)

from datetime import date, datetime, timedelta
from decimal import Decimal

from app import create_app, db
from app.models import (
    Organization, CustomerType,
    Contract, ContractStatus,
    User, UserType,
    OrganizationalUnit, UnitType,
    JobLevel, JobFamily, JobFamilyType, JobTitle,
    UserNumberingRule,
    Role, UserRoleAssignment,
)
from app.models.approval_category import (
    ApprovalCategory,
    JobLevelApprovalLimit,
    DEFAULT_APPROVAL_CATEGORIES,
)
from app.models.employee_position import EmployeePosition, PositionType
from app.models.user_unit_membership import UserUnitMembership, MembershipType, MembershipRole
from app.models.user_numbering_rule import (
    UserNumberingCounter, UsedUserNumber,
    NumberingUsageScope, NumberingDefaultFor, NumberingElementType,
)

# ============================================================================
# 常數
# ============================================================================

SEED_ADMIN_PASSWORD = 'SeedAdmin2026!#'
TEST_PASSWORD = SEED_ADMIN_PASSWORD
CONTRACT_START = date(2026, 1, 1)
CONTRACT_END = date(2027, 1, 1)

# 虛構姓氏 (查無百家姓/戶政記錄，用於截圖避免法律爭議)
FAKE_SURNAMES = ['晧', '霄', '燁', '琥', '翎', '璃', '嵐', '灃', '珩', '澈']

# 標記用：方便清除
SEED_TAG = 'seed_test_companies_v1'
# 範例企業合約啟用的模組（表單流程是所有示範的前提）
SEED_CONTRACT_MODULES = ['form_workflow']

SQL_IDENTIFIER_RE = re.compile(r'^[a-z_][a-z0-9_]*$')


# ============================================================================
# 四家企業定義
# ============================================================================

COMPANIES = [
    # --- 1. 傳統製造業 ---
    {
        'code': 'GHTRAVEL',
        'name': '傳統文化製造集團',
        'domain': 'ghtravelexample.com.zz',
        'display_name': 'Traditional Culture Manufacturing',
        'contact_person': '晧志遠',
        'contact_email': 'contact@ghtravelexample.com.zz',
        'contact_phone': '02-2700-0001',
        'description': '傳統製造業 -- 文化商品製造、品牌經營、通路管理',
        'user_limit': 50,
        # 企業成員編號格式: GH + 4位序號
        'numbering': {
            'employee': {
                'name': '企業成員編號',
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
            ('TRAVEL_PLANNER', '旅遊規劃師', 'Travel Planner', 'L200', 'GEN', False),
            ('TRAVEL_OP', '旅遊作業人員', 'Travel Operator', 'L100', 'GEN', False),
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
            ('業務處', 'SALES_DIV', 'GM'),
            ('團體旅遊部', 'GROUP_TOUR', 'SALES_DIV'),
            ('自由行部', 'FIT', 'SALES_DIV'),
            ('企業旅遊部', 'CORP_TOUR', 'SALES_DIV'),
            ('產品開發處', 'PROD_DIV', 'GM'),
            ('國內旅遊部', 'DOMESTIC', 'PROD_DIV'),
            ('海外旅遊部', 'OVERSEAS', 'PROD_DIV'),
            ('客服部', 'CS_DEPT', 'GM'),
            ('行銷企劃部', 'MKT_DEPT', 'GM'),
            ('資訊部', 'IT_DEPT', 'GM'),
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
        'admin_member': ('admin.ops', '晧安琪', 'Angel Hao', 'ADMIN_DEPT', 'ADMIN_SPEC', False),
        # 群組 (供外部廠商歸屬)
        'groups': [
            ('EXT_PARTNER', '外部合作夥伴'),
        ],
        # 外部廠商: (email, display_name, group_code)
        'external_users': [
            ('vendor01@partnerexample.com.zz', '合作旅行社A', 'EXT_PARTNER'),
        ],
    },

    # --- 2. 資訊公司 ---
    {
        'code': 'BRIGHTCODE',
        'name': '外星萊德科技公司',
        'domain': 'brightcodeexample.com.zz',
        'display_name': 'Alien Rider Technology',
        'contact_person': '霄伯達',
        'contact_email': 'contact@brightcodeexample.com.zz',
        'contact_phone': '02-2700-0002',
        'description': '資訊公司 -- 軟體研發、系統整合、專案管理',
        'user_limit': 50,
        'numbering': {
            'employee': {
                'name': '企業成員編號',
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
            ('SCRUM_MASTER', 'Scrum Master', 'Scrum Master', 'L300', 'GEN', False),
            ('DEVOPS_ENG', 'DevOps 工程師', 'DevOps Engineer', 'L200', 'TECH', False),
            ('ARCHITECT', '系統架構師', 'System Architect', 'L400', 'TECH', False),
            ('TECH_LEAD', '技術主管', 'Tech Lead', 'L300', 'TECH', True),
        ],
        'departments': [
            ('總經理室', 'GM', None),
            ('行政管理部', 'ADMIN_DEPT', 'GM'),
            ('財務部', 'FIN', 'GM'),
            ('研發處', 'RD_DIV', 'GM'),
            ('前端開發部', 'FE_DEPT', 'RD_DIV'),
            ('後端開發部', 'BE_DEPT', 'RD_DIV'),
            ('品質保證部', 'QA_DEPT', 'RD_DIV'),
            ('產品部', 'PROD_DEPT', 'GM'),
            ('專案管理部', 'PM_DEPT', 'GM'),
            ('業務部', 'SALES_DEPT', 'GM'),
            ('資訊部', 'IT_DEPT', 'GM'),
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
            ('bruce.che', '澈布魯', 'Bruce Che', 'IT_DEPT', 'DEVOPS_ENG', True),
            ('diana.hao', '晧黛安', 'Diana Hao', 'RD_DIV', 'ARCHITECT', False),
        ],
        'admin_member': ('admin.ops', '霄安琪', 'Angel Xiao', 'ADMIN_DEPT', 'ADMIN_SPEC', False),
        'groups': [
            ('EXT_PARTNER', '外部合作夥伴'),
        ],
        'external_users': [
            ('vendor01@clientexample.com.zz', '外包開發商A', 'EXT_PARTNER'),
        ],
    },

    # --- 3. 資安公司 ---
    {
        'code': 'SHIELDEDGE',
        'name': '綠色乖乖資安網',
        'domain': 'shieldedgeexample.com.zz',
        'display_name': 'Green Kuai Kuai CyberSec',
        'contact_person': '燁守誠',
        'contact_email': 'contact@shieldedgeexample.com.zz',
        'contact_phone': '02-2700-0003',
        'description': '資安公司 -- SOC 監控、滲透測試、資安顧問、威脅情報',
        'user_limit': 50,
        'numbering': {
            'employee': {
                'name': '企業成員編號',
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
            ('SOC 監控中心', 'SOC', 'GM'),
            ('滲透測試部', 'PENTEST', 'GM'),
            ('資安顧問部', 'SEC_CONSULT', 'GM'),
            ('研發處', 'RD_DIV', 'GM'),
            ('威脅情報部', 'CTI', 'RD_DIV'),
            ('工具開發部', 'TOOL_DEV', 'RD_DIV'),
            ('業務部', 'SALES_DEPT', 'GM'),
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
        'admin_member': ('admin.ops', '燁安琪', 'Angel Ye', 'ADMIN_DEPT', 'ADMIN_SPEC', False),
        'groups': [
            ('EXT_PARTNER', '外部合作夥伴'),
        ],
        'external_users': [
            ('auditor01@auditexample.com.zz', '外部稽核員A', 'EXT_PARTNER'),
        ],
    },

    # --- 4. 個人測試環境 (僅 admin) ---
    {
        'code': 'TESTPERSONAL',
        'name': '測試用個人環境',
        'domain': 'testpersonalexample.com.zz',
        'display_name': 'Test Personal Environment',
        'contact_person': '澈測試',
        'contact_email': 'contact@testpersonalexample.com.zz',
        'contact_phone': '02-2700-0004',
        'description': '個人測試環境 -- 僅含管理員帳號',
        'user_limit': 10,
        'numbering': {
            'employee': {
                'name': '企業成員編號',
                'elements': {
                    'components': [
                        {'type': 'prefix', 'order': 1, 'values': ['TP']},
                        {'type': 'sequence', 'order': 2, 'start': 1, 'digits': 4, 'reset_period': 'never'},
                    ],
                    'total_length': 6,
                },
            },
        },
        'admin_member': ('admin.ops', '澈安琪', 'Angel Che', 'GM', 'ADMIN_SPEC', False),
        'admin_only': True,
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
    ('L000', '約聘人員', 'Contract Staff', 0, Decimal('0'), False, None),
]

STANDARD_JOB_FAMILIES = [
    ('MGR', '管理職', 'People Manager', JobFamilyType.MANAGER, None, '帶人主管，負責團隊管理與人員發展'),
    ('PROF', '專業職', 'Individual Contributor', JobFamilyType.PROFESSIONAL, None, '不帶人的專業人員'),
    # 專業職已有子職系，職稱只能掛末端職系；不屬特定領域的專業職稱一律掛 GEN
    ('GEN', '綜合專業職', 'General Professional', JobFamilyType.PROFESSIONAL, 'PROF', '不屬特定領域的專業人員'),
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
    ('SR_SPEC', '高級專員', 'Senior Specialist', 'L200', 'GEN', False),
    ('SR_ENG', '高級工程師', 'Senior Engineer', 'L200', 'TECH', False),
    ('SR_SALES', '高級業務代表', 'Senior Sales Rep', 'L200', 'SALES', False),
    ('SPEC', '專員', 'Specialist', 'L100', 'GEN', False),
    ('ENG', '工程師', 'Engineer', 'L100', 'TECH', False),
    ('SALES_REP', '業務代表', 'Sales Representative', 'L100', 'SALES', False),
    ('CSR', '客服代表', 'Customer Service Rep', 'L100', 'CS', False),
    ('ADMIN_SPEC', '行政專員', 'Admin Specialist', 'L100', 'ADMIN', False),
]

JOB_LEVEL_APPROVAL_LIMITS = {
    'L000': Decimal('0'),
    'L100': Decimal('10000'),
    'L200': Decimal('50000'),
    'L300': Decimal('100000'),
    'L400': Decimal('500000'),
    'L500': Decimal('1000000'),
    'L600': Decimal('5000000'),
    'L700': Decimal('10000000'),
    'L800': Decimal('50000000'),
    'L900': Decimal('999999999'),
}


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


def create_approval_categories(org_sc, levels):
    """建立核決類別與每個職等的核決上限"""
    categories = {}
    warned_missing_codes = set()

    for cfg in DEFAULT_APPROVAL_CATEGORIES:
        category = ApprovalCategory(
            org_secure_code=org_sc,
            code=cfg['code'],
            name=cfg['name'],
            name_en=cfg.get('name_en'),
            description=cfg.get('description'),
            currency='TWD',
            sort_order=cfg.get('sort_order', 0),
            is_system_default=False,
            is_active=True,
        )
        db.session.add(category)
        db.session.flush()
        categories[cfg['code']] = category

        for level_code, base_limit in JOB_LEVEL_APPROVAL_LIMITS.items():
            level = levels.get(level_code)
            if not level:
                if level_code not in warned_missing_codes:
                    print(f"  [WARN] 職等 {level_code} 不存在，跳過核決上限")
                    warned_missing_codes.add(level_code)
                continue

            approval_limit = base_limit
            if cfg['code'] == 'PETTY_CASH':
                approval_limit = base_limit // Decimal('10')
            elif cfg['code'] == 'MARKETING' and level.level_order <= 300:
                approval_limit = Decimal('0')

            limit = JobLevelApprovalLimit(
                org_secure_code=org_sc,
                job_level_secure_code=level.secure_code,
                category_secure_code=category.secure_code,
                approval_limit=approval_limit,
            )
            db.session.add(limit)

    return categories


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
        # 公司特定規則一律不標預設：出廠 6 組（含 EMPLOYEE／EXTERNAL／FORM／ORG_ADMIN 預設）
        # 已由 OrganizationService.create_organization_with_contract() 種入，
        # 再標預設會與平台預設撞成兩個（2026-09-13 bpserv DemoSOC 踩到）
        default_for = None
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
    """根據編號規則產生企業成員編號"""
    parts = []
    for comp in sorted(rule.elements.get('components', []), key=lambda x: x.get('order', 0)):
        ctype = comp.get('type')
        if ctype == 'prefix':
            parts.append(comp['values'][0])
        elif ctype == 'sequence':
            digits = comp.get('digits', 4)
            parts.append(str(seq_num).zfill(digits))
    return ''.join(parts)


def _assign_seed_role(org_sc, user, role, operator):
    if not role:
        return
    from app.services.role_assignment_service import assign_role
    assign_role(
        org_sc,
        user.secure_code,
        role.secure_code,
        operator=operator,
        source_ref='seed_script',
        commit=False,
    )


def create_employees(org, org_sc, domain, emp_list, depts, titles, numbering_rules,
                     password=TEST_PASSWORD, operator=None):
    """建立企業成員帳號 + 職位指派 + 企業成員編號 + EMPLOYEE 角色指派"""
    employee_rule = numbering_rules.get('employee')
    users = {}

    # 取得 EMPLOYEE 角色
    employee_role = Role.query.filter(
        Role.org_secure_code == org_sc,
        Role.code == 'EMPLOYEE',
        Role.is_deleted == False,
    ).first()

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
        user.set_password(password)
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

        # 指派 EMPLOYEE 角色 (鑰匙2)
        if employee_role:
            _assign_seed_role(org_sc, user, employee_role, operator)

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


def _first_unit_heads(emp_list):
    """依帳號清單順序取得每個部門的第一位主管。"""
    unit_heads = {}
    for username, native_name, english_name, dept_code, title_code, is_head in emp_list:
        if is_head and dept_code not in unit_heads:
            unit_heads[dept_code] = username
    return unit_heads


def _department_parent_map(dept_list):
    return {code: parent_code for name, code, parent_code in dept_list}


def _find_manager_username(username, dept_code, is_head, unit_heads, parent_by_dept):
    if not is_head:
        manager_username = unit_heads.get(dept_code)
        return manager_username if manager_username != username else None

    parent_code = parent_by_dept.get(dept_code)
    while parent_code:
        manager_username = unit_heads.get(parent_code)
        if manager_username and manager_username != username:
            return manager_username
        parent_code = parent_by_dept.get(parent_code)
    return None


def _expected_manager_usernames(company_def):
    """預覽：依部門主管推導預期會得到的直屬主管，不寫任何資料。"""
    emp_list = company_def.get('employees', [])
    unit_heads = _first_unit_heads(emp_list)
    parent_by_dept = _department_parent_map(company_def.get('departments', []))
    managers = {}

    for username, native_name, english_name, dept_code, title_code, is_head in emp_list:
        is_first_head = unit_heads.get(dept_code) == username
        managers[username] = _find_manager_username(
            username=username,
            dept_code=dept_code,
            is_head=is_head and is_first_head,
            unit_heads=unit_heads,
            parent_by_dept=parent_by_dept,
        )

    return managers


def print_manager_chain_preview(company_def):
    """列印 dry-run 主管鏈預覽。"""
    managers = _expected_manager_usernames(company_def)
    names_by_username = {emp[0]: emp[1] for emp in company_def.get('employees', [])}
    dept_names = {code: name for name, code, parent_code in company_def.get('departments', [])}
    all_titles = STANDARD_JOB_TITLES + company_def.get('extra_titles', [])
    title_names = {code: name for code, name, name_en, level_code, family_code, is_supv in all_titles}

    print(f"  預期直屬主管（由部門主管推導）:")
    for username, native_name, english_name, dept_code, title_code, is_head in company_def.get('employees', []):
        manager_username = managers.get(username)
        manager_name = names_by_username.get(manager_username, '無')
        dept_name = dept_names.get(dept_code, dept_code)
        title_name = title_names.get(title_code, title_code)
        print(f"    {native_name} ({dept_name}/{title_name}) -> {manager_name}")

def sync_dept_roles(org_sc, operator='seed_script'):
    """依 PRIMARY 任職卡同步部門成員關係與部門主管角色；只 flush，不 commit。"""
    from app.services.dept_membership_service import (
        ensure_dept_membership,
        get_system_role,
        reconcile_dept_manager,
    )

    roles = {
        code: get_system_role(org_sc, code)
        for code in ('DEPT_MEMBER', 'DEPT_EMPLOYEE', 'DEPT_MANAGER')
    }
    missing = [code for code, role in roles.items() if not role]
    if missing:
        print(f"         (跳過部門角色同步：缺少 {', '.join(missing)})")
        return {'skipped': True}

    positions = EmployeePosition.query.join(
        User,
        EmployeePosition.user_secure_code == User.secure_code,
    ).filter(
        EmployeePosition.org_secure_code == org_sc,
        EmployeePosition.position_type == PositionType.PRIMARY,
        EmployeePosition.is_deleted == False,
        EmployeePosition.is_active == True,
        User.org_secure_code == org_sc,
        User.is_deleted == False,
        User.is_active == True,
    ).order_by(
        EmployeePosition.unit_secure_code.asc(),
        EmployeePosition.id.asc(),
    ).all()

    expected_managers = {}
    skipped_units = 0
    for position in positions:
        if not position.is_unit_head or position.unit_secure_code in expected_managers:
            if position.is_unit_head:
                skipped_units += 1
                print(
                    "         (同單位已有預期主管，第二位以上視為一般成員: "
                    f"{position.user.display_name if position.user else position.user_secure_code})"
                )
            continue
        expected_managers[position.unit_secure_code] = (position.user, position.unit)

    before_memberships = UserUnitMembership.query.filter(
        UserUnitMembership.org_secure_code == org_sc,
    ).count()
    before_roles = UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org_sc,
    ).count()

    for position in positions:
        if not position.user or not position.unit:
            continue
        expected = expected_managers.get(position.unit_secure_code)
        if expected and expected[0].secure_code == position.user_secure_code:
            if position.user.primary_unit_secure_code is None:
                position.user.primary_unit_secure_code = position.unit_secure_code
            continue
        ensure_dept_membership(position.user, position.unit, operator)
        if position.user.primary_unit_secure_code is None:
            position.user.primary_unit_secure_code = position.unit_secure_code

    managers_set = 0
    for unit_sc, (manager, unit) in expected_managers.items():
        if reconcile_dept_manager(manager, unit, operator):
            managers_set += 1

    db.session.flush()
    after_memberships = UserUnitMembership.query.filter(
        UserUnitMembership.org_secure_code == org_sc,
    ).count()
    after_roles = UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org_sc,
    ).count()

    return {
        'positions': len(positions),
        'memberships_created': after_memberships - before_memberships,
        'roles_created': after_roles - before_roles,
        'managers_set': managers_set,
        'skipped_units': skipped_units,
    }


def _first_leaf_department(dept_list, excluded_code):
    parent_codes = {parent_code for name, code, parent_code in dept_list if parent_code}
    for name, code, parent_code in dept_list:
        if code != excluded_code and code not in parent_codes:
            return code
    return None


def _lowest_supervisor_title(titles):
    supervisor_titles = [title for title in titles.values() if title.is_supervisor]
    if not supervisor_titles:
        return None
    return min(
        supervisor_titles,
        key=lambda title: title.job_level.level_order if title.job_level else 999999,
    )


def create_additional_positions(org_sc, company_def, users, depts, titles):
    """建立兼任與代理職位樣本。"""
    emp_list = company_def.get('employees', [])
    if len(emp_list) < 3:
        print("         (跳過兼任/代理職位：企業成員不足)")
        return {'concurrent': 0, 'acting': 0}

    created = {'concurrent': 0, 'acting': 0}

    second_emp = emp_list[1]
    second_user = users.get(second_emp[0])
    concurrent_dept_code = _first_leaf_department(company_def.get('departments', []), second_emp[3])
    if not second_user or not concurrent_dept_code or concurrent_dept_code not in depts or second_emp[4] not in titles:
        print("         (跳過兼任職位：找不到合適成員、葉部門或職稱)")
    else:
        position = EmployeePosition(
            org_secure_code=org_sc,
            user_secure_code=second_user.secure_code,
            job_title_secure_code=titles[second_emp[4]].secure_code,
            unit_secure_code=depts[concurrent_dept_code].secure_code,
            position_type=PositionType.CONCURRENT,
            is_unit_head=False,
            effective_from=date(2026, 1, 1),
            effective_until=None,
            is_active=True,
        )
        db.session.add(position)
        created['concurrent'] += 1
        print(f"         兼任: {second_emp[1]} -> {depts[concurrent_dept_code].name}/{titles[second_emp[4]].name}")

    third_emp = emp_list[2]
    third_user = users.get(third_emp[0])
    acting_title = _lowest_supervisor_title(titles)
    today = date.today()
    if not third_user or not acting_title or third_emp[3] not in depts:
        print("         (跳過代理職位：找不到合適成員、主管職稱或部門)")
    else:
        position = EmployeePosition(
            org_secure_code=org_sc,
            user_secure_code=third_user.secure_code,
            job_title_secure_code=acting_title.secure_code,
            unit_secure_code=depts[third_emp[3]].secure_code,
            position_type=PositionType.ACTING,
            is_unit_head=False,
            effective_from=today,
            effective_until=today + timedelta(days=90),
            remarks='代理職務（種子資料）',
            is_active=True,
        )
        db.session.add(position)
        created['acting'] += 1
        print(f"         代理: {third_emp[1]} -> {depts[third_emp[3]].name}/{acting_title.name}")

    return created


def create_groups(org_sc, group_list):
    """建立群組"""
    groups = {}
    for code, name in group_list:
        group = OrganizationalUnit(
            org_secure_code=org_sc,
            name=name,
            code=code,
            unit_type=UnitType.GROUP,
            is_active=True,
        )
        db.session.add(group)
        db.session.flush()
        groups[code] = group
    return groups


def create_external_users(org, org_sc, ext_list, groups, numbering_rules,
                          password=TEST_PASSWORD, operator=None):
    """建立外部廠商帳號 + EXTERNAL_USERS 角色指派 + 群組成員關係"""
    external_rule = numbering_rules.get('external')
    if not external_rule:
        print("         (跳過：無外部廠商編號規則)")
        return {}

    # 取得 EXTERNAL_USERS 角色
    external_role = Role.query.filter(
        Role.org_secure_code == org_sc,
        Role.code == 'EXTERNAL_USERS',
        Role.is_deleted == False,
    ).first()

    users = {}
    for i, (email, display_name, group_code) in enumerate(ext_list):
        seq = i + 1
        emp_id = generate_employee_id(external_rule, seq) if external_rule else f'X{seq:03d}'
        username = email.split('@')[0]

        user = User(
            org_secure_code=org_sc,
            username=username,
            email=email,
            display_name=display_name,
            user_type=UserType.EXTERNAL,
            is_active=True,
            employee_id=emp_id,
            backup_email_1=email,
            must_change_password=False,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        users[username] = user

        UsedUserNumber.record_number(
            org_secure_code=org_sc,
            number=emp_id,
            user_secure_code=user.secure_code,
            rule_secure_code=external_rule.secure_code if external_rule else None,
        )

        # 指派 EXTERNAL_USERS 角色 (鑰匙2)
        if external_role:
            _assign_seed_role(org_sc, user, external_role, operator)

        # 群組成員關係
        if group_code in groups:
            membership = UserUnitMembership(
                org_secure_code=org_sc,
                user_secure_code=user.secure_code,
                unit_secure_code=groups[group_code].secure_code,
                membership_type=MembershipType.MEMBER,
                role_type=MembershipRole.MEMBER,
                start_date=date.today(),
            )
            db.session.add(membership)

    # 更新計數器
    if external_rule and ext_list:
        counter = UserNumberingCounter(
            org_secure_code=org_sc,
            rule_secure_code=external_rule.secure_code,
            period_key='forever',
            current_seq=len(ext_list),
        )
        db.session.add(counter)

    return users


# ============================================================================
# 主流程
# ============================================================================

def _get_seed_created_by():
    system_org = Organization.query.filter_by(code='SYSTEM', is_deleted=False).first()
    if not system_org:
        return None
    system_admin = User.query.filter_by(
        user_type=UserType.SYSTEM_ADMIN,
        is_deleted=False,
        is_active=True,
    ).first()
    return system_admin.secure_code if system_admin else None


def _complete_admin_initial_setup(org, admin_user, company_def, password, depts=None, titles=None):
    from app.services.org_initial_setup_service import complete_initial_setup

    member = company_def.get('admin_member')
    if not member:
        return None
    username, native_name, english_name, dept_code, title_code, is_head = member
    result = complete_initial_setup(
        org,
        admin_user,
        username,
        native_name,
        english_name,
        password,
        must_change_password=False,
    )
    employee = result['employee']
    if depts and titles and dept_code in depts and title_code in titles:
        position = EmployeePosition(
            org_secure_code=org.secure_code,
            user_secure_code=employee.secure_code,
            job_title_secure_code=titles[title_code].secure_code,
            unit_secure_code=depts[dept_code].secure_code,
            position_type=PositionType.PRIMARY,
            is_unit_head=is_head,
            effective_from=date(2026, 1, 1),
            is_active=True,
        )
        db.session.add(position)
        employee.primary_unit_secure_code = depts[dept_code].secure_code
    return result


def seed_one_company(company_def, *, password=TEST_PASSWORD, commit=True, emit_summary=True):
    """建立一家企業的完整資料"""
    from app.services.organization_service import OrganizationService
    from app.services.password_policy_service import PasswordPolicyService

    code = company_def['code']
    name = company_def['name']
    domain = company_def['domain']
    admin_only = company_def.get('admin_only', False)

    total_steps = 2 if admin_only else 12

    print(f"\n{'='*60}")
    print(f"  建立企業: {name} ({code})")
    print(f"{'='*60}")

    # 1. 企業 + 合約 + 原始管理員
    print(f"  [1/{total_steps}] 企業 + 合約 + 原始管理員...")
    pw_valid, pw_errors = PasswordPolicyService.validate_password(password, None)
    if not pw_valid:
        raise ValueError('；'.join(pw_errors))
    contract_modules = company_def.get('modules_config', SEED_CONTRACT_MODULES)
    org, admin_user, contract = OrganizationService.create_organization_with_contract(
        code=code,
        name=name,
        domain_name=domain,
        display_name=company_def.get('display_name'),
        contract_start_date=CONTRACT_START,
        contract_end_date=CONTRACT_END,
        customer_type=CustomerType.FORMAL,
        user_limit=company_def.get('user_limit', 50),
        admin_password=password,
        modules_config=contract_modules,
        created_by=_get_seed_created_by(),
        description=company_def.get('description'),
        contact_person=company_def.get('contact_person'),
        contact_email=company_def.get('contact_email'),
        contact_phone=company_def.get('contact_phone'),
    )
    db.session.flush()
    org_sc = org.secure_code
    print(f"         org_sc: {org_sc}")
    print(f"         admin: admin@{domain}")

    if admin_only:
        print(f"  [2/2] 初始設定...")
        _complete_admin_initial_setup(org, admin_user, company_def, password)
        if commit:
            db.session.commit()
        if emit_summary:
            print(f"\n  完成! 企業 {name} (僅管理員):")
            print(f"    管理員: admin-{company_def['admin_member'][0]}@{domain}")
            print(f"    密碼: {password}")
        return org

    # 2. 公司編號規則（出廠 6 組預設規則已由 create_organization_with_contract 種入）
    print(f"  [2/{total_steps}] 公司編號規則...")
    numbering_rules = create_numbering_rules(org_sc, company_def['numbering'])
    for key, rule in numbering_rules.items():
        print(f"         {key}: {rule.name}")

    # 4. 職等
    print(f"  [3/{total_steps}] 職等 (10 級)...")
    levels = create_job_levels(org_sc)

    # 5. 核決類別與上限
    print(f"  [4/{total_steps}] 核決類別 ({len(DEFAULT_APPROVAL_CATEGORIES)} 類) + 職等上限...")
    approval_categories = create_approval_categories(org_sc, levels)
    print(f"         {len(approval_categories)} 類，{len(approval_categories) * len(levels)} 筆上限")

    # 6. 職系
    extra_fam = company_def.get('extra_families', [])
    print(f"  [5/{total_steps}] 職系 ({len(STANDARD_JOB_FAMILIES) + len(extra_fam)} 個)...")
    families = create_job_families(org_sc, extra_fam)

    # 7. 職稱
    extra_titles = company_def.get('extra_titles', [])
    print(f"  [6/{total_steps}] 職稱 ({len(STANDARD_JOB_TITLES) + len(extra_titles)} 個)...")
    titles = create_job_titles(org_sc, levels, families, extra_titles)

    # 8. 部門
    dept_list = company_def['departments']
    print(f"  [7/{total_steps}] 部門 ({len(dept_list)} 個)...")
    depts = create_departments(org_sc, dept_list)

    # 9. 企業成員帳號 + 職位 + EMPLOYEE 角色
    emp_list = company_def['employees']
    print(f"  [8/{total_steps}] 企業成員帳號 ({len(emp_list)} 人) + 職位指派 + 角色...")
    users = create_employees(
        org, org_sc, domain, emp_list, depts, titles, numbering_rules,
        password=password, operator=admin_user,
    )

    print(f"         初始設定: 建立綁定管理員 admin-{company_def['admin_member'][0]}@{domain}")
    _complete_admin_initial_setup(org, admin_user, company_def, password, depts, titles)

    # 10. 部門成員與部門主管角色
    print(f"  [9/{total_steps}] 部門成員與部門主管角色...")
    role_counts = sync_dept_roles(org_sc)
    print(f"         {role_counts}")

    # 11. 兼任與代理職位
    print(f"  [10/{total_steps}] 兼任/代理職位樣本...")
    create_additional_positions(org_sc, company_def, users, depts, titles)

    # 12. 群組
    group_list = company_def.get('groups', [])
    print(f"  [11/{total_steps}] 群組 ({len(group_list)} 個)...")
    groups = create_groups(org_sc, group_list) if group_list else {}

    # 13. 外部廠商帳號 + EXTERNAL_USERS 角色
    ext_list = company_def.get('external_users', [])
    print(f"  [12/{total_steps}] 外部廠商 ({len(ext_list)} 人) + 角色...")
    ext_users = (
        create_external_users(
            org, org_sc, ext_list, groups, numbering_rules,
            password=password, operator=admin_user,
        )
        if ext_list else {}
    )

    if commit:
        db.session.commit()

    if emit_summary:
        print(f"\n  完成! 企業 {name}:")
        print(f"    管理員: admin-{company_def['admin_member'][0]}@{domain}")
        print(f"    企業成員: {len(users) + 1} 人")
        print(f"    外部廠商: {len(ext_users)} 人")
        print(f"    密碼: {password}")

    return org


def clean_test_companies():
    """清除本腳本建立的三家測試企業資料"""
    from sqlalchemy import text

    domains = [c['domain'] for c in COMPANIES]

    def _quote_identifier(identifier):
        if not SQL_IDENTIFIER_RE.match(identifier):
            raise ValueError(f"Invalid SQL identifier: {identifier}")
        return f'"{identifier}"'

    def _table_exists(table):
        if not SQL_IDENTIFIER_RE.match(table):
            raise ValueError(f"Invalid SQL identifier: {table}")
        return db.session.execute(
            text("SELECT to_regclass(:table_name) IS NOT NULL"),
            {'table_name': f'public.{table}'},
        ).scalar()

    def _delete_by_org(table, org_sc):
        if not _table_exists(table):
            print(f"    (跳過：資料表 {table} 不存在)")
            return
        db.session.execute(
            text(f"DELETE FROM {_quote_identifier(table)} WHERE org_secure_code = :osc"),
            {'osc': org_sc}
        )

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
            'menu_role_requirements',
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
            'fw_mapping_permissions',
            'fw_published_form_workflows',
            'fw_form_workflow_mappings',
            'fw_workflow_templates',
            'fw_form_templates',
        ]
        for table in phase1_tables:
            _delete_by_org(table, org_sc)

        # menu_permissions 透過 menu_items 子查詢 (無 org_secure_code)
        if _table_exists('menu_permissions') and _table_exists('menu_items'):
            db.session.execute(
                text("DELETE FROM menu_permissions WHERE menu_secure_code IN "
                     "(SELECT secure_code FROM menu_items WHERE org_secure_code = :osc)"),
                {'osc': org_sc}
            )

        # password_history 透過 user_secure_code (無 org_secure_code)
        if _table_exists('password_history') and _table_exists('users'):
            db.session.execute(
                text("DELETE FROM password_history WHERE user_secure_code IN "
                     "(SELECT secure_code FROM users WHERE org_secure_code = :osc)"),
                {'osc': org_sc}
            )

        # role_permissions 透過 role_secure_code (無 org_secure_code)
        if _table_exists('role_permissions') and _table_exists('roles'):
            db.session.execute(
                text("DELETE FROM role_permissions WHERE role_secure_code IN "
                     "(SELECT secure_code FROM roles WHERE org_secure_code = :osc)"),
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
            _delete_by_org(table, org_sc)

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
        admin_only = company.get('admin_only', False)
        print(f"\n{'='*60}")
        print(f"企業: {company['name']} ({company['code']})")
        print(f"網域: {company['domain']}")
        print(f"{'='*60}")
        print(f"  管理員: admin@{company['domain']}")
        if admin_only:
            print(f"  (僅管理員，無其他資料)")
            continue
        print(f"  編號規則: {len(company['numbering'])} 組")
        print(f"  核決類別: {len(DEFAULT_APPROVAL_CATEGORIES)} 類")
        print(f"  核決上限: {len(DEFAULT_APPROVAL_CATEGORIES) * len(STANDARD_JOB_LEVELS)} 筆")
        print(f"  職系: {len(STANDARD_JOB_FAMILIES) + len(company.get('extra_families', []))} 個")
        print(f"  職稱: {len(STANDARD_JOB_TITLES) + len(company.get('extra_titles', []))} 個")
        print(f"  部門: {len(company['departments'])} 個")
        print(f"  企業成員: {len(company['employees'])} 人")
        print(f"  兼任/代理職位: 各 1 筆 (若成員與部門足夠)")
        print(f"  部門結構:")
        for name, code, parent in company['departments']:
            indent = '    '
            if parent:
                indent = '      '
            print(f"{indent}{name} ({code})")
        print(f"  企業成員列表:")
        for username, native, english, dept, title, head in company['employees']:
            head_mark = ' [主管]' if head else ''
            print(f"    {native} ({english}) - {dept}/{title}{head_mark}")
        print_manager_chain_preview(company)


def main():
    parser = argparse.ArgumentParser(
        description='BeakMask 測試企業種子資料',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python scripts/seed_test_companies.py --dry-run   預覽資料結構
  python scripts/seed_test_companies.py --run        執行建立
  python scripts/seed_test_companies.py --clean      清除測試企業
  python scripts/seed_test_companies.py --sync-dept-roles  補齊既有範例企業的部門角色

建立的企業:
  1. 傳統文化製造集團 (GHTRAVEL) - ghtravelexample.com.zz
  2. 外星萊德科技公司 (BRIGHTCODE) - brightcodeexample.com.zz
  3. 綠色乖乖資安網 (SHIELDEDGE) - shieldedgeexample.com.zz
  4. 測試用個人環境 (TESTPERSONAL) - testpersonalexample.com.zz (僅 admin)

前三家企業包含:
  - 1 個管理員 (admin)
  - 20 個企業成員帳號 (含 PRIMARY 職位、部門成員關係與部門主管角色)
  - 兼任 CONCURRENT 與代理 ACTING 職位樣本各 1 筆
  - 核決類別與各職等核決上限
  - 編號規則、職等、職系、職稱、部門
  - 密碼統一: SEED_ADMIN_PASSWORD
        """,
    )
    parser.add_argument('--run', action='store_true', help='執行建立測試資料')
    parser.add_argument('--clean', action='store_true', help='清除本腳本建立的測試企業')
    parser.add_argument('--dry-run', action='store_true', help='預覽資料結構，不寫入')
    parser.add_argument('--sync-dept-roles', action='store_true', help='補齊既有範例企業的部門成員關係與部門主管角色')

    args = parser.parse_args()

    if not any([args.run, args.clean, args.dry_run, args.sync_dept_roles]):
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

        if args.sync_dept_roles:
            for company in COMPANIES:
                if company.get('admin_only'):
                    continue
                org = Organization.query.filter(
                    Organization.domain_name == company['domain'],
                    Organization.is_deleted == False,
                ).first()
                if not org:
                    print(f"企業 {company['name']} ({company['domain']}) 不存在，跳過")
                    continue
                counts = sync_dept_roles(org.secure_code)
                db.session.commit()
                print(f"企業 {company['name']}: {counts}")
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
            full_companies = [c for c in COMPANIES if not c.get('admin_only')]
            admin_only_companies = [c for c in COMPANIES if c.get('admin_only')]
            print(f"\n共建立 {len(COMPANIES)} 家企業")
            if full_companies:
                print(f"  完整企業 {len(full_companies)} 家 (admin + 20 企業成員)")
            if admin_only_companies:
                print(f"  僅管理員 {len(admin_only_companies)} 家")
            print(f"統一密碼: {TEST_PASSWORD}")
            print(f"\n登入方式:")
            for company in COMPANIES:
                print(f"  admin@{company['domain']}")


if __name__ == '__main__':
    main()
