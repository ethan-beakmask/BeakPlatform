#!/usr/bin/env python3
"""
113 - 表單中心選單 Key2 補 EXTERNAL_USERS（冪等）

用途：
  表單中心（form_workflow.center）對 EXTERNAL 是刻意開放的
  （Key1 含 EXTERNAL、`@module_access_required('form_workflow', False)` 只驗合約），
  但 Key2 的出廠預設 MENU_ROLE_DEFAULTS 只有 ['ORG_ADMIN', 'EMPLOYEE']，
  漏了 EXTERNAL_USERS。

  後果：早期企業（BELUGA/LION/SYSTEM）的 DB 有人補過所以正常，
  而依出廠預設新建的企業（TEST00 之後）其 EXTERNAL 帳號會在 PageRoleGuard
  Key2 被擋下 → 302 強制登出，廠商進不了表單中心，且不會有任何錯誤訊息。

  本 migration 對所有企業補上 form_workflow.center → EXTERNAL_USERS。
  出廠預設同步改在 backend/app/defaults/menu_defaults.py，
  只跑 migration 不改出廠值的話，新建企業會長回舊的樣子（MENU-01）。

  發現於 PF-145 施工3（查 form_workflow.center 的 Key1/Key2 現況時）。

使用方式：
    cd /opt/BeakPlatform-dev
    ./venv/bin/python scripts/migrations/113_form_center_menu_external_users.py --dry-run
    ./venv/bin/python scripts/migrations/113_form_center_menu_external_users.py --run
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

MIGRATION_ID = '113_form_center_menu_external_users'

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent.parent
BACKEND_DIR = PROJECT_DIR / 'backend'
sys.path.insert(0, str(BACKEND_DIR))

MENU_CODE = 'form_workflow.center'
ROLE_CODE = 'EXTERNAL_USERS'


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
    print('用途：對所有企業補上表單中心選單的 Key2 角色 EXTERNAL_USERS，')
    print('      讓新建企業的廠商帳號也能進入表單中心。')
    print('用法：')
    print(f'  ./venv/bin/python scripts/migrations/{MIGRATION_ID}.py --dry-run')
    print(f'  ./venv/bin/python scripts/migrations/{MIGRATION_ID}.py --run')


def run(dry_run: bool) -> int:
    _load_env_file()
    if not os.environ.get('DATABASE_URL'):
        print(f'[{MIGRATION_ID}] [ERR] DATABASE_URL 未設定，且 .env 未提供，無法連線')
        return 1

    from sqlalchemy import text

    from app import create_app, db
    from app.defaults.menu_defaults import MENU_ROLE_DEFAULTS
    from app.models import MenuItem, MenuRoleRequirement, Organization, Role

    app = create_app()
    with app.app_context():
        print(f"[{MIGRATION_ID}] 模式: {'dry-run（未寫入）' if dry_run else 'run（會寫入）'}")
        db.session.execute(text("SET LOCAL app.is_system_admin = 'true'"))

        if ROLE_CODE not in MENU_ROLE_DEFAULTS.get(MENU_CODE, []):
            print(f'[ERR ] MENU_ROLE_DEFAULTS[{MENU_CODE}] 不含 {ROLE_CODE}，'
                  '請先更新 backend/app/defaults/menu_defaults.py（MENU-01：'
                  'DB 與出廠預設要一起改）')
            return 1

        menu = MenuItem.query.filter(
            MenuItem.code == MENU_CODE,
            MenuItem.is_deleted == False
        ).order_by(MenuItem.id).first()
        if not menu:
            print(f'[ERR ] 找不到選單 {MENU_CODE}')
            return 1

        added = 0
        orgs = Organization.query.filter(
            Organization.is_deleted == False
        ).order_by(Organization.id).all()
        print(f'[DONE] 待處理企業數 {len(orgs)}')

        for org in orgs:
            # roles.code 跨企業不唯一，一律用該企業自己的 role secure_code
            role = Role.query.filter_by(
                org_secure_code=org.secure_code,
                code=ROLE_CODE,
                is_deleted=False
            ).first()
            if not role:
                print(f'[WARN] org={org.code} 找不到角色 {ROLE_CODE}，略過')
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
            added += 1
            print(f'[ADD ] org={org.code} menu={MENU_CODE} role={ROLE_CODE}')
            if not dry_run:
                if deleted:
                    deleted.is_deleted = False
                    deleted.deleted_at = None
                else:
                    db.session.add(MenuRoleRequirement(
                        menu_secure_code=menu.secure_code,
                        role_secure_code=role.secure_code,
                        org_secure_code=org.secure_code,
                    ))

        if dry_run:
            db.session.rollback()
            print(f'[{MIGRATION_ID}] dry-run 結束：待補 {added} 筆（未寫入）')
        else:
            db.session.commit()
            print(f'[{MIGRATION_ID}] 完成：新增 {added} 筆')
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
