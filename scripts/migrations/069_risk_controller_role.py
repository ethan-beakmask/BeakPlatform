#!/usr/bin/env python3
"""
為既有企業新增 RISK_CONTROLLER (弱點風險管制員) 角色

功能：
  1. 為所有非系統企業建立 RISK_CONTROLLER 角色（若不存在）
  2. 配置 vuln_lifecycle 模組相關權限

前提：
  vuln_lifecycle 模組需先載入一次（Flask 啟動會自動同步權限到 DB）

使用方式:
    cd /opt/BeakPlatform-dev
    source venv/bin/activate
    python scripts/migrations/069_risk_controller_role.py          # 顯示說明
    python scripts/migrations/069_risk_controller_role.py --run    # 執行
    python scripts/migrations/069_risk_controller_role.py --dry-run # 預覽
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


ROLE_CODE = 'RISK_CONTROLLER'
ROLE_NAME = '弱點風險管制員'
ROLE_DESC = '管理弱點生命週期、風險調整審核與資產弱點追蹤'

ROLE_PERMS = [
    'vuln_lifecycle.dashboard.view',
    'vuln_lifecycle.asset.view',
    'vuln_lifecycle.finding.view',
    'vuln_lifecycle.risk.view',
    'vuln_lifecycle.risk.adjust',
    'vuln_lifecycle.risk.approve',
]


def _ensure_role(org, dry_run):
    """確保 RISK_CONTROLLER 角色存在，不存在則建立"""
    role = Role.query.filter_by(
        org_secure_code=org.secure_code,
        code=ROLE_CODE,
        is_deleted=False
    ).first()

    if role:
        return role, False

    role = Role(
        org_secure_code=org.secure_code,
        role_type=RoleType.ROLE,
        scope_type=ScopeType.GLOBAL,
        code=ROLE_CODE,
        name=ROLE_NAME,
        description=ROLE_DESC,
        is_manager=False,
        is_system_role=True,
        is_active=True
    )
    role.update_full_path()
    if not dry_run:
        db.session.add(role)
        db.session.flush()
    return role, True


def _patch_role_perms(role, perm_by_code, dry_run):
    """為角色補上缺少的權限"""
    if not role:
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
    for code in ROLE_PERMS:
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


def run_migration(dry_run=False):
    """為所有企業補上 RISK_CONTROLLER 角色與權限"""

    orgs = Organization.query.filter(
        Organization.is_deleted == False,
        Organization.secure_code != SYSTEM_ORG_CODE
    ).all()

    if not orgs:
        print("無非系統企業，跳過")
        return

    # 查詢權限
    perms = Permission.query.filter(
        Permission.code.in_(ROLE_PERMS),
        Permission.is_deleted == False,
        Permission.is_active == True
    ).all()
    perm_by_code = {p.code: p for p in perms}

    missing_perms = set(ROLE_PERMS) - set(perm_by_code.keys())
    if missing_perms:
        print(f"[WARNING] 以下權限不存在 (需先啟動 Flask 同步模組權限): {missing_perms}")
        print("請先執行一次 Flask 啟動讓 vuln_lifecycle 模組權限同步到 DB")
        return

    total_roles = 0
    total_perms = 0

    for org in orgs:
        print(f"  [{org.code} / {org.name}]")

        role, is_new = _ensure_role(org, dry_run)

        if is_new:
            total_roles += 1
            tag = "(dry-run)" if dry_run else ""
            print(f"    {ROLE_CODE}: 建立角色 {tag}")
        else:
            print(f"    {ROLE_CODE}: 角色已存在")

        created = _patch_role_perms(role, perm_by_code, dry_run)
        if created > 0:
            total_perms += created
            tag = "(dry-run)" if dry_run else ""
            print(f"    +{created} 筆權限 {tag}")
        else:
            print(f"    權限已完整")

    if not dry_run and (total_roles > 0 or total_perms > 0):
        db.session.commit()

    suffix = ' (dry-run)' if dry_run else ''
    print(f"\n新建 {total_roles} 個角色，配置 {total_perms} 筆權限{suffix}")


def main():
    parser = argparse.ArgumentParser(
        description='為既有企業新增 RISK_CONTROLLER 角色'
    )
    parser.add_argument('--run', action='store_true', help='執行遷移')
    parser.add_argument('--dry-run', action='store_true', help='預覽不寫入')
    args = parser.parse_args()

    if not args.run and not args.dry_run:
        parser.print_help()
        print(f"\n說明:")
        print(f"  為所有企業建立 {ROLE_CODE} ({ROLE_NAME}) 角色")
        print(f"  並配置 vuln_lifecycle 模組權限:")
        for p in ROLE_PERMS:
            print(f"    - {p}")
        return

    app = create_app('development')
    with app.app_context():
        print(f"為既有企業新增 {ROLE_CODE} ({ROLE_NAME}) 角色\n")
        run_migration(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
