#!/usr/bin/env python3
"""
BeakPlatform SYSTEM_ADMIN 密碼重設工具（本機開發環境自救用）

讀取執行路徑下 .env 的 DATABASE_URL 與 SYSTEM_ORG_CODE，
對該組織的 SYSTEM_ADMIN 帳號重設密碼。
"""

import argparse
import getpass
import sys
from datetime import datetime, timezone
from pathlib import Path

# 依賴檢查
_missing_deps = []
try:
    import bcrypt
except ImportError:
    _missing_deps.append("bcrypt")
try:
    import psycopg2
except ImportError:
    _missing_deps.append("psycopg2-binary")
try:
    from dotenv import dotenv_values
except ImportError:
    _missing_deps.append("python-dotenv")

if _missing_deps:
    print(f"[錯誤] 缺少套件: {', '.join(_missing_deps)}")
    print(f"  pip install {' '.join(_missing_deps)}")
    sys.exit(1)


def load_env():
    """從 working directory 載入 .env，回傳 (DATABASE_URL, SYSTEM_ORG_CODE)"""
    env_path = Path.cwd() / ".env"
    if not env_path.exists():
        print(f"[錯誤] 找不到 .env: {env_path}")
        sys.exit(1)

    env = dotenv_values(env_path)

    database_url = env.get("DATABASE_URL")
    org_code = env.get("SYSTEM_ORG_CODE")

    missing = []
    if not database_url:
        missing.append("DATABASE_URL")
    if not org_code:
        missing.append("SYSTEM_ORG_CODE")

    if missing:
        print(f"[錯誤] .env 缺少必要變數: {', '.join(missing)}")
        sys.exit(1)

    return database_url, org_code


def prompt_password() -> str:
    """互動式輸入密碼（避免 shell 特殊字元問題）"""
    pw1 = getpass.getpass("請輸入新密碼: ")
    if not pw1:
        print("[錯誤] 密碼不可為空")
        sys.exit(1)
    pw2 = getpass.getpass("再次輸入新密碼: ")
    if pw1 != pw2:
        print("[錯誤] 兩次輸入的密碼不一致")
        sys.exit(1)
    return pw1


def hash_password(password: str) -> str:
    """用 bcrypt 雜湊密碼，與 BeakPlatform User.set_password() 一致"""
    raw = password.encode("utf-8")
    if len(raw) > 72:
        print("[錯誤] 密碼長度超過 bcrypt 72 bytes 上限")
        sys.exit(1)
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(raw, salt).decode("utf-8")


def get_admins(conn, org_code: str) -> list:
    """查詢目標 SYSTEM_ADMIN 帳號"""
    sql = """
        SELECT id, secure_code, username, email, display_name, is_active
        FROM public.users
        WHERE user_type = 'SYSTEM_ADMIN'
          AND org_secure_code = %s
          AND is_deleted = false
        ORDER BY id
    """
    with conn.cursor() as cur:
        cur.execute(sql, (org_code,))
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def update_password(conn, org_code: str, password_hash: str) -> int:
    """更新密碼，回傳影響筆數"""
    sql = """
        UPDATE public.users
        SET password_hash = %s,
            password_changed_at = %s,
            must_change_password = false
        WHERE user_type = 'SYSTEM_ADMIN'
          AND org_secure_code = %s
          AND is_deleted = false
    """
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute(sql, (password_hash, now, org_code))
        return cur.rowcount


def verify_password(conn, org_code: str, password: str) -> bool:
    """從 DB 讀回 hash 驗證密碼是否正確寫入"""
    sql = """
        SELECT id, username, password_hash
        FROM public.users
        WHERE user_type = 'SYSTEM_ADMIN'
          AND org_secure_code = %s
          AND is_deleted = false
        ORDER BY id
    """
    with conn.cursor() as cur:
        cur.execute(sql, (org_code,))
        rows = cur.fetchall()

    raw = password.encode("utf-8")
    all_ok = True
    for uid, username, stored_hash in rows:
        ok = bcrypt.checkpw(raw, stored_hash.encode("utf-8"))
        status = "OK" if ok else "FAIL"
        print(f"  [{status}] id={uid} username={username}")
        if not ok:
            all_ok = False
    return all_ok


def print_admins(admins: list):
    """印出管理員清單"""
    if not admins:
        print("  (無符合條件的帳號)")
        return
    print(f"  {'ID':<6} {'username':<20} {'email':<35} {'active'}")
    print(f"  {'-'*6} {'-'*20} {'-'*35} {'-'*6}")
    for a in admins:
        active = "Y" if a["is_active"] else "N"
        print(f"  {a['id']:<6} {a['username']:<20} {a['email']:<35} {active}")


def main():
    parser = argparse.ArgumentParser(
        description="BeakPlatform SYSTEM_ADMIN 密碼重設工具（本機開發環境自救用）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用範例:
  # 查看會被影響的帳號（不做變更）
  python3 reset_password.py --dry-run

  # 互動式輸入密碼（推薦，避免 shell 特殊字元問題）
  python3 reset_password.py

  # 命令列指定密碼
  python3 reset_password.py --password 'NewPass123'

注意:
  - 必須在含有 .env 的目錄下執行（需要 DATABASE_URL 和 SYSTEM_ORG_CODE）
  - 僅限本機開發環境使用
  - 密碼含特殊字元（如 $%^!& 等）時，--password 值必須用單引號包住：
    python3 reset_password.py --password 'MyP@ss$123'
    若未加單引號，shell 會展開特殊字元，導致寫入的 hash 與原始密碼不符
  - 最安全的做法是不加 --password，使用互動式輸入（不經過 shell 解析）
        """,
    )
    parser.add_argument("--password", "-p", help="新密碼（未指定則互動式輸入）")
    parser.add_argument(
        "--dry-run", "-n", action="store_true", help="僅查詢目標帳號，不做任何變更"
    )

    args = parser.parse_args()

    database_url, org_code = load_env()

    print(f"[資訊] SYSTEM_ORG_CODE = {org_code}")

    try:
        conn = psycopg2.connect(database_url)
    except psycopg2.Error as e:
        print(f"[錯誤] 資料庫連線失敗: {e}")
        sys.exit(1)

    try:
        admins = get_admins(conn, org_code)
        print(f"[資訊] 找到 {len(admins)} 個 SYSTEM_ADMIN 帳號:")
        print_admins(admins)

        if args.dry_run:
            print("\n[dry-run] 僅查詢，未做任何變更")
            return

        if not admins:
            print("\n[略過] 無帳號需要更新")
            return

        # 取得密碼：命令列參數或互動式輸入
        password = args.password if args.password else prompt_password()

        password_hash = hash_password(password)
        affected = update_password(conn, org_code, password_hash)
        conn.commit()

        print(f"\n[完成] 已更新 {affected} 個帳號的密碼")

        # 驗證：從 DB 讀回 hash 確認密碼正確寫入
        print("\n[驗證] 從 DB 讀回 hash 驗證...")
        if verify_password(conn, org_code, password):
            print("[驗證] 全部通過")
        else:
            print("[驗證] 有帳號驗證失敗，請檢查")
            sys.exit(1)

    except psycopg2.Error as e:
        conn.rollback()
        print(f"[錯誤] 資料庫操作失敗: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
