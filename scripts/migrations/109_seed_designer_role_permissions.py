#!/usr/bin/env python3
"""
109 - 回填設計者角色的表單流程權限（冪等）

用途：
  修正既有企業因 organization_service 早期 role key 錯誤，導致
  FORM_DESIGNER / FLOW_DESIGNER 未取得出廠預設權限的問題。

使用方式：
    cd /opt/BeakPlatform-dev
    ./venv/bin/python scripts/migrations/109_seed_designer_role_permissions.py --dry-run
    ./venv/bin/python scripts/migrations/109_seed_designer_role_permissions.py --run
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

MIGRATION_ID = '109_seed_designer_role_permissions'

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent.parent
BACKEND_DIR = PROJECT_DIR / 'backend'
sys.path.insert(0, str(BACKEND_DIR))

ROLE_PERM_MAP = {
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
}


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
    print('用途：回填既有企業 FORM_DESIGNER / FLOW_DESIGNER 缺少的表單流程權限。')
    print('用法：')
    print('  ./venv/bin/python scripts/migrations/109_seed_designer_role_permissions.py --dry-run')
    print('  ./venv/bin/python scripts/migrations/109_seed_designer_role_permissions.py --run')


def run(dry_run: bool) -> int:
    _load_env_file()
    if not os.environ.get('DATABASE_URL'):
        print(f'[{MIGRATION_ID}] [ERR] DATABASE_URL 未設定，且 .env 未提供，無法連線')
        return 1

    from app import create_app, db
    from app.models import Organization, Permission, Role, RolePermission

    app = create_app()
    with app.app_context():
        print(f"[{MIGRATION_ID}] 模式: {'dry-run（未寫入）' if dry_run else 'run（會寫入）'}")

        all_perm_codes = sorted({code for codes in ROLE_PERM_MAP.values() for code in codes})
        permissions = Permission.query.filter(
            Permission.code.in_(all_perm_codes),
            Permission.is_deleted == False,
            Permission.is_active == True
        ).all()
        perm_by_code = {p.code: p for p in permissions}

        orgs = Organization.query.filter(
            Organization.is_deleted == False
        ).order_by(Organization.id).all()
        print(f'[CHECK] 待處理企業數: {len(orgs)}')

        created_count = 0
        for org in orgs:
            org_created = 0
            for role_code, perm_codes in ROLE_PERM_MAP.items():
                role = Role.query.filter_by(
                    org_secure_code=org.secure_code,
                    code=role_code,
                    is_deleted=False
                ).first()
                if not role:
                    print(f'[WARN] org={org.code} 找不到角色 {role_code}，略過')
                    continue

                for perm_code in perm_codes:
                    perm = perm_by_code.get(perm_code)
                    if not perm:
                        print(f'[WARN] org={org.code} 找不到權限定義 {perm_code}，略過')
                        continue

                    existing = RolePermission.query.filter_by(
                        role_secure_code=role.secure_code,
                        permission_secure_code=perm.secure_code,
                        is_deleted=False
                    ).first()
                    if existing:
                        continue

                    org_created += 1
                    created_count += 1
                    print(f'[ADD ] org={org.code} role={role_code} permission={perm_code}')
                    if not dry_run:
                        db.session.add(RolePermission(
                            role_secure_code=role.secure_code,
                            permission_secure_code=perm.secure_code,
                            is_active=True,
                        ))

            print(f'[DONE] org={org.code} 待新增 {org_created} 筆 role_permissions')

        if dry_run:
            db.session.rollback()
            print('[DRY ] 已 rollback，未寫入')
        else:
            db.session.commit()
            print('[DONE] 已 commit')

        print(f'新增 {created_count} 筆 role_permissions')
        return 0


def main() -> int:
    if len(sys.argv) == 1:
        _print_usage()
        return 0

    parser = argparse.ArgumentParser(
        description='回填設計者角色的表單流程權限',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true', help='只列出待新增項目，不寫入')
    mode.add_argument('--run', action='store_true', help='執行寫入')
    args = parser.parse_args()
    return run(dry_run=args.dry_run)


if __name__ == '__main__':
    sys.exit(main())
