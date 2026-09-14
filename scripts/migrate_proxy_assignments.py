#!/usr/bin/env python3
"""PF-251 角色級代理指派資料遷移。

既有環境升級:

ALTER TABLE user_role_assignments ADD COLUMN IF NOT EXISTS assignment_kind VARCHAR(10) NOT NULL DEFAULT 'regular';
ALTER TABLE user_role_assignments ADD COLUMN IF NOT EXISTS acting_for_user_secure_code VARCHAR(32) REFERENCES users(secure_code);
ALTER TABLE user_role_assignments ADD COLUMN IF NOT EXISTS allowed_form_templates JSONB;
ALTER TABLE user_role_assignments ADD COLUMN IF NOT EXISTS source_ref VARCHAR(100);
ALTER TABLE user_role_assignments ADD COLUMN IF NOT EXISTS grant_reason TEXT;
ALTER TABLE fw_approval_records ADD COLUMN IF NOT EXISTS acted_as_kind VARCHAR(10);
CREATE INDEX IF NOT EXISTS ix_user_role_assignments_role_unit_kind
  ON user_role_assignments (org_secure_code, role_secure_code, unit_secure_code, assignment_kind) WHERE is_deleted = false;
"""
import os
import sys

os.environ['SKIP_MODULE_SYNC'] = '1'
os.environ['EXECUTOR_STANDALONE'] = '1'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


USAGE = """用法:
  scripts/migrate_proxy_assignments.py --dry-run
  scripts/migrate_proxy_assignments.py --apply
  scripts/migrate_proxy_assignments.py --dry-run --org ORG_CODE [--org ORG_CODE...]
  scripts/migrate_proxy_assignments.py --apply --org ORG_CODE [--org ORG_CODE...]

說明:
  PF-251 遷移：
  1. 補種 DEPT_HEAD 系統角色
  2. 將出廠預設 DEPT_MANAGER/DEPT_DEPUTY 顯示名改成新名稱
  3. 回填 DEPT_HEAD@單位 給既有正、副主管正式指派
  4. 既有 DEPT_MANAGER＋缺席順位關卡改指 DEPT_HEAD
  5. DEPT_PROXY1／DEPT_PROXY2 指派各遷成 DEPT_HEAD／DEPT_MANAGER／DEPT_DEPUTY 三列候補（standby），角色退役（決策點 K2）
  6. 未到期且未撤銷的 delegations 遷成角色 proxy 指派列，並全域退役舊代理選單與 DELEGATED 條件

  --dry-run 只顯示結果；--apply 才會寫入資料庫。
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
    if any(arg in ('--help', '-h') for arg in argv):
        _print_usage()
        return None, 0
    if not argv:
        _print_usage()
        return None, 1

    mode = None
    org_codes = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ('--dry-run', '--apply'):
            if mode is not None:
                _print_usage()
                return None, 1
            mode = arg
            i += 1
            continue
        if arg == '--org':
            if i + 1 >= len(argv) or argv[i + 1].startswith('--'):
                _print_usage()
                return None, 1
            org_codes.append(argv[i + 1])
            i += 2
            continue
        _print_usage()
        return None, 1

    if mode is None:
        _print_usage()
        return None, 1
    return (mode, org_codes), 0


def _empty_counts():
    return {
        'roles_created': 0,
        'roles_skipped': 0,
        'renamed': 0,
        'rename_skipped': 0,
        'head_created': 0,
        'head_revived': 0,
        'head_skipped': 0,
        'gate_skipped_no_role': 0,
        'gate_templates': 0,
        'gate_template_nodes': 0,
        'gate_snapshots': 0,
        'gate_snapshot_nodes': 0,
        'proxy_rows_migrated': 0,
        'proxy_rows_dropped_no_unit': 0,
        'standby_created': 0,
        'standby_revived': 0,
        'standby_skipped': 0,
        'proxy_roles_deleted': 0,
        'delegation_migrated': 0,
        'delegation_skipped_empty_scope': 0,
        'delegation_skipped_approval_limit': 0,
        'delegation_skipped_type': 0,
        'delegation_skipped_delegate_inactive': 0,
        'delegation_skipped_no_roles': 0,
        'proxy_rows_layer_skipped': 0,
        'proxy_created': 0,
        'proxy_revived': 0,
        'proxy_skipped': 0,
        'menu_retired': 0,
        'condition_retired': 0,
    }


def seed_dept_head_role(org, ctx):
    Role = ctx['Role']
    build_dept_head_role = ctx['build_dept_head_role']
    db = ctx['db']

    manager = Role.query.filter(
        Role.org_secure_code == org.secure_code,
        Role.code == 'DEPT_MANAGER',
        Role.is_deleted == False,  # noqa: E712
    ).first()
    if not manager:
        return {'roles_skipped': 1}

    existing = Role.query.filter(
        Role.org_secure_code == org.secure_code,
        Role.code == 'DEPT_HEAD',
        Role.is_deleted == False,  # noqa: E712
    ).first()
    if existing:
        return {'roles_skipped': 1}

    role = build_dept_head_role(org.secure_code)
    role.update_full_path()
    db.session.add(role)
    return {'roles_created': 1}


def rename_dept_roles(org, ctx):
    Role = ctx['Role']
    constants = ctx['constants']
    renamed = 0
    skipped = 0
    descriptions = {
        'DEPT_MANAGER': constants['DEPT_MANAGER_ROLE_DESCRIPTION'],
        'DEPT_DEPUTY': constants['DEPT_DEPUTY_ROLE_DESCRIPTION'],
    }
    for code, (old_name, new_name) in constants['DEPT_ROLE_RENAMES'].items():
        role = Role.query.filter(
            Role.org_secure_code == org.secure_code,
            Role.code == code,
            Role.is_deleted == False,  # noqa: E712
        ).first()
        if not role:
            skipped += 1
            continue
        if role.name == old_name:
            role.name = new_name
            role.description = descriptions[code]
            renamed += 1
        else:
            skipped += 1
    return {'renamed': renamed, 'rename_skipped': skipped}


def backfill_dept_head(org, ctx):
    Role = ctx['Role']
    UserRoleAssignment = ctx['UserRoleAssignment']
    AssignmentKind = ctx['AssignmentKind']
    db = ctx['db']

    head_role = Role.query.filter(
        Role.org_secure_code == org.secure_code,
        Role.code == 'DEPT_HEAD',
        Role.is_deleted == False,  # noqa: E712
    ).first()
    if not head_role:
        return {}

    source_roles = Role.query.filter(
        Role.org_secure_code == org.secure_code,
        Role.code.in_(('DEPT_MANAGER', 'DEPT_DEPUTY')),
        Role.is_deleted == False,  # noqa: E712
    ).all()
    source_role_scs = {role.secure_code for role in source_roles}
    if not source_role_scs:
        return {}

    sources = UserRoleAssignment.query.filter(
        UserRoleAssignment.org_secure_code == org.secure_code,
        UserRoleAssignment.role_secure_code.in_(source_role_scs),
        UserRoleAssignment.assignment_kind == AssignmentKind.REGULAR,
        UserRoleAssignment.is_deleted == False,  # noqa: E712
    ).order_by(
        UserRoleAssignment.role_secure_code.asc(),
        UserRoleAssignment.assigned_at.asc(),
        UserRoleAssignment.id.asc(),
    ).all()
    sources.sort(key=lambda row: (
        0 if next((r.code for r in source_roles if r.secure_code == row.role_secure_code), '') == 'DEPT_MANAGER' else 1,
        row.assigned_at,
        row.id,
    ))

    created = 0
    revived = 0
    skipped = 0
    for source in sources:
        existing = UserRoleAssignment.query.filter(
            UserRoleAssignment.org_secure_code == org.secure_code,
            UserRoleAssignment.user_secure_code == source.user_secure_code,
            UserRoleAssignment.role_secure_code == head_role.secure_code,
            UserRoleAssignment.unit_secure_code == source.unit_secure_code,
            UserRoleAssignment.assignment_kind == AssignmentKind.REGULAR,
        ).order_by(
            UserRoleAssignment.is_deleted.asc(),
            UserRoleAssignment.id.asc(),
        ).first()
        if existing and not existing.is_deleted:
            skipped += 1
            continue
        if existing and existing.is_deleted:
            existing.is_deleted = False
            existing.deleted_at = None
            existing.valid_from = source.valid_from
            existing.valid_until = source.valid_until
            existing.source_ref = 'migration:pf251'
            revived += 1
            continue

        db.session.add(UserRoleAssignment(
            org_secure_code=org.secure_code,
            user_secure_code=source.user_secure_code,
            role_secure_code=head_role.secure_code,
            unit_secure_code=source.unit_secure_code,
            valid_from=source.valid_from,
            valid_until=source.valid_until,
            assigned_by='migration:pf251',
            source_ref='migration:pf251',
            assignment_kind=AssignmentKind.REGULAR,
        ))
        created += 1

    return {
        'head_created': created,
        'head_revived': revived,
        'head_skipped': skipped,
    }


STEPS = (
    seed_dept_head_role,
    rename_dept_roles,
    backfill_dept_head,
)


def _merge_counts(target, incoming):
    for key, value in incoming.items():
        target[key] = target.get(key, 0) + value


def main():
    parsed, exit_code = _parse_args(sys.argv[1:])
    if parsed is None:
        return exit_code
    mode, org_codes = parsed

    _load_dotenv()
    from app import create_app, db
    from app.models import AssignmentKind, Organization, Role, UserRoleAssignment
    from app.services.organization_service import (
        DEPT_DEPUTY_ROLE_DESCRIPTION,
        DEPT_MANAGER_ROLE_DESCRIPTION,
        DEPT_ROLE_RENAMES,
        build_dept_head_role,
    )

    app = create_app()
    with app.app_context():
        from modules.form_workflow.models import FwPublishedFormWorkflow, FwWorkflowTemplate
        from modules.form_workflow.services.manager_gate_migration import migrate_org_manager_gates
        from app.services.delegation_migration import migrate_org_delegations, retire_delegation_globals
        from app.services.proxy_role_migration import migrate_org_proxy_roles
        steps = (*STEPS, migrate_org_manager_gates, migrate_org_proxy_roles, migrate_org_delegations)

        query = Organization.query.filter(Organization.is_deleted == False)  # noqa: E712
        if org_codes:
            query = query.filter(Organization.code.in_(org_codes))
        orgs = query.order_by(Organization.code.asc()).all()

        ctx = {
            'db': db,
            'Role': Role,
            'UserRoleAssignment': UserRoleAssignment,
            'AssignmentKind': AssignmentKind,
            'FwWorkflowTemplate': FwWorkflowTemplate,
            'FwPublishedFormWorkflow': FwPublishedFormWorkflow,
            'build_dept_head_role': build_dept_head_role,
            'constants': {
                'DEPT_ROLE_RENAMES': DEPT_ROLE_RENAMES,
                'DEPT_MANAGER_ROLE_DESCRIPTION': DEPT_MANAGER_ROLE_DESCRIPTION,
                'DEPT_DEPUTY_ROLE_DESCRIPTION': DEPT_DEPUTY_ROLE_DESCRIPTION,
            },
        }
        total = _empty_counts()
        for org in orgs:
            counts = _empty_counts()
            for step in steps:
                _merge_counts(counts, step(org, ctx))
            _merge_counts(total, counts)
            print(f"{org.code}: " + ', '.join(f'{k}={v}' for k, v in counts.items()))

        global_counts = retire_delegation_globals(ctx)
        _merge_counts(total, global_counts)
        print('全域: ' + ', '.join(f'{k}={v}' for k, v in global_counts.items()))

        if mode == '--apply':
            db.session.commit()
            print("已寫入資料庫")
        else:
            db.session.rollback()
            print("預覽，未寫入")

        print('總計: ' + ', '.join(f'{k}={v}' for k, v in total.items()))

    return 0


if __name__ == '__main__':
    sys.exit(main())
