#!/usr/bin/env python3
"""
SQL Sync — 舊資料回補工具

將已終態（APPROVED/REJECTED/CANCELLED/ERROR）且有 active registry 的
form instances 批次寫入 fw_sync_queue，由 Worker 處理。

用法:
    cd /opt/BeakPlatform
    source venv/bin/activate
    set -a && source .env && set +a

    python scripts/backfill_sync.py --dry-run          # 預覽，不入列
    python scripts/backfill_sync.py                     # 全部回補
    python scripts/backfill_sync.py --org ORG_SC        # 指定企業
    python scripts/backfill_sync.py --mapping MAP_SC    # 指定配對
    python scripts/backfill_sync.py --batch-size 200    # 自訂批次大小
"""
import sys
import os
import argparse
import logging

# 設定路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger('backfill_sync')

# 終態列表
TERMINAL_STATUSES = ('APPROVED', 'REJECTED', 'CANCELLED', 'ERROR')


def parse_args():
    parser = argparse.ArgumentParser(description='SQL Sync 舊資料回補工具')
    parser.add_argument('--org', dest='org_sc', help='指定企業 secure_code')
    parser.add_argument('--mapping', dest='mapping_sc', help='指定配對 secure_code')
    parser.add_argument('--dry-run', action='store_true', help='預覽模式，不實際入列')
    parser.add_argument('--batch-size', type=int, default=100, help='每批入列筆數 (預設 100)')
    return parser.parse_args()


def main():
    args = parse_args()

    from app import create_app, db
    app = create_app()

    with app.app_context():
        from modules.form_workflow.models.sql_form_registry import FwSqlFormRegistry
        from modules.form_workflow.models.form_instance import FwFormInstance
        from modules.form_workflow.models.sync_queue import FwSyncQueue

        # 1. 查詢所有 active registry
        query = FwSqlFormRegistry.query.filter_by(status='active')
        if args.org_sc:
            query = query.filter_by(org_secure_code=args.org_sc)
        if args.mapping_sc:
            query = query.filter_by(mapping_secure_code=args.mapping_sc)

        registries = query.all()
        if not registries:
            logger.info('沒有找到 active 的 SQL Sync registry')
            return

        logger.info(f'找到 {len(registries)} 個 active registry')

        total_found = 0
        total_enqueued = 0
        total_skipped = 0

        for reg in registries:
            logger.info(
                f'處理 registry: {reg.table_name} '
                f'(published_sc={reg.published_secure_code})'
            )

            # 2. 查詢對應的終態 form instances
            instances = FwFormInstance.query.filter(
                FwFormInstance.published_secure_code == reg.published_secure_code,
                FwFormInstance.org_secure_code == reg.org_secure_code,
                FwFormInstance.status.in_(TERMINAL_STATUSES),
                FwFormInstance.is_deleted == False,
            ).all()

            if not instances:
                logger.info(f'  → 沒有終態的 form instances，跳過')
                continue

            total_found += len(instances)

            # 3. 排除已在 queue 中且已完成的
            existing_completed = set()
            completed_items = FwSyncQueue.query.filter(
                FwSyncQueue.registry_id == reg.id,
                FwSyncQueue.status == 'completed',
                FwSyncQueue.is_deleted == False,
            ).with_entities(FwSyncQueue.form_instance_secure_code).all()
            existing_completed = {item[0] for item in completed_items}

            # 也排除正在等待處理的 (pending/processing)
            pending_items = FwSyncQueue.query.filter(
                FwSyncQueue.registry_id == reg.id,
                FwSyncQueue.status.in_(('pending', 'processing')),
                FwSyncQueue.is_deleted == False,
            ).with_entities(FwSyncQueue.form_instance_secure_code).all()
            existing_pending = {item[0] for item in pending_items}

            to_enqueue = []
            for inst in instances:
                if inst.secure_code in existing_completed:
                    total_skipped += 1
                    continue
                if inst.secure_code in existing_pending:
                    total_skipped += 1
                    continue
                to_enqueue.append(inst)

            if not to_enqueue:
                logger.info(f'  → {len(instances)} 筆全部已同步或待處理，跳過')
                continue

            logger.info(
                f'  → 找到 {len(instances)} 筆終態，'
                f'{len(instances) - len(to_enqueue)} 筆已處理，'
                f'{len(to_enqueue)} 筆需回補'
            )

            if args.dry_run:
                total_enqueued += len(to_enqueue)
                continue

            # 4. 批次入列
            batch_count = 0
            for i in range(0, len(to_enqueue), args.batch_size):
                batch = to_enqueue[i:i + args.batch_size]
                for inst in batch:
                    item = FwSyncQueue(
                        org_secure_code=inst.org_secure_code,
                        form_instance_secure_code=inst.secure_code,
                        published_secure_code=reg.published_secure_code,
                        registry_id=reg.id,
                        action='upsert',
                    )
                    db.session.add(item)
                db.session.flush()
                batch_count += len(batch)
                logger.info(f'  → 已入列 {batch_count}/{len(to_enqueue)}')

            db.session.commit()
            total_enqueued += len(to_enqueue)

        # 5. 結果摘要
        logger.info('=' * 50)
        logger.info(f'回補完成{"（預覽模式）" if args.dry_run else ""}')
        logger.info(f'  Registry 數量: {len(registries)}')
        logger.info(f'  終態 instances: {total_found}')
        logger.info(f'  已同步/跳過:    {total_skipped}')
        logger.info(f'  {"需" if args.dry_run else "已"}入列:     {total_enqueued}')
        logger.info('=' * 50)


if __name__ == '__main__':
    main()
