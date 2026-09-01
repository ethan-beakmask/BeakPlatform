#!/usr/bin/env python3
"""
119 - 退役流程控制死節點並修正 execution_handler 路徑（冪等）

使用方式:
    cd /opt/BeakPlatform-dev
    venv/bin/python scripts/migrations/119_retire_flow_control_nodes.py --dry-run
    venv/bin/python scripts/migrations/119_retire_flow_control_nodes.py
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from sqlalchemy import text

from app import create_app, db


MIGRATION_FILENAME = '119_retire_flow_control_nodes.py'
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
RETIRED_NODE_TYPES = ('Converge', 'Switch', 'Condition', 'ParallelFork')
HANDLER_FIXES = {
    'OpFieldRead': 'modules.form_workflow.services.node_handlers.fieldread_handler.FieldReadHandler',
    'OpFieldWrite': 'modules.form_workflow.services.node_handlers.fieldwrite_handler.FieldWriteHandler',
    'EmailAdapter': 'modules.form_workflow.services.node_handlers.email_handler.EmailHandler',
    'SysTelegram': 'modules.form_workflow.services.node_handlers.telegram_handler.TelegramHandler',
}


def _load_env_defaults() -> None:
    env_path = os.path.join(PROJECT_ROOT, '.env')
    if not os.path.exists(env_path):
        return

    with open(env_path, encoding='utf-8') as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def run(dry_run: bool = False) -> int:
    _load_env_defaults()
    app = create_app()
    with app.app_context():
        db.session.execute(text("SET LOCAL app.is_system_admin = 'true'"))

        print(f"[119] 模式: {'dry-run（未寫入）' if dry_run else 'apply（會寫入）'}")

        retire_rows = db.session.execute(text("""
            SELECT node_type, is_active, is_deleted
            FROM workflow_node_definitions
            WHERE node_type = ANY(:node_types)
            ORDER BY node_type
        """), {'node_types': list(RETIRED_NODE_TYPES)}).fetchall()

        print("[BEFORE] 退役節點狀態：")
        for row in retire_rows:
            print(f"  {row.node_type}: active={row.is_active}, deleted={row.is_deleted}")

        retire_result = db.session.execute(text("""
            UPDATE workflow_node_definitions
            SET is_active = false,
                is_deleted = true,
                deleted_at = COALESCE(deleted_at, now()),
                updated_at = now()
            WHERE node_type = ANY(:node_types)
              AND is_deleted = false
        """), {'node_types': list(RETIRED_NODE_TYPES)})
        print(f"[UPDATE] 退役節點異動筆數={retire_result.rowcount}")

        fixed_count = 0
        for node_type, handler in HANDLER_FIXES.items():
            result = db.session.execute(text("""
                UPDATE workflow_node_definitions
                SET execution_handler = :handler,
                    updated_at = now()
                WHERE node_type = :node_type
                  AND execution_handler IS DISTINCT FROM :handler
            """), {'node_type': node_type, 'handler': handler})
            fixed_count += result.rowcount
            print(f"[FIX  ] {node_type} execution_handler -> {handler} ({result.rowcount})")

        if dry_run:
            db.session.rollback()
            print("[DRY ] 已 rollback，未寫入")
        else:
            db.session.execute(text("""
                INSERT INTO schema_migrations (filename)
                VALUES (:filename)
                ON CONFLICT (filename) DO NOTHING
            """), {'filename': MIGRATION_FILENAME})
            db.session.commit()
            print("[DONE] 已 commit")

        db.session.execute(text("SET LOCAL app.is_system_admin = 'true'"))
        verify_retired = db.session.execute(text("""
            SELECT node_type, is_active, is_deleted
            FROM workflow_node_definitions
            WHERE node_type = ANY(:node_types)
            ORDER BY node_type
        """), {'node_types': list(RETIRED_NODE_TYPES)}).fetchall()
        print("[VERIFY] 退役節點狀態：")
        for row in verify_retired:
            print(f"  {row.node_type}: active={row.is_active}, deleted={row.is_deleted}")

        verify_handlers = db.session.execute(text("""
            SELECT node_type, execution_handler
            FROM workflow_node_definitions
            WHERE node_type = ANY(:node_types)
            ORDER BY node_type
        """), {'node_types': list(HANDLER_FIXES.keys())}).fetchall()
        print("[VERIFY] execution_handler：")
        for row in verify_handlers:
            print(f"  {row.node_type}: {row.execution_handler}")

        print(f"[SUMMARY] 退役異動={retire_result.rowcount}, handler 修正={fixed_count}")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description='119: 退役流程控制死節點並修正 execution_handler 路徑',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--dry-run', action='store_true', help='預覽但不寫入')
    args = parser.parse_args()

    return run(dry_run=args.dry_run)


if __name__ == '__main__':
    sys.exit(main())
