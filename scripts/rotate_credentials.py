#!/usr/bin/env python3
"""
SQL Sync — 企業 DB 密碼輪換工具

輪換 bfadmin_{id} / bfsync_{id} 密碼，降低憑證洩漏風險。
腳本內部檢查 last_credential_rotation 年齡，只輪換超過閾值的企業。

用法:
    cd /opt/BeakPlatform
    source venv/bin/activate
    set -a && source .env && set +a

    python scripts/rotate_credentials.py --dry-run          # 預覽
    python scripts/rotate_credentials.py                     # 執行（僅輪換超齡的）
    python scripts/rotate_credentials.py --force             # 強制輪換全部
    python scripts/rotate_credentials.py --max-age 60       # 自訂天數（預設 90）
    python scripts/rotate_credentials.py --org ORG_SC       # 指定企業
"""
import sys
import os
import argparse
import logging
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger('rotate_credentials')


def parse_args():
    parser = argparse.ArgumentParser(
        description='SQL Sync — 企業 DB 密碼輪換工具'
    )
    parser.add_argument('--org', dest='org_sc', help='指定企業 secure_code')
    parser.add_argument(
        '--dry-run', action='store_true',
        help='預覽模式，不實際輪換',
    )
    parser.add_argument(
        '--force', action='store_true',
        help='強制輪換全部（不檢查年齡）',
    )
    parser.add_argument(
        '--max-age', type=int, default=90,
        help='密碼最大使用天數（預設 90）',
    )
    return parser.parse_args()


def main():
    args = parse_args()

    from app import create_app, db
    app = create_app()

    with app.app_context():
        from modules.form_workflow.models.org_database import FwOrgDatabase
        from modules.form_workflow.services.sql_sync.org_db_manager import (
            rotate_credentials,
        )
        from modules.form_workflow.services.sql_sync.pool import invalidate_conn

        # 查詢所有就緒的企業 DB
        query = FwOrgDatabase.query.filter_by(is_ready=True, is_deleted=False)
        if args.org_sc:
            query = query.filter_by(org_secure_code=args.org_sc)

        org_dbs = query.all()
        if not org_dbs:
            logger.info('沒有找到就緒的企業 DB')
            return

        logger.info(f'找到 {len(org_dbs)} 個就緒的企業 DB')

        cutoff = datetime.utcnow() - timedelta(days=args.max_age)
        total_rotated = 0
        total_skipped = 0
        total_failed = 0

        for org_db in org_dbs:
            last_rotation = org_db.last_credential_rotation
            age_days = (
                (datetime.utcnow() - last_rotation).days
                if last_rotation else None
            )
            age_str = f'{age_days} 天前' if age_days is not None else '從未輪換'

            # 判斷是否需要輪換
            needs_rotation = args.force or last_rotation is None or last_rotation < cutoff

            if not needs_rotation:
                logger.info(
                    f'  {org_db.db_name} — 上次輪換: {age_str}，未到期，跳過'
                )
                total_skipped += 1
                continue

            if args.dry_run:
                logger.info(
                    f'  {org_db.db_name} — 上次輪換: {age_str}，需要輪換'
                )
                total_rotated += 1
                continue

            try:
                rotate_credentials(org_db)
                db.session.commit()

                # 清除同 process 的連線快取（不同 process 的 Worker 會自然重連）
                invalidate_conn(org_db.org_secure_code)

                total_rotated += 1
                logger.info(
                    f'  {org_db.db_name} — 已輪換（上次: {age_str}）'
                )
            except Exception as e:
                total_failed += 1
                logger.error(
                    f'  {org_db.db_name} — 輪換失敗: {e}',
                    exc_info=True,
                )
                db.session.rollback()

        logger.info('=' * 50)
        logger.info(f'輪換完成{"（預覽模式）" if args.dry_run else ""}')
        logger.info(f'  企業 DB 數量: {len(org_dbs)}')
        logger.info(f'  {"需" if args.dry_run else "已"}輪換:     {total_rotated}')
        logger.info(f'  跳過（未到期）: {total_skipped}')
        if total_failed:
            logger.info(f'  失敗:           {total_failed}')
        logger.info('=' * 50)


if __name__ == '__main__':
    main()
