#!/usr/bin/env python3
"""
BeakPlatform 出廠預設值匯出工具（原廠專用）

從 menu_defaults 和 rbac_defaults 資料表產出安裝用 SQL
（scripts/sql/seed_menu_defaults.sql / seed_rbac_defaults.sql），
供 install.sh / init_database.sh 全新安裝時灌入預設值。

不會覆蓋用戶設定：SQL 使用 IF NOT EXISTS 條件，表有資料時不插入。

用法:
    python3 scripts/export_factory_defaults.py              # 匯出全部
    python3 scripts/export_factory_defaults.py --menu       # 只匯出選單
    python3 scripts/export_factory_defaults.py --rbac       # 只匯出 RBAC
    python3 scripts/export_factory_defaults.py --dry-run    # 預覽不寫檔
"""

import sys
import os
import json
import argparse
from datetime import datetime, timezone

# 加入 backend 路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL_DIR = os.path.join(PROJECT_ROOT, 'scripts', 'sql')

MENU_SQL_FILE = 'seed_menu_defaults.sql'
RBAC_SQL_FILE = 'seed_rbac_defaults.sql'


def export_menu_defaults(app, dry_run=False):
    """從 menu_defaults 表匯出安裝用 SQL"""
    from app.models.menu_default import MenuDefault

    with app.app_context():
        rows = MenuDefault.query.order_by(
            MenuDefault.depth, MenuDefault.display_order
        ).all()

        if not rows:
            print("[menu] menu_defaults 表為空，跳過")
            print("       請先在 /menu/ 頁面按「設定目前組態成出廠值」")
            return False

        now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        lines = [
            '-- BeakPlatform Menu Factory Defaults (install-only)',
            f'-- Generated: {now_str}',
            '-- ',
            '-- 安全機制: 只在 menu_defaults 表為空時才插入',
            '-- (upgrade 不會覆蓋用戶已儲存的預設值)',
            '',
            '-- 條件: 僅當 menu_defaults 表為空時執行',
            'DO $$',
            'BEGIN',
            '    IF NOT EXISTS (SELECT 1 FROM menu_defaults LIMIT 1) THEN',
            '',
        ]

        for row in rows:
            title_i18n = json.dumps(row.title_i18n or {}, ensure_ascii=False)
            user_types = json.dumps(row.user_types or [], ensure_ascii=False)
            role_codes = json.dumps(row.role_codes or [], ensure_ascii=False)

            title_esc = (row.title or '').replace("'", "''")
            icon_val = f"'{row.icon}'" if row.icon else 'NULL'
            link_target_val = (
                f"'{(row.link_target or '').replace(chr(39), chr(39)*2)}'"
                if row.link_target else 'NULL'
            )
            parent_code_val = (
                f"'{row.parent_code}'" if row.parent_code else 'NULL'
            )
            req_perm_val = (
                f"'{row.required_permission}'"
                if row.required_permission else 'NULL'
            )

            sql = (
                f"        INSERT INTO menu_defaults "
                f"(code, title, title_i18n, icon, link_type, link_target, "
                f"display_order, depth, parent_code, is_expanded, is_shared, "
                f"required_permission, user_types, role_codes, "
                f"saved_by, saved_at) VALUES ("
                f"'{row.code}', '{title_esc}', "
                f"'{title_i18n}'::jsonb, {icon_val}, "
                f"'{row.link_type}', {link_target_val}, "
                f"{row.display_order}, {row.depth}, {parent_code_val}, "
                f"{'true' if row.is_expanded else 'false'}, "
                f"{'true' if row.is_shared else 'false'}, "
                f"{req_perm_val}, "
                f"'{user_types}'::jsonb, '{role_codes}'::jsonb, "
                f"'factory_install', NOW());"
            )
            lines.append(sql)

        lines.extend([
            '',
            '    END IF;',
            'END $$;',
        ])

        sql_content = '\n'.join(lines)

        if dry_run:
            print(f"[menu] 預覽: {len(rows)} 筆 -> {MENU_SQL_FILE}")
            print(f"       前 3 筆: {', '.join(r.code for r in rows[:3])}...")
        else:
            path = os.path.join(SQL_DIR, MENU_SQL_FILE)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(sql_content)
            print(f"[menu] {len(rows)} 筆 -> {MENU_SQL_FILE}")

        return True


def export_rbac_defaults(app, dry_run=False):
    """從 rbac_defaults 表匯出安裝用 SQL"""
    from app.models.rbac_default import RbacDefault

    with app.app_context():
        rows = RbacDefault.query.order_by(
            RbacDefault.role_code, RbacDefault.permission_code
        ).all()

        if not rows:
            print("[rbac] rbac_defaults 表為空，跳過")
            print("       請先在 /access/ 頁面按「設定目前組態成出廠值」")
            return False

        # 統計
        roles = {}
        for row in rows:
            roles.setdefault(row.role_code, []).append(row.permission_code)

        now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        lines = [
            '-- BeakPlatform RBAC Factory Defaults (install-only)',
            f'-- Generated: {now_str}',
            '-- ',
            '-- 安全機制: 只在 rbac_defaults 表為空時才插入',
            '-- (upgrade 不會覆蓋用戶已儲存的預設值)',
            '',
            '-- 條件: 僅當 rbac_defaults 表為空時執行',
            'DO $$',
            'BEGIN',
            '    IF NOT EXISTS (SELECT 1 FROM rbac_defaults LIMIT 1) THEN',
            '',
        ]

        for role_code in sorted(roles.keys()):
            perm_codes = sorted(roles[role_code])
            lines.append(
                f'        -- Role: {role_code} '
                f'({len(perm_codes)} permissions)'
            )
            for perm_code in perm_codes:
                sql = (
                    f"        INSERT INTO rbac_defaults "
                    f"(role_code, permission_code, saved_by, saved_at) "
                    f"VALUES ('{role_code}', '{perm_code}', "
                    f"'factory_install', NOW());"
                )
                lines.append(sql)
            lines.append('')

        lines.extend([
            '    END IF;',
            'END $$;',
        ])

        sql_content = '\n'.join(lines)

        if dry_run:
            print(f"[rbac] 預覽: {len(roles)} 角色, {len(rows)} 筆 -> {RBAC_SQL_FILE}")
            for rc, pcs in sorted(roles.items()):
                print(f"       {rc}: {len(pcs)} permissions")
        else:
            path = os.path.join(SQL_DIR, RBAC_SQL_FILE)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(sql_content)
            print(f"[rbac] {len(roles)} 角色, {len(rows)} 筆 -> {RBAC_SQL_FILE}")

        return True


def main():
    parser = argparse.ArgumentParser(
        description='BeakPlatform 出廠預設值匯出工具（原廠專用）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
輸出檔案:
  scripts/migrations/058_seed_menu_defaults.sql   選單預設值
  scripts/migrations/060_seed_rbac_defaults.sql   RBAC 預設值

前置條件:
  1. 在 /menu/ 按「設定目前組態成出廠值」 -> menu_defaults 表
  2. 在 /access/ 按「設定目前組態成出廠值」 -> rbac_defaults 表
  3. 執行本工具產出 SQL

install.sh 安全機制:
  - 全新安裝: SQL 灌入預設值（表為空時）
  - --update: 不重跑已執行的 migration + SQL 有 IF NOT EXISTS 保護
""",
    )
    parser.add_argument('--all', action='store_true',
                        help='匯出全部（選單 + RBAC）')
    parser.add_argument('--menu', action='store_true',
                        help='只匯出選單預設值')
    parser.add_argument('--rbac', action='store_true',
                        help='只匯出 RBAC 預設值')
    parser.add_argument('--dry-run', action='store_true',
                        help='預覽不寫檔')
    args = parser.parse_args()

    # 無參數時顯示使用說明
    if not args.all and not args.menu and not args.rbac:
        parser.print_help()
        return 0

    do_menu = args.all or args.menu
    do_rbac = args.all or args.rbac

    # 跳過模組同步（只需要 DB 連線）
    os.environ['SKIP_MODULE_SYNC'] = '1'

    from app import create_app
    app = create_app()

    print("=" * 50)
    print("BeakPlatform 出廠預設值匯出")
    print("=" * 50)
    if args.dry_run:
        print("(dry-run 模式，不寫入檔案)")
    print()

    results = []

    if do_menu:
        results.append(('menu', export_menu_defaults(app, args.dry_run)))

    if do_rbac:
        results.append(('rbac', export_rbac_defaults(app, args.dry_run)))

    print()
    success = all(r for _, r in results)
    if success:
        if args.dry_run:
            print("預覽完成。移除 --dry-run 執行實際匯出。")
        else:
            print("匯出完成。請 commit 產出的 SQL 檔案。")
    else:
        failed = [name for name, r in results if not r]
        print(f"部分匯出失敗: {', '.join(failed)}")
        print("請先透過 UI 儲存出廠預設值。")

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
