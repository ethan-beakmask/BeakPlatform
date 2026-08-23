#!/usr/bin/env python3
"""
112 - 回填既有企業的管理員帳號編號（ADM001 起，冪等）

用途：
  兩帳號制（PERMISSION_MODEL.md §5.1）下，企業管理員帳號原本不發 employee_id，
  導致選人清單等處遇到同名的成員／管理員帳號時沒有可用的區隔依據（PF-145）。

  111 之後新建企業已會自動發號（organization_service._assign_admin_employee_id），
  本 migration 補既有企業：
  1. 企業若沒有 default_for='ORG_ADMIN' 的編號規則，就建一條
     （沿用出廠格式：ADM + 3 位序號）
  2. 依 id 順序給該企業每個 employee_id 為空的 ORG_ADMIN 帳號取號

  只處理 ORG_ADMIN。SYSTEM_ADMIN 是平台級身分、不屬於任何企業的人事編制，
  而且新企業流程也不發給它，這裡保持一致。

  停用中的帳號一樣發號——編號是識別碼不是授權，日後啟用就直接有號可用。

使用方式：
    cd /opt/BeakPlatform-dev
    ./venv/bin/python scripts/migrations/112_backfill_org_admin_employee_id.py --dry-run
    ./venv/bin/python scripts/migrations/112_backfill_org_admin_employee_id.py --run
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

MIGRATION_ID = '112_backfill_org_admin_employee_id'

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
    print('用途：回填既有企業的管理員帳號編號（ADM001 起）。')
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
    from app.models import Organization, User
    from app.models.user import UserType
    from app.models.user_numbering_rule import (
        NumberingDefaultFor, NumberingElementType, NumberingUsageScope,
        UserNumberingRule,
    )
    from app.services.numbering_service import NumberingService

    app = create_app()
    with app.app_context():
        print(f"[{MIGRATION_ID}] 模式: {'dry-run（未寫入）' if dry_run else 'run（會寫入）'}")
        db.session.execute(text("SET LOCAL app.is_system_admin = 'true'"))

        rule_created = 0
        numbered = 0

        orgs = Organization.query.filter(
            Organization.is_deleted == False
        ).order_by(Organization.id).all()

        for org in orgs:
            admins = User.query.filter(
                User.org_secure_code == org.secure_code,
                User.user_type == UserType.ORG_ADMIN,
                User.is_deleted == False,
            ).order_by(User.id).all()
            pending = [u for u in admins if not (u.employee_id or '').strip()]
            if not pending:
                continue

            rule = NumberingService.get_default_rule(
                org.secure_code, NumberingDefaultFor.ORG_ADMIN)
            if not rule:
                rule_created += 1
                print(f'[ADD ] org={org.code} 建立「預設企業管理員編號」規則（ADM + 3 位序號）')
                rule = UserNumberingRule(
                    org_secure_code=org.secure_code,
                    name='預設企業管理員編號',
                    description='ADM + 3 位序號',
                    elements={
                        'components': [
                            {'type': NumberingElementType.PREFIX, 'order': 1,
                             'values': ['ADM']},
                            {'type': NumberingElementType.SEQUENCE, 'order': 2,
                             'start': 1, 'digits': 3, 'reset_period': 'never'},
                        ],
                        'total_length': 0,
                    },
                    usage_scope=NumberingUsageScope.INTERNAL_ONLY,
                    default_for=NumberingDefaultFor.ORG_ADMIN,
                    is_active=True,
                )
                db.session.add(rule)
                db.session.flush()

            for user in pending:
                try:
                    number = NumberingService.get_next_number(rule, consume=not dry_run)
                except ValueError as exc:
                    print(f'[WARN] org={org.code} user={user.username} 取號失敗: {exc}')
                    continue
                numbered += 1
                print(f'[SET ] org={org.code} user={user.username} employee_id={number}')
                if not dry_run:
                    user.employee_id = number

        if dry_run:
            db.session.rollback()
            print(f'[{MIGRATION_ID}] dry-run 結束：待建規則 {rule_created} 條、'
                  f'待發號 {numbered} 個帳號（未寫入）')
            print('       註：dry-run 不消耗計數器，同一企業有多個帳號時會重複顯示同一個號；'
                  '實際執行時會依序遞增（ADM001, ADM002, ...）')
        else:
            db.session.commit()
            print(f'[{MIGRATION_ID}] 完成：新建規則 {rule_created} 條、'
                  f'發號 {numbered} 個帳號')
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
