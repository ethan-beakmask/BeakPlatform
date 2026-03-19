#!/usr/bin/env python3
"""
BeakPlatform 稽核日誌查詢工具

查詢 audit_logs 表的安全相關事件，用於掃描期間即時觀測。

使用方式:
  python3 audit_query.py                     顯示使用說明
  python3 audit_query.py recent              最近 50 筆稽核紀錄
  python3 audit_query.py recent -n 100       最近 100 筆
  python3 audit_query.py login               登入/登出事件
  python3 audit_query.py failed              登入失敗事件
  python3 audit_query.py failed -n 100       最近 100 筆登入失敗
  python3 audit_query.py errors              4xx/5xx 錯誤回應
  python3 audit_query.py ip                  IP 統計 (請求次數排序)
  python3 audit_query.py watch               即時監控模式 (每 3 秒更新)
"""
import argparse
import sys
import time
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


def get_connection():
    """取得資料庫連線"""
    import psycopg2
    return psycopg2.connect(
        host='localhost',
        port=5432,
        dbname='beakplatform_dev',
        user='beakplatform',
        password='postgres123'
    )


def print_rows(rows, headers):
    """格式化輸出"""
    if not rows:
        print("  (無資料)")
        return

    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val or '')))

    # 限制最大欄寬
    col_widths = [min(w, 60) for w in col_widths]

    header_line = '  '.join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    print(header_line)
    print('-' * len(header_line))

    for row in rows:
        line = '  '.join(str(v or '').ljust(col_widths[i])[:col_widths[i]] for i, v in enumerate(row))
        print(line)


def cmd_recent(args):
    """最近 N 筆稽核紀錄"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT created_at, action, ip_address, request_method,
               request_path, status_code, details
        FROM audit_logs
        ORDER BY created_at DESC
        LIMIT %s
    """, (args.n,))
    rows = cur.fetchall()
    headers = ['時間', '動作', 'IP', '方法', '路徑', '狀態碼', '詳情']
    print_rows(rows, headers)
    conn.close()


def cmd_login(args):
    """登入/登出事件"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT created_at, action, ip_address, user_agent,
               details
        FROM audit_logs
        WHERE action IN ('LOGIN', 'LOGOUT', 'LOGIN_FAILED')
        ORDER BY created_at DESC
        LIMIT %s
    """, (args.n,))
    rows = cur.fetchall()
    headers = ['時間', '動作', 'IP', 'User-Agent', '詳情']
    print_rows(rows, headers)
    conn.close()


def cmd_failed(args):
    """登入失敗事件"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT created_at, ip_address, user_agent, details
        FROM audit_logs
        WHERE action = 'LOGIN_FAILED'
        ORDER BY created_at DESC
        LIMIT %s
    """, (args.n,))
    rows = cur.fetchall()
    headers = ['時間', 'IP', 'User-Agent', '詳情']
    print_rows(rows, headers)
    print(f"\n  共 {len(rows)} 筆登入失敗紀錄")
    conn.close()


def cmd_errors(args):
    """4xx/5xx 錯誤回應"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT created_at, ip_address, request_method, request_path,
               status_code, details
        FROM audit_logs
        WHERE status_code >= 400
        ORDER BY created_at DESC
        LIMIT %s
    """, (args.n,))
    rows = cur.fetchall()
    headers = ['時間', 'IP', '方法', '路徑', '狀態碼', '詳情']
    print_rows(rows, headers)
    conn.close()


def cmd_ip(args):
    """IP 統計"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT ip_address,
               COUNT(*) as total,
               COUNT(*) FILTER (WHERE action = 'LOGIN_FAILED') as failed,
               COUNT(*) FILTER (WHERE status_code >= 400) as errors,
               MIN(created_at) as first_seen,
               MAX(created_at) as last_seen
        FROM audit_logs
        WHERE ip_address IS NOT NULL
        GROUP BY ip_address
        ORDER BY total DESC
        LIMIT %s
    """, (args.n,))
    rows = cur.fetchall()
    headers = ['IP', '總請求', '登入失敗', '錯誤', '首次出現', '最後出現']
    print_rows(rows, headers)
    conn.close()


def cmd_watch(args):
    """即時監控模式"""
    last_id = 0
    conn = get_connection()
    cur = conn.cursor()

    # 取得目前最大 id
    cur.execute("SELECT COALESCE(MAX(id), 0) FROM audit_logs")
    last_id = cur.fetchone()[0]
    conn.close()

    print(f"[即時監控] 從 id={last_id} 開始，每 3 秒更新... (Ctrl+C 結束)")
    print()

    try:
        while True:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT id, created_at, action, ip_address,
                       request_method, request_path, status_code
                FROM audit_logs
                WHERE id > %s
                ORDER BY id ASC
            """, (last_id,))
            rows = cur.fetchall()
            conn.close()

            for row in rows:
                last_id = row[0]
                status = row[6] or ''
                flag = ''
                if row[2] == 'LOGIN_FAILED':
                    flag = ' << FAILED LOGIN'
                elif isinstance(status, int) and status >= 400:
                    flag = f' << HTTP {status}'

                print(f"  {row[1]}  {row[2]:<15} {row[3] or '-':<18} "
                      f"{row[4] or '':<6} {row[5] or ''}{flag}")

            time.sleep(3)

    except KeyboardInterrupt:
        print("\n[結束監控]")


def print_usage():
    """顯示使用說明"""
    print(__doc__)


def main():
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(0)

    parser = argparse.ArgumentParser(description='BeakPlatform 稽核日誌查詢工具')
    sub = parser.add_subparsers(dest='command')

    for name, func in [('recent', cmd_recent), ('login', cmd_login),
                        ('failed', cmd_failed), ('errors', cmd_errors),
                        ('ip', cmd_ip), ('watch', cmd_watch)]:
        p = sub.add_parser(name)
        p.add_argument('-n', type=int, default=50, help='筆數 (預設 50)')
        p.set_defaults(func=func)

    args = parser.parse_args()
    if not args.command:
        print_usage()
        sys.exit(0)

    args.func(args)


if __name__ == '__main__':
    main()
