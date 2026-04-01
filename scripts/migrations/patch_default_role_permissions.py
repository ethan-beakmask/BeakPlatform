#!/usr/bin/env python3
"""
修補既有企業的預設角色權限

問題：_create_default_roles() 只建角色，未配權限 (role_permissions 為空)
修正：
  1. 為所有企業的 EMPLOYEE 角色補上基本表單使用權限
  2. 為所有企業建立 FORM_DESIGNER 角色並配權限（若不存在）
  3. 為所有企業建立 FLOW_DESIGNER 角色並配權限（若不存在）
  4. 為所有企業建立 SPEC_DESIGNER 角色（若不存在）
  5. 為所有企業建立 SUBSYS_DESIGNER 角色（若不存在）

使用方式:
    cd /opt/BeakPlatform
    source venv/bin/activate
    python scripts/migrations/patch_default_role_permissions.py          # 顯示說明
    python scripts/migrations/patch_default_role_permissions.py --run    # 執行
    python scripts/migrations/patch_default_role_permissions.py --dry-run # 預覽
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from app import create_app, db
from app.models import Organization, Role, RoleType, ScopeType
from app.models.permission import Permission
from app.models.role_permission import RolePermission
from app.constants import SYSTEM_ORG_CODE

# 角色 → 預設權限對照表（無權限的角色用空 list）
ROLE_PERM_MAP = {
    'EMPLOYEE': [
        'form_workflow.form.create',
        'form_workflow.form.view',
        'form_workflow.approval.approve',
        'form_workflow.approval.transfer',
    ],
    'FORM_DESIGNER': [
        'form_workflow.template.view',
        'form_workflow.template.manage',
        'form_workflow.template.publish',
        'form_workflow.design.tryout',
    ],
    'FLOW_DESIGNER': [
        'form_workflow.workflow.view',
        'form_workflow.workflow.manage',
        'form_workflow.design.tryout',
    ],
    'SPEC_DESIGNER': [],
    'SUBSYS_DESIGNER': [],
}

# 角色建立定義（code → 屬性）
ROLE_DEFINITIONS = {
    'FORM_DESIGNER': {
        'name': '表單設計師',
        'description': '管理表單範本、流程設計，並可試行未發行的設計稿',
    },
    'FLOW_DESIGNER': {
        'name': '流程設計師',
        'description': '設計與管理簽核流程',
    },
    'SPEC_DESIGNER': {
        'name': '規格管理師',
        'description': '管理系統規格與參數定義',
    },
    'SUBSYS_DESIGNER': {
        'name': '子系統架構師',
        'description': '管理子系統架構與模組配置',
    },
}


def _ensure_role(org, role_code, dry_run):
    """確保角色存在，不存在則建立"""
    role = Role.query.filter_by(
        org_secure_code=org.secure_code,
        code=role_code,
        is_deleted=False
    ).first()

    if role:
        return role, False

    defn = ROLE_DEFINITIONS.get(role_code)
    if not defn:
        return None, False

    role = Role(
        org_secure_code=org.secure_code,
        role_type=RoleType.ROLE,
        scope_type=ScopeType.GLOBAL,
        code=role_code,
        name=defn['name'],
        description=defn['description'],
        is_manager=False,
        is_system_role=True,
        is_active=True
    )
    role.update_full_path()
    if not dry_run:
        db.session.add(role)
        db.session.flush()
    return role, True


def _patch_role_perms(role, perm_codes, perm_by_code, dry_run):
    """為角色補上缺少的權限，回傳新增數"""
    if not role or not perm_codes:
        return 0

    existing = RolePermission.query.filter(
        RolePermission.role_secure_code == role.secure_code,
        RolePermission.is_deleted == False
    ).all()
    existing_perm_codes = set()
    for rp in existing:
        if rp.permission:
            existing_perm_codes.add(rp.permission.code)

    created = 0
    for code in perm_codes:
        if code in existing_perm_codes:
            continue
        perm = perm_by_code.get(code)
        if not perm:
            continue
        rp = RolePermission(
            role_secure_code=role.secure_code,
            permission_secure_code=perm.secure_code,
            is_active=True,
        )
        if not dry_run:
            db.session.add(rp)
        created += 1

    return created


def patch_permissions(dry_run=False):
    """為所有企業補上預設角色與權限"""

    # 查詢所有非系統企業
    orgs = Organization.query.filter(
        Organization.is_deleted == False,
        Organization.secure_code != SYSTEM_ORG_CODE
    ).all()

    # 收集所有需要的權限代碼
    all_perm_codes = set()
    for codes in ROLE_PERM_MAP.values():
        all_perm_codes.update(codes)

    # 查詢權限
    perm_by_code = {}
    if all_perm_codes:
        perms = Permission.query.filter(
            Permission.code.in_(list(all_perm_codes)),
            Permission.is_deleted == False,
            Permission.is_active == True
        ).all()
        perm_by_code = {p.code: p for p in perms}

        missing_perms = all_perm_codes - set(perm_by_code.keys())
        if missing_perms:
            print(f"[WARNING] 以下權限不存在 (需先啟動 Flask 同步模組權限): {missing_perms}")
            print("請先執行一次 Flask 啟動讓模組權限同步到 DB")
            return

    total_roles_created = 0
    total_perms_created = 0

    for org in orgs:
        print(f"  [{org.domain_name}]")

        for role_code, perm_codes in ROLE_PERM_MAP.items():
            role, is_new = _ensure_role(org, role_code, dry_run)

            if not role:
                print(f"    {role_code}: 無法建立，跳過")
                continue

            if is_new:
                total_roles_created += 1
                tag = "(new role, dry-run)" if dry_run else "(new role)"
                print(f"    {role_code}: 建立角色 {tag}")

            created = _patch_role_perms(role, perm_codes, perm_by_code, dry_run)
            if created > 0:
                total_perms_created += created
                tag = "(dry-run)" if dry_run else ""
                print(f"    {role_code}: +{created} 權限 {tag}")
            else:
                if perm_codes:
                    print(f"    {role_code}: 權限已完整")
                else:
                    print(f"    {role_code}: 無需配權限")

    if not dry_run and (total_roles_created > 0 or total_perms_created > 0):
        db.session.commit()

    suffix = ' (dry-run)' if dry_run else ''
    print(f"\n新建 {total_roles_created} 個角色，修補 {total_perms_created} 筆權限{suffix}")


def main():
    parser = argparse.ArgumentParser(description='修補既有企業的預設角色權限')
    parser.add_argument('--run', action='store_true', help='執行修補')
    parser.add_argument('--dry-run', action='store_true', help='預覽不寫入')
    args = parser.parse_args()

    if not args.run and not args.dry_run:
        parser.print_help()
        print("\n說明:")
        print("  1. 為所有企業的 EMPLOYEE 補上基本表單使用權限")
        print("  2. 為所有企業建立 FORM_DESIGNER 角色 + 表單管理/試行權限")
        print("  3. 為所有企業建立 FLOW_DESIGNER 角色 + 流程管理/試行權限")
        print("  4. 為所有企業建立 SPEC_DESIGNER 角色")
        print("  5. 為所有企業建立 SUBSYS_DESIGNER 角色")
        return

    app = create_app('development')
    with app.app_context():
        print("修補既有企業的預設角色與權限\n")
        patch_permissions(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
