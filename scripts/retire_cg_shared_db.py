#!/usr/bin/env python3
"""PF-269 退役集團共用資料庫功能。

2026-09-13 Ethan 定案（BBN 待辦 PF-269）：
- spec_formulate（規格制定模組）保留，其 DDL 注入問題另案 PF-268 白名單化。
- 集團共用資料庫（Conglomerate shared DB，cg_<id> 庫）功能因安全因素整個移除：
  它讓多家企業共用一個 PostgreSQL 庫、只靠 RLS 隔離，且建表 DDL 走原樣內插，
  攻擊面不值得保留。dev 與 bpserv 兩個環境都是 0 個集團、0 個 cg_* 庫，沒有資料要遷移。
- 「集團」作為企業分群的概念保留（conglomerates / conglomerate_logs 表、
  organizations.conglomerate_secure_code、企業列表的 [集團設定]／篩選／徽章、部門頁顯示集團名）。
  只拿掉「共用 DB」那一半。

既有環境（bpserv）install.sh --update 的 create_all 不會刪表刪欄位，升級後要手動跑本腳本 --apply。
"""
import argparse
import os
import sys

from sqlalchemy import text

os.environ['SKIP_MODULE_SYNC'] = '1'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


USAGE = """用法:
  scripts/retire_cg_shared_db.py --dry-run
  scripts/retire_cg_shared_db.py --apply

說明:
  PF-269 退役集團共用資料庫功能：
  1. 軟刪 menu_items 中 code='cg_databases_overview' 且 is_deleted=false 的選單項目
  2. DROP TABLE IF EXISTS fw_conglomerate_table_registry
  3. DROP TABLE IF EXISTS fw_conglomerate_databases
  4. ALTER TABLE conglomerates DROP COLUMN IF EXISTS shared_db_* / has_shared_db

  --dry-run 只顯示會做什麼；--apply 才會寫入資料庫。
"""


CG_COLUMNS = [
    'shared_db_host',
    'shared_db_port',
    'shared_db_name',
    'shared_db_user',
    'shared_db_password_encrypted',
    'has_shared_db',
]


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
    if any(arg in ('--help', '-h') for arg in argv):
        _print_usage()
        return None, 0
    if not argv:
        _print_usage()
        return None, 1

    parser = argparse.ArgumentParser(add_help=False)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--apply', action='store_true')
    try:
        parsed = parser.parse_args(argv)
    except SystemExit:
        _print_usage()
        return None, 1
    return ('--apply' if parsed.apply else '--dry-run'), 0


def _scalar(db, sql, params=None):
    return db.session.execute(text(sql), params or {}).scalar() or 0


def _table_exists(db, table_name):
    return bool(_scalar(db, """
        SELECT count(*)
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = :table_name
    """, {'table_name': table_name}))


def _existing_cg_columns(db):
    rows = db.session.execute(text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'conglomerates'
          AND column_name IN (
              'shared_db_host',
              'shared_db_port',
              'shared_db_name',
              'shared_db_user',
              'shared_db_password_encrypted',
              'has_shared_db'
          )
        ORDER BY ordinal_position
    """)).fetchall()
    return [row[0] for row in rows]


def _collect_state(db):
    return {
        'menu_items': _scalar(db, """
            SELECT count(*)
            FROM menu_items
            WHERE code = 'cg_databases_overview'
              AND is_deleted = false
        """),
        'fw_conglomerate_table_registry': _table_exists(
            db, 'fw_conglomerate_table_registry'
        ),
        'fw_conglomerate_databases': _table_exists(
            db, 'fw_conglomerate_databases'
        ),
        'columns': _existing_cg_columns(db),
    }


def _print_state(state, apply_changes):
    prefix = '執行' if apply_changes else 'dry-run'
    print(f'[{prefix}] PF-269 集團共用資料庫退役')

    menu_count = state['menu_items']
    if menu_count:
        print(f'- 會做：軟刪 menu_items cg_databases_overview，共 {menu_count} 筆')
    else:
        print('- 已是目標狀態：menu_items 沒有未刪除的 cg_databases_overview')

    for table_name in ('fw_conglomerate_table_registry', 'fw_conglomerate_databases'):
        if state[table_name]:
            print(f'- 會做：DROP TABLE IF EXISTS {table_name}')
        else:
            print(f'- 已是目標狀態：{table_name} 不存在')

    columns = state['columns']
    if columns:
        print('- 會做：ALTER TABLE conglomerates DROP COLUMN IF EXISTS ' + ', '.join(columns))
    else:
        print('- 已是目標狀態：conglomerates 沒有集團共用資料庫欄位')


def _apply(db):
    db.session.execute(text("""
        UPDATE menu_items
        SET is_deleted = true,
            deleted_at = now()
        WHERE code = 'cg_databases_overview'
          AND is_deleted = false
    """))
    db.session.execute(text('DROP TABLE IF EXISTS fw_conglomerate_table_registry'))
    db.session.execute(text('DROP TABLE IF EXISTS fw_conglomerate_databases'))
    db.session.execute(text("""
        ALTER TABLE conglomerates
            DROP COLUMN IF EXISTS shared_db_host,
            DROP COLUMN IF EXISTS shared_db_port,
            DROP COLUMN IF EXISTS shared_db_name,
            DROP COLUMN IF EXISTS shared_db_user,
            DROP COLUMN IF EXISTS shared_db_password_encrypted,
            DROP COLUMN IF EXISTS has_shared_db
    """))


def main(argv=None):
    mode, code = _parse_args(argv if argv is not None else sys.argv[1:])
    if mode is None:
        return code

    _load_dotenv()

    from app import create_app, db

    app = create_app()
    apply_changes = mode == '--apply'
    with app.app_context():
        state = _collect_state(db)
        _print_state(state, apply_changes)
        if apply_changes:
            _apply(db)
            db.session.commit()
            print('- 完成：已 commit')
        else:
            db.session.rollback()
            print('- dry-run 完成：未寫入資料庫')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
