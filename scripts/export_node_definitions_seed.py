#!/usr/bin/env python3
"""
export_node_definitions_seed.py - 從 dev 庫匯出節點型別定義的安裝 seed SQL

背景（PF-168）：workflow_node_definitions 是 single source of truth（FRONT-03），
dev 的資料由歷代 migration 種出來；migration 制度廢止後，全新安裝的種子改由
本工具產出的 scripts/sql/seed_workflow_node_definitions.sql 提供，
由 scripts/init_database.sh 在建立初始資料後執行。

**新增或修改節點型別定義後必須重跑本工具**，否則全新安裝的設計器
不會出現新節點（且不報錯）。

用法：
  set -a && source .env && set +a
  venv/bin/python scripts/export_node_definitions_seed.py

只匯出 is_deleted=false 的定義（退役節點如 ParallelFork 不進新安裝）。
"""
import argparse
import os
import sys

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("錯誤: 需要 psycopg2（venv/bin/python 執行）", file=sys.stderr)
    sys.exit(2)

# id（serial）與 deleted_at（恆 NULL）不匯出；時間戳由 seed 執行當下決定
COLUMNS = [
    'secure_code', 'node_type', 'scope', 'org_secure_code', 'category',
    'display_name', 'description', 'icon', 'execution_handler', 'config_schema',
    'canvas_shape', 'canvas_color', 'canvas_width', 'canvas_height',
    'max_input_connections', 'max_output_connections',
    'default_timeout_seconds', 'max_timeout_seconds',
    'require_system_admin', 'is_active', 'is_deleted', 'org_restricted',
]

HEADER = """\
-- seed_workflow_node_definitions.sql — 節點型別定義出廠 seed（安裝用）
-- 本檔由 scripts/export_node_definitions_seed.py 從 dev 庫自動產生，禁止手改。
-- 冪等：以 node_type 唯一鍵 ON CONFLICT DO NOTHING（既有定義不覆蓋）。
--
-- 執行必須帶 system_org 變數（系統企業 secure_code，即 .env 的 SYSTEM_ORG_CODE）：
--   psql -v system_org="$SYSTEM_ORG_CODE" -f scripts/sql/seed_workflow_node_definitions.sql

BEGIN;
"""

FOOTER = "COMMIT;\n"


def sql_literal(v):
    if v is None:
        return 'NULL'
    if isinstance(v, bool):
        return 'TRUE' if v else 'FALSE'
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, dict) or isinstance(v, list):
        import json
        s = json.dumps(v, ensure_ascii=False)
        return "'" + s.replace("'", "''") + "'::jsonb"
    return "'" + str(v).replace("'", "''") + "'"


def main():
    parser = argparse.ArgumentParser(
        description='從 dev 庫匯出 workflow_node_definitions 的安裝 seed SQL')
    parser.add_argument('--out', default='scripts/sql/seed_workflow_node_definitions.sql',
                        help='輸出檔路徑（預設 scripts/sql/seed_workflow_node_definitions.sql）')
    parser.add_argument('--dsn', default=os.environ.get('DATABASE_URL', ''),
                        help='來源庫 DSN（預設取環境變數 DATABASE_URL）')
    args = parser.parse_args()

    if not args.dsn:
        print("錯誤: 未指定 --dsn 且環境變數 DATABASE_URL 為空", file=sys.stderr)
        sys.exit(2)

    conn = psycopg2.connect(args.dsn)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(f"""
        SELECT {', '.join(COLUMNS)}
        FROM workflow_node_definitions
        WHERE is_deleted = false
        ORDER BY node_type
    """)
    rows = cur.fetchall()
    if not rows:
        print("錯誤: 來源庫沒有任何未刪除的節點定義，拒絕輸出空 seed", file=sys.stderr)
        sys.exit(1)

    # org_secure_code 是安裝環境相關值：等於本環境 SYSTEM_ORG_CODE 的改成
    # psql 變數 :'system_org'（各安裝環境自訂）；指向其他企業的定義無法移植，直接擋
    system_org = os.environ.get('SYSTEM_ORG_CODE', '')
    for r in rows:
        org = r['org_secure_code']
        if org is not None and org != system_org:
            print(f"錯誤: {r['node_type']} 的 org_secure_code={org!r} 不是系統企業，"
                  f"企業專屬定義不可進安裝 seed", file=sys.stderr)
            sys.exit(1)

    cols_sql = ', '.join(COLUMNS + ['created_at', 'updated_at'])
    lines = [HEADER]
    for r in rows:
        vals = ', '.join(
            ":'system_org'" if (c == 'org_secure_code' and r[c] is not None)
            else sql_literal(r[c])
            for c in COLUMNS)
        lines.append(
            f"INSERT INTO workflow_node_definitions ({cols_sql})\n"
            f"VALUES ({vals}, now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC')\n"
            f"ON CONFLICT (node_type) DO NOTHING;\n"
        )
    lines.append(FOOTER)

    with open(args.out, 'w') as f:
        f.write('\n'.join(lines))
    print(f"已輸出 {len(rows)} 筆節點定義 -> {args.out}")


if __name__ == '__main__':
    main()
