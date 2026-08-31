#!/usr/bin/env python3
"""
135 - 模組 ACL fail-closed 配套：為既有企業補種預設 ACL（冪等）

用途：
  PF-145 階段三之一將 ModuleAccessService.check_user_access() 從 fail-open
  （零筆 ACL = 不限制）改為 fail-closed（零筆 ACL = 拒絕，僅 ORG_ADMIN 經
  decorator 層放行）。沒有這個 migration，凡是「有有效合約、但從未設過
  module_access_control」的既有企業，其非管理員帳號會被 check_acl=True 的
  模組 API 全數擋下。

  本 migration 對所有非系統企業，依 ACTIVE 且效期內合約的 modules_config
  聯集，種入各模組宣告的 default_acl_roles（ROLE 型記錄）。
  規則與 ModuleAccessService.seed_org_module_acl 相同：
  該 (企業, 模組) 已有任何未刪除 ACL 記錄就整組跳過（不覆蓋企業自行設定）。

  系統企業（SYSTEM_ORG_CODE）刻意排除——它的 ACL 現況是刻意配置
  （見 CLAUDE.md PERM-04），且 ModuleRoleService 的種入機制同樣跳過它。

  新企業不靠本 migration：合約建立（OrganizationService.create_contract →
  ModuleRoleService.seed_contract_module_roles）與 `flask module sync`
  都會走同一套種入。

使用方式：
    cd /opt/BeakPlatform-dev
    ./venv/bin/python scripts/migrations/135_seed_module_acl_fail_closed.py --dry-run
    ./venv/bin/python scripts/migrations/135_seed_module_acl_fail_closed.py --run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

MIGRATION_ID = '135_seed_module_acl_fail_closed'

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent.parent
BACKEND_DIR = PROJECT_DIR / 'backend'
sys.path.insert(0, str(BACKEND_DIR))


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
    print('用途：模組 ACL 改 fail-closed 的配套。為所有非系統企業，')
    print('      依有效合約模組種入各模組宣告的 default_acl_roles。')
    print('      已有 ACL 記錄的 (企業, 模組) 一律不動。')
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
    from app.constants import SYSTEM_ORG_CODE
    from app.models.contract import Contract, ContractStatus
    from app.models.module_access_control import ModuleAccessControl
    from app.models.organization import Organization
    from app.module_loader import module_loader
    from app.services.module_access_service import ModuleAccessService

    app = create_app()
    with app.app_context():
        print(f"[{MIGRATION_ID}] 模式: {'dry-run（未寫入）' if dry_run else 'run（會寫入）'}")
        db.session.execute(text("SET LOCAL app.is_system_admin = 'true'"))

        # 有宣告 default_acl_roles 的已載入模組
        acl_modules = {
            m.name: m for m in module_loader.get_loaded_modules()
            if getattr(m, 'default_acl_roles', None) and m.enabled
        }
        if not acl_modules:
            print('[ERR ] 沒有任何已載入模組宣告 default_acl_roles，'
                  '確認是否在 SKIP_MODULE_SYNC 之外仍未載入模組')
            return 1
        print(f'[INFO] 宣告 default_acl_roles 的模組: '
              f'{ {k: v.default_acl_roles for k, v in acl_modules.items()} }')

        # org → ACTIVE 效期內合約的模組聯集（與 sync_all_module_roles 同邏輯）
        today = date.today()
        contracts = Contract.query.filter(
            Contract.status == ContractStatus.ACTIVE,
            Contract.start_date <= today,
            Contract.end_date >= today,
            Contract.is_deleted == False,
        ).all()
        org_modules: dict[str, set] = {}
        for contract in contracts:
            if not contract.modules_config:
                continue
            try:
                modules = json.loads(contract.modules_config)
            except (json.JSONDecodeError, TypeError):
                print(f'[WARN] 合約 {contract.secure_code} modules_config 非法，略過')
                continue
            if isinstance(modules, list):
                org_modules.setdefault(
                    contract.org_secure_code, set()).update(modules)

        orgs = Organization.query.filter(
            Organization.is_deleted == False,
            Organization.secure_code != SYSTEM_ORG_CODE,
        ).order_by(Organization.id).all()

        total_created = 0
        for org in orgs:
            modules = org_modules.get(org.secure_code) or set()
            for module_code in sorted(modules):
                module = acl_modules.get(module_code)
                if not module:
                    continue

                existing = ModuleAccessControl.query.filter(
                    ModuleAccessControl.org_secure_code == org.secure_code,
                    ModuleAccessControl.module_code == module_code,
                    ModuleAccessControl.is_deleted == False,
                ).count()
                if existing:
                    print(f'[SKIP] org={org.code} module={module_code} '
                          f'已有 {existing} 筆 ACL，不動')
                    continue

                result = ModuleAccessService.seed_org_module_acl(
                    org.secure_code, module)
                total_created += result['acl_created']
                print(f'[ADD ] org={org.code} module={module_code} '
                      f'roles={module.default_acl_roles} '
                      f'created={result["acl_created"]} '
                      f'skipped={result["acl_skipped"]}')

        if dry_run:
            db.session.rollback()
            print(f'[{MIGRATION_ID}] dry-run 結束：待補 {total_created} 筆（未寫入）')
        else:
            db.session.commit()
            print(f'[{MIGRATION_ID}] 完成：新增 {total_created} 筆')
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
