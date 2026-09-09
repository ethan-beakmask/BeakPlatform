#!/usr/bin/env python3
"""
發放「防禦節點」憑證並產生開通字串（平台端）。

用途
    防禦節點（defense-node，另一台主機上的 WAF / IDS / od-bridge）要連回平台需要三樣東西：
      1. 平台網址
      2. 事件受理金鑰（API Key，scope 含 od_intake）——節點把偵測到的事件簽章後送進來
      3. 執行帳號（service account）——節點定期拉取平台核可的封鎖決策去落地
    本腳本一次建好 2 與 3，連同 1 打包成一行「開通字串」，貼給防禦節點的 install.sh 即可：

        sudo bash install.sh --pair 'ODN1....' --backend http://<被保護網站>

    秘密只在建立當下顯示一次，之後無法再取得；重跑本腳本會發一組新的（舊的仍有效，
    不需要時到「安全中心 / API Key」與「開放防禦 / 服務帳號」停用）。

前置
    企業必須已有 Open Defense 事件路由（否則事件送進來會得到 422 no_mapping）。
    還沒有的話加 --provision，會先呼叫 scripts/examples/provision_od_intake_for_org.py
    建立最小可用的受理鏈路（資安分類、表單、流程、路由規則）。

用法
    cd <安裝目錄>            # 例 /opt/BeakPlatform
    set -a && source .env && set +a
    venv/bin/python scripts/od_node_pairing.py --org demo.example --base-url http://192.168.1.16:8000/beakplatform --apply

參數
    --org <值>              必填。企業 secure_code 或 domain_name
    --base-url <URL>        防禦節點連回平台用的網址，含 /beakplatform 前綴。
                            省略時取「主機設定 / 系統對外網址」加上前綴
    --name <名稱>           節點名稱，用於金鑰與帳號的顯示名稱（預設 defense-node）
    --source-system <值>    可重複。事件來源白名單，預設 coraza suricata vector
    --enforcement-points    逗號分隔，執行帳號可落地的封鎖點，預設 nftables,crowdsec,edl,cloudflare
    --provision             企業尚無事件路由時先建立最小受理鏈路
    --apply                 實際建立；省略時只檢查並預演
"""
import argparse
import base64
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'backend'))
sys.path.insert(0, _REPO_ROOT)

DEFAULT_SOURCE_SYSTEMS = ['coraza', 'suricata', 'vector']
DEFAULT_EPS = 'nftables,crowdsec,edl,cloudflare'
PROVISION_SCRIPT = os.path.join(_REPO_ROOT, 'scripts', 'examples', 'provision_od_intake_for_org.py')


def log(msg=''):
    print(msg, flush=True)


def resolve_org(Organization, value):
    org = Organization.query.filter_by(secure_code=value, is_deleted=False).first()
    if not org:
        org = Organization.query.filter_by(domain_name=value, is_deleted=False).first()
    if not org:
        raise SystemExit(f'找不到企業：{value}（可填 secure_code 或 domain_name）')
    return org


def pick_admin(User, org_sc):
    admin = (User.query.filter_by(org_secure_code=org_sc, user_type='ORG_ADMIN',
                                  is_deleted=False, is_active=True)
             .order_by(User.id.asc()).first())
    return admin


def routing_ready(OdFormTemplateMapping, org_sc):
    return OdFormTemplateMapping.query.filter_by(
        org_secure_code=org_sc, is_active=True, is_deleted=False).count() > 0


def default_base_url():
    from app.utils.external_url import get_system_base_url
    base = get_system_base_url()
    if not base:
        return None
    prefix = os.environ.get('APP_PREFIX', '/beakplatform') or ''
    return base.rstrip('/') + prefix


def make_pair_string(payload):
    raw = json.dumps(payload, separators=(',', ':')).encode()
    return 'ODN1.' + base64.urlsafe_b64encode(raw).decode().rstrip('=')


def parse_args(argv):
    p = argparse.ArgumentParser(description='發放防禦節點憑證並產生開通字串',
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument('--org', required=True)
    p.add_argument('--base-url', default=None)
    p.add_argument('--name', default='defense-node')
    p.add_argument('--source-system', action='append', default=None)
    p.add_argument('--enforcement-points', default=DEFAULT_EPS)
    p.add_argument('--provision', action='store_true')
    p.add_argument('--apply', action='store_true')
    return p.parse_args(argv)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        log(__doc__)
        return 0
    args = parse_args(argv)
    source_systems = args.source_system or DEFAULT_SOURCE_SYSTEMS
    eps = [x.strip() for x in args.enforcement_points.split(',') if x.strip()]

    from app import create_app, db
    from app.models import Organization, User
    from app.services import api_key_service
    from modules.open_defense.models import OdFormTemplateMapping
    from modules.open_defense.services.service_account_service import create_service_account

    app = create_app(os.environ.get('FLASK_ENV', 'development'))
    with app.app_context():
        org = resolve_org(Organization, args.org)
        base_url = (args.base_url or default_base_url() or '').rstrip('/')
        log(f'企業：{org.name} / {org.domain_name} / {org.secure_code}')
        log(f'平台網址：{base_url or "（未設定，請用 --base-url 或在主機設定填「系統對外網址」）"}')
        if not base_url:
            return 1
        admin = pick_admin(User, org.secure_code)
        creator_sc = admin.secure_code if admin else None

        if not routing_ready(OdFormTemplateMapping, org.secure_code):
            if not args.provision:
                log('\n[!] 這家企業還沒有啟用中的事件路由規則，事件送進來會得到 422 no_mapping。')
                log('    加 --provision 讓本腳本先建立最小受理鏈路，或到「開放防禦 / 事件路由設定」自行建立。')
                return 1
            log('\n[provision] 企業尚無事件路由，先建立最小受理鏈路')
            cmd = [sys.executable, PROVISION_SCRIPT, '--org', org.secure_code, '--skip-api-key']
            for s in source_systems:
                cmd += ['--source-system', s]
            if args.apply:
                cmd.append('--apply')
            rc = subprocess.call(cmd, cwd=_REPO_ROOT)
            if rc != 0:
                log('[!] provision 失敗，中止')
                return rc
            db.session.expire_all()

        if not args.apply:
            log('\n預演模式：不會建立任何憑證。加上 --apply 才會實際建立。')
            log(f'  將建立 API Key「{args.name} intake」scope od_intake.source_systems={source_systems}')
            log(f'  將建立服務帳號「{args.name} executor」allowed_enforcement_points={eps}')
            return 0

        key, key_secret = api_key_service.create_api_key(
            org_secure_code=org.secure_code,
            name=f'{args.name} intake',
            consumer_label='defense-node',
            description='由 scripts/od_node_pairing.py 建立，防禦節點事件受理用',
            scopes={'od_intake': {'source_systems': source_systems}},
            created_by_secure_code=creator_sc,
        )
        sa, sa_secret = create_service_account(
            org_secure_code=org.secure_code,
            name=f'{args.name} executor',
            allowed_enforcement_points=eps,
            created_by_secure_code=creator_sc,
            sa_id_hint=args.name.replace('-', '_'),
        )
        db.session.commit()

        payload = {
            'v': 1, 'org': org.domain_name or org.secure_code, 'base_url': base_url,
            'key_id': key.key_id, 'secret': key_secret,
            'sa_id': sa.sa_id, 'sa_secret': sa_secret,
        }
        log('\n已建立：')
        log(f'  API Key   {key.key_id}（{key.name}）')
        log(f'  服務帳號  {sa.sa_id}（{sa.name}，EP={",".join(eps)}）')
        log('\n===== 開通字串（只顯示這一次，貼到防禦節點）=====')
        log(make_pair_string(payload))
        log('\n在防禦節點執行：')
        log("  sudo bash install.sh --pair '<上面那一行>' --backend http://<被保護網站>:<埠>")
        log('\n或手動填進防禦節點的 .env：')
        log(f'  BEAK_BASE_URL={base_url}')
        log(f'  INTAKE_KEY_ID={key.key_id}')
        log(f'  INTAKE_SECRET_B64={key_secret}')
        log(f'  SA_ID={sa.sa_id}')
        log(f'  SA_SECRET={sa_secret}')
        return 0


if __name__ == '__main__':
    sys.exit(main())
