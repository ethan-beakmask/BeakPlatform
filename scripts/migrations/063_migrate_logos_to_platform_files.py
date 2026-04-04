"""
063: 遷移舊 Logo 檔案到 platform_files

將 organizations.settings 中 logo_path 指向的檔案遷移為 platform_files 記錄，
並將實體檔案從 logos/{org_sc}.ext 改名為 uploads/{uuid}.ext (UUID 檔名)。
遷移後清除 org settings 中的 logo_path（改由 platform_files 管理）。

用法:
    python scripts/migrations/063_migrate_logos_to_platform_files.py          顯示說明
    python scripts/migrations/063_migrate_logos_to_platform_files.py --run    執行遷移
    python scripts/migrations/063_migrate_logos_to_platform_files.py --status 檢查狀態
"""
import argparse
import os
import shutil
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from app import create_app, db
from app.models import Organization
from app.models.platform_file import PlatformFile
from app.utils.security import generate_secure_code


MIGRATION_ID = '063_migrate_logos_to_platform_files'


def run_migration():
    app = create_app()
    with app.app_context():
        static_folder = app.static_folder
        upload_base = os.path.join(static_folder, 'uploads')
        os.makedirs(upload_base, exist_ok=True)

        orgs = Organization.query.filter_by(is_deleted=False).all()
        migrated = 0
        skipped = 0

        for org in orgs:
            logo_path = org.get_setting('logo_path')
            if not logo_path:
                continue

            full_path = os.path.join(static_folder, logo_path)
            if not os.path.exists(full_path):
                print(f"  [{org.domain_name}] 檔案不存在: {logo_path}，清除設定")
                org.set_setting('logo_path', None)
                skipped += 1
                continue

            # 檢查是否已遷移（platform_files 已有此企業的 org_logo）
            existing = PlatformFile.query.filter_by(
                org_secure_code=org.secure_code,
                context_type='org_logo',
                is_deleted=False,
            ).first()
            if existing:
                print(f"  [{org.domain_name}] 已有 platform_file 記錄，跳過")
                skipped += 1
                continue

            # 取得檔案資訊
            file_size = os.path.getsize(full_path)
            ext = logo_path.rsplit('.', 1)[1].lower() if '.' in logo_path else ''

            # 用 UUID 建立新檔名
            new_filename = f'{uuid.uuid4().hex}.{ext}' if ext else uuid.uuid4().hex
            new_relative_path = os.path.join('uploads', new_filename)
            new_full_path = os.path.join(static_folder, new_relative_path)

            # 複製檔案到新位置
            shutil.copy2(full_path, new_full_path)

            # MIME type 推斷
            mime_map = {
                'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
                'gif': 'image/gif', 'svg': 'image/svg+xml', 'webp': 'image/webp',
            }

            # 建立 platform_files 記錄
            record = PlatformFile(
                secure_code=generate_secure_code(),
                org_secure_code=org.secure_code,
                storage_type='local',
                storage_ref=new_relative_path,
                original_name=os.path.basename(logo_path),
                file_size=file_size,
                mime_type=mime_map.get(ext, 'application/octet-stream'),
                file_ext=ext,
                context_type='org_logo',
                uploader_sc=None,
                status='active',
            )
            db.session.add(record)

            # 清除舊設定
            org.set_setting('logo_path', None)

            # 刪除舊檔案
            os.remove(full_path)

            print(f"  [{org.domain_name}] 遷移成功: {logo_path} -> {new_relative_path} (sc={record.secure_code})")
            migrated += 1

        # 清理 logos 目錄中所有殘留檔案（無設定指向的孤兒檔案）
        logos_dir = os.path.join(static_folder, 'uploads', 'logos')
        orphans_removed = 0
        if os.path.exists(logos_dir):
            for f in os.listdir(logos_dir):
                fpath = os.path.join(logos_dir, f)
                if os.path.isfile(fpath):
                    os.remove(fpath)
                    orphans_removed += 1
            # 移除空目錄
            try:
                os.rmdir(logos_dir)
            except OSError:
                pass

        db.session.commit()
        print(f"\n[{MIGRATION_ID}] 完成: 遷移 {migrated} 筆, 跳過 {skipped} 筆, 清理孤兒 {orphans_removed} 個")


def show_status():
    app = create_app()
    with app.app_context():
        # 檢查 platform_files 中的 org_logo
        count = PlatformFile.query.filter_by(
            context_type='org_logo',
            is_deleted=False,
        ).count()
        print(f"[{MIGRATION_ID}] platform_files 中 org_logo 記錄: {count} 筆")

        # 檢查還有沒有 org settings 中殘留的 logo_path
        orgs = Organization.query.filter_by(is_deleted=False).all()
        legacy = 0
        for org in orgs:
            if org.get_setting('logo_path'):
                legacy += 1
                print(f"  未遷移: {org.domain_name} -> {org.get_setting('logo_path')}")
        if legacy == 0:
            print("  所有企業的 logo_path 設定已清除")

        # 檢查 logos 目錄
        logos_dir = os.path.join(app.static_folder, 'uploads', 'logos')
        if os.path.exists(logos_dir):
            files = os.listdir(logos_dir)
            print(f"  logos/ 目錄仍存在，內含 {len(files)} 個檔案")
        else:
            print("  logos/ 目錄已移除")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='063: 遷移舊 Logo 到 platform_files')
    parser.add_argument('--run', action='store_true', help='執行遷移')
    parser.add_argument('--status', action='store_true', help='檢查狀態')
    args = parser.parse_args()

    if args.run:
        run_migration()
    elif args.status:
        show_status()
    else:
        parser.print_help()
