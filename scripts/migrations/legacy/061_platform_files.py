"""
061: 建立 platform_files 表

統一管理平台所有檔案（公開資源 + 加密檔案），
取代原本散落在 static/uploads/ 的直接存取模式。

用法:
    python scripts/migrations/061_platform_files.py          顯示說明
    python scripts/migrations/061_platform_files.py --run    執行遷移
    python scripts/migrations/061_platform_files.py --status 檢查狀態
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from app import create_app, db
from sqlalchemy import text


MIGRATION_ID = '061_platform_files'


def check_status():
    """檢查表是否已存在"""
    result = db.session.execute(text("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'platform_files'
    """))
    return result.fetchone() is not None


def run_migration():
    app = create_app()
    with app.app_context():
        if check_status():
            print(f"[{MIGRATION_ID}] platform_files 表已存在，跳過")
            return True

        print(f"[{MIGRATION_ID}] 建立 platform_files 表...")

        db.session.execute(text("""
            CREATE TABLE platform_files (
                id              SERIAL PRIMARY KEY,
                secure_code     VARCHAR(32) UNIQUE NOT NULL,
                org_secure_code VARCHAR(32) NOT NULL,

                -- 儲存資訊
                storage_type    VARCHAR(16) NOT NULL,
                storage_ref     VARCHAR(255) NOT NULL,

                -- 檔案 metadata
                original_name   VARCHAR(255) NOT NULL,
                file_size       BIGINT NOT NULL DEFAULT 0,
                mime_type       VARCHAR(100),
                file_ext        VARCHAR(10),

                -- 用途 context
                context_type    VARCHAR(50) NOT NULL,
                context_id      VARCHAR(32),

                -- 上傳者
                uploader_sc     VARCHAR(32),

                -- 狀態與時間
                status          VARCHAR(20) NOT NULL DEFAULT 'active',
                is_deleted      BOOLEAN NOT NULL DEFAULT FALSE,
                created_at      TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
                updated_at      TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
                deleted_at      TIMESTAMP,

                CONSTRAINT fk_pf_org
                    FOREIGN KEY (org_secure_code) REFERENCES organizations(secure_code)
            )
        """))

        # 索引
        db.session.execute(text("""
            CREATE INDEX idx_pf_secure_code ON platform_files(secure_code)
        """))
        db.session.execute(text("""
            CREATE INDEX idx_pf_org ON platform_files(org_secure_code) WHERE NOT is_deleted
        """))
        db.session.execute(text("""
            CREATE INDEX idx_pf_context ON platform_files(context_type, context_id) WHERE NOT is_deleted
        """))
        db.session.execute(text("""
            CREATE INDEX idx_pf_storage ON platform_files(storage_type, storage_ref)
        """))

        db.session.commit()
        print(f"[{MIGRATION_ID}] 完成")
        return True


def show_status():
    app = create_app()
    with app.app_context():
        exists = check_status()
        if exists:
            result = db.session.execute(text("""
                SELECT count(*) FROM platform_files
            """))
            count = result.scalar()
            print(f"[{MIGRATION_ID}] platform_files 表已存在，{count} 筆記錄")
        else:
            print(f"[{MIGRATION_ID}] platform_files 表尚未建立")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='061: 建立 platform_files 表')
    parser.add_argument('--run', action='store_true', help='執行遷移')
    parser.add_argument('--status', action='store_true', help='檢查狀態')
    args = parser.parse_args()

    if args.run:
        run_migration()
    elif args.status:
        show_status()
    else:
        parser.print_help()
