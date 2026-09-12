#!/usr/bin/env python3
"""補建企業專屬資料庫（org_<id>）。

用於 PF-256 定案「建立企業時就建一個空的專屬 DB」之前已存在的企業，
以及「登記在、實體庫不存在」的修復（本機 SYSTEM 的 org_14 即此狀態）。
"""
import os
import sys

os.environ['SKIP_MODULE_SYNC'] = '1'
os.environ['EXECUTOR_STANDALONE'] = '1'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


USAGE = """用法:
  scripts/provision_missing_org_databases.py --dry-run
  scripts/provision_missing_org_databases.py --apply
  scripts/provision_missing_org_databases.py --dry-run --skip-system

說明:
  為每一家未刪除的企業確認專屬資料庫 org_<id> 存在，缺的補建。
  會同時檢查「fw_org_databases 登記」與「PostgreSQL 實體庫」兩邊：

    ok          登記在、實體庫也在          -> 不動
    missing_db  登記在 is_ready=true、庫不在 -> 重新佈建（重新產生密碼）
    not_ready   登記在但 is_ready=false      -> 補建
    none        沒有登記                     -> 建庫與登記

  --apply 完成後會以 sync 角色實際連一次每個庫（SELECT 1）作為驗收。
  預設含系統企業；--skip-system 可略過。
  需要 .env 的 SYNC_PG_ADMIN_URL（LOGIN + CREATEDB + CREATEROLE，不需要 superuser）。
"""


def _print_usage():
    print(USAGE)


def _load_dotenv():
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding='utf-8') as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _parse_args(argv):
    if not argv or any(arg in ('--help', '-h') for arg in argv):
        _print_usage()
        return None, 0
    mode_args = [arg for arg in argv if arg in ('--dry-run', '--apply')]
    allowed = {'--dry-run', '--apply', '--skip-system'}
    if len(mode_args) != 1 or any(arg not in allowed for arg in argv):
        _print_usage()
        return None, 1
    return (mode_args[0], '--skip-system' in argv), 0


def _existing_databases():
    """以 superuser 連線列出現存的 org_* 資料庫名稱"""
    import psycopg2
    url = os.environ.get('SYNC_PG_ADMIN_URL')
    if not url:
        raise RuntimeError('SYNC_PG_ADMIN_URL 環境變數未設定')
    conn = psycopg2.connect(url)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT datname FROM pg_database WHERE datname LIKE 'org\\_%'")
            return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()


def main():
    parsed, exit_code = _parse_args(sys.argv[1:])
    if parsed is None:
        return exit_code
    mode, skip_system = parsed

    _load_dotenv()
    from app import create_app, db
    from app.models import Organization

    app = create_app()
    with app.app_context():
        from modules.form_workflow.models.org_database import FwOrgDatabase
        from modules.form_workflow.services.sql_sync.org_db_manager import (
            provision_org_database,
        )

        live_dbs = _existing_databases()
        orgs = Organization.query.filter(
            Organization.is_deleted == False  # noqa: E712
        ).order_by(Organization.id.asc()).all()

        stats = {'ok': 0, 'created': 0, 'repaired': 0, 'skipped': 0}
        provisioned = []

        for org in orgs:
            if skip_system and org.is_system_org:
                stats['skipped'] += 1
                print(f'{org.code}: skipped(system)')
                continue

            db_name = f'org_{org.id}'
            reg = FwOrgDatabase.query.filter_by(
                org_id=org.id, is_deleted=False
            ).first()
            db_live = db_name in live_dbs

            if reg and reg.is_ready and db_live:
                stats['ok'] += 1
                print(f'{org.code}: ok ({db_name})')
                continue

            if reg and reg.is_ready and not db_live:
                state, bucket = 'missing_db -> repair', 'repaired'
            elif reg:
                state, bucket = 'not_ready -> provision', 'created'
            else:
                state, bucket = 'none -> provision', 'created'

            stats[bucket] += 1
            print(f'{org.code}: {state} ({db_name})')

            if mode != '--apply':
                continue

            # provision_org_database 的冪等檢查自 PF-256 起會同時看登記與實體庫，
            # is_ready=true 但庫不在時它自己就會重新佈建，這裡不必再清旗標。
            provision_org_database(org.id, org.secure_code)
            provisioned.append(org)

        if mode == '--apply':
            db.session.commit()
            print('已寫入資料庫')

            # 驗收：以 sync 角色實際連一次
            from modules.form_workflow.services.sql_sync.pool import get_org_conn
            for org in provisioned:
                try:
                    with get_org_conn(org.secure_code, role='sync') as conn:
                        with conn.cursor() as cur:
                            cur.execute('SELECT 1')
                            cur.fetchone()
                    print(f'{org.code}: verify ok')
                except Exception as exc:  # noqa: BLE001
                    print(f'{org.code}: verify FAILED: {exc}')
                    return 1
        else:
            db.session.rollback()
            print('dry-run，未寫入資料庫')

        print(
            f"統計: ok={stats['ok']}, created={stats['created']}, "
            f"repaired={stats['repaired']}, skipped={stats['skipped']}"
        )

    return 0


if __name__ == '__main__':
    sys.exit(main())
