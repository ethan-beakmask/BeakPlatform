#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""維運用 node展覽館補種 CLI。"""
from __future__ import annotations

import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
BACKEND_DIR = os.path.join(REPO_ROOT, 'backend')
sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, REPO_ROOT)


USAGE = """用法：
  venv/bin/python scripts/seed_node_showcase.py --dry-run --password <password>
  venv/bin/python scripts/seed_node_showcase.py --apply --password <password>
  venv/bin/python scripts/seed_node_showcase.py --apply --only B8 --only waf_failover

說明：
  不帶參數時只顯示本說明並以 exit 1 結束。
  --password 可省略，省略時讀 ADMIN_INITIAL_PASSWORD；兩者都沒有就拒絕執行。
"""


def parse_args(argv):
    if not argv:
        print(USAGE)
        sys.exit(1)
    parser = argparse.ArgumentParser(
        description='補種系統預設企業 node展覽館示範表單與流程',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=USAGE,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--dry-run', action='store_true', help='只列出會做什麼，不寫入（預設）')
    group.add_argument('--apply', action='store_true', help='實際寫入資料庫')
    parser.add_argument('--only', action='append', default=[],
                        help='只跑指定項目，可重複；可填完整名稱或尾端名稱，例如 B8 sqlexecutor / sqlexecutor')
    parser.add_argument('--password', help='B0 示範帳號初始密碼；省略時讀 ADMIN_INITIAL_PASSWORD')
    parser.add_argument('--node', action='append', default=[],
                        help='waf_failover 目標節點，可重複。格式：「顯示名稱=節點識別」')
    return parser.parse_args(argv)


def parse_node(raw):
    if '=' not in raw:
        raise ValueError('--node 格式必須是「顯示名稱=節點識別」')
    label, value = raw.split('=', 1)
    label = label.strip()
    value = value.strip()
    if not label or not value:
        raise ValueError('--node 的顯示名稱與節點識別都不可空白')
    return label, value


def main():
    args = parse_args(sys.argv[1:])
    password = args.password or os.environ.get('ADMIN_INITIAL_PASSWORD', '').strip()
    if not password:
        print('錯誤：--password 或 ADMIN_INITIAL_PASSWORD 必填', file=sys.stderr)
        return 1
    try:
        node_options = [parse_node(raw) for raw in args.node]
    except ValueError as exc:
        print(f'錯誤：{exc}', file=sys.stderr)
        return 1

    from app import create_app, db
    from app.models import Organization
    from scripts.examples.node_showcase import seed_node_showcase

    app = create_app('development')
    with app.app_context():
        org = Organization.query.filter_by(code='SYSTEM', is_deleted=False).first()
        if not org:
            print('錯誤：找不到系統企業 SYSTEM', file=sys.stderr)
            return 1

        result = seed_node_showcase(
            org,
            apply=args.apply,
            password=password,
            only=args.only,
            node=node_options,
        )
        if args.apply:
            if result['failed']:
                db.session.rollback()
            else:
                db.session.commit()
        else:
            db.session.rollback()

    print(f"分類：{result['category_secure_code']}")
    for name, _item in result['done']:
        print(f'DONE   {name}')
    for name, err in result['failed']:
        print(f'FAILED {name}: {err}')
    print(f"總結：done={len(result['done'])} failed={len(result['failed'])}")
    return 1 if result['failed'] else 0


if __name__ == '__main__':
    sys.exit(main())

