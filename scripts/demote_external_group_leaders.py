#!/usr/bin/env python3
"""將不合資格的群組管理層降為一般成員。"""
import argparse
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / 'backend'
sys.path.insert(0, str(BACKEND_DIR))

USAGE = """用法：
  venv/bin/python scripts/demote_external_group_leaders.py --org all
  venv/bin/python scripts/demote_external_group_leaders.py --org <code|domain|secure_code> [--apply]

說明：
  未加 --apply 時只列出預計結果，不寫入資料庫。
  --org all 會處理全部未刪除企業（包含停用企業）。
"""


def _load_env():
    path = REPO_ROOT / '.env'
    if not path.exists():
        return
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _parser():
    parser = argparse.ArgumentParser(
        description='將不合資格的群組管理層降為一般成員',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=USAGE,
    )
    parser.add_argument('--org', help='all 或企業 code、domain_name、secure_code')
    parser.add_argument('--apply', action='store_true', help='實際寫入資料庫')
    return parser


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(USAGE)
        return 0
    args = _parser().parse_args(argv)
    if not args.org:
        print(USAGE)
        return 0

    _load_env()
    from sqlalchemy import or_
    from app import create_app, db
    from app.models import Organization, OrganizationalUnit, User, UserUnitMembership

    app = create_app('development')
    with app.app_context():
        query = Organization.query.filter(Organization.is_deleted.is_(False))
        if args.org != 'all':
            query = query.filter(or_(
                Organization.code == args.org,
                Organization.domain_name == args.org,
                Organization.secure_code == args.org,
            ))
        orgs = query.order_by(Organization.code).all()
        if not orgs:
            print(f'找不到企業：{args.org}')
            return 1

        count = 0
        for org in orgs:
            rows = db.session.query(UserUnitMembership, OrganizationalUnit, User).join(
                OrganizationalUnit,
                OrganizationalUnit.secure_code == UserUnitMembership.unit_secure_code,
            ).join(User, User.secure_code == UserUnitMembership.user_secure_code).filter(
                UserUnitMembership.org_secure_code == org.secure_code,
                UserUnitMembership.is_deleted.is_(False),
                UserUnitMembership.role_type.in_(('MANAGER', 'DEPUTY', 'PROXY1', 'PROXY2')),
                OrganizationalUnit.org_secure_code == org.secure_code,
                OrganizationalUnit.unit_type == 'GROUP',
                User.org_secure_code == org.secure_code,
                or_(User.user_type != 'EMPLOYEE', User.is_active.is_(False),
                    User.is_deleted.is_(True)),
            ).order_by(OrganizationalUnit.name, User.email).all()
            for membership, unit, user in rows:
                print(f'{org.code} / {unit.name} / {user.email} / {membership.role_type}')
                count += 1
                if args.apply:
                    membership.role_type = 'MEMBER'

        if args.apply:
            db.session.commit()
        else:
            db.session.rollback()
        print(f'{"已降級" if args.apply else "將降級"} {count} 筆')
    return 0


if __name__ == '__main__':
    sys.exit(main())
