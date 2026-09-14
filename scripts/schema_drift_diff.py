#!/usr/bin/env python3
"""
schema_drift_diff.py - 比對兩個 PostgreSQL 資料庫的 schema 差異

用途：PF-168 收斂機制的核心比對器。
比對「乾淨安裝庫（db.create_all 產出）」與「dev 庫」的：
  1. 表清單（public schema 的 BASE TABLE）
  2. 欄位（名稱、型別 udt_name、NOT NULL）
  3. fw_sp schema 存在性、fw_sp_owner 角色與 nspacl
  4. 僅警告、不列入失敗判定：索引、欄位 server default、fw_sp 函式清單
     （函式是白名單「資料」，migration 管理，dev 有 demo SP 屬正常，見 PF-205）

比對一律用 set 差集（不可用 comm，collation 排序不一致，見 CLAUDE.md）。

結束碼：0 = 無差異（索引警告不算）；1 = 有差異；2 = 執行錯誤。
"""
import argparse
import sys

try:
    import psycopg2
except ImportError:
    print("錯誤: 需要 psycopg2（venv/bin/python 執行）", file=sys.stderr)
    sys.exit(2)


def fetch_tables(cur):
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema='public' AND table_type='BASE TABLE'
    """)
    return {r[0] for r in cur.fetchall()}


def fetch_columns(cur):
    """回傳 {(table, column): (udt_name, is_nullable, column_default)}"""
    cur.execute("""
        SELECT table_name, column_name, udt_name, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema='public'
    """)
    return {(r[0], r[1]): (r[2], r[3], r[4]) for r in cur.fetchall()}


def fetch_indexes(cur):
    """回傳 {(table, indexname): normalized indexdef}"""
    cur.execute("""
        SELECT tablename, indexname, indexdef FROM pg_indexes
        WHERE schemaname='public'
    """)
    return {(r[0], r[1]): ' '.join(r[2].split()) for r in cur.fetchall()}


def fetch_fw_sp(cur):
    """回傳 (schema 存在, 函式名集合, nspacl 文字, fw_sp_owner 角色存在)"""
    cur.execute("SELECT nspacl::text FROM pg_namespace WHERE nspname='fw_sp'")
    row = cur.fetchone()
    exists = row is not None
    acl = row[0] if row else None
    funcs = set()
    if exists:
        cur.execute("""
            SELECT p.proname FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'fw_sp'
        """)
        funcs = {r[0] for r in cur.fetchall()}
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname='fw_sp_owner'")
    role_exists = cur.fetchone() is not None
    return exists, funcs, acl, role_exists


def main():
    parser = argparse.ArgumentParser(
        description='比對乾淨安裝庫與 dev 庫的 schema 差異（PF-168 守恆機制）')
    parser.add_argument('--fresh-dsn', required=True,
                        help='乾淨安裝庫 DSN（db.create_all 產出）')
    parser.add_argument('--dev-dsn', required=True, help='dev 庫 DSN')
    parser.add_argument('--show-indexes', action='store_true',
                        help='列出索引差異（僅警告，不影響結束碼）')
    parser.add_argument('--show-defaults', action='store_true',
                        help='列出欄位 server default 差異（僅警告，不影響結束碼）')
    args = parser.parse_args()

    try:
        fresh = psycopg2.connect(args.fresh_dsn)
        dev = psycopg2.connect(args.dev_dsn)
    except Exception as e:
        print(f"錯誤: 連線失敗: {e}", file=sys.stderr)
        sys.exit(2)

    fc, dc = fresh.cursor(), dev.cursor()
    failed = False

    # 1. 表清單
    ft, dt = fetch_tables(fc), fetch_tables(dc)
    only_dev = sorted(dt - ft)
    only_fresh = sorted(ft - dt)
    if only_dev:
        failed = True
        print(f"[表] dev 有、乾淨安裝沒有 ({len(only_dev)}):")
        for t in only_dev:
            print(f"  - {t}")
    if only_fresh:
        failed = True
        print(f"[表] 乾淨安裝有、dev 沒有 ({len(only_fresh)}):")
        for t in only_fresh:
            print(f"  - {t}")

    # 2. 欄位（只比兩邊都存在的表）
    common = ft & dt
    fcols = {k: v for k, v in fetch_columns(fc).items() if k[0] in common}
    dcols = {k: v for k, v in fetch_columns(dc).items() if k[0] in common}
    col_only_dev = sorted(set(dcols) - set(fcols))
    col_only_fresh = sorted(set(fcols) - set(dcols))
    if col_only_dev:
        failed = True
        print(f"[欄位] dev 有、乾淨安裝沒有 ({len(col_only_dev)}):")
        for t, c in col_only_dev:
            print(f"  - {t}.{c} ({dcols[(t, c)][0]})")
    if col_only_fresh:
        failed = True
        print(f"[欄位] 乾淨安裝有、dev 沒有 ({len(col_only_fresh)}):")
        for t, c in col_only_fresh:
            print(f"  - {t}.{c} ({fcols[(t, c)][0]})")

    type_diff = []
    default_diff = []
    for k in set(fcols) & set(dcols):
        f_type, f_null, f_def = fcols[k]
        d_type, d_null, d_def = dcols[k]
        if f_type != d_type or f_null != d_null:
            type_diff.append((k[0], k[1], d_type, d_null, f_type, f_null))
        if f_def != d_def:
            default_diff.append((k[0], k[1], d_def, f_def))
    if type_diff:
        failed = True
        print(f"[型別/NULL] 不一致 ({len(type_diff)}): (dev -> 乾淨安裝)")
        for t, c, d_type, d_null, f_type, f_null in sorted(type_diff):
            print(f"  - {t}.{c}: {d_type}"
                  f"{'' if d_null == 'YES' else ' NOT NULL'}"
                  f" -> {f_type}{'' if f_null == 'YES' else ' NOT NULL'}")

    # 3. fw_sp schema / ACL / 角色（函式清單是白名單資料，僅警告）
    f_sp, f_funcs, f_acl, f_role = fetch_fw_sp(fc)
    d_sp, d_funcs, d_acl, d_role = fetch_fw_sp(dc)
    if f_sp != d_sp:
        failed = True
        print(f"[fw_sp] schema 存在性不一致: dev={d_sp} 乾淨安裝={f_sp}")
    if f_sp and d_sp:
        sp_only_dev = sorted(d_funcs - f_funcs)
        sp_only_fresh = sorted(f_funcs - d_funcs)
        if sp_only_dev:
            print(f"[fw_sp 函式][警告] dev 有、乾淨安裝沒有: {sp_only_dev}")
        if sp_only_fresh:
            print(f"[fw_sp 函式][警告] 乾淨安裝有、dev 沒有: {sp_only_fresh}")
        if f_acl != d_acl:
            failed = True
            print(f"[fw_sp ACL] 不一致: dev={d_acl} 乾淨安裝={f_acl}")
    if not f_role or not d_role:
        failed = True
        print(f"[角色] fw_sp_owner 存在性: 檢查時={f_role and d_role}"
              f"（角色是 cluster 級，兩庫共用，False 即缺）")

    # 4. 欄位 server default（警告——dev 許多表由歷史 SQL migration 建立，
    #    帶 DEFAULT now() 之類；ORM 建的表用 Python 端 default，raw SQL INSERT
    #    的行為兩邊會不同，先讓差異可見）
    if default_diff:
        print(f"[server default][警告] 差異 {len(default_diff)} 筆，不列入失敗判定")
        if args.show_defaults:
            for t, c, d_def, f_def in sorted(default_diff):
                print(f"  - {t}.{c}: dev={d_def!r} fresh={f_def!r}")

    # 5. 索引（警告）
    fidx = {k: v for k, v in fetch_indexes(fc).items() if k[0] in common}
    didx = {k: v for k, v in fetch_indexes(dc).items() if k[0] in common}
    idx_only_dev = sorted(set(didx) - set(fidx))
    idx_only_fresh = sorted(set(fidx) - set(didx))
    idx_def_diff = sorted(k for k in set(fidx) & set(didx) if fidx[k] != didx[k])
    n_idx = len(idx_only_dev) + len(idx_only_fresh) + len(idx_def_diff)
    if n_idx:
        print(f"[索引][警告] 差異 {n_idx} 筆"
              f"（dev-only {len(idx_only_dev)} / 乾淨安裝-only {len(idx_only_fresh)}"
              f" / 定義不同 {len(idx_def_diff)}）不列入失敗判定")
        if args.show_indexes:
            for t, i in idx_only_dev:
                print(f"  [dev-only] {t}.{i}")
            for t, i in idx_only_fresh:
                print(f"  [fresh-only] {t}.{i}")
            for t, i in idx_def_diff:
                print(f"  [定義不同] {t}.{i}\n    dev:   {didx[(t, i)]}\n    fresh: {fidx[(t, i)]}")

    if failed:
        print("\n結果: 有差異（紅）")
        sys.exit(1)
    print(f"\n結果: 無差異（綠）。表 {len(common)} 張、欄位 {len(fcols)} 個一致；"
          f"索引警告 {n_idx} 筆")
    sys.exit(0)


if __name__ == '__main__':
    main()
