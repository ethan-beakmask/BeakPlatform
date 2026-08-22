#!/usr/bin/env python3
"""
110 - 開放表單流程設計選單給 EMPLOYEE 設計者（冪等）

用途：
  BeakPlatform 的頁面存取需要同時通過 menu_permissions（user_type）
  與 menu_role_requirements（per-org role）兩道閘門。本 migration 會：
  1. 對表單流程設計相關選單補上 EMPLOYEE 的 menu_permissions。
  2. 依 MENU_ROLE_DEFAULTS 對各企業補齊表單流程設計選單的角色需求。

  form_workflow.ai_usage 不在名單內，因為 AI 用量與配額屬管理員成本管理面，
  本次刻意不開放 EMPLOYEE。

使用方式：
    cd /opt/BeakPlatform-dev
    ./venv/bin/python scripts/migrations/110_open_form_workflow_menu_to_employee.py --dry-run
    ./venv/bin/python scripts/migrations/110_open_form_workflow_menu_to_employee.py --run
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

MIGRATION_ID = '110_open_form_workflow_menu_to_employee'

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent.parent
BACKEND_DIR = PROJECT_DIR / 'backend'
sys.path.insert(0, str(BACKEND_DIR))

# Key1（menu_permissions）要補 EMPLOYEE 的選單；
# form_workflow.ai_usage 刻意不列（管理員成本管理面）。
KEY1_MENU_CODES = [
    'form_workflow',
    'form_workflow.workflows',
    'form_workflow.templates',
    'form_workflow.mappings',
    'form_workflow.categories',
    'form_workflow.form_themes',
]


def _load_env_file() -> None:
    """讀取 repo 根目錄 .env；既有環境變數優先，不覆蓋呼叫端設定。"""
    env_path = PROJECT_DIR / '.env'
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _print_usage() -> None:
    print(f'[{MIGRATION_ID}] 參數使用說明')
    print('用途：開放表單流程設計選單給 EMPLOYEE 設計者，並補齊各企業角色選單需求。')
    print('用法：')
    print('  ./venv/bin/python scripts/migrations/110_open_form_workflow_menu_to_employee.py --dry-run')
    print('  ./venv/bin/python scripts/migrations/110_open_form_workflow_menu_to_employee.py --run')


def _restore_soft_deleted(row) -> None:
    row.is_deleted = False
    row.deleted_at = None


def run(dry_run: bool) -> int:
    _load_env_file()
    if not os.environ.get('DATABASE_URL'):
        print(f'[{MIGRATION_ID}] [ERR] DATABASE_URL 未設定，且 .env 未提供，無法連線')
        return 1

    from sqlalchemy import text

    from app import create_app, db
    from app.defaults.menu_defaults import MENU_ROLE_DEFAULTS
    from app.models import (
        MenuItem,
        MenuPermission,
        MenuRoleRequirement,
        Organization,
        Role,
    )

    app = create_app()
    with app.app_context():
        print(f"[{MIGRATION_ID}] 模式: {'dry-run（未寫入）' if dry_run else 'run（會寫入）'}")

        db.session.execute(text("SET LOCAL app.is_system_admin = 'true'"))

        employee_user_type = 'EMPLOYEE'  # menu_permissions.user_type 存大寫字串
        key1_created_count = 0
        key2_created_count = 0

        print('[DONE] A 段 Key1：檢查表單流程選單 EMPLOYEE 可見性')
        for menu_code in KEY1_MENU_CODES:
            menu = MenuItem.query.filter(
                MenuItem.code == menu_code,
                MenuItem.is_deleted == False
            ).order_by(MenuItem.id).first()
            if not menu:
                print(f'[WARN] menu={menu_code} 找不到選單，略過')
                continue

            existing = MenuPermission.query.filter_by(
                menu_secure_code=menu.secure_code,
                user_type=employee_user_type,
                is_deleted=False
            ).first()
            if existing:
                continue

            deleted = MenuPermission.query.filter_by(
                menu_secure_code=menu.secure_code,
                user_type=employee_user_type,
                is_deleted=True
            ).first()
            key1_created_count += 1
            print(f'[ADD ] menu={menu_code} user_type={employee_user_type}')
            if not dry_run:
                if deleted:
                    _restore_soft_deleted(deleted)
                else:
                    db.session.add(MenuPermission(
                        menu_secure_code=menu.secure_code,
                        user_type=employee_user_type,
                    ))

        form_role_defaults = {
            code: role_codes
            for code, role_codes in MENU_ROLE_DEFAULTS.items()
            if code.startswith('form_workflow.') and code != 'form_workflow.center'
        }
        menus = MenuItem.query.filter(
            MenuItem.code.in_(form_role_defaults.keys()),
            MenuItem.is_deleted == False
        ).all()
        menu_by_code = {menu.code: menu for menu in menus}

        orgs = Organization.query.filter(
            Organization.is_deleted == False
        ).order_by(Organization.id).all()
        print(f'[DONE] B 段 Key2：待處理企業數 {len(orgs)}')

        for org in orgs:
            org_created = 0
            for menu_code, role_codes in form_role_defaults.items():
                menu = menu_by_code.get(menu_code)
                if not menu:
                    print(f'[WARN] org={org.code} menu={menu_code} 找不到選單，略過')
                    continue

                for role_code in role_codes:
                    role = Role.query.filter_by(
                        org_secure_code=org.secure_code,
                        code=role_code,
                        is_deleted=False
                    ).first()
                    if not role:
                        print(f'[WARN] org={org.code} 找不到角色 {role_code}，略過')
                        continue

                    existing = MenuRoleRequirement.query.filter_by(
                        menu_secure_code=menu.secure_code,
                        role_secure_code=role.secure_code,
                        org_secure_code=org.secure_code,
                        is_deleted=False
                    ).first()
                    if existing:
                        continue

                    deleted = MenuRoleRequirement.query.filter_by(
                        menu_secure_code=menu.secure_code,
                        role_secure_code=role.secure_code,
                        org_secure_code=org.secure_code,
                        is_deleted=True
                    ).first()
                    org_created += 1
                    key2_created_count += 1
                    print(f'[ADD ] org={org.code} menu={menu_code} role={role_code}')
                    if not dry_run:
                        if deleted:
                            _restore_soft_deleted(deleted)
                        else:
                            db.session.add(MenuRoleRequirement(
                                org_secure_code=org.secure_code,
                                menu_secure_code=menu.secure_code,
                                role_secure_code=role.secure_code,
                            ))

            print(f'[DONE] org={org.code} 待新增 {org_created} 筆 menu_role_requirements')

        if dry_run:
            db.session.rollback()
            print('[DONE] dry-run 已 rollback，未寫入')
        else:
            db.session.commit()
            print('[DONE] 已 commit')

        print(f'[DONE] 新增/恢復 {key1_created_count} 筆 menu_permissions')
        print(f'[DONE] 新增/恢復 {key2_created_count} 筆 menu_role_requirements')
        return 0


def main() -> int:
    if len(sys.argv) == 1:
        _print_usage()
        return 0

    parser = argparse.ArgumentParser(
        description='開放表單流程設計選單給 EMPLOYEE 設計者',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true', help='只列出待新增項目，不寫入')
    mode.add_argument('--run', action='store_true', help='執行寫入')
    args = parser.parse_args()
    return run(dry_run=args.dry_run)


if __name__ == '__main__':
    sys.exit(main())
