#!/usr/bin/env python3
"""
111 - 開放弱點管理選單給 RISK_CONTROLLER（冪等）

用途：
  弱點管理三個功能選單的雙鑰匙與角色設計對不上：
  Key1（menu_permissions）只開 ORG_ADMIN、Key2（menu_role_requirements）是空的，
  但 RISK_CONTROLLER 角色（EMPLOYEE 型）握有全部 vuln_lifecycle permission，
  API 實測全部 200。症狀是「API 打得到、選單看不到」。

  本 migration 讓兩者一致：
  1. Key1：vuln_lifecycle 及其子選單補上 EMPLOYEE
  2. Key2：依 MENU_ROLE_DEFAULTS 對各企業補 RISK_CONTROLLER

  搭配 PF-145 施工2 對 vuln_lifecycle 的 8 支 API 加掛 @page_keys_required；
  沒有這個 migration 先跑，那 8 支會把 RISK_CONTROLLER 從 200 打成 403。

  出廠預設同步改在 modules/vuln_lifecycle/__init__.py（Key1）與
  backend/app/defaults/menu_defaults.py（Key2），只跑 migration 不改出廠值的話，
  新建企業會長回舊的樣子（MENU-01）。

使用方式：
    cd /opt/BeakPlatform-dev
    ./venv/bin/python scripts/migrations/111_open_vuln_lifecycle_menu_to_risk_controller.py --dry-run
    ./venv/bin/python scripts/migrations/111_open_vuln_lifecycle_menu_to_risk_controller.py --run
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

MIGRATION_ID = '111_open_vuln_lifecycle_menu_to_risk_controller'

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent.parent
BACKEND_DIR = PROJECT_DIR / 'backend'
sys.path.insert(0, str(BACKEND_DIR))

# Key1 要補 EMPLOYEE 的選單（含 header 型父選單，否則子選單不會出現）
KEY1_MENU_CODES = [
    'vuln_lifecycle',
    'vuln_lifecycle.dashboard',
    'vuln_lifecycle.assets',
    'vuln_lifecycle.risk',
    'vuln_lifecycle.kynd',
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
    print('用途：開放弱點管理選單給 RISK_CONTROLLER，讓選單可見性與 API 權限一致。')
    print('用法：')
    print(f'  ./venv/bin/python scripts/migrations/{MIGRATION_ID}.py --dry-run')
    print(f'  ./venv/bin/python scripts/migrations/{MIGRATION_ID}.py --run')


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
        MenuItem, MenuPermission, MenuRoleRequirement, Organization, Role,
    )

    app = create_app()
    with app.app_context():
        print(f"[{MIGRATION_ID}] 模式: {'dry-run（未寫入）' if dry_run else 'run（會寫入）'}")
        db.session.execute(text("SET LOCAL app.is_system_admin = 'true'"))

        employee_user_type = 'EMPLOYEE'
        key1_count = 0
        key2_count = 0

        print('[DONE] A 段 Key1：弱點管理選單補 EMPLOYEE')
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
            key1_count += 1
            print(f'[ADD ] menu={menu_code} user_type={employee_user_type}')
            if not dry_run:
                if deleted:
                    _restore_soft_deleted(deleted)
                else:
                    db.session.add(MenuPermission(
                        menu_secure_code=menu.secure_code,
                        user_type=employee_user_type,
                    ))

        vuln_role_defaults = {
            code: roles for code, roles in MENU_ROLE_DEFAULTS.items()
            if code.startswith('vuln_lifecycle.')
        }
        if not vuln_role_defaults:
            print('[ERR ] MENU_ROLE_DEFAULTS 沒有 vuln_lifecycle.* 條目，'
                  '請先更新 backend/app/defaults/menu_defaults.py')
            return 1

        menus = MenuItem.query.filter(
            MenuItem.code.in_(vuln_role_defaults.keys()),
            MenuItem.is_deleted == False
        ).all()
        menu_by_code = {m.code: m for m in menus}

        orgs = Organization.query.filter(
            Organization.is_deleted == False
        ).order_by(Organization.id).all()
        print(f'[DONE] B 段 Key2：待處理企業數 {len(orgs)}')

        for org in orgs:
            for menu_code, role_codes in vuln_role_defaults.items():
                menu = menu_by_code.get(menu_code)
                if not menu:
                    print(f'[WARN] org={org.code} menu={menu_code} 找不到選單，略過')
                    continue
                for role_code in role_codes:
                    # roles.code 跨企業不唯一，一律用該企業自己的 role secure_code
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
                    key2_count += 1
                    print(f'[ADD ] org={org.code} menu={menu_code} role={role_code}')
                    if not dry_run:
                        if deleted:
                            _restore_soft_deleted(deleted)
                        else:
                            db.session.add(MenuRoleRequirement(
                                menu_secure_code=menu.secure_code,
                                role_secure_code=role.secure_code,
                                org_secure_code=org.secure_code,
                            ))

        if dry_run:
            db.session.rollback()
            print(f'[{MIGRATION_ID}] dry-run 結束：Key1 待補 {key1_count} 筆、'
                  f'Key2 待補 {key2_count} 筆（未寫入）')
        else:
            db.session.commit()
            print(f'[{MIGRATION_ID}] 完成：Key1 新增 {key1_count} 筆、'
                  f'Key2 新增 {key2_count} 筆')
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--run', action='store_true')
    parser.add_argument('-h', '--help', action='store_true')
    args = parser.parse_args()

    if args.help or (not args.dry_run and not args.run):
        _print_usage()
        return 0
    return run(dry_run=args.dry_run)


if __name__ == '__main__':
    sys.exit(main())
