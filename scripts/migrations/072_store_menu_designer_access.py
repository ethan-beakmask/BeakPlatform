#!/usr/bin/env python3
"""
讓 FLOW_DESIGNER / FORM_DESIGNER 角色能看到「內部商場」選單

調整內容：
  1. menu_permissions: 新增 user_type='EMPLOYEE' 列（store 選單）
  2. menu_role_requirements: 為每個 org 新增 FLOW_DESIGNER + FORM_DESIGNER 兩筆

背景：
  「內部商場」(menu code=store) 原本只允許 SYSTEM_ADMIN / ORG_ADMIN，
  但商場上架後的範本，FLOW_DESIGNER 與 FORM_DESIGNER 也需要能瀏覽 + 安裝。
  路由維持 @login_required，view 內依角色分流（後續商場重做時實作）。

使用方式:
    cd /opt/BeakPlatform-dev
    source venv/bin/activate
    python scripts/migrations/072_store_menu_designer_access.py --run
    python scripts/migrations/072_store_menu_designer_access.py --dry-run
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from app import create_app, db
from app.models import MenuItem, Role
from app.models.menu_permission import MenuPermission
from app.models.menu_role_requirement import MenuRoleRequirement


STORE_MENU_CODE = 'store'
DESIGNER_ROLE_CODES = ['FLOW_DESIGNER', 'FORM_DESIGNER']


def run(dry_run: bool = False) -> int:
    app = create_app()
    with app.app_context():
        store = MenuItem.query.filter_by(code=STORE_MENU_CODE, is_deleted=False).first()
        if not store:
            print(f"[ERR] 找不到 menu code={STORE_MENU_CODE}")
            return 1

        print(f"[INFO] 目標選單: id={store.id}, sc={store.secure_code}, title={store.title}")

        # 1) menu_permissions 新增 EMPLOYEE
        existing = MenuPermission.query.filter_by(
            menu_secure_code=store.secure_code,
            user_type='EMPLOYEE',
            is_deleted=False,
        ).first()
        if existing:
            print("[SKIP] menu_permissions EMPLOYEE 已存在")
        else:
            print("[ADD ] menu_permissions: user_type=EMPLOYEE")
            if not dry_run:
                db.session.add(MenuPermission(
                    menu_secure_code=store.secure_code,
                    user_type='EMPLOYEE',
                ))

        # 2) menu_role_requirements per org × DESIGNER role
        roles = Role.query.filter(
            Role.code.in_(DESIGNER_ROLE_CODES),
            Role.is_deleted == False,  # noqa: E712
        ).all()
        if not roles:
            print("[WARN] 找不到 FLOW_DESIGNER / FORM_DESIGNER 角色，跳過 role_requirements")
        for role in roles:
            existing = MenuRoleRequirement.query.filter_by(
                menu_secure_code=store.secure_code,
                role_secure_code=role.secure_code,
                org_secure_code=role.org_secure_code,
                is_deleted=False,
            ).first()
            tag = f"role={role.code} org={role.org_secure_code}"
            if existing:
                print(f"[SKIP] menu_role_requirements 已存在: {tag}")
            else:
                print(f"[ADD ] menu_role_requirements: {tag}")
                if not dry_run:
                    db.session.add(MenuRoleRequirement(
                        menu_secure_code=store.secure_code,
                        role_secure_code=role.secure_code,
                        org_secure_code=role.org_secure_code,
                    ))

        if dry_run:
            db.session.rollback()
            print("[DRY ] 已 rollback，未寫入")
        else:
            db.session.commit()
            print("[DONE] 已 commit")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--run', action='store_true', help='實際執行')
    parser.add_argument('--dry-run', action='store_true', help='預覽但不寫入')
    args = parser.parse_args()
    if not (args.run or args.dry_run):
        parser.print_help()
        return 0
    return run(dry_run=args.dry_run)


if __name__ == '__main__':
    sys.exit(main())
