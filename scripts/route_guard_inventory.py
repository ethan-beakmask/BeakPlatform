#!/usr/bin/env python3
"""
產生與檢查 Flask route guard 宣告表。

無參數時只顯示使用說明；實際操作請用 --check、--update 或 --stats。
"""
import argparse
import ast
import inspect
import os
import sys
from collections import Counter
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / 'backend'
TABLE_PATH = BACKEND_ROOT / 'app' / 'security' / 'route_guard_table.yaml'
MANUAL_FIELDS = ('max_audience', 'review', 'note')
GUARD_NAMES = {
    'login_required',
    'admin_required',
    'system_admin_required',
    'page_keys_required',
    'permission_required',
    'require_permission',
    'require_any_permission',
    'module_access_required',
    'service_account_required',
    'webhook_hmac_required',
    'api_key_hmac_required',
    'public_route',
}
# answer_source：這條路由的「誰進得來」由誰決定。
# 這是程式碼事實（由哪個機制回答），不是答案本身，所以不隨企業資料變動。
#   code -- decorator 直接鎖死身分上限，讀程式碼即可確認
#   db   -- 要查資料庫（選單 Key1/Key2、模組合約與 ACL、permission 指派）才有答案
#   none -- 沒有任何收斂身分的守門，任何登入帳號都到得了
# 注意：本欄只從 decorator 推導，**不含 PageRoleGuard 的選單前綴涵蓋**
# （那需要查 menu_items）。所以標成 none 的路由仍可能被某個 url 型選單的領地涵蓋，
# 複審時要另外查。詳見 dev-notes/ROUTE_GUARD_TABLE_SPEC.md。
CODE_ANSWER_GUARDS = {
    'system_admin_required',
    'admin_required',
    'public_route',
    'service_account_required',
    'webhook_hmac_required',
    'api_key_hmac_required',
}
DB_ANSWER_GUARDS = {
    'page_keys_required',
    'module_access_required',
    'permission_required',
    'require_permission',
    'require_any_permission',
}
# login_required 刻意不列入任何一邊：它只要求登入，不收斂到某一階身分。

AUTO_FIELDS = (
    'rules',
    'methods',
    'source',
    'guards',
    'guard_args',
    'answer_source',
    'has_internal_check',
    'internal_identity_check',
)


def classify_answer_source(guards):
    """依守門 decorator 判斷「誰進得來」這個問題由誰回答。"""
    names = set(guards or ())
    if names & CODE_ANSWER_GUARDS:
        return 'code'
    if names & DB_ANSWER_GUARDS:
        return 'db'
    return 'none'

_ast_cache = {}


def load_dotenv(path=REPO_ROOT / '.env'):
    """載入 .env，避免 create_app 因 SECRET_KEY 缺失而失敗。"""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _repo_relative(path):
    return Path(path).resolve().relative_to(REPO_ROOT).as_posix()


def _is_venv_path(path):
    try:
        rel = Path(path).resolve().relative_to(REPO_ROOT)
    except ValueError:
        return False
    return 'venv' in rel.parts


def _function_node(fn):
    real = inspect.unwrap(fn)
    src_file = inspect.getsourcefile(real)
    _, lineno = inspect.getsourcelines(real)
    if src_file not in _ast_cache:
        _ast_cache[src_file] = ast.parse(open(src_file, encoding='utf-8').read())
    tree = _ast_cache[src_file]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = min([d.lineno for d in node.decorator_list] + [node.lineno])
            if start == lineno and node.name == real.__name__:
                return node, src_file
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == real.__name__:
            return node, src_file
    return None, src_file


def decorators_of(fn):
    """用 inspect.unwrap 找到被 decorator 包住的原始 view function，
    再用 AST 精確取它的 decorator 清單。回傳 (decorator 字串list, 相對路徑)。"""
    node, src_file = _function_node(fn)
    if node is None:
        return None, src_file
    return [ast.unparse(d) for d in node.decorator_list], src_file


def _decorator_name(node):
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _literal_string(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _literal_bool(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, bool) else None


def _keyword(call, name):
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _guard_args(name, node):
    if not isinstance(node, ast.Call):
        return None

    if name == 'page_keys_required':
        menu_node = node.args[0] if node.args else _keyword(node, 'menu_code')
        menu_code = _literal_string(menu_node) if menu_node is not None else None
        return {'menu_code': menu_code}

    if name == 'module_access_required':
        module_node = node.args[0] if node.args else _keyword(node, 'module_code')
        module = _literal_string(module_node) if module_node is not None else None
        check_node = node.args[1] if len(node.args) > 1 else _keyword(node, 'check_acl')
        check_acl = _literal_bool(check_node) if check_node is not None else True
        return {'module': module, 'check_acl': check_acl}

    if name in {'require_permission', 'permission_required', 'require_any_permission'}:
        codes = [_literal_string(arg) for arg in node.args]
        codes.extend(
            _literal_string(kw.value)
            for kw in node.keywords
            if kw.arg in {'code', 'permission_code'}
        )
        return {'permissions': [code for code in codes if code]}

    return None


def _guard_data(fn):
    node, src_file = _function_node(fn)
    if node is None:
        return [], {}, False, False, src_file

    guards = []
    guard_args = {}
    for decorator in node.decorator_list:
        name = _decorator_name(decorator)
        if name not in GUARD_NAMES:
            continue
        guards.append(name)
        args = _guard_args(name, decorator)
        if args is not None:
            guard_args[name] = args

    has_internal_check, internal_identity_check = _scan_internal_checks(node)
    return guards, guard_args, has_internal_check, internal_identity_check, src_file


class _InternalCheckVisitor(ast.NodeVisitor):
    def __init__(self):
        self.has_internal_check = False
        self.internal_identity_check = False

    def visit_FunctionDef(self, node):
        return

    def visit_AsyncFunctionDef(self, node):
        return

    def visit_Name(self, node):
        if node.id in {'is_org_admin', 'is_system_admin', 'user_type'}:
            self.internal_identity_check = True

    def visit_Attribute(self, node):
        if node.attr in {'is_org_admin', 'is_system_admin', 'user_type'}:
            self.internal_identity_check = True
        self.generic_visit(node)

    def visit_Call(self, node):
        func_name = _decorator_name(node.func)
        if func_name == 'abort' and node.args:
            code = node.args[0]
            if isinstance(code, ast.Constant) and code.value in {401, 403}:
                self.has_internal_check = True
        if func_name in {'jsonify', 'abort', 'Response'}:
            for arg in node.args:
                if _contains_status_code(arg, {403}):
                    self.has_internal_check = True
            for kw in node.keywords:
                if _contains_status_code(kw.value, {403}):
                    self.has_internal_check = True
        self.generic_visit(node)

    def visit_Return(self, node):
        if isinstance(node.value, ast.Tuple):
            for elt in node.value.elts[1:]:
                if _contains_status_code(elt, {403}):
                    self.has_internal_check = True
        self.generic_visit(node)


def _contains_status_code(node, values):
    return any(
        isinstance(child, ast.Constant) and child.value in values
        for child in ast.walk(node)
    )


def _scan_internal_checks(fn_node):
    visitor = _InternalCheckVisitor()
    for stmt in fn_node.body:
        visitor.visit(stmt)
    return visitor.has_internal_check, visitor.internal_identity_check


def _create_app(config_name='development'):
    load_dotenv()
    os.environ.setdefault('SKIP_MODULE_SYNC', '1')
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    old_cwd = Path.cwd()
    os.chdir(BACKEND_ROOT)
    try:
        from app import create_app
        return create_app(config_name)
    finally:
        os.chdir(old_cwd)


def collect_route_inventory(app=None, config_name='development'):
    if app is None:
        app = _create_app(config_name)

    routes = {}
    for rule in app.url_map.iter_rules():
        if rule.endpoint == 'static':
            continue
        view = app.view_functions[rule.endpoint]
        guards, guard_args, has_internal_check, internal_identity_check, src_file = _guard_data(view)
        if src_file and _is_venv_path(src_file):
            continue

        entry = routes.setdefault(
            rule.endpoint,
            {
                'rules': set(),
                'methods': set(),
                'source': _repo_relative(src_file),
                'guards': guards,
                'guard_args': guard_args,
                'answer_source': classify_answer_source(guards),
                'has_internal_check': has_internal_check,
                'internal_identity_check': internal_identity_check,
            },
        )
        entry['rules'].add(rule.rule)
        entry['methods'].update(sorted((rule.methods or set()) - {'HEAD', 'OPTIONS'}))

    normalized = {}
    for endpoint, entry in sorted(routes.items()):
        normalized[endpoint] = {
            'rules': sorted(entry['rules']),
            'methods': sorted(entry['methods']),
            'source': entry['source'],
            'guards': entry['guards'],
            'guard_args': entry['guard_args'],
            'answer_source': entry['answer_source'],
            'has_internal_check': entry['has_internal_check'],
            'internal_identity_check': entry['internal_identity_check'],
        }
    return normalized


def load_table(path=TABLE_PATH):
    if not path.exists():
        return {'version': 1, 'routes': {}}
    with path.open(encoding='utf-8') as fh:
        return yaml.safe_load(fh) or {'version': 1, 'routes': {}}


def build_table(current, existing=None):
    existing_routes = (existing or {}).get('routes', {})
    routes = {}
    for endpoint, scanned in sorted(current.items()):
        old = existing_routes.get(endpoint, {})
        entry = {field: scanned[field] for field in AUTO_FIELDS}
        # 人工欄位只在新條目建立預設值；既有條目絕不覆寫。
        entry['max_audience'] = old.get('max_audience')
        entry['review'] = old.get('review', 'unreviewed')
        entry['note'] = old.get('note', '')
        routes[endpoint] = entry
    return {'version': 1, 'routes': routes}


def dump_table(data, path=TABLE_PATH):
    header = (
        "version: 1\n"
        "# 這張表的用途與維護方式見 dev-notes/ROUTE_GUARD_TABLE_SPEC.md\n"
        "# 自動欄位（guards / guard_args / has_internal_check / internal_identity_check / rules / methods）\n"
        "# 由 scripts/route_guard_inventory.py --update 產生，不要手改。\n"
        "# 人工欄位（max_audience / review / note）只能由人填，工具不得覆寫。\n"
    )
    body = yaml.safe_dump(
        {'routes': data['routes']},
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=True,
    )
    path.write_text(header + body, encoding='utf-8')


def diff_table(current, table):
    declared = table.get('routes', {})
    current_endpoints = set(current)
    declared_endpoints = set(declared)
    missing = sorted(current_endpoints - declared_endpoints)
    stale = sorted(declared_endpoints - current_endpoints)
    changed = []
    for endpoint in sorted(current_endpoints & declared_endpoints):
        expected = declared[endpoint]
        actual = current[endpoint]
        if (expected.get('guards', []) != actual.get('guards', [])
                or expected.get('guard_args', {}) != actual.get('guard_args', {})
                or expected.get('answer_source') != actual.get('answer_source')):
            changed.append((
                endpoint,
                expected.get('guards', []), expected.get('guard_args', {}), expected.get('answer_source'),
                actual.get('guards', []), actual.get('guard_args', {}), actual.get('answer_source'),
            ))
    return missing, stale, changed


def print_diff(missing, stale, changed):
    if missing:
        print('缺少宣告的 endpoint：')
        for endpoint in missing:
            print(f'  - {endpoint}')
    if stale:
        print('表中已不存在的 endpoint：')
        for endpoint in stale:
            print(f'  - {endpoint}')
    if changed:
        print('守門與程式碼不一致的 endpoint：')
        for (endpoint, old_guards, old_args, old_src,
             new_guards, new_args, new_src) in changed:
            print(f'  - {endpoint}')
            print(f'    表裡 guards={old_guards} guard_args={old_args} answer_source={old_src}')
            print(f'    程式碼 guards={new_guards} guard_args={new_args} answer_source={new_src}')


def print_stats(current, table):
    declared = table.get('routes', {})
    combos = Counter(tuple(entry['guards']) for entry in current.values())
    print(f"目前 url_map endpoint 數：{len(current)}")
    print(f"宣告表 endpoint 數：{len(declared)}")
    print(f"review: unreviewed 條數：{sum(1 for e in declared.values() if e.get('review') == 'unreviewed')}")
    print()
    print('answer_source 分布（「誰進得來」由誰決定）：')
    src_label = {
        'code': 'code  程式碼直接鎖死，讀 decorator 即可確認',
        'db': 'db    要查資料庫（選單/合約/ACL/permission）才有答案',
        'none': 'none  沒有收斂身分的守門，任何登入帳號都到得了',
    }
    src_counter = Counter(entry['answer_source'] for entry in current.values())
    total = max(len(current), 1)
    for key in ('code', 'db', 'none'):
        count = src_counter.get(key, 0)
        print(f'  {count:4d}  {count * 100 // total:3d}%  {src_label[key]}')
    print()
    print('守門組合分布：')
    for guards, count in sorted(combos.items(), key=lambda item: (-item[1], item[0])):
        label = ', '.join(guards) if guards else '(無白名單 decorator)'
        print(f'  {count:4d}  {label}')


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description='產生、檢查與統計 Flask 路由守門宣告表。',
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--check', action='store_true', help='比對程式碼現況與宣告表，不寫檔；有差異時退出碼為 1。')
    group.add_argument('--update', action='store_true', help='把程式碼現況寫回宣告表，並保留 max_audience / review / note 人工欄位。')
    group.add_argument('--stats', action='store_true', help='印出守門組合分布與未複審條數，退出碼恆為 0。')
    return parser, parser.parse_args(argv)


def main(argv=None):
    parser, args = parse_args(argv)
    if not (args.check or args.update or args.stats):
        parser.print_help()
        return 0

    current = collect_route_inventory()
    table = load_table()

    if args.update:
        dump_table(build_table(current, table))
        print(f'已更新 {TABLE_PATH.relative_to(REPO_ROOT)}，endpoint 數：{len(current)}')
        return 0

    if args.check:
        missing, stale, changed = diff_table(current, table)
        if missing or stale or changed:
            print_diff(missing, stale, changed)
            return 1
        print('路由守門宣告表與程式碼一致。')
        return 0

    if args.stats:
        print_stats(current, table)
        return 0

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
