#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BeakPlatform - 軟刪除資料實體清除工具

把全庫 is_deleted = true 的記錄真正 DELETE 掉。

用途：
  1. 清掉開發過程累積的軟刪除干擾資料
  2. 出廠資料包的前置作業 -- 「有資料的 DB」與「空白 DB」做 diff 之前，
     必須先把軟刪除垃圾清掉，否則 diff 會夾帶大量無意義的墓碑記錄

作法：
  自動掃出所有含 is_deleted 欄位的表，用「反覆迭代刪除直到無進展」處理外鍵
  相依（含 menu_items / roles / users 這類自我參照的表），全程在單一 transaction
  內執行，任一步失敗即整批 rollback。

用法：
  python3 scripts/purge_soft_deleted.py                # 預設 dry-run，只報告不寫入
  python3 scripts/purge_soft_deleted.py --apply        # 實際刪除
  python3 scripts/purge_soft_deleted.py --apply --skip users,roles
  python3 scripts/purge_soft_deleted.py --orphan-check # 額外報告邏輯孤兒（不刪）

  DATABASE_URL 未提供時，從專案 .env 解析。
"""

import argparse
import os
import re
import sys
from urllib.parse import urlparse, unquote

try:
    import psycopg2
except ImportError:
    sys.exit('需要 psycopg2，請用專案 venv 執行：venv/bin/python scripts/purge_soft_deleted.py')

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 邏輯孤兒檢查：(子表, 子表欄位, 父表, 父表欄位)
# 這些是用 secure_code 邏輯關聯、沒有 DB 外鍵的模組表，刪父表後子表會變孤兒。
ORPHAN_CHECKS = [
    ('fw_approval_records', 'form_instance_secure_code', 'fw_form_instances', 'secure_code'),
    ('fw_workflow_instances', 'form_instance_secure_code', 'fw_form_instances', 'secure_code'),
    ('fw_node_execution_queue', 'workflow_instance_secure_code', 'fw_workflow_instances', 'secure_code'),
    ('fw_node_execution_logs', 'workflow_instance_id', 'fw_workflow_instances', 'id'),
    ('od_intake_events', 'case_secure_code', 'fw_workflow_instances', 'secure_code'),
    ('dc_site_map_nodes', 'sub_system_secure_code', 'dc_sub_systems', 'secure_code'),
    ('dc_sub_system_pages', 'sub_system_secure_code', 'dc_sub_systems', 'secure_code'),
    ('dc_site_map_nodes', 'page_layout_secure_code', 'dc_page_layouts', 'secure_code'),
]


def resolve_db_url():
    url = os.environ.get('DATABASE_URL')
    if url:
        return url
    env_path = os.path.join(REPO_ROOT, '.env')
    if os.path.exists(env_path):
        with open(env_path, encoding='utf-8') as fh:
            for line in fh:
                m = re.match(r'\s*DATABASE_URL\s*=\s*(.+?)\s*$', line)
                if m:
                    return m.group(1).strip().strip('"').strip("'")
    sys.exit('找不到 DATABASE_URL（環境變數與 .env 都沒有）')


def connect(url):
    p = urlparse(url)
    return psycopg2.connect(
        host=p.hostname or 'localhost',
        port=p.port or 5432,
        dbname=(p.path or '/').lstrip('/'),
        user=unquote(p.username or ''),
        password=unquote(p.password or ''),
    )


def find_soft_delete_tables(cur):
    cur.execute("""
        SELECT c.table_name
        FROM information_schema.columns c
        JOIN information_schema.tables t
          ON t.table_name = c.table_name AND t.table_schema = c.table_schema
        WHERE c.column_name = 'is_deleted'
          AND c.table_schema = 'public'
          AND t.table_type = 'BASE TABLE'
        ORDER BY c.table_name
    """)
    return [r[0] for r in cur.fetchall()]


def count_pending(cur, tables):
    counts = {}
    for t in tables:
        cur.execute(f'SELECT count(*) FROM "{t}" WHERE is_deleted = true')
        n = cur.fetchone()[0]
        if n:
            counts[t] = n
    return counts


def report_orphans(cur, label):
    print(f'\n=== 邏輯孤兒檢查（{label}）===')
    print('（子表活著、但指向的父表記錄不存在或已軟刪 -- 沒有 DB 外鍵保護的關聯）')
    any_found = False
    for child, ccol, parent, pcol in ORPHAN_CHECKS:
        try:
            cur.execute(f"""
                SELECT count(*) FROM "{child}" c
                WHERE c.is_deleted = false
                  AND c."{ccol}" IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM "{parent}" p
                    WHERE p."{pcol}" = c."{ccol}" AND p.is_deleted = false
                  )
            """)
            n = cur.fetchone()[0]
        except psycopg2.Error as e:
            cur.connection.rollback()
            print(f'  {child}.{ccol} -> {parent}: 查詢失敗（{str(e).splitlines()[0]}）')
            continue
        if n:
            any_found = True
            print(f'  {child}.{ccol} -> {parent}: {n} 筆孤兒')
    if not any_found:
        print('  （無）')



def purge_dangling_refs(cur, dry_run=True):
    """
    清掉「本身活著、但外鍵指向 is_deleted 父記錄」的子表行。

    這種行指向一個已被刪除的對象（例如指向已刪除使用者的角色指派），
    本身就是無效資料，也是 purge 主流程被外鍵擋下的原因。

    關聯關係一律從 pg_constraint 推導，不寫死表名欄名。
    """
    cur.execute("""
        SELECT conrelid::regclass::text  AS child,
               confrelid::regclass::text AS parent,
               pg_get_constraintdef(oid) AS def
        FROM pg_constraint
        WHERE contype = 'f'
          AND confrelid::regclass::text IN (
            SELECT c.table_name FROM information_schema.columns c
            JOIN information_schema.tables t
              ON t.table_name = c.table_name AND t.table_schema = c.table_schema
            WHERE c.column_name = 'is_deleted' AND c.table_schema = 'public'
              AND t.table_type = 'BASE TABLE')
    """)
    rows = cur.fetchall()
    found = {}
    for child, parent, cdef in rows:
        m = re.match(r'FOREIGN KEY \((.+?)\) REFERENCES .+?\((.+?)\)', cdef)
        if not m:
            continue
        ccol, pcol = m.group(1).strip('" '), m.group(2).strip('" ')
        if ',' in ccol or child == parent:
            continue  # 略過複合鍵與自我參照（自我參照由迭代刪除自然解決）
        cur.execute('SAVEPOINT sp_dang')
        try:
            sql = (f'DELETE FROM "{child}" c WHERE c.is_deleted = false '
                   f'AND c."{ccol}" IS NOT NULL AND EXISTS ('
                   f'SELECT 1 FROM "{parent}" p WHERE p."{pcol}" = c."{ccol}" '
                   f'AND p.is_deleted = true)')
            if dry_run:
                sql = sql.replace(f'DELETE FROM "{child}" c WHERE',
                                  f'SELECT count(*) FROM "{child}" c WHERE', 1)
                cur.execute(sql)
                n = cur.fetchone()[0]
            else:
                cur.execute(sql)
                n = cur.rowcount
            cur.execute('RELEASE SAVEPOINT sp_dang')
            if n:
                key = f'{child}.{ccol} -> {parent}'
                found[key] = found.get(key, 0) + n
        except psycopg2.Error:
            cur.execute('ROLLBACK TO SAVEPOINT sp_dang')
            cur.execute('RELEASE SAVEPOINT sp_dang')
    return found


def purge(cur, tables, skip):
    """反覆迭代刪除，直到某一輪完全沒有進展。回傳 (已刪統計, 卡住的表)"""
    deleted = {}
    remaining = {t: None for t in tables if t not in skip}
    rnd = 0
    while remaining:
        rnd += 1
        progressed = False
        blocked = {}
        for t in list(remaining):
            cur.execute('SAVEPOINT sp_purge')
            try:
                cur.execute(f'DELETE FROM "{t}" WHERE is_deleted = true')
                n = cur.rowcount
                cur.execute('RELEASE SAVEPOINT sp_purge')
                if n:
                    deleted[t] = deleted.get(t, 0) + n
                    progressed = True
                del remaining[t]
            except psycopg2.Error as e:
                cur.execute('ROLLBACK TO SAVEPOINT sp_purge')
                cur.execute('RELEASE SAVEPOINT sp_purge')
                blocked[t] = str(e).splitlines()[0]
        print(f'  第 {rnd} 輪：刪除 {len(deleted)} 表累計 {sum(deleted.values())} 筆，'
              f'剩 {len(remaining)} 表待處理')
        if not progressed:
            return deleted, blocked
    return deleted, {}


def main():
    ap = argparse.ArgumentParser(
        description='把全庫 is_deleted = true 的記錄真正刪除',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='預設是 dry-run，要真的寫入必須加 --apply。')
    ap.add_argument('--apply', action='store_true',
                    help='實際執行刪除（不加此參數只做 dry-run 報告）')
    ap.add_argument('--skip', default='',
                    help='跳過的表名，逗號分隔（例如 users,roles）')
    ap.add_argument('--purge-dangling-refs', action='store_true',
                    help='一併清掉「本身活著、但外鍵指向已軟刪記錄」的子表行'
                         '（例如指向已刪除使用者的角色指派）')
    ap.add_argument('--orphan-check', action='store_true',
                    help='額外報告邏輯孤兒（沒有 DB 外鍵保護的跨表關聯）')
    ap.add_argument('--db', default=None,
                    help='資料庫連線字串（預設取 DATABASE_URL 或專案 .env）')
    args = ap.parse_args()

    skip = {s.strip() for s in args.skip.split(',') if s.strip()}
    url = args.db or resolve_db_url()
    conn = connect(url)
    conn.autocommit = False
    cur = conn.cursor()

    dbname = urlparse(url).path.lstrip('/')
    mode = '實際執行 (--apply)' if args.apply else 'DRY-RUN（不寫入）'
    print(f'資料庫: {dbname}')
    print(f'模式  : {mode}')
    if skip:
        print(f'跳過  : {", ".join(sorted(skip))}')

    tables = find_soft_delete_tables(cur)
    before = count_pending(cur, tables)
    total_before = sum(before.values())
    print(f'\n=== 清除前：{len(tables)} 張表含 is_deleted 欄位，'
          f'其中 {len(before)} 張有軟刪除資料，共 {total_before} 筆 ===')
    for t, n in sorted(before.items(), key=lambda x: -x[1]):
        mark = '  [skip]' if t in skip else ''
        print(f'  {t:38s} {n:6d}{mark}')

    if args.orphan_check:
        report_orphans(cur, '清除前')

    if total_before == 0:
        print('\n沒有軟刪除資料，結束。')
        conn.rollback()
        return 0

    if args.purge_dangling_refs:
        print('\n=== 清理指向軟刪記錄的無效引用 ===')
        dang = purge_dangling_refs(cur, dry_run=not args.apply)
        if dang:
            for k, n in sorted(dang.items(), key=lambda x: -x[1]):
                print(f'  {k}: {n} 筆')
        else:
            print('  （無）')

    print('\n=== 執行刪除 ===')
    deleted, blocked = purge(cur, list(before), skip)

    print(f'\n=== 結果：刪除 {sum(deleted.values())} 筆 ===')
    for t, n in sorted(deleted.items(), key=lambda x: -x[1]):
        print(f'  {t:38s} {n:6d}')

    if blocked:
        print(f'\n=== 卡住（外鍵擋下）{len(blocked)} 張表 ===')
        for t, err in blocked.items():
            print(f'  {t}: {err}')

    if args.orphan_check:
        report_orphans(cur, '清除後')

    if args.apply and not blocked:
        conn.commit()
        print('\n已 COMMIT。')
    elif args.apply and blocked:
        conn.rollback()
        print('\n有表被外鍵擋下，整批 ROLLBACK（沒有任何變更寫入）。')
        print('請先處理引用方，或用 --skip 排除該表後重跑。')
        return 1
    else:
        conn.rollback()
        print('\nDRY-RUN，已 ROLLBACK。確認無誤後加 --apply 重跑。')

    cur.close()
    conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
