#!/usr/bin/env python3
"""
流程節點型別企業授權維運工具。
"""
import argparse
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / 'backend'
ENV_FILE = REPO_ROOT / '.env'


USAGE = """流程節點型別企業授權工具

用法:
  venv/bin/python scripts/node_grant.py list
  venv/bin/python scripts/node_grant.py grant <node_type> <企業 secure_code 或 code> [--by <授權者>] [--note <備註>]
  venv/bin/python scripts/node_grant.py revoke <node_type> <企業 secure_code 或 code>

說明:
  list    列出目前所有 restricted 節點型別與各自的授權企業
  grant   授權指定企業使用指定 restricted 節點型別；已授權時不會重複建立
  revoke  軟刪除指定授權
"""


def _bootstrap():
    """讓此 script 能 standalone 執行(載入 .env、加入 backend 到 sys.path)。"""
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def _parser():
    parser = argparse.ArgumentParser(
        description='流程節點型別企業授權工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=USAGE,
    )
    subparsers = parser.add_subparsers(dest='command')

    subparsers.add_parser('list', help='列出 restricted 節點型別與授權企業')

    grant = subparsers.add_parser('grant', help='授權企業使用 restricted 節點型別')
    grant.add_argument('node_type', help='節點型別，例如 OsExecutor')
    grant.add_argument('org', help='企業 secure_code 或 code，例如 SYSTEM')
    grant.add_argument('--by', dest='granted_by_name', help='授權者名稱')
    grant.add_argument('--note', help='備註')

    revoke = subparsers.add_parser('revoke', help='撤銷企業節點授權')
    revoke.add_argument('node_type', help='節點型別，例如 OsExecutor')
    revoke.add_argument('org', help='企業 secure_code 或 code，例如 SYSTEM')

    return parser


def _restricted_node_or_error(node_type):
    from modules.form_workflow.models import WorkflowNodeDefinition

    node_def = WorkflowNodeDefinition.query.filter(
        WorkflowNodeDefinition.node_type == node_type,
        WorkflowNodeDefinition.is_deleted.is_(False),
    ).first()
    if not node_def:
        raise ValueError(f'找不到節點型別：{node_type}')
    if not node_def.org_restricted:
        raise ValueError(f'節點型別不是 restricted：{node_type}')
    return node_def


def _org_or_error(identifier):
    from app.models import Organization
    from sqlalchemy import or_

    org = Organization.query.filter(
        or_(Organization.secure_code == identifier, Organization.code == identifier),
        Organization.is_deleted.is_(False),
    ).first()
    if not org:
        raise ValueError(f'找不到企業：{identifier}')
    return org


def _list_grants():
    from app.models import Organization
    from modules.form_workflow.models import WorkflowNodeDefinition, WorkflowNodeOrgGrant

    node_defs = WorkflowNodeDefinition.query.filter(
        WorkflowNodeDefinition.org_restricted.is_(True),
        WorkflowNodeDefinition.is_deleted.is_(False),
    ).order_by(WorkflowNodeDefinition.node_type).all()

    if not node_defs:
        print('目前沒有 restricted 節點型別。')
        return 0

    for node_def in node_defs:
        print(f'{node_def.node_type}')
        grants = WorkflowNodeOrgGrant.query.filter(
            WorkflowNodeOrgGrant.node_type == node_def.node_type,
            WorkflowNodeOrgGrant.is_deleted.is_(False),
        ).order_by(WorkflowNodeOrgGrant.org_secure_code).all()
        if not grants:
            print('  （無授權企業）')
            continue
        org_codes = [grant.org_secure_code for grant in grants]
        orgs = Organization.query.filter(
            Organization.secure_code.in_(org_codes),
            Organization.is_deleted.is_(False),
        ).all()
        org_by_secure_code = {org.secure_code: org for org in orgs}
        for grant in grants:
            org = org_by_secure_code.get(grant.org_secure_code)
            if org:
                print(f'  {org.code}  {org.secure_code}  {org.name}')
            else:
                print(f'  {grant.org_secure_code}  （企業不存在或已刪除）')
    return 0


def _grant(node_type, org_identifier, granted_by_name=None, note=None):
    from modules.form_workflow.services.node_grant_service import grant_node_to_org

    org = _org_or_error(org_identifier)

    changed = grant_node_to_org(
        node_type,
        org.secure_code,
        granted_by_name=granted_by_name,
        note=note,
    )
    if not changed:
        print(f'已授權：{node_type} -> {org.code} ({org.secure_code})')
        return 0

    print(f'授權完成：{node_type} -> {org.code} ({org.secure_code})')
    return 0


def _revoke(node_type, org_identifier):
    from modules.form_workflow.services.node_grant_service import revoke_node_from_org

    org = _org_or_error(org_identifier)

    changed = revoke_node_from_org(node_type, org.secure_code)
    if not changed:
        print(f'沒有可撤銷的授權：{node_type} -> {org.code} ({org.secure_code})')
        return 0

    print(f'已撤銷：{node_type} -> {org.code} ({org.secure_code})')
    return 0


def main() -> int:
    if len(sys.argv) == 1:
        print(USAGE)
        return 0

    parser = _parser()
    args = parser.parse_args()

    _bootstrap()
    try:
        from app import create_app, db
    except Exception as exc:
        print(f'無法載入 Flask app：{exc}', file=sys.stderr)
        return 2

    app = create_app()
    with app.app_context():
        try:
            if args.command == 'list':
                return _list_grants()
            if args.command == 'grant':
                return _grant(args.node_type, args.org, args.granted_by_name, args.note)
            if args.command == 'revoke':
                return _revoke(args.node_type, args.org)
            parser.print_help()
            return 0
        except ValueError as exc:
            db.session.rollback()
            print(str(exc), file=sys.stderr)
            return 1
        except Exception as exc:
            db.session.rollback()
            print(f'執行失敗：{exc}', file=sys.stderr)
            return 3


if __name__ == '__main__':
    sys.exit(main())
