#!/usr/bin/env python3
"""
BeakPlatform 路由安全盤點工具

掃描所有 Flask 路由，比對裝飾器保護狀態、MenuItem 對應、MenuRoleRequirement 角色需求，
產出安全盤點報告。

用法：
    python route_audit.py              顯示使用說明
    python route_audit.py --audit      完整盤點
    python route_audit.py --danger-only  只列危險 + 警告
    python route_audit.py --module form_workflow  只檢查指定模組
"""

import argparse
import os
import re
import sys

# 確保 backend 目錄在 sys.path
BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend')
sys.path.insert(0, os.path.abspath(BACKEND_DIR))


# === 常數 ===

# 白名單路由前綴 — 不列入盤點
WHITELIST_PREFIXES = (
    '/static/',
    '/auth/',
    '/public/',
    '/dev/',
    '/health',
)

# 裝飾器屬性名稱 → 顯示標籤
DECORATOR_ATTRS = {
    '_public_route': '@public_route',
    '_login_required': '@login_required',
    '_admin_required': '@admin_required',
    '_system_admin_required': '@system_admin_required',
    '_module_access_required': '@module_access_required',
    '_permission_required': '@permission_required',
}

# 危險等級
LEVEL_DANGER = 0
LEVEL_WARNING = 1
LEVEL_NORMAL = 2

LEVEL_LABELS = {
    LEVEL_DANGER: '[危險]',
    LEVEL_WARNING: '[警告]',
    LEVEL_NORMAL: '[正常]',
}


def create_flask_app():
    """建立 Flask app instance"""
    from app import create_app
    app = create_app()
    return app


def get_decorator_info(view_func):
    """取得 view function 的裝飾器保護狀態"""
    decorators = []
    for attr, label in DECORATOR_ATTRS.items():
        value = getattr(view_func, attr, False)
        if value:
            if attr == '_module_access_required':
                decorators.append(f'{label}({value})')
            elif attr == '_permission_required':
                res_type, action = value
                decorators.append(f'{label}({res_type}:{action})')
            else:
                decorators.append(label)
    return decorators


def is_whitelisted(url_rule):
    """判斷路由是否在白名單中"""
    rule_str = url_rule.rule
    for prefix in WHITELIST_PREFIXES:
        if rule_str.startswith(prefix) or rule_str == prefix.rstrip('/'):
            return True
    return False


def normalize_url_pattern(url_rule):
    """將 Flask URL rule 轉為可比對的正規式

    例如 /menu/<secure_code>/edit → /menu/.+/edit
    """
    pattern = re.sub(r'<[^>]+>', '[^/]+', url_rule)
    return f'^{pattern}$'


def build_menu_url_map(app):
    """建立 MenuItem link_target → MenuItem 映射

    只取 link_type='route' 且 link_target 以 / 開頭的選單項目。
    """
    from app.models import MenuItem

    with app.app_context():
        items = MenuItem.query.filter(
            MenuItem.link_type == 'route',
            MenuItem.link_target.isnot(None),
            MenuItem.is_active.is_(True),
        ).all()

        url_map = {}
        for item in items:
            target = item.link_target
            if target and target.startswith('/'):
                url_map[target] = {
                    'secure_code': item.secure_code,
                    'title': item.title,
                    'code': item.code,
                    'module_secure_code': item.module_secure_code,
                    'is_shared': item.is_shared,
                }
        return url_map


def build_role_requirement_map(app):
    """建立 menu_secure_code → [角色列表] 映射"""
    from app.models import MenuRoleRequirement

    with app.app_context():
        reqs = MenuRoleRequirement.query.all()
        role_map = {}
        for req in reqs:
            if req.menu_secure_code not in role_map:
                role_map[req.menu_secure_code] = []
            role_map[req.menu_secure_code].append(req.role_secure_code)
        return role_map


def match_menu_item(url_rule, menu_url_map):
    """比對路由是否有對應的 MenuItem

    支援前綴匹配 — 例如 MenuItem link_target=/menu/ 可匹配 /menu/<code>
    """
    rule_str = url_rule.rule

    # 精確匹配
    if rule_str in menu_url_map:
        return menu_url_map[rule_str]

    # 前綴匹配：將 URL rule 的參數部分去掉，逐級向上匹配
    # /menu/<code>/edit → 嘗試 /menu/<code>/edit, /menu/<code>/, /menu/
    stripped = re.sub(r'<[^>]+>', '', rule_str)
    parts = stripped.rstrip('/').split('/')

    for i in range(len(parts), 0, -1):
        prefix = '/'.join(parts[:i])
        if not prefix:
            continue
        # 嘗試帶尾斜線和不帶尾斜線
        for candidate in [prefix + '/', prefix]:
            if candidate in menu_url_map:
                return menu_url_map[candidate]

    # 嘗試以 menu link_target 為前綴匹配 rule
    for link_target, menu_info in menu_url_map.items():
        target_clean = link_target.rstrip('/')
        rule_clean = rule_str.split('<')[0].rstrip('/')
        if rule_clean == target_clean:
            return menu_info

    return None


def classify_route(decorators, menu_match, role_map, methods):
    """分類路由的危險等級與原因"""
    is_get = 'GET' in methods
    has_public = '@public_route' in decorators
    has_login = '@login_required' in decorators
    has_admin = '@admin_required' in decorators
    has_sys_admin = '@system_admin_required' in decorators
    has_module = any(d.startswith('@module_access_required') for d in decorators)
    has_permission = any(d.startswith('@permission_required') for d in decorators)

    has_any_decorator = bool(decorators)
    has_strong_decorator = has_admin or has_sys_admin or has_module or has_permission

    # 公開路由 — 正常
    if has_public:
        return LEVEL_NORMAL, '公開路由 (有 @public_route)'

    # 無任何裝飾器的 GET 路由 — 危險
    if not has_any_decorator and is_get:
        return LEVEL_DANGER, '無任何裝飾器保護的 GET 路由'

    # 無任何裝飾器的非 GET 路由 — 也是危險
    if not has_any_decorator:
        return LEVEL_DANGER, '無任何裝飾器保護'

    # 有強裝飾器 — 正常
    if has_strong_decorator:
        if menu_match:
            menu_sc = menu_match['secure_code']
            has_roles = menu_sc in role_map and len(role_map[menu_sc]) > 0
            if has_roles:
                return LEVEL_NORMAL, '裝飾器 + MenuItem + 角色需求完整'
            else:
                return LEVEL_NORMAL, '有強裝飾器保護'
        return LEVEL_NORMAL, '有強裝飾器保護 (無需 MenuItem)'

    # 只有 @login_required
    if has_login and not has_strong_decorator:
        if not menu_match and is_get:
            return LEVEL_WARNING, '僅 @login_required，無 MenuItem 對應 (可繞過選單直接存取)'

        if menu_match:
            menu_sc = menu_match['secure_code']
            has_roles = menu_sc in role_map and len(role_map[menu_sc]) > 0
            if not has_roles:
                return LEVEL_WARNING, '有 MenuItem 但無 MenuRoleRequirement (缺少角色控制)'
            return LEVEL_NORMAL, '@login_required + MenuItem + 角色需求完整'

        # 非 GET + 只有 login_required
        return LEVEL_NORMAL, '@login_required (非 GET 路由)'

    return LEVEL_NORMAL, '有裝飾器保護'


def audit_routes(app, module_filter=None):
    """執行路由盤點，回傳分類結果列表"""
    menu_url_map = build_menu_url_map(app)
    role_map = build_role_requirement_map(app)

    results = []

    with app.app_context():
        for rule in app.url_map.iter_rules():
            # 跳過白名單
            if is_whitelisted(rule):
                continue

            # 跳過 HEAD/OPTIONS（自動產生的）
            methods = rule.methods - {'HEAD', 'OPTIONS'}
            if not methods:
                continue

            endpoint = rule.endpoint
            view_func = app.view_functions.get(endpoint)
            if view_func is None:
                continue

            # 取得裝飾器
            decorators = get_decorator_info(view_func)

            # 模組過濾：裝飾器模組代碼 / endpoint 名稱 / URL 路徑 任一匹配即納入
            module_code = getattr(view_func, '_module_access_required', None)
            if module_filter:
                # 將模組代碼轉為 URL 格式 (form_workflow → form-workflow)
                module_url_slug = module_filter.replace('_', '-')
                matched = False
                if module_code == module_filter:
                    matched = True
                elif module_filter in endpoint:
                    matched = True
                elif module_url_slug in rule.rule:
                    matched = True
                else:
                    # 檢查 MenuItem 的 module_secure_code
                    pre_match = match_menu_item(rule, menu_url_map)
                    if pre_match and pre_match.get('module_secure_code') == module_filter:
                        matched = True
                if not matched:
                    continue

            # 比對 MenuItem
            menu_match = match_menu_item(rule, menu_url_map)

            # 分類
            level, reason = classify_route(decorators, menu_match, role_map, methods)

            results.append({
                'level': level,
                'reason': reason,
                'url': rule.rule,
                'methods': sorted(methods),
                'endpoint': endpoint,
                'decorators': decorators,
                'menu_match': menu_match,
                'module_code': module_code if module_code else '-',
            })

    # 按危險等級排序，同等級按 URL 排序
    results.sort(key=lambda r: (r['level'], r['url']))
    return results


def format_table(results, show_normal=True):
    """格式化輸出表格"""
    if not show_normal:
        results = [r for r in results if r['level'] != LEVEL_NORMAL]

    if not results:
        print('\n  (無符合條件的路由)')
        return

    # 統計
    counts = {LEVEL_DANGER: 0, LEVEL_WARNING: 0, LEVEL_NORMAL: 0}
    for r in results:
        counts[r['level']] += 1

    # 表頭
    print()
    print(f'  盤點結果：危險 {counts[LEVEL_DANGER]} / 警告 {counts[LEVEL_WARNING]} / 正常 {counts[LEVEL_NORMAL]}')
    print()

    # 欄位寬度計算
    col_level = 6
    col_url = max(len(r['url']) for r in results)
    col_url = max(col_url, 6)
    col_methods = max(len(','.join(r['methods'])) for r in results)
    col_methods = max(col_methods, 6)
    col_deco = max(len(', '.join(r['decorators'])) if r['decorators'] else 1 for r in results)
    col_deco = max(col_deco, 8)
    col_menu = 20

    header = (
        f'  {"等級":<{col_level}}'
        f'  {"URL":<{col_url}}'
        f'  {"方法":<{col_methods}}'
        f'  {"裝飾器":<{col_deco}}'
        f'  {"MenuItem":<{col_menu}}'
        f'  原因'
    )
    separator = '  ' + '-' * (len(header) + 10)

    print(header)
    print(separator)

    current_level = None
    for r in results:
        level_label = LEVEL_LABELS[r['level']]
        methods_str = ','.join(r['methods'])
        deco_str = ', '.join(r['decorators']) if r['decorators'] else '-'
        menu_str = r['menu_match']['code'] if r['menu_match'] else '-'

        if current_level is not None and r['level'] != current_level:
            print()

        current_level = r['level']

        print(
            f'  {level_label:<{col_level}}'
            f'  {r["url"]:<{col_url}}'
            f'  {methods_str:<{col_methods}}'
            f'  {deco_str:<{col_deco}}'
            f'  {menu_str:<{col_menu}}'
            f'  {r["reason"]}'
        )

    print()


def print_detail_section(results, level, title):
    """印出特定等級的詳細資訊"""
    filtered = [r for r in results if r['level'] == level]
    if not filtered:
        return

    print(f'\n{"=" * 60}')
    print(f'  {title} ({len(filtered)} 筆)')
    print(f'{"=" * 60}')

    for r in filtered:
        methods_str = ','.join(r['methods'])
        deco_str = ', '.join(r['decorators']) if r['decorators'] else '(無)'
        menu_info = ''
        if r['menu_match']:
            m = r['menu_match']
            menu_info = f'{m["code"]} ({m["title"]})'
        else:
            menu_info = '(無對應)'

        print(f'\n  {r["url"]}  [{methods_str}]')
        print(f'    endpoint:   {r["endpoint"]}')
        print(f'    裝飾器:     {deco_str}')
        print(f'    MenuItem:   {menu_info}')
        print(f'    模組:       {r["module_code"]}')
        print(f'    原因:       {r["reason"]}')


def run_audit(danger_only=False, module_filter=None):
    """執行盤點主流程"""
    print('\n  BeakPlatform 路由安全盤點')
    print('  ' + '=' * 40)

    if module_filter:
        print(f'  篩選模組: {module_filter}')

    print('  載入 Flask app ...')
    app = create_flask_app()

    print('  掃描路由 ...')
    results = audit_routes(app, module_filter=module_filter)

    total = len(results)
    danger_count = sum(1 for r in results if r['level'] == LEVEL_DANGER)
    warning_count = sum(1 for r in results if r['level'] == LEVEL_WARNING)
    normal_count = sum(1 for r in results if r['level'] == LEVEL_NORMAL)

    print(f'  掃描完成：共 {total} 條路由 (排除白名單)')

    # 危險與警告詳細列表
    if danger_count > 0:
        print_detail_section(results, LEVEL_DANGER, '危險 - 需立即處理')

    if warning_count > 0:
        print_detail_section(results, LEVEL_WARNING, '警告 - 建議補強')

    # 正常列表 (非 danger-only 模式)
    if not danger_only and normal_count > 0:
        print_detail_section(results, LEVEL_NORMAL, '正常 - 保護完整')

    # 總覽表格
    print(f'\n{"=" * 60}')
    print('  總覽表格')
    print(f'{"=" * 60}')
    format_table(results, show_normal=not danger_only)

    # 結尾摘要
    print(f'  白名單前綴 (不列入盤點): {", ".join(WHITELIST_PREFIXES)}')
    print()

    return danger_count + warning_count


def main():
    parser = argparse.ArgumentParser(
        description='BeakPlatform 路由安全盤點工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python route_audit.py --audit              完整盤點所有路由
  python route_audit.py --danger-only        只列出危險與警告
  python route_audit.py --module form_workflow  只檢查指定模組的路由
  python route_audit.py --audit --module nocode_builder

白名單 (自動排除):
  /static/  /auth/  /public/  /dev/  /health

檢查項目:
  裝飾器: @public_route, @login_required, @admin_required,
          @system_admin_required, @module_access_required, @permission_required
  MenuItem: link_type='route' 且 link_target 以 / 開頭的選單項目
  MenuRoleRequirement: MenuItem 對應的角色需求記錄
        """,
    )
    parser.add_argument(
        '--audit', action='store_true',
        help='執行完整盤點，列出所有路由的安全狀態',
    )
    parser.add_argument(
        '--danger-only', action='store_true',
        help='只列出危險與警告等級的路由',
    )
    parser.add_argument(
        '--module', type=str, metavar='CODE',
        help='只檢查指定模組代碼的路由 (如 form_workflow)',
    )

    # 無參數時顯示說明
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    if not args.audit and not args.danger_only:
        parser.print_help()
        sys.exit(0)

    # 切換到 backend 目錄 (Flask app 需要)
    os.chdir(os.path.abspath(BACKEND_DIR))

    issue_count = run_audit(
        danger_only=args.danger_only,
        module_filter=args.module,
    )

    sys.exit(1 if issue_count > 0 else 0)


if __name__ == '__main__':
    main()
