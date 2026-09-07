#!/usr/bin/env python3
"""
建置代理指定申請單與同意流程。

用途
    在指定企業內建立「代理指定申請單」的完整鏈路：

      1. 表單模板 PROXY_REQUEST
      2. 流程模板 PROXY_REQUEST_FLOW
      3. 表單流程配對並發行
      4. 兩筆配對填寫權限，讓企業成員、企業管理員可申請

    腳本冪等，重跑不會新增重複資料；只做建置，不做任何刪除。
    權威資料定義在 app.defaults.proxy_request_defaults，本腳本只負責 CLI。

用法
    cd /opt/BeakPlatform-dev
    set -a && source .env && set +a
    venv/bin/python scripts/examples/provision_proxy_request_flow.py --org beluga.com --apply

參數
    --apply      實際寫入資料庫；省略時只做檢查與預演
    --org <值>   企業 secure_code 或 domain_name；實際建置時必填
    --force      表單／流程已存在時覆寫內容、bump revision 並重新發行
"""
import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'backend'))
sys.path.insert(0, _REPO_ROOT)

from app.defaults.proxy_request_defaults import (  # noqa: E402
    FORM_CODE, WORKFLOW_CODE, MAPPING_PERMISSION_SPECS, describe_org_state,
    seed_org_proxy_request_flow,
)


def log(msg):
    print(msg, flush=True)


def resolve_org(Organization, org_arg):
    org = Organization.query.filter_by(
        secure_code=org_arg, is_deleted=False).first()
    if not org:
        org = Organization.query.filter_by(
            domain_name=org_arg, is_deleted=False).first()
    if org:
        return org

    log(f'找不到企業：{org_arg}')
    log('可用企業：')
    for item in Organization.query.filter_by(is_deleted=False).order_by(Organization.id).all():
        log(f'  {item.secure_code} | {item.domain_name or ""} | {item.name}')
    raise SystemExit('請用 --org 指定上列企業的 secure_code 或 domain_name')


def list_available_orgs(Organization):
    log('可用企業：')
    for item in Organization.query.filter_by(is_deleted=False).order_by(Organization.id).all():
        log(f'  {item.secure_code} | {item.domain_name or ""} | {item.name}')


def _print_state(state, *, force=False):
    log('\n[1/4] 表單模板')
    if state['form']['exists']:
        action = '會覆寫' if force else '已存在'
        log(f'  {action}表單 {FORM_CODE}：{state["form"]["secure_code"]}')
    else:
        log(f'  [預演] 會建立表單 {FORM_CODE}')

    log('\n[2/4] 流程模板')
    if state['workflow']['exists']:
        action = '會覆寫' if force else '已存在'
        log(f'  {action}流程 {WORKFLOW_CODE}：{state["workflow"]["secure_code"]}')
        log(f'  graph 欄位：{"已存在" if state["workflow"]["has_graph"] else "缺少"}')
        log(f'  cytoscape_config 欄位：{"已存在" if state["workflow"]["has_cytoscape"] else "缺少"}')
    else:
        log(f'  [預演] 會建立流程 {WORKFLOW_CODE}')

    log('\n[3/4] 配對與發行')
    if state['mapping']['exists']:
        log(f'  配對已存在：{state["mapping"]["secure_code"]}')
    else:
        log('  [預演] 會建立表單流程配對')
    if state['published']['exists']:
        log(
            f'  發行版本已存在 v{state["published"]["publish_version"]}：'
            f'{state["published"]["secure_code"]}'
        )
    else:
        log('  [預演] 會發行目前版本')

    log('\n[4/4] 填寫權限')
    existing = {
        (item['grant_type'], item['grant_target'], item['include_children'])
        for item in state['permissions']
    }
    for grant_type, grant_target, grant_target_name, include_children in MAPPING_PERMISSION_SPECS:
        label = f'{grant_type}:{grant_target}（{grant_target_name}）'
        if (grant_type, grant_target, include_children) in existing:
            log(f'  填寫權限已存在 {label}')
        else:
            log(f'  [預演] 會確保填寫權限 {label}')


def main():
    parser = argparse.ArgumentParser(
        description='建置代理指定申請單與同意流程',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--apply', action='store_true',
                        help='實際寫入資料庫；省略時只做檢查與預演')
    parser.add_argument('--org', default=None,
                        help='企業 secure_code 或 domain_name；實際建置時必填')
    parser.add_argument('--force', action='store_true',
                        help='表單／流程已存在時覆寫內容、bump revision 並重新發行')
    args = parser.parse_args()

    from app import create_app, db
    from app.models import Organization

    app = create_app('development')
    with app.app_context():
        if not args.org:
            if args.apply:
                raise SystemExit('實際寫入資料庫時必須指定 --org')
            log('未指定 --org，預演模式只列出可用企業，不寫入資料庫。')
            list_available_orgs(Organization)
            db.session.rollback()
            return

        org = resolve_org(Organization, args.org)
        org_sc = org.secure_code
        log(f'企業：{org.secure_code} | {org.domain_name or ""} | {org.name}')

        state = describe_org_state(org_sc)
        if args.apply:
            result = seed_org_proxy_request_flow(org_sc, force=args.force)
            if not result.get('ok'):
                db.session.rollback()
                log(f'建置失敗：{result.get("reason")}')
                if result.get('error'):
                    log(f'錯誤：{result["error"]}')
                if result.get('problems'):
                    for problem in result['problems']:
                        log(f'  - {problem}')
                raise SystemExit(1)
            if result.get('skipped'):
                db.session.rollback()
                log(f'建置跳過：{result.get("reason")}')
                return

            db.session.commit()
            log('\n已 commit')
            log('\n' + '=' * 72)
            log('建置完成，識別碼如下')
            log('=' * 72)
            log(f'表單模板 secure_code / code：{result["form_secure_code"]} / {FORM_CODE}')
            log(f'流程模板 secure_code / code：{result["workflow_secure_code"]} / {WORKFLOW_CODE}')
            log(f'配對 secure_code：{result["mapping_secure_code"]}')
            log(
                f'發行版本 secure_code / publish_version：'
                f'{result["published_secure_code"]} / {result["publish_version"]}'
            )
            log('以下網址都要加 nginx 前綴 /beakplatform：')
            log(f'  表單設計器：/forms/templates/{result["form_secure_code"]}')
            log(f'  流程設計器：/forms/workflows/{result["workflow_secure_code"]}')
            log(f'  表單中心填寫：/forms/center?fill={result["published_secure_code"]}')
            return

        _print_state(state, force=args.force)
        db.session.rollback()
        log('\n預演模式，未寫入任何資料。加上 --apply 才會實際建置')


if __name__ == '__main__':
    main()
