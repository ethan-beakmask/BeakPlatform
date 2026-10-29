#!/usr/bin/env python3
"""補登記帳號身上、卻沒有記在 used_user_numbers 的用戶編號。

2026-10-30 之前，在帳號編輯頁換的新編號不會登記；帳號刪除後，這些號碼可能再被發給別人。
本腳本把所有帳號（含停用與已刪除）目前的編號補登記，冪等，重跑不會重複寫入。
"""
import argparse
import os
import sys

os.environ['SKIP_MODULE_SYNC'] = '1'
os.environ['EXECUTOR_STANDALONE'] = '1'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

USAGE = """用法:
  venv/bin/python scripts/backfill_used_user_numbers.py --dry-run
  venv/bin/python scripts/backfill_used_user_numbers.py --apply

說明:
  找出帳號身上有用戶編號、但 used_user_numbers 沒有登記的情況並補登記（含停用與已刪除的帳號）。
  --dry-run 只列出會補哪些，--apply 才寫入。同一企業有兩個帳號用同一個編號時只登記一次，並列出衝突供人工處理。
"""


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
    if not argv:
        print(USAGE)
        return None
    parser = argparse.ArgumentParser(
        description='補登記未記在 used_user_numbers 的用戶編號',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=USAGE,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--dry-run', action='store_true', help='只列出，不寫入')
    group.add_argument('--apply', action='store_true', help='實際寫入資料庫')
    return parser.parse_args(argv)


def main():
    args = _parse_args(sys.argv[1:])
    if args is None:
        return 0
    _load_dotenv()

    from app import create_app, db
    from app.models.user import User
    from app.models.user_numbering_rule import UsedUserNumber

    app = create_app()
    with app.app_context():
        users = (User.query
                 .filter(User.employee_id.isnot(None), User.employee_id != '')
                 .order_by(User.org_secure_code, User.employee_id, User.id)
                 .all())
        to_record = {}
        conflicts = {}
        for user in users:
            key = (user.org_secure_code, user.employee_id)
            if UsedUserNumber.is_number_used(*key):
                continue
            if key in to_record:
                conflicts.setdefault(key, [to_record[key].secure_code]).append(user.secure_code)
                continue
            to_record[key] = user

        for (org_sc, number), user in to_record.items():
            state = '已刪除' if user.is_deleted else ('停用' if not user.is_active else '啟用')
            print(f'補登記 org={org_sc} number={number} user={user.secure_code}（{state}）')
            if args.apply:
                UsedUserNumber.record_number(org_secure_code=org_sc, number=number,
                                             user_secure_code=user.secure_code)
        for (org_sc, number), codes in conflicts.items():
            print(f'衝突（同企業多個帳號同編號，只登記第一個，請人工處理）org={org_sc} number={number} users={",".join(codes)}')

        if args.apply:
            try:
                db.session.commit()
            except Exception as exc:
                db.session.rollback()
                print(f'寫入失敗：{exc}', file=sys.stderr)
                return 1
        mode = '已寫入' if args.apply else 'dry-run'
        print(f'{mode}：補登記 {len(to_record)} 筆，衝突 {len(conflicts)} 筆')
    return 0


if __name__ == '__main__':
    sys.exit(main())
