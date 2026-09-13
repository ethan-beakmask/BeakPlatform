#!/usr/bin/env python3
"""一鍵建立企業級示範企業資料包。"""
import argparse
import os
import secrets
import string
import sys
from copy import deepcopy

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'backend'))
sys.path.insert(0, _REPO_ROOT)

from scripts.seed_test_companies import seed_one_company  # noqa: E402


DEMO_COMPANY = {
    'code': 'DEMOSOC',
    'name': '示範企業 DemoSOC',
    'domain': 'demo-soc.example',
    'display_name': 'DemoSOC',
    'contact_person': '晧承宇',
    'contact_email': 'contact@demo-soc.example',
    'contact_phone': '02-2700-0099',
    'description': '企業級資料包 -- 人資結構、Open Defense、表單流程示範',
    'country': 'TW',
    'user_limit': 50,
    'modules_config': ['form_workflow', 'open_defense', 'nocode_builder', 'spec_formulate', 'vuln_lifecycle'],
    'numbering': {
        'employee': {
            'name': '示範企業成員編號',
            'elements': {
                'components': [
                    {'type': 'prefix', 'order': 1, 'values': ['DC']},
                    {'type': 'sequence', 'order': 2, 'start': 1, 'digits': 4, 'reset_period': 'never'},
                ],
                'total_length': 6,
            },
        },
        'external': {
            'name': '示範外部廠商編號',
            'elements': {
                'components': [
                    {'type': 'prefix', 'order': 1, 'values': ['DCX']},
                    {'type': 'sequence', 'order': 2, 'start': 1, 'digits': 3, 'reset_period': 'never'},
                ],
                'total_length': 6,
            },
        },
    },
    'extra_families': [
        ('SEC', '資安職', 'Security Position', 'PROFESSIONAL', 'PROF', '資安監控、事件處置與威脅分析'),
        ('OPS', '營運職', 'Operations Position', 'PROFESSIONAL', 'PROF', '客戶營運與日常支援'),
    ],
    'extra_titles': [
        ('SOC_ANALYST', 'SOC 分析師', 'SOC Analyst', 'L100', 'SEC', False),
        ('SR_SOC_ANALYST', '高級 SOC 分析師', 'Senior SOC Analyst', 'L200', 'SEC', False),
        ('SEC_MGR', '資安經理', 'Security Manager', 'L500', 'MGR', True),
        ('OPS_SPEC', '營運專員', 'Operations Specialist', 'L100', 'OPS', False),
    ],
    'departments': [
        ('總經理室', 'GM', None),
        ('資訊處', 'INFO_DIV', 'GM'),
        ('資安部', 'SEC_DEPT', 'INFO_DIV'),
        ('平台維運部', 'IT_OPS', 'INFO_DIV'),
        ('營運部', 'OPS_DIV', 'GM'),
        ('客戶營運組', 'CUSTOMER_OPS', 'OPS_DIV'),
        ('人資行政部', 'HR_ADMIN', 'GM'),
        ('財務部', 'FIN', 'GM'),
    ],
    'employees': [
        ('david.hao', '晧承宇', 'David Hao', 'GM', 'PRES', True),
        ('amy.xiao', '霄以安', 'Amy Xiao', 'INFO_DIV', 'DIR', True),
        ('kevin.ye', '燁守澄', 'Kevin Ye', 'SEC_DEPT', 'SEC_MGR', True),
        ('linda.hu', '琥琳恩', 'Linda Hu', 'SEC_DEPT', 'SR_SOC_ANALYST', False),
        ('jason.ling', '翎杰安', 'Jason Ling', 'SEC_DEPT', 'SOC_ANALYST', False),
        ('sophia.li', '璃書涵', 'Sophia Li', 'IT_OPS', 'MGR', True),
        ('ryan.lan', '嵐睿遠', 'Ryan Lan', 'OPS_DIV', 'DIR', True),
        ('emma.feng', '灃艾瑪', 'Emma Feng', 'CUSTOMER_OPS', 'MGR', True),
        ('leo.heng', '珩立恩', 'Leo Heng', 'CUSTOMER_OPS', 'OPS_SPEC', False),
        ('mia.che', '澈明雅', 'Mia Che', 'HR_ADMIN', 'SUPV', True),
        ('tom.hao', '晧志明', 'Tom Hao', 'FIN', 'SUPV', True),
        ('nina.xiao', '霄寧娜', 'Nina Xiao', 'IT_OPS', 'ENG', False),
    ],
    'admin_member': ('admin.ops', '璃安琪', 'Angel Li', 'GM', 'ADMIN_SPEC', False),
    'groups': [
        ('EXT_PARTNER', '外部合作夥伴'),
    ],
    'external_users': [],
}

SECURITY_STAFF_USERS = ['linda.hu', 'jason.ling']
SECURITY_SUPERVISOR_USER = 'kevin.ye'
APPLICANT_USER = 'leo.heng'
MANAGER_CHAIN = ['leo.heng', 'emma.feng', 'ryan.lan']


def log(message):
    print(message, flush=True)


def _generated_password():
    alphabet = string.ascii_letters + string.digits + '!@#$%^&*'
    while True:
        value = ''.join(secrets.choice(alphabet) for _ in range(16))
        if (any(c.islower() for c in value)
                and any(c.isupper() for c in value)
                and any(c.isdigit() for c in value)
                and any(c in '!@#$%^&*' for c in value)):
            return value


def _resolve_password(args):
    if args.password:
        return args.password, False
    env_password = os.getenv('DEMO_ORG_PASSWORD')
    if env_password:
        return env_password, False
    return _generated_password(), True


def _company_from_args(args):
    company = deepcopy(DEMO_COMPANY)
    company['code'] = args.code
    company['domain'] = args.domain
    company['contact_email'] = f"contact@{args.domain}"
    return company


def _preflight(company, password):
    from flask import current_app

    from app.models import Module, Organization
    from app.services.password_policy_service import PasswordPolicyService

    log('[1/8] 前置檢查')
    system_org = Organization.query.filter_by(code='SYSTEM', is_deleted=False).first()
    if not system_org:
        raise RuntimeError('找不到系統企業 SYSTEM')

    missing_modules = []
    loader = current_app.extensions.get('module_loader')
    for code in company['modules_config']:
        module = Module.query.filter_by(code=code, is_deleted=False, is_active=True).first()
        loaded = bool(loader and loader.get_module(code))
        if not module and not loaded:
            missing_modules.append(code)
    if missing_modules:
        raise RuntimeError(f"模組未註冊: {', '.join(missing_modules)}")

    existing = Organization.query.filter(
        Organization.domain_name == company['domain'],
        Organization.is_deleted == False,
    ).first()
    if existing:
        log(f"企業 domain {company['domain']} 已存在，移除請由系統管理員硬刪除該企業")
        raise SystemExit(2)

    pw_valid, pw_errors = PasswordPolicyService.validate_password(password, None)
    if not pw_valid:
        raise RuntimeError('密碼不符合政策: ' + '；'.join(pw_errors))


def _assign_security_roles(org, company):
    from app import db
    from app.models import Role, User
    from app.services.role_assignment_service import assign_role

    log('[4/8] 指派資安人員角色')
    operator = User.query.filter_by(
        org_secure_code=org.secure_code,
        email=f"admin-{company['admin_member'][0]}@{org.domain_name}",
        user_type='ORG_ADMIN',
        is_deleted=False,
        is_active=True,
    ).first()
    if not operator:
        raise RuntimeError('找不到新建立的企業管理員，無法指派資安角色')

    role = Role.query.filter_by(
        org_secure_code=org.secure_code,
        code='SECURITY_STAFF',
        is_deleted=False,
        is_active=True,
    ).first()
    if not role:
        raise RuntimeError('找不到 SECURITY_STAFF 角色，請確認 open_defense 模組已採購')

    assigned = []
    for username in SECURITY_STAFF_USERS:
        user = User.query.filter_by(
            org_secure_code=org.secure_code,
            username=username,
            is_deleted=False,
            is_active=True,
        ).first()
        if not user:
            raise RuntimeError(f'找不到資安人員帳號 {username}')
        assign_role(
            org.secure_code,
            user.secure_code,
            role.secure_code,
            operator=operator,
            source_ref='seed_demo_org',
            commit=False,
        )
        assigned.append(user)
    db.session.flush()
    return assigned


def _user_email(org, username):
    return f'{username}@{org.domain_name}'


def _published_flows(org):
    from modules.form_workflow.models import FwPublishedFormWorkflow
    rows = FwPublishedFormWorkflow.query.filter_by(
        org_secure_code=org.secure_code,
        status='Published',
        is_deleted=False,
    ).order_by(FwPublishedFormWorkflow.created_at.asc()).all()
    return [(row.name, row.secure_code) for row in rows]


def _print_summary(org, company, password, generated_password, db_result, node_showcase_result=None):
    log('\n' + '=' * 72)
    log('示範企業佈建完成')
    log('=' * 72)
    log(f"企業 code/domain/secure_code: {org.code} / {org.domain_name} / {org.secure_code}")
    log(f"管理員帳號: admin-{company['admin_member'][0]}@{org.domain_name}")
    log('資安人員帳號: ' + ', '.join(_user_email(org, u) for u in SECURITY_STAFF_USERS))
    log(f"資安主管帳號: {_user_email(org, SECURITY_SUPERVISOR_USER)}")
    log('申請人與主管鏈範例: ' + ' -> '.join(_user_email(org, u) for u in MANAGER_CHAIN))
    log(f"企業資料庫: {db_result.get('status')} {db_result.get('db_name') or ''} {db_result.get('message') or ''}".strip())
    log('已發行流程:')
    for name, secure_code in _published_flows(org):
        log(f'  - {name}: {secure_code}')
    if node_showcase_result is not None:
        log(
            'node展覽館: '
            f"done={len(node_showcase_result.get('done', []))} "
            f"skipped={len(node_showcase_result.get('skipped', []))} "
            f"failed={len(node_showcase_result.get('failed', []))}"
        )
        for name, reason in node_showcase_result.get('skipped', []):
            log(f'  - SKIP {name}: {reason}')
    marker = '（自動產生，只顯示這一次）' if generated_password else '（只顯示這一次）'
    log(f'示範帳號共用密碼 {marker}: {password}')
    log('下一步:')
    log(f"  - 配對防禦節點: scripts/od_node_pairing.py --org {org.domain_name} --apply")
    log('  - 用申請人帳號登入表單中心，送出「差旅費申請（人事取值示範）」查看核決鏈')


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description='建立示範企業資料包',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
用法:
  set -a && source .env && set +a
  venv/bin/python scripts/seed_demo_org.py --dry-run
  venv/bin/python scripts/seed_demo_org.py --apply --password '<密碼>'
  venv/bin/python scripts/seed_demo_org.py --apply --node-showcase --password '<密碼>'
        """,
    )
    parser.add_argument('--dry-run', action='store_true', help='只檢查與預演，不寫入')
    parser.add_argument('--apply', action='store_true', help='實際建立示範企業')
    parser.add_argument('--password', default=None, help='示範帳號共用密碼；未給則讀 DEMO_ORG_PASSWORD 或自動產生')
    parser.add_argument('--code', default='DEMOSOC', help='企業 code，預設 DEMOSOC')
    parser.add_argument('--domain', default='demo-soc.example', help='企業登入 domain，預設 demo-soc.example')
    parser.add_argument('--node-showcase', action='store_true',
                        help='建立示範企業時一併佈建企業級 node展覽館；受限節點示範自動跳過')
    args = parser.parse_args(argv)
    if not args.dry_run and not args.apply:
        parser.print_help()
        raise SystemExit(1)
    if args.dry_run and args.apply:
        raise SystemExit('--dry-run 與 --apply 只能擇一')
    return args


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    password, generated_password = _resolve_password(args)
    company = _company_from_args(args)

    from app import create_app, db
    from app.models import Organization
    from app.services.org_database_service import ensure_org_database
    from scripts.examples.node_showcase import seed_node_showcase
    from scripts.examples import provision_hr_lookup_demo
    from scripts.examples import provision_od_intake_for_org
    from scripts.examples import provision_od_workflow_variants

    app = create_app('development')
    with app.app_context():
        try:
            _preflight(company, password)
            verb = '將' if args.dry_run else '開始'
            log(f"[2/8] {verb}建立企業、人資結構與已綁定管理員")
            org = None
            if args.apply:
                org = seed_one_company(
                    company,
                    password=password,
                    commit=False,
                    emit_summary=False,
                )
            else:
                log(f"  將建立 {company['name']} ({company['code']}) / {company['domain']}")
                log(f"  將建立 {len(company['departments'])} 個部門、{len(company['employees']) + 1} 位企業成員")

            org_sc = org.secure_code if org else '<apply 後產生>'
            log('[3/8] 企業資料庫')
            if args.apply:
                log('  將在主資料 commit 後呼叫 ensure_org_database(org)')
                _assign_security_roles(org, company)
            else:
                log('  將在主資料 commit 後確保企業專屬資料庫')
                log('[4/8] 將指派資安人員角色')

            log('[5/8] Open Defense 受理鏈路')
            if args.apply:
                provision_od_intake_for_org.provision(
                    org_sc,
                    True,
                    skip_api_key=True,
                )
            else:
                log('  將建立資安分類、受理表單、受理流程、發行版本與 catch-all 路由')

            log('[6/8] Open Defense 流程變體與啟用中路由')
            if args.apply:
                provision_od_workflow_variants.provision(
                    org_sc,
                    True,
                    with_routing=True,
                    supervisor_email=_user_email(org, SECURITY_SUPERVISOR_USER),
                    soc_min_severity=3,
                    activate_soc_routing=True,
                )
            else:
                log('  將建立 SOC 團隊版與小企業單人版，並啟用 severity_id >= 3 的 SOC 路由')

            log('[7/8] 人事取值示範流程')
            if args.apply:
                provision_hr_lookup_demo.run(company['code'], apply=True)
            else:
                log('  將建立並發行差旅費申請（人事取值示範）')

            node_showcase_result = None
            if args.node_showcase:
                log('[8/8] 企業級 node展覽館')
                if args.apply:
                    node_showcase_result = seed_node_showcase(
                        org,
                        apply=True,
                        password=password,
                    )
                    for name, reason in node_showcase_result.get('skipped', []):
                        log(f'  - SKIP {name}: {reason}')
                    failed = node_showcase_result.get('failed', [])
                    if failed:
                        detail = '；'.join(f'{name}: {err}' for name, err in failed)
                        raise RuntimeError(f'node展覽館佈建失敗: {detail}')
                    log(
                        f"  done={len(node_showcase_result.get('done', []))} "
                        f"skipped={len(node_showcase_result.get('skipped', []))} failed=0"
                    )
                else:
                    log('  將佈建企業級 node展覽館；受限節點示範會依授權自動跳過')

            if args.apply:
                db.session.commit()
                db_result = ensure_org_database(org)
                db.session.refresh(org)
                _print_summary(
                    org,
                    company,
                    password,
                    generated_password,
                    db_result,
                    node_showcase_result=node_showcase_result,
                )
            else:
                db.session.rollback()
                log('[8/8] 預演完成，未寫入任何資料')
            return 0
        except SystemExit:
            db.session.rollback()
            raise
        except Exception as exc:
            db.session.rollback()
            log(f'失敗步驟: {exc}')
            return 1


if __name__ == '__main__':
    raise SystemExit(main())
