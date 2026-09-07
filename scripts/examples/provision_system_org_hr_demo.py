#!/usr/bin/env python3
"""佈建系統預設企業（SYSTEM，secure_code=system.local）的最小人資結構，
供 OpHrLookup（人事資料取值）節點示範使用（dev-notes/HR_LOOKUP_NODE_SPEC.md）。

系統企業出廠時沒有任何職等／職系／職稱／核決類別／任職卡（刻意不種，
見 CLAUDE.md「【測系統級 node 前必讀】」），OpHrLookup 節點若拿系統企業的
帳號當範例會找不到任何有效職位。本腳本補上一組乾淨、不影響既有資料的示範結構：

- 3 級職等：L200（示範專員）／L500（示範經理，部門主管）／L700（示範處長，處主管）
- 2 個職系：MGR（管理職）／PROF > GEN（綜合專業職）
- 3 個職稱：DEMO_STAFF／DEMO_MANAGER／DEMO_DIRECTOR
- TRAVEL 核決類別（差旅費，與 provision_hr_lookup_demo.py 的 approval_category_code
  一致）：L200=0／L500=300000／L700=999999999（30 萬以下由 L500 核，超過由 L700 核）
- 兩層部門：示範處（DEMO_DIV，根）> 示範部（DEMO_DEPT，子）
- 3 個帳號：demo-director@system.local（DEMO_DIV 主管）／
  demo-manager@system.local（DEMO_DEPT 主管，示範專員的直屬主管）／
  demo-staff@system.local（DEMO_DEPT 一般成員，申請人）
  密碼統一 NodeDemo2026#Ok

部門成員與部門主管角色只走 dept_membership_service（唯一寫入路徑，見
backend/app/services/dept_membership_service.py），不自己寫 user_role_assignments。
直屬主管由 unit_resolver.resolve_direct_manager() 從 DEPT_MANAGER@單位 推導，
不依賴任何任職卡欄位。

冪等：以 code / email 查找既有記錄，重跑不會重複建立。

用法：
    cd /opt/BeakPlatform-dev
    set -a && source .env && set +a
    venv/bin/python scripts/examples/provision_system_org_hr_demo.py --apply
"""
import argparse
import os
import sys
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'backend'))

ORG_CODE = 'SYSTEM'
DEMO_PASSWORD = 'NodeDemo2026#Ok'
OPERATOR = 'provision_system_org_hr_demo'
EFFECTIVE_FROM = date(2026, 1, 1)

# (code, name, name_en, level_order, general_limit, is_manager, management_scope)
JOB_LEVELS = [
    ('L200', '示範專員級', 'Demo Staff Level', 200, Decimal('50000'), False, None),
    ('L500', '示範經理級', 'Demo Manager Level', 500, Decimal('1000000'), True, '單一部門'),
    ('L700', '示範處長級', 'Demo Director Level', 700, Decimal('10000000'), True, '單一處室'),
]

# (code, name, name_en, family_type, parent_code, description)
JOB_FAMILIES = [
    ('MGR', '管理職', 'People Manager', 'MANAGER', None, '帶人主管，負責團隊管理與人員發展'),
    ('PROF', '專業職', 'Individual Contributor', 'PROFESSIONAL', None, '不帶人的專業人員'),
    ('GEN', '綜合專業職', 'General Professional', 'PROFESSIONAL', 'PROF', '不屬特定領域的專業人員'),
]

# (code, name, name_en, level_code, family_code, is_supervisor)
JOB_TITLES = [
    ('DEMO_STAFF', '示範專員', 'Demo Staff', 'L200', 'GEN', False),
    ('DEMO_MANAGER', '示範經理', 'Demo Manager', 'L500', 'MGR', True),
    ('DEMO_DIRECTOR', '示範處長', 'Demo Director', 'L700', 'MGR', True),
]

# TRAVEL 與 provision_hr_lookup_demo.py 的 approval_category_code='TRAVEL' 一致
APPROVAL_CATEGORY = {
    'code': 'TRAVEL', 'name': '差旅費', 'name_en': 'Travel',
    'description': '出差相關費用（OpHrLookup 示範用）', 'sort_order': 50,
}
# 30 萬以下由 L500 核，超過由 L700 核；L200 本身不核決（申請人層級）
APPROVAL_LIMITS = {
    'L200': Decimal('0'),
    'L500': Decimal('300000'),
    'L700': Decimal('999999999'),
}

# (unit_code, unit_name, parent_code)
DEPARTMENTS = [
    ('DEMO_DIV', '示範處', None),
    ('DEMO_DEPT', '示範部', 'DEMO_DIV'),
]

# (username, native_name, english_name, employee_id, unit_code, title_code, is_head)
EMPLOYEES = [
    ('demo-director', '示範處長', 'Demo Director', 'DEMO-DIR', 'DEMO_DIV', 'DEMO_DIRECTOR', True),
    ('demo-manager', '示範經理', 'Demo Manager', 'DEMO-MGR', 'DEMO_DEPT', 'DEMO_MANAGER', True),
    ('demo-staff', '示範專員', 'Demo Staff', 'DEMO-STAFF', 'DEMO_DEPT', 'DEMO_STAFF', False),
]


def get_or_create_job_level(db, JobLevel, org_sc, code, name, name_en, order, limit, is_mgr, scope):
    level = JobLevel.query.filter_by(org_secure_code=org_sc, code=code, is_deleted=False).first()
    if level:
        return level, False
    level = JobLevel(
        org_secure_code=org_sc, code=code, name=name, name_en=name_en,
        level_order=order, approval_limit=limit, approval_currency='TWD',
        is_manager_level=is_mgr, management_scope=scope,
        sort_order=order, is_system_default=True, is_active=True,
    )
    db.session.add(level)
    db.session.flush()
    return level, True


def get_or_create_job_family(db, JobFamily, org_sc, code, name, name_en, ftype, parent, desc):
    family = JobFamily.query.filter_by(org_secure_code=org_sc, code=code, is_deleted=False).first()
    if family:
        return family, False
    family = JobFamily(
        org_secure_code=org_sc, code=code, name=name, name_en=name_en,
        family_type=ftype, parent_secure_code=parent.secure_code if parent else None,
        description=desc, sort_order=10, is_system_default=True, is_active=True,
    )
    db.session.add(family)
    db.session.flush()
    return family, True


def get_or_create_job_title(db, JobTitle, org_sc, code, name, name_en, level, family, is_supv):
    title = JobTitle.query.filter_by(org_secure_code=org_sc, code=code, is_deleted=False).first()
    if title:
        return title, False
    title = JobTitle(
        org_secure_code=org_sc, code=code, name=name, name_en=name_en,
        job_level_secure_code=level.secure_code, job_family_secure_code=family.secure_code,
        is_supervisor=is_supv, sort_order=level.level_order, is_system_default=True, is_active=True,
    )
    db.session.add(title)
    db.session.flush()
    return title, True


def get_or_create_approval_category(db, ApprovalCategory, org_sc, cfg):
    category = ApprovalCategory.query.filter_by(org_secure_code=org_sc, code=cfg['code'], is_deleted=False).first()
    if category:
        return category, False
    category = ApprovalCategory(
        org_secure_code=org_sc, code=cfg['code'], name=cfg['name'], name_en=cfg.get('name_en'),
        description=cfg.get('description'), currency='TWD', sort_order=cfg.get('sort_order', 0),
        is_system_default=False, is_active=True,
    )
    db.session.add(category)
    db.session.flush()
    return category, True


def upsert_job_level_approval_limit(db, JobLevelApprovalLimit, org_sc, level, category, limit_value):
    row = JobLevelApprovalLimit.query.filter_by(
        org_secure_code=org_sc, job_level_secure_code=level.secure_code,
        category_secure_code=category.secure_code,
    ).first()
    if row:
        changed = row.is_deleted or row.approval_limit != limit_value
        row.is_deleted = False
        row.deleted_at = None
        row.approval_limit = limit_value
        return row, changed
    row = JobLevelApprovalLimit(
        org_secure_code=org_sc, job_level_secure_code=level.secure_code,
        category_secure_code=category.secure_code, approval_limit=limit_value,
    )
    db.session.add(row)
    db.session.flush()
    return row, True


def get_or_create_unit(db, OrganizationalUnit, UnitType, org_sc, code, name, parent):
    unit = OrganizationalUnit.query.filter_by(org_secure_code=org_sc, code=code, is_deleted=False).first()
    if unit:
        return unit, False
    unit = OrganizationalUnit(
        org_secure_code=org_sc, unit_type=UnitType.DEPARTMENT, code=code, name=name,
        is_active=True, sort_order=10, parent_secure_code=parent.secure_code if parent else None,
    )
    unit.update_full_path()
    db.session.add(unit)
    db.session.flush()
    return unit, True


def get_or_create_user(db, User, UserType, org_sc, domain, username, native_name, english_name, employee_id):
    email = f'{username}@{domain}'
    user = User.query.filter_by(org_secure_code=org_sc, email=email, is_deleted=False).first()
    if user:
        return user, False
    user = User(
        org_secure_code=org_sc, username=username, email=email,
        display_name=native_name, native_name=native_name, english_name=english_name,
        user_type=UserType.EMPLOYEE, is_active=True, employee_id=employee_id,
        must_change_password=False,
    )
    user.set_password(DEMO_PASSWORD)
    db.session.add(user)
    db.session.flush()
    return user, True


def ensure_employee_role(db, Role, UserRoleAssignment, org_sc, user):
    role = Role.query.filter_by(org_secure_code=org_sc, code='EMPLOYEE', is_deleted=False).first()
    if not role:
        print(f'  [WARN] {org_sc} 找不到 EMPLOYEE 角色，跳過角色指派')
        return
    exists = UserRoleAssignment.query.filter_by(
        org_secure_code=org_sc, user_secure_code=user.secure_code,
        role_secure_code=role.secure_code, unit_secure_code=None, is_deleted=False,
    ).first()
    if exists:
        return
    db.session.add(UserRoleAssignment(
        org_secure_code=org_sc, user_secure_code=user.secure_code,
        role_secure_code=role.secure_code, assigned_by=OPERATOR,
    ))


def get_or_create_position(db, EmployeePosition, PositionType, org_sc, user, title, unit, is_head):
    position = EmployeePosition.query.filter_by(
        org_secure_code=org_sc, user_secure_code=user.secure_code,
        unit_secure_code=unit.secure_code, position_type=PositionType.PRIMARY, is_deleted=False,
    ).first()
    if position:
        position.job_title_secure_code = title.secure_code
        position.is_unit_head = is_head
        position.is_active = True
        return position, False
    position = EmployeePosition(
        org_secure_code=org_sc, user_secure_code=user.secure_code,
        job_title_secure_code=title.secure_code, unit_secure_code=unit.secure_code,
        position_type=PositionType.PRIMARY, is_unit_head=is_head,
        effective_from=EFFECTIVE_FROM, is_active=True,
    )
    db.session.add(position)
    db.session.flush()
    return position, True


def run():
    from app import create_app, db
    app = create_app('development')
    with app.app_context():
        from app.models import (
            Organization, User, UserType, OrganizationalUnit, UnitType,
            JobLevel, JobFamily, JobTitle, Role, UserRoleAssignment,
        )
        from app.models.approval_category import ApprovalCategory, JobLevelApprovalLimit
        from app.models.employee_position import EmployeePosition, PositionType
        from app.services.dept_membership_service import ensure_dept_membership, reconcile_dept_manager

        org = Organization.query.filter_by(code=ORG_CODE, is_deleted=False).first()
        if not org:
            raise SystemExit(f'找不到企業 {ORG_CODE}')
        osc = org.secure_code
        domain = org.domain_name if hasattr(org, 'domain_name') and org.domain_name else 'system.local'
        report = {'created': [], 'reused': []}

        def note(kind, label, obj_created):
            report['created' if obj_created else 'reused'].append(label)

        # 1. 職等
        levels = {}
        for code, name, name_en, order, limit, is_mgr, scope in JOB_LEVELS:
            level, created = get_or_create_job_level(db, JobLevel, osc, code, name, name_en, order, limit, is_mgr, scope)
            levels[code] = level
            note('job_level', f'{code} {name} ({level.secure_code})', created)

        # 2. 職系（PROF 必須先建，GEN 才能掛在它底下）
        families = {}
        for code, name, name_en, ftype, parent_code, desc in JOB_FAMILIES:
            parent = families.get(parent_code)
            family, created = get_or_create_job_family(db, JobFamily, osc, code, name, name_en, ftype, parent, desc)
            families[code] = family
            note('job_family', f'{code} {name} ({family.secure_code})', created)

        # 3. 職稱
        titles = {}
        for code, name, name_en, level_code, family_code, is_supv in JOB_TITLES:
            title, created = get_or_create_job_title(
                db, JobTitle, osc, code, name, name_en, levels[level_code], families[family_code], is_supv)
            titles[code] = title
            note('job_title', f'{code} {name} ({title.secure_code})', created)

        # 4. 核決類別與職等上限
        category, created = get_or_create_approval_category(db, ApprovalCategory, osc, APPROVAL_CATEGORY)
        note('approval_category', f"{APPROVAL_CATEGORY['code']} {APPROVAL_CATEGORY['name']} ({category.secure_code})", created)
        for level_code, limit_value in APPROVAL_LIMITS.items():
            _row, changed = upsert_job_level_approval_limit(db, JobLevelApprovalLimit, osc, levels[level_code], category, limit_value)
            note('approval_limit', f'{level_code} -> {limit_value}', changed)

        # 5. 部門（先建根，再建子）
        units = {}
        for code, name, parent_code in DEPARTMENTS:
            parent = units.get(parent_code)
            unit, created = get_or_create_unit(db, OrganizationalUnit, UnitType, osc, code, name, parent)
            units[code] = unit
            note('unit', f'{code} {name} ({unit.secure_code})', created)

        # 6. 帳號 + EMPLOYEE 角色 + 任職卡
        users = {}
        for username, native_name, english_name, employee_id, unit_code, title_code, is_head in EMPLOYEES:
            user, created = get_or_create_user(db, User, UserType, osc, domain, username, native_name, english_name, employee_id)
            users[username] = user
            note('user', f'{username}@{domain} {native_name} ({user.secure_code})', created)
            ensure_employee_role(db, Role, UserRoleAssignment, osc, user)
            position, pos_created = get_or_create_position(
                db, EmployeePosition, PositionType, osc, user, titles[title_code], units[unit_code], is_head)
            note('position', f'{username} @ {unit_code} / {title_code} ({position.secure_code})', pos_created)

        db.session.flush()

        # 7. 部門成員關係與部門主管角色（唯一寫入路徑：dept_membership_service）
        # 先處理一般成員（非主管），再處理主管，避免 reconcile 誤判
        for username, native_name, english_name, employee_id, unit_code, title_code, is_head in EMPLOYEES:
            if is_head:
                continue
            ensure_dept_membership(users[username], units[unit_code], OPERATOR)
        for username, native_name, english_name, employee_id, unit_code, title_code, is_head in EMPLOYEES:
            if not is_head:
                continue
            reconcile_dept_manager(users[username], units[unit_code], OPERATOR)

        db.session.commit()

        print(f'\n企業：{ORG_CODE}（{osc}）')
        print(f'新建 {len(report["created"])} 筆：')
        for line in report['created']:
            print(f'  + {line}')
        print(f'沿用既有 {len(report["reused"])} 筆：')
        for line in report['reused']:
            print(f'  = {line}')

        print('\n三個示範帳號 secure_code：')
        for username, native_name, *_ in EMPLOYEES:
            print(f'  {username}@{domain}（{native_name}）: {users[username].secure_code}')


def main():
    parser = argparse.ArgumentParser(description='佈建系統預設企業的最小人資結構（OpHrLookup 示範用）')
    parser.add_argument('--apply', action='store_true', help='實際寫入資料庫；未加此參數只顯示說明')
    args = parser.parse_args()
    if not args.apply:
        parser.print_help()
        return 0
    run()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
