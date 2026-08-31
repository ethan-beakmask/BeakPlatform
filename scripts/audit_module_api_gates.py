#!/usr/bin/env python3
r"""
模組 API 身分閘門盤點（PF-145 階段二）

用 AST 解析 modules/<模組>/api 底下所有路由函式，取出實際掛著的 decorator，
依「最強閘門」分級，並反查前端呼叫者與可能對應的選單 code。

判級規則（與 dev-notes/PF145_MODULE_API_KEY1_AUDIT.md 一致）：
  A  只有 @module_access_required(mod, False)      僅驗企業合約，無 user_type 硬界線
  B  只有 @module_access_required(mod)             合約 + 模組 ACL（無 ACL 記錄時 fail-open）
  C  @require_permission / @permission_required    角色制，無 user_type 硬界線（PERM-03）
  D  @page_keys_required / @admin_required / @system_admin_required   有 user_type 硬界線
  E  webhook HMAC / service account / api key / @public_route         各自認證

為什麼不用 grep：spec_formulate 的路由全寫在 def register(bp) 內、decorator 有縮排，
grep '^@.*\.route(' 一支都抓不到（待辦卡上「spec_formulate 路由數 0」就是這樣來的）。
"""
import argparse
import ast
import collections
import csv
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULES = ['form_workflow', 'open_defense', 'nocode_builder',
           'vuln_lifecycle', 'spec_formulate']
SEARCH_DIRS = ['modules', 'backend/app/templates', 'backend/app/static']

STRONG = {'page_keys_required', 'admin_required', 'system_admin_required'}
ROLE = {'require_permission', 'permission_required', 'require_any_permission'}
OTHER = {'service_account_required', 'webhook_hmac_required',
         'api_key_hmac_required', 'api_key_required', 'public_route',
         'portal_login_required'}

# spec_formulate 的 _mf_*.py 走 register(bp)，bp 一律是 schema.py 的 schema_bp
REGISTER_BP_PREFIX = {'spec_formulate': '/api/spec-formulate/schema'}


def dec_name(node):
    """decorator 的可讀表示，含常數參數（判 check_acl=False 要靠它）。"""
    if isinstance(node, ast.Call):
        args = []
        for a in node.args:
            args.append(repr(a.value) if isinstance(a, ast.Constant) else '...')
        for kw in node.keywords:
            v = kw.value
            args.append(f'{kw.arg}={v.value!r}' if isinstance(v, ast.Constant)
                        else f'{kw.arg}=...')
        return f"{dec_name(node.func)}({', '.join(args)})"
    if isinstance(node, ast.Attribute):
        return f'{dec_name(node.value)}.{node.attr}'
    if isinstance(node, ast.Name):
        return node.id
    return '<expr>'


def collect_blueprint_prefixes():
    """掃 modules/*/api 全部 .py 的 Blueprint 定義，取 url_prefix。"""
    prefixes = {}
    for mod in MODULES:
        api_dir = os.path.join(ROOT, 'modules', mod, 'api')
        if not os.path.isdir(api_dir):
            continue
        for dirpath, _dirs, files in os.walk(api_dir):
            for fn in files:
                if not fn.endswith('.py'):
                    continue
                path = os.path.join(dirpath, fn)
                tree = ast.parse(open(path).read(), filename=path)
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Assign):
                        continue
                    v = node.value
                    if not (isinstance(v, ast.Call)
                            and getattr(v.func, 'id', None) == 'Blueprint'):
                        continue
                    if not isinstance(node.targets[0], ast.Name):
                        continue
                    up = ''
                    for kw in v.keywords:
                        if kw.arg == 'url_prefix' and isinstance(kw.value, ast.Constant):
                            up = kw.value.value
                    prefixes[(mod, node.targets[0].id)] = up
    return prefixes


def collect_routes(prefixes):
    rows = []
    for mod in MODULES:
        api_dir = os.path.join(ROOT, 'modules', mod, 'api')
        if not os.path.isdir(api_dir):
            continue
        for dirpath, _dirs, files in os.walk(api_dir):
            for fn in sorted(files):
                if not fn.endswith('.py'):
                    continue
                path = os.path.join(dirpath, fn)
                tree = ast.parse(open(path).read(), filename=path)
                for node in ast.walk(tree):
                    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    decs = [dec_name(d) for d in node.decorator_list]
                    routes = [d for d in decs if '.route(' in d]
                    if not routes:
                        continue
                    bp = routes[0].split('.route(')[0]
                    prefix = prefixes.get((mod, bp))
                    if prefix is None:
                        prefix = REGISTER_BP_PREFIX.get(mod, '?')
                    m = re.search(r"route\('([^']*)'", routes[0])
                    p = m.group(1) if m else '?'
                    rows.append({
                        'module': mod,
                        'file': os.path.relpath(path, ROOT),
                        'line': node.lineno,
                        'func': node.name,
                        'decorators': decs,
                        'prefix': prefix,
                        'path': p,
                        'full': (prefix if prefix != '?' else '') + p,
                    })
    return rows


def classify(r):
    heads = {d.split('(')[0].split('.')[-1] for d in r['decorators']}
    gates = [d for d in r['decorators']
             if d.split('(')[0].split('.')[-1] in (STRONG | ROLE | OTHER
                                                   | {'module_access_required'})]
    r['gates'] = gates
    if heads & STRONG:
        return 'D'
    if heads & OTHER:
        return 'E'
    if heads & ROLE:
        return 'C'
    if any(g.startswith('module_access_required') and 'False' in g for g in gates):
        return 'A'
    if any(g.startswith('module_access_required') for g in gates):
        return 'B'
    return 'X'


def grep_callers(frag):
    if len(frag) <= 8:
        return []
    out = subprocess.run(
        ['grep', '-rl', '--include=*.js', '--include=*.html', frag] + SEARCH_DIRS,
        cwd=ROOT, capture_output=True, text=True).stdout
    return sorted(x for x in out.strip().split('\n') if x)


def build_menu_index():
    """JS 檔 -> template -> web route function -> menu_items.code（候選，需人工確認）。"""
    render_map = collections.defaultdict(list)
    route_files = []
    for base in (os.path.join(ROOT, 'modules'), os.path.join(ROOT, 'backend', 'app', 'web')):
        for dirpath, _dirs, files in os.walk(base):
            if base.endswith('modules') and os.sep + 'web' not in dirpath:
                continue
            route_files += [os.path.join(dirpath, f) for f in files if f.endswith('.py')]
    for path in route_files:
        try:
            tree = ast.parse(open(path).read(), filename=path)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            tpls = [n.args[0].value for n in ast.walk(node)
                    if isinstance(n, ast.Call)
                    and getattr(n.func, 'id', None) == 'render_template'
                    and n.args and isinstance(n.args[0], ast.Constant)]
            for t in tpls:
                render_map[t].append(node.name)
    return render_map


def load_menus(dsn_args):
    """從 DB 取 menu_items 的 code 與 link_target（route 型別才有用）。"""
    sql = ("SELECT DISTINCT code, coalesce(link_target,'') FROM menu_items "
           "WHERE is_deleted=false AND link_type='route';")
    env = dict(os.environ, PGPASSWORD=dsn_args['password'])
    out = subprocess.run(
        ['psql', '-h', dsn_args['host'], '-U', dsn_args['user'], '-d', dsn_args['db'],
         '-t', '-A', '-F', '|', '-c', sql],
        capture_output=True, text=True, env=env).stdout
    menus = collections.defaultdict(list)
    for line in out.strip().split('\n'):
        if '|' not in line:
            continue
        code, target = line.split('|', 1)
        menus[target].append(code)
    return menus


def main():
    ap = argparse.ArgumentParser(
        description='盤點模組 API 的身分閘門（PF-145 階段二）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='範例：\n'
               '  venv/bin/python scripts/audit_module_api_gates.py --csv out.csv\n'
               '  venv/bin/python scripts/audit_module_api_gates.py --summary\n')
    ap.add_argument('--csv', metavar='路徑',
                    default='dev-notes/pf145_module_api_audit.csv',
                    help='盤點結果輸出的 CSV 路徑（預設 dev-notes/pf145_module_api_audit.csv）')
    ap.add_argument('--summary', action='store_true',
                    help='只印分級統計，不寫 CSV')
    ap.add_argument('--no-callers', action='store_true',
                    help='跳過前端呼叫者反查（快很多，但少了判斷依據）')
    ap.add_argument('--db', default='beakplatform_dev', help='資料庫名稱')
    ap.add_argument('--db-host', default='localhost', help='資料庫主機')
    ap.add_argument('--db-user', default='beakplatform', help='資料庫帳號')
    ap.add_argument('--db-password', default=os.getenv('PGPASSWORD', ''),
                    help='資料庫密碼（預設依序取 PGPASSWORD、repo .env 的 DATABASE_URL）')
    args = ap.parse_args()

    if not args.db_password:
        # 不硬編碼密碼（PF-199）：從 repo .env 的 DATABASE_URL 撈
        env_path = os.path.join(ROOT, '.env')
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    m = re.match(r'DATABASE_URL=postgresql://[^:]+:([^@]+)@', line.strip())
                    if m:
                        args.db_password = m.group(1)
                        break
    if not args.db_password:
        ap.error('未提供資料庫密碼：請設定 PGPASSWORD 或 --db-password，'
                 '或確認 repo .env 的 DATABASE_URL')

    prefixes = collect_blueprint_prefixes()
    rows = collect_routes(prefixes)
    for r in rows:
        r['level'] = classify(r)
        r['callers'] = [] if args.no_callers else grep_callers(
            r['full'].split('<')[0].rstrip('/'))

    render_map = build_menu_index()
    menus = load_menus({'db': args.db, 'host': args.db_host,
                        'user': args.db_user, 'password': args.db_password})
    for r in rows:
        cands = set()
        for c in r['callers']:
            # caller 是 template 就直接用它；是 JS 才要再找哪些 template include 它。
            # 只處理 .js 會漏掉「template 內嵌 script 直接打 API」的情況
            # （vuln_lifecycle 五個頁面全是這樣寫的）。
            if c.endswith('.html'):
                tpls = [c]
            elif c.endswith('.js'):
                tpls = subprocess.run(
                    ['grep', '-rl', '--include=*.html', os.path.basename(c),
                     'modules', 'backend/app/templates'],
                    cwd=ROOT, capture_output=True, text=True).stdout.strip().split('\n')
            else:
                continue
            for tpl in tpls:
                for key, funcs in render_map.items():
                    if not tpl or key not in tpl:
                        continue
                    for fn in funcs:
                        for target, codes in menus.items():
                            if target.endswith('.' + fn):
                                cands.update(codes)
        r['menu_candidates'] = sorted(cands)

    lv = collections.Counter(r['level'] for r in rows)
    by = collections.defaultdict(collections.Counter)
    for r in rows:
        by[r['module']][r['level']] += 1
    print(f'路由函式總數: {len(rows)}')
    print('分級:', dict(sorted(lv.items())))
    for m in MODULES:
        print(f'  {m:16}', dict(sorted(by[m].items())))

    if args.summary:
        return 0

    out_path = args.csv if os.path.isabs(args.csv) else os.path.join(ROOT, args.csv)
    with open(out_path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['level', 'module', 'url', 'file', 'line', 'func',
                    'gates', 'callers', 'menu_candidates'])
        for r in sorted(rows, key=lambda x: (x['level'], x['module'], x['full'])):
            w.writerow([
                r['level'], r['module'], r['full'], r['file'], r['line'], r['func'],
                ' + '.join(r['gates']),
                ';'.join(os.path.basename(c) for c in r['callers']
                         if c.endswith(('.js', '.html'))),
                ';'.join(r['menu_candidates']),
            ])
    print('CSV ->', out_path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
