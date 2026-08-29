#!/usr/bin/env python3
"""
118: dev 環境一次性清理（PF-169）

【這支 migration 只服務這台開發機，外部使用者的乾淨安裝不需要它】

三批東西都是這台機器長期試誤的殘留，成因不在產品邏輯：

  一、實體檔案已不存在的 platform_files 記錄
      舊格式路徑 <org_sc>/<uuid>.enc（還沒有月份子目錄那層），
      實體檔案在某次歷史清理中被移除、DB 記錄留著。
      使用者點下載一定失敗。判定是動態的（逐筆檢查檔案存不存在），
      不寫死 secure_code。

  二、系統企業（system.local）底下的表單業務資料
      系統企業是平台級身分，不該有表單實例。這批是 2026-02~04 的
      TEST-* / FORM-* / SYS-* 試誤產物。

  三、六張死表
      workflow_node_categories / timeout_trackers / fw_sql_form_layouts
        -- 有資料但全庫沒有任何 Python 程式引用
      dc_shared_menus       -- PF-29 改用共用元件後停用
      fw_data_employee / fw_demo_inventory -- 測試業務表

      這六張在 db.create_all() 的乾淨安裝裡本來就不存在（它們沒有 ORM
      model，是 migration 建的），所以「刪掉本來就不該存在的表」對新安裝
      是 no-op。這也是 PF-168 schema diff 的一部分成因。

冪等：三批都先查再刪，重複執行不會出錯。
用法：--dry-run 只印不改。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'backend'))

from app import create_app, db  # noqa: E402
from app.services import file_service  # noqa: E402

DEAD_TABLES = [
    'fw_data_employee',
    'fw_demo_inventory',
    'fw_sql_form_layouts',
    'dc_shared_menus',
    'workflow_node_categories',
    'timeout_trackers',
]

# 系統企業的表單業務資料，依 FK 由子到父
SYSTEM_ORG_FORM_TABLES = [
    ('fw_node_execution_logs', 'org_secure_code'),
    ('fw_node_execution_queue', 'org_secure_code'),
    ('fw_workflow_variables', 'org_secure_code'),
    ('fw_approval_records', 'org_secure_code'),
    ('fw_form_field_changes', 'org_secure_code'),
    ('fw_workflow_instances', 'org_secure_code'),
    ('fw_form_instances', 'org_secure_code'),
]

SYSTEM_ORG_SC = 'system.local'


def _resolve_path(storage_type, storage_ref):
    if storage_type == 'encrypted':
        return os.path.join(file_service.ENCRYPTED_STORAGE_DIR, storage_ref)
    ref = storage_ref[len('uploads/'):] if storage_ref.startswith('uploads/') else storage_ref
    return os.path.join(file_service.UPLOAD_BASE_DIR, ref)


def purge_dangling_file_records(dry_run):
    rows = db.session.execute(db.text(
        "SELECT secure_code, storage_type, storage_ref, file_size, original_name "
        "FROM platform_files ORDER BY id"
    )).fetchall()

    missing = [r for r in rows if not os.path.exists(_resolve_path(r[1], r[2]))]
    total_mb = sum(r[3] for r in missing) / 1048576

    print(f'[一] platform_files 共 {len(rows)} 筆，實體不存在 {len(missing)} 筆'
          f'（帳面 {total_mb:.1f} MB）')
    if not missing:
        return 0
    for r in missing[:5]:
        print(f'      {r[4][:40]}  ref={r[2]}')
    if len(missing) > 5:
        print(f'      ...（其餘 {len(missing) - 5} 筆）')

    if dry_run:
        return 0

    codes = [r[0] for r in missing]
    res = db.session.execute(
        db.text("DELETE FROM platform_files WHERE secure_code IN :codes")
        .bindparams(db.bindparam('codes', expanding=True)),
        {'codes': codes},
    )
    print(f'      已刪除 {res.rowcount} 筆記錄（實體檔案本來就不在，無檔案可刪）')
    return res.rowcount


def purge_system_org_form_data(dry_run):
    print(f'[二] 系統企業（{SYSTEM_ORG_SC}）的表單業務資料')
    total = 0
    for table, col in SYSTEM_ORG_FORM_TABLES:
        exists = db.session.execute(db.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :t"
        ), {'t': table}).fetchone()
        if not exists:
            continue
        cnt = db.session.execute(
            db.text(f"SELECT count(*) FROM {table} WHERE {col} = :org"),
            {'org': SYSTEM_ORG_SC},
        ).scalar()
        if not cnt:
            continue
        print(f'      {table}: {cnt} 筆')
        if not dry_run:
            res = db.session.execute(
                db.text(f"DELETE FROM {table} WHERE {col} = :org"),
                {'org': SYSTEM_ORG_SC},
            )
            total += res.rowcount
    if dry_run:
        print('      [dry-run] 未刪除')
    else:
        print(f'      合計刪除 {total} 筆')
    return total


def drop_dead_tables(dry_run):
    print('[三] 死表')
    dropped = 0
    for table in DEAD_TABLES:
        exists = db.session.execute(db.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :t"
        ), {'t': table}).fetchone()
        if not exists:
            print(f'      {table}: 不存在，略過')
            continue
        cnt = db.session.execute(db.text(f'SELECT count(*) FROM {table}')).scalar()
        print(f'      {table}: {cnt} 筆' + ('（dry-run 不刪）' if dry_run else ' -> DROP'))
        if not dry_run:
            db.session.execute(db.text(f'DROP TABLE {table} CASCADE'))
            dropped += 1
    return dropped


def main():
    dry_run = '--dry-run' in sys.argv
    app = create_app()
    with app.app_context():
        db.session.execute(db.text("SET LOCAL app.is_system_admin = 'true'"))

        purge_dangling_file_records(dry_run)
        print()
        purge_system_org_form_data(dry_run)
        print()
        drop_dead_tables(dry_run)

        if dry_run:
            db.session.rollback()
            print('\n[dry-run] 已回滾，未變更任何資料')
            return

        db.session.execute(db.text(
            "INSERT INTO schema_migrations (filename) VALUES (:f) ON CONFLICT DO NOTHING"
        ), {'f': os.path.basename(__file__)})
        db.session.commit()
        print('\n完成')


if __name__ == '__main__':
    main()
