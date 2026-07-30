#!/usr/bin/env python3
"""
既有子系統 portal_data.db 業務表補 portal_user_ref 欄位（089 migration 的 SQLite 部分）

背景：
    portal 業務表原本沒有任何欄位記錄「這列是誰建的」，導致列級擁有權無法實作
    （任何被允許編輯的訪客拿到 row id 就能改別人的列）。089 之後新建的表由
    `create_portal_data_table` 端點自動注入 portal_user_ref，既有表要靠本腳本補。

行為：
    掃描每個子系統的 portal_data.db，對所有使用者表（排除 sqlite_ 內部表與
    portal_ 前綴的系統表）檢查有無 portal_user_ref，缺的就 ADD COLUMN。
    已存在的表跳過，可重複執行（冪等）。

    舊列的 portal_user_ref 為 NULL = 無主，在 row_owner_scope='own' 的視圖下
    誰都看不到（這是刻意的 fail-closed 設計，2026-07-30 用戶裁決）。
"""
import argparse
import os
import sqlite3
import sys

DEFAULT_DATA_DIR = '/opt/BeakPlatform-dev/data/nocode_portals'
OWNER_COLUMN = 'portal_user_ref'


def iter_business_tables(conn):
    """回傳該 DB 的業務表名稱（排除 sqlite 內部表與 portal_ 系統表）"""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'portal_%'"
    ).fetchall()
    return [r[0] for r in rows]


def table_has_owner_column(conn, table_name):
    rows = conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    return any(r[1] == OWNER_COLUMN for r in rows)


def process_db(db_path, apply_changes):
    """處理單一 portal_data.db，回傳 (已補欄位的表, 已存在而跳過的表)"""
    added, skipped = [], []
    conn = sqlite3.connect(db_path)
    try:
        for table_name in iter_business_tables(conn):
            if table_has_owner_column(conn, table_name):
                skipped.append(table_name)
                continue
            if apply_changes:
                conn.execute(
                    f'ALTER TABLE "{table_name}" ADD COLUMN {OWNER_COLUMN} TEXT'
                )
            added.append(table_name)
        if apply_changes and added:
            conn.commit()
    finally:
        conn.close()
    return added, skipped


def main():
    parser = argparse.ArgumentParser(
        description='既有子系統 portal_data.db 業務表補 portal_user_ref 欄位',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '範例：\n'
            '  先看會改什麼（不寫入）：\n'
            '    ./add_portal_user_ref.py --dry-run\n'
            '  實際補欄位：\n'
            '    ./add_portal_user_ref.py --apply\n'
        ),
    )
    parser.add_argument(
        '--data-dir',
        default=DEFAULT_DATA_DIR,
        help=f'子系統資料目錄（預設 {DEFAULT_DATA_DIR}）',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='只列出會補欄位的表，不實際寫入',
    )
    parser.add_argument(
        '--apply',
        action='store_true',
        help='實際執行 ALTER TABLE（與 --dry-run 二者必須指定其一）',
    )

    if len(sys.argv) == 1:
        parser.print_help()
        return 0

    args = parser.parse_args()
    if args.dry_run == args.apply:
        print('錯誤：--dry-run 與 --apply 必須指定其中一個（且不可同時指定）')
        return 2

    if not os.path.isdir(args.data_dir):
        print(f'錯誤：資料目錄不存在 {args.data_dir}')
        return 2

    total_added = 0
    total_skipped = 0
    for sub_sc in sorted(os.listdir(args.data_dir)):
        db_path = os.path.join(args.data_dir, sub_sc, 'portal_data.db')
        if not os.path.isfile(db_path):
            continue
        added, skipped = process_db(db_path, args.apply)
        total_added += len(added)
        total_skipped += len(skipped)
        if added:
            action = '已補' if args.apply else '待補'
            print(f'{sub_sc}: {action} {", ".join(added)}')

    mode = '實際寫入' if args.apply else '試跑（未寫入）'
    print(f'--- 完成（{mode}）：處理 {total_added} 張表，'
          f'已有欄位而跳過 {total_skipped} 張')
    return 0


if __name__ == '__main__':
    sys.exit(main())
