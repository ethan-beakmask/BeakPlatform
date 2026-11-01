#!/usr/bin/env python3
"""補建既有企業的「專案類」系統群組。"""
import argparse
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / 'backend'
sys.path.insert(0, str(BACKEND_DIR))

USAGE = """用法：
  venv/bin/python scripts/ensure_projects_group_class.py --org all
  venv/bin/python scripts/ensure_projects_group_class.py --org <code|domain|secure_code> [--apply]

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
        description='補建企業的「專案類」系統群組',
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
    from app.models import Organization, OrganizationalUnit
    from app.services.oidc_org_defaults import ensure_projects_group_class

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

        created = 0
        existing = 0
        for org in orgs:
            found = OrganizationalUnit.query.filter(
                OrganizationalUnit.org_secure_code == org.secure_code,
                OrganizationalUnit.code == 'PROJECTS_GROUPCLASS',
                OrganizationalUnit.is_deleted.is_(False),
            ).first()
            if found:
                existing += 1
                print(f'已存在：{org.code} {org.name}')
                continue
            created += 1
            print(f'{"新建" if args.apply else "將新建"}：{org.code} {org.name}')
            if args.apply:
                ensure_projects_group_class(org)

        if args.apply:
            db.session.commit()
        else:
            db.session.rollback()
        print(f'新建 {created}、已存在 {existing}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
