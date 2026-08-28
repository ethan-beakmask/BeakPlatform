#!/usr/bin/env python3
"""
116 - 補既有企業的 API Key 申請單鏈路（冪等）

用途：
  讓 116 以前已存在的企業也具備出廠預設的「API Key 申請單」：
  1. 表單模板 API_KEY_REQUEST
  2. 流程模板 API_KEY_REQUEST_FLOW
  3. 表單流程配對並發行
  4. 三筆配對填寫權限

使用方式：
    cd /opt/BeakPlatform-dev
    ./venv/bin/python scripts/migrations/116_seed_api_key_request_flow_existing_orgs.py --dry-run
    ./venv/bin/python scripts/migrations/116_seed_api_key_request_flow_existing_orgs.py --run
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

MIGRATION_ID = '116_seed_api_key_request_flow_existing_orgs'

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
    print('用途：補既有企業的 API Key 申請單鏈路。')
    print('用法：')
    print(f'  ./venv/bin/python scripts/migrations/{MIGRATION_ID}.py --dry-run')
    print(f'  ./venv/bin/python scripts/migrations/{MIGRATION_ID}.py --run')


def _pending_items(state: dict) -> list[str]:
    pending = []
    if not state.get('org_admin_role_secure_code'):
        pending.append('缺少 ORG_ADMIN 角色')
    if not state['form']['exists']:
        pending.append('表單模板')
    if (not state['workflow']['exists']
            or not state['workflow']['has_graph']
            or not state['workflow']['has_cytoscape']):
        pending.append('流程模板')
    if not state['mapping']['exists']:
        pending.append('表單流程配對')
    if not state['published']['exists']:
        pending.append('發行版本')

    existing_permissions = {
        (
            item['grant_type'], item['grant_target'],
            item['grant_target_name'], item['include_children'],
        )
        for item in state['permissions']
    }
    from app.defaults.api_key_request_defaults import MAPPING_PERMISSION_SPECS
    for grant_type, grant_target, grant_target_name, include_children in MAPPING_PERMISSION_SPECS:
        if (grant_type, grant_target, grant_target_name, include_children) not in existing_permissions:
            pending.append(f'填寫權限 {grant_type}:{grant_target}')
    return pending


def run(dry_run: bool) -> int:
    _load_env_file()
    if not os.environ.get('DATABASE_URL'):
        print(f'[{MIGRATION_ID}] [ERR] DATABASE_URL 未設定，且 .env 未提供，無法連線')
        return 1

    from sqlalchemy import text

    from app import create_app, db
    from app.defaults.api_key_request_defaults import (
        describe_org_state, seed_org_api_key_request_flow,
    )
    from app.models import Organization

    app = create_app()
    with app.app_context():
        print(f"[{MIGRATION_ID}] 模式: {'dry-run（未寫入）' if dry_run else 'run（會寫入）'}")
        db.session.execute(text("SET LOCAL app.is_system_admin = 'true'"))

        processed = 0
        created = 0
        existing = 0
        skipped_or_failed = 0

        orgs = Organization.query.filter(
            Organization.is_deleted == False
        ).order_by(Organization.id).all()

        for org in orgs:
            processed += 1
            state = describe_org_state(org.secure_code)
            pending = _pending_items(state)
            org_label = f'org={org.code} secure_code={org.secure_code}'

            if dry_run:
                if state.get('complete'):
                    existing += 1
                    print(f'[SKIP] {org_label} 已存在完整鏈路')
                elif not state.get('org_admin_role_secure_code'):
                    skipped_or_failed += 1
                    print(f'[WARN] {org_label} 缺少 ORG_ADMIN 角色，會跳過')
                else:
                    created += 1
                    print(f'[ADD ] {org_label} 會建立/補齊：{", ".join(pending)}')
                continue

            try:
                result = seed_org_api_key_request_flow(org.secure_code)
                if result.get('ok') and not result.get('skipped'):
                    db.session.commit()
                    if pending:
                        created += 1
                        print(f'[SET ] {org_label} 已建立/補齊 API Key 申請單鏈路')
                    else:
                        existing += 1
                        print(f'[SKIP] {org_label} 已存在完整鏈路')
                else:
                    db.session.rollback()
                    skipped_or_failed += 1
                    reason = result.get('reason')
                    error = result.get('error')
                    suffix = f'：{error}' if error else ''
                    print(f'[WARN] {org_label} 跳過/失敗 reason={reason}{suffix}')
            except Exception as exc:
                db.session.rollback()
                skipped_or_failed += 1
                print(f'[WARN] {org_label} 跳過/失敗 reason=error：{exc}')
                continue

        if dry_run:
            db.session.rollback()
            print(f'[{MIGRATION_ID}] dry-run 結束：處理 {processed} 家、'
                  f'待新建/補齊 {created} 家、已存在 {existing} 家、跳過/失敗 {skipped_or_failed} 家')
        else:
            print(f'[{MIGRATION_ID}] 完成：處理 {processed} 家、'
                  f'新建/補齊 {created} 家、已存在 {existing} 家、跳過/失敗 {skipped_or_failed} 家')
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
