#!/usr/bin/env python3
"""
104 - 軟刪 OpenDefense 遺留事件接收金鑰選單（冪等）

使用方式:
    cd /opt/BeakPlatform-dev
    venv/bin/python scripts/migrations/104_retire_od_intake_keys_menu.py --dry-run
    venv/bin/python scripts/migrations/104_retire_od_intake_keys_menu.py --apply
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from sqlalchemy import text

from app import create_app, db
from app.models import MenuItem


MIGRATION_ID = '104_retire_od_intake_keys_menu'
TARGET_CODE = 'open_defense.intake_keys'


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def run(dry_run: bool = True) -> int:
    app = create_app()
    with app.app_context():
        db.session.execute(text("SET LOCAL app.is_system_admin = 'true'"))

        print(f"[{MIGRATION_ID}] 模式: {'dry-run（未寫入）' if dry_run else 'apply（會寫入）'}")

        rows = MenuItem.query.filter(
            MenuItem.code == TARGET_CODE,
            MenuItem.is_deleted == False,  # noqa: E712
        ).order_by(MenuItem.org_secure_code, MenuItem.id).all()

        if not rows:
            print(f"[SKIP] 找不到未刪除選單: code={TARGET_CODE}")
        for item in rows:
            print(
                "[DEL ] menu_items 軟刪: "
                f"org={item.org_secure_code} code={item.code} sc={item.secure_code}"
            )
            if not dry_run:
                item.is_deleted = True
                item.deleted_at = _now()
                item.updated_at = _now()

        if dry_run:
            db.session.rollback()
            print("[DRY ] 已 rollback，未寫入")
        else:
            db.session.commit()
            print("[DONE] 已 commit")

        print(f"[SUMMARY] 影響筆數={len(rows)}")

        db.session.execute(text("SET LOCAL app.is_system_admin = 'true'"))
        verify_rows = db.session.execute(text("""
            SELECT org_secure_code, code, is_deleted
            FROM menu_items
            WHERE code = :code
            ORDER BY org_secure_code, id
        """), {'code': TARGET_CODE}).fetchall()
        print("[VERIFY] open_defense.intake_keys 選單狀態：")
        for row in verify_rows:
            print(
                "  "
                f"org={row.org_secure_code}, code={row.code}, deleted={row.is_deleted}"
            )
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description='104: 軟刪 OpenDefense 遺留事件接收金鑰選單',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--apply', action='store_true', help='實際執行並 commit')
    parser.add_argument('--dry-run', action='store_true', help='預覽但不寫入')
    args = parser.parse_args()

    if args.apply and args.dry_run:
        parser.error('--apply 與 --dry-run 只能擇一')

    return run(dry_run=not args.apply)


if __name__ == '__main__':
    sys.exit(main())
