#!/usr/bin/env python3
"""
008: 遷移 CRUD 權限和資料篩選從節點層級到 widget 層級

Phase 3: 將 DcSiteMapNode.crud_overrides/data_filters
複製到 layout_json 中每個 widget 的 rolePermissions/roleFilters。

用法:
    cd /opt/BeakPlatform/backend
    python3 ../modules/nocode_builder/migrations/008_widget_role_permissions.py --dry-run
    python3 ../modules/nocode_builder/migrations/008_widget_role_permissions.py --run
"""
import sys
import os
import json
import argparse
import copy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'backend'))

from app import create_app, db
from sqlalchemy import text


def find_widget_configs(layout):
    """
    從 layout_json 中提取所有 widget config 參照。
    修改回傳的物件會直接反映到 layout。
    """
    configs = []
    for w in layout.get('widgets', []):
        wc = w.get('widget')
        if wc and wc.get('viewCode'):
            configs.append(wc)
    return configs


def run(dry_run=False):
    app = create_app()
    with app.app_context():
        # 找到有 crud_overrides 或 data_filters 的節點
        rows = db.session.execute(text("""
            SELECT secure_code, page_layout_secure_code,
                   crud_overrides, data_filters
            FROM dc_site_map_nodes
            WHERE is_deleted = FALSE
              AND (
                  (crud_overrides IS NOT NULL AND crud_overrides != '{}'::jsonb)
                  OR
                  (data_filters IS NOT NULL AND data_filters != '{}'::jsonb)
              )
        """)).fetchall()

        mode = '[DRY-RUN]' if dry_run else '[MIGRATE]'
        print(f'{mode} 找到 {len(rows)} 個有 crud_overrides/data_filters 的節點')

        if not rows:
            print(f'{mode} 無需遷移 (所有節點的 crud_overrides/data_filters 皆為空)')
            return

        total_migrated = 0
        for row in rows:
            node_sc = row[0]
            page_layout_sc = row[1]
            crud_overrides = row[2] or {}
            data_filters = row[3] or {}

            if not page_layout_sc:
                print(f'  SKIP node={node_sc}: 無 page_layout_secure_code')
                continue

            # 取得頁面佈局
            layout_row = db.session.execute(text("""
                SELECT secure_code, layout_json
                FROM dc_page_layouts
                WHERE secure_code = :sc AND is_deleted = FALSE
            """), {'sc': page_layout_sc}).fetchone()

            if not layout_row:
                print(f'  SKIP node={node_sc}: page_layout {page_layout_sc} not found')
                continue

            layout = copy.deepcopy(layout_row[1] or {})
            widget_configs = find_widget_configs(layout)

            if not widget_configs:
                print(f'  SKIP node={node_sc}: layout 無 widget')
                continue

            migrated = 0
            for wc in widget_configs:
                changed = False

                if crud_overrides and 'rolePermissions' not in wc:
                    wc['rolePermissions'] = crud_overrides
                    changed = True

                if data_filters and 'roleFilters' not in wc:
                    wc['roleFilters'] = data_filters
                    changed = True

                if changed:
                    migrated += 1

            if migrated > 0:
                co_roles = list(crud_overrides.keys()) if crud_overrides else '-'
                df_roles = list(data_filters.keys()) if data_filters else '-'
                print(f'  OK   node={node_sc}: {migrated} widget(s) '
                      f'[crud={co_roles}, filters={df_roles}]')

                if not dry_run:
                    db.session.execute(text("""
                        UPDATE dc_page_layouts
                        SET layout_json = :layout
                        WHERE secure_code = :sc
                    """), {'layout': json.dumps(layout), 'sc': page_layout_sc})

                total_migrated += migrated
            else:
                print(f'  SKIP node={node_sc}: widgets 已有 rolePermissions')

        if not dry_run and total_migrated > 0:
            db.session.commit()
            print(f'\n{mode} 完成: 遷移了 {total_migrated} 個 widget')
        elif dry_run:
            print(f'\n{mode} 預覽完成: 將遷移 {total_migrated} 個 widget')
        else:
            print(f'\n{mode} 無需遷移')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='遷移 CRUD 權限從節點層級到 widget 層級'
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--dry-run', action='store_true', help='預覽變更，不修改 DB')
    group.add_argument('--run', action='store_true', help='執行遷移')
    args = parser.parse_args()

    run(dry_run=args.dry_run)
