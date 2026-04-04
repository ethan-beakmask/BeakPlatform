"""
064: 遷移舊背景圖到 platform_files

將 fw_workflow_backgrounds 中 platform_file_sc=NULL 的記錄遷移：
1. 在 platform_files 建立對應記錄
2. 將背景圖從 backgrounds/ 子目錄移到 uploads/ 根目錄
3. 更新 fw_workflow_backgrounds.platform_file_sc

用法:
    python scripts/migrations/064_migrate_backgrounds_to_platform_files.py          顯示說明
    python scripts/migrations/064_migrate_backgrounds_to_platform_files.py --run    執行遷移
    python scripts/migrations/064_migrate_backgrounds_to_platform_files.py --status 檢查狀態
"""
import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from app import create_app, db
from app.models.platform_file import PlatformFile
from app.utils.security import generate_secure_code

MIGRATION_ID = '064_migrate_backgrounds_to_platform_files'

# uploads 目錄（在 static/ 之外）
UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'backend', 'uploads'
)


def run_migration():
    app = create_app()
    with app.app_context():
        from modules.form_workflow.models import FwWorkflowBackground

        backgrounds = FwWorkflowBackground.query.filter_by(
            is_deleted=False,
            platform_file_sc=None,
        ).all()

        if not backgrounds:
            print(f"[{MIGRATION_ID}] 沒有需要遷移的背景圖")
            return True

        bg_dir = os.path.join(UPLOAD_DIR, 'backgrounds')
        migrated = 0
        skipped = 0

        for bg in backgrounds:
            old_path = os.path.join(bg_dir, bg.filename)
            if not os.path.exists(old_path):
                print(f"  [{bg.secure_code}] 檔案不存在: {bg.filename}，跳過")
                skipped += 1
                continue

            file_size = os.path.getsize(old_path)

            # 移到 uploads/ 根目錄（檔名已是 UUID，不需改名）
            new_path = os.path.join(UPLOAD_DIR, bg.filename)
            shutil.move(old_path, new_path)

            # 建立 platform_files 記錄
            sc = generate_secure_code()
            record = PlatformFile(
                secure_code=sc,
                org_secure_code=bg.org_secure_code,
                storage_type='local',
                storage_ref=bg.filename,
                original_name=bg.original_filename or bg.filename,
                file_size=file_size,
                mime_type=bg.mimetype or 'image/png',
                file_ext=bg.filename.rsplit('.', 1)[1] if '.' in bg.filename else '',
                context_type='wf_background',
                context_id=bg.secure_code,
                status='active',
            )
            db.session.add(record)

            # 更新背景圖記錄
            bg.platform_file_sc = sc
            bg.filepath = bg.filename

            print(f"  [{bg.secure_code}] 遷移成功: backgrounds/{bg.filename} -> {bg.filename} (pf_sc={sc})")
            migrated += 1

        # 清理空的 backgrounds 子目錄
        if os.path.exists(bg_dir):
            remaining = os.listdir(bg_dir)
            if not remaining:
                os.rmdir(bg_dir)
                print(f"  backgrounds/ 子目錄已移除")
            else:
                print(f"  backgrounds/ 子目錄仍有 {len(remaining)} 個檔案")

        db.session.commit()
        print(f"\n[{MIGRATION_ID}] 完成: 遷移 {migrated} 筆, 跳過 {skipped} 筆")
        return True


def show_status():
    app = create_app()
    with app.app_context():
        from modules.form_workflow.models import FwWorkflowBackground

        total = FwWorkflowBackground.query.filter_by(is_deleted=False).count()
        unmigrated = FwWorkflowBackground.query.filter_by(
            is_deleted=False, platform_file_sc=None).count()

        pf_count = PlatformFile.query.filter_by(
            context_type='wf_background', is_deleted=False).count()

        print(f"[{MIGRATION_ID}] 背景圖: {total} 筆, 未遷移: {unmigrated} 筆, platform_files: {pf_count} 筆")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='064: 遷移舊背景圖到 platform_files')
    parser.add_argument('--run', action='store_true', help='執行遷移')
    parser.add_argument('--status', action='store_true', help='檢查狀態')
    args = parser.parse_args()

    if args.run:
        run_migration()
    elif args.status:
        show_status()
    else:
        parser.print_help()
