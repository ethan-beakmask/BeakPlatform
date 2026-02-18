#!/usr/bin/env python3
"""
SQL Sync — 既有 Registry 補建 Approval 子表

為 Phase 2 建立的 FwSqlFormRegistry 補建 _approvals 子表。
已有 _approval_table metadata 的 registry 會自動跳過。

用法:
    cd /opt/BeakPlatform
    source venv/bin/activate
    set -a && source .env && set +a

    python scripts/upgrade_approval_tables.py --dry-run     # 預覽
    python scripts/upgrade_approval_tables.py               # 執行
    python scripts/upgrade_approval_tables.py --org ORG_SC  # 指定企業
"""
import sys
import os
import argparse
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger('upgrade_approval_tables')


def parse_args():
    parser = argparse.ArgumentParser(
        description='SQL Sync — 既有 Registry 補建 Approval 子表'
    )
    parser.add_argument('--org', dest='org_sc', help='指定企業 secure_code')
    parser.add_argument(
        '--dry-run', action='store_true',
        help='預覽模式，不實際建表',
    )
    return parser.parse_args()


def main():
    args = parse_args()

    from app import create_app
    app = create_app()

    with app.app_context():
        from modules.form_workflow.models.sql_form_registry import FwSqlFormRegistry
        from modules.form_workflow.services.sql_sync.table_manager import (
            upgrade_registry_approval_table,
        )

        # 查詢所有 active registry
        query = FwSqlFormRegistry.query.filter_by(status='active')
        if args.org_sc:
            query = query.filter_by(org_secure_code=args.org_sc)

        registries = query.all()
        if not registries:
            logger.info('沒有找到 active 的 SQL Sync registry')
            return

        logger.info(f'找到 {len(registries)} 個 active registry')

        total_upgraded = 0
        total_skipped = 0

        for reg in registries:
            column_mapping = reg.column_mapping or {}
            if '_approval_table' in column_mapping:
                logger.info(
                    f'  {reg.table_name} — 已有 approval 表，跳過'
                )
                total_skipped += 1
                continue

            if args.dry_run:
                logger.info(
                    f'  {reg.table_name} — 需要補建 approval 表'
                )
                total_upgraded += 1
                continue

            try:
                result = upgrade_registry_approval_table(reg)
                if result:
                    total_upgraded += 1
                    logger.info(
                        f'  {reg.table_name} — 已補建 {result}'
                    )
                else:
                    total_skipped += 1
            except Exception as e:
                logger.error(
                    f'  {reg.table_name} — 補建失敗: {e}',
                    exc_info=True,
                )

        logger.info('=' * 50)
        logger.info(f'升級完成{"（預覽模式）" if args.dry_run else ""}')
        logger.info(f'  Registry 數量: {len(registries)}')
        logger.info(f'  {"需" if args.dry_run else "已"}升級:     {total_upgraded}')
        logger.info(f'  跳過:           {total_skipped}')
        logger.info('=' * 50)


if __name__ == '__main__':
    main()
