#!/usr/bin/env python3
"""
105 - 備份後移除 OpenDefense 遺留 od_intake_keys 表（冪等）

使用方式:
    cd /opt/BeakPlatform-dev
    venv/bin/python scripts/migrations/105_drop_od_intake_keys.py --dry-run
    venv/bin/python scripts/migrations/105_drop_od_intake_keys.py --apply
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from sqlalchemy import text

from app import create_app, db


MIGRATION_ID = '105_drop_od_intake_keys'
TARGET_TABLE = 'od_intake_keys'
BACKUP_DIR = '/opt/tmp/backup'


def _table_exists() -> bool:
    return bool(db.session.execute(text("""
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = :table_name
        LIMIT 1
    """), {'table_name': TARGET_TABLE}).scalar())


def _quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _sql_literal(value) -> str:
    if value is None:
        return 'NULL'
    if isinstance(value, bool):
        return 'TRUE' if value else 'FALSE'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, memoryview):
        return f"decode('{value.tobytes().hex()}', 'hex')"
    if isinstance(value, bytes):
        return f"decode('{value.hex()}', 'hex')"
    if isinstance(value, (dict, list)):
        encoded = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
        return "'" + encoded.replace("'", "''") + "'::jsonb"
    if isinstance(value, datetime):
        return "'" + value.isoformat(sep=' ') + "'::timestamp"
    if isinstance(value, date):
        return "'" + value.isoformat() + "'::date"
    return "'" + str(value).replace("'", "''") + "'"


def _backup_rows() -> tuple[str, int]:
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_path = os.path.join(BACKUP_DIR, f'{TARGET_TABLE}_{timestamp}.sql')
    os.makedirs(BACKUP_DIR, exist_ok=True)

    db.session.execute(text('SET LOCAL row_security = off'))
    rows = db.session.execute(text(f'SELECT * FROM {_quote_ident(TARGET_TABLE)} ORDER BY id')).fetchall()
    columns = list(rows[0]._mapping.keys()) if rows else [
        row.column_name for row in db.session.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
            ORDER BY ordinal_position
        """), {'table_name': TARGET_TABLE}).fetchall()
    ]

    column_sql = ', '.join(_quote_ident(col) for col in columns)
    with open(backup_path, 'w', encoding='utf-8') as fh:
        fh.write(f'-- Backup of public.{TARGET_TABLE}\n')
        fh.write(f'-- Created at {timestamp}\n')
        fh.write(f'-- Rows: {len(rows)}\n\n')
        for row in rows:
            mapping = row._mapping
            values_sql = ', '.join(_sql_literal(mapping[col]) for col in columns)
            fh.write(
                f'INSERT INTO {_quote_ident(TARGET_TABLE)} ({column_sql}) '
                f'VALUES ({values_sql});\n'
            )

    return backup_path, len(rows)


def run(dry_run: bool = True) -> int:
    app = create_app()
    with app.app_context():
        db.session.execute(text("SET LOCAL app.is_system_admin = 'true'"))

        print(f"[{MIGRATION_ID}] 模式: {'dry-run（未寫入）' if dry_run else 'apply（會寫入）'}")

        if not _table_exists():
            print(f"[SKIP] public.{TARGET_TABLE} 已不存在，視為已完成")
            db.session.rollback()
            return 0

        count = db.session.execute(text(f'SELECT count(*) FROM {_quote_ident(TARGET_TABLE)}')).scalar()
        print(f"[PLAN] 將備份 public.{TARGET_TABLE}: {count} 筆")
        print(f"[PLAN] 將 DROP TABLE public.{TARGET_TABLE}")

        if dry_run:
            db.session.rollback()
            print("[DRY ] 已 rollback，未寫入")
            return 0

        backup_path, backup_count = _backup_rows()
        print(f"[BACKUP] 已寫入 {backup_path} ({backup_count} 筆)")

        db.session.execute(text(f'DROP TABLE {_quote_ident(TARGET_TABLE)}'))
        db.session.commit()
        print(f"[DONE] 已 DROP TABLE public.{TARGET_TABLE}")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description='105: 備份後移除 OpenDefense 遺留 od_intake_keys 表',
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
