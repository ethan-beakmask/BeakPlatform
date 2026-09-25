#!/usr/bin/env python3
"""補種資安表單填寫角色規則。"""
import argparse
import os
import sys

os.environ['SKIP_MODULE_SYNC'] = '1'
os.environ['EXECUTOR_STANDALONE'] = '1'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


ROLE_CODES = ['SECURITY_STAFF', 'SOC_SUPERVISOR']

USAGE = """用法:
  venv/bin/python scripts/seed_security_form_fill_permissions.py --org <secure_code|domain_name|all> [--apply]

說明:
  補上資安案件表單配對的填寫角色規則。預設 dry-run，只顯示將建立或已存在的規則；
  加上 --apply 才會寫入資料庫。角色不存在時會列入 missing_roles，不會中止。
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
        return None, 0
    parser = argparse.ArgumentParser(
        description='補種資安表單填寫角色規則',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=USAGE,
    )
    parser.add_argument(
        '--org',
        required=True,
        help='企業 secure_code、domain_name，或 all',
    )
    parser.add_argument(
        '--apply',
        action='store_true',
        help='實際寫入資料庫；省略時只做 dry-run',
    )
    return parser.parse_args(argv), 0


def _target_orgs(Organization, org_arg):
    if org_arg == 'all':
        return Organization.query.filter(
            Organization.is_deleted == False  # noqa: E712
        ).order_by(Organization.code.asc()).all()

    org = Organization.query.filter(
        Organization.is_deleted == False,  # noqa: E712
        (
            (Organization.secure_code == org_arg)
            | (Organization.domain_name == org_arg)
        ),
    ).first()
    return [org] if org else []


def _security_mappings(db, FwFormTemplate, FwFormWorkflowMapping, org_sc):
    from modules.form_workflow.services.security_center import SECURITY_CATEGORY_PREFIX

    return FwFormWorkflowMapping.query.join(
        FwFormTemplate,
        FwFormTemplate.secure_code == FwFormWorkflowMapping.form_template_secure_code,
    ).filter(
        FwFormWorkflowMapping.org_secure_code == org_sc,
        FwFormWorkflowMapping.is_deleted == False,  # noqa: E712
        FwFormTemplate.org_secure_code == org_sc,
        FwFormTemplate.is_deleted == False,  # noqa: E712
        FwFormTemplate.category_secure_code.like(f'{SECURITY_CATEGORY_PREFIX}%'),
    ).order_by(
        FwFormTemplate.code.asc(),
        FwFormWorkflowMapping.secure_code.asc(),
    ).all()


def main():
    args, exit_code = _parse_args(sys.argv[1:])
    if args is None:
        return exit_code

    _load_dotenv()
    from app import create_app, db
    from app.models import Organization
    from modules.form_workflow.models import FwFormTemplate, FwFormWorkflowMapping
    from modules.form_workflow.services.fill_permission_service import (
        ensure_role_fill_permissions,
    )

    app = create_app()
    with app.app_context():
        orgs = _target_orgs(Organization, args.org)
        if not orgs:
            print(f"找不到企業：{args.org}")
            return 1

        totals = {'created': 0, 'existing': 0, 'missing_roles': 0, 'mappings': 0}
        mode = 'apply' if args.apply else 'dry-run'
        print(f"模式：{mode}")
        print("角色：" + ', '.join(ROLE_CODES))

        for org in orgs:
            print(f"\n企業：{org.code} / {org.domain_name} / {org.secure_code}")
            mappings = _security_mappings(db, FwFormTemplate, FwFormWorkflowMapping, org.secure_code)
            if not mappings:
                print("  沒有資安表單配對")
                continue

            for mapping in mappings:
                totals['mappings'] += 1
                result = ensure_role_fill_permissions(
                    org.secure_code,
                    mapping.secure_code,
                    ROLE_CODES,
                    apply=args.apply,
                )
                totals['created'] += len(result['created'])
                totals['existing'] += len(result['existing'])
                totals['missing_roles'] += len(result['missing_roles'])
                print(
                    f"  mapping={mapping.secure_code} form={mapping.form_template_code}: "
                    f"created={result['created'] or []}, "
                    f"existing={result['existing'] or []}, "
                    f"missing_roles={result['missing_roles'] or []}"
                )

        if args.apply:
            db.session.commit()
            print("\n已寫入資料庫")
        else:
            db.session.rollback()
            print("\ndry-run，未寫入資料庫")

        print(
            "總計："
            f"mappings={totals['mappings']}, "
            f"created={totals['created']}, "
            f"existing={totals['existing']}, "
            f"missing_roles={totals['missing_roles']}"
        )

    return 0


if __name__ == '__main__':
    sys.exit(main())
